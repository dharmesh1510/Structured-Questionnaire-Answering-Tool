from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import List

import streamlit as st
from sqlalchemy.orm import joinedload

from app import auth, models
from app.db import Base, SessionLocal, engine
from app.services.ai import NOT_FOUND, generate_grounded_answer
from app.services.exporter import to_csv_rows, to_xlsx_bytes
from app.services.parsing import chunk_text, parse_questionnaire, parse_reference_doc
from app.services.retrieval import retrieve_top_chunks


Base.metadata.create_all(bind=engine)


def db_session():
    return SessionLocal()


def current_user(db):
    user_id = st.session_state.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def signup_view(db):
    st.subheader("Create account")
    with st.form("signup_form", clear_on_submit=False):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign up")
    if submitted:
        email_clean = email.lower().strip()
        if not email_clean or len(password) < 8:
            st.error("Enter a valid email and password (min 8 chars).")
            return
        exists = db.query(models.User).filter(models.User.email == email_clean).first()
        if exists:
            st.error("Email already exists.")
            return
        user = models.User(email=email_clean, password_hash=auth.hash_password(password))
        db.add(user)
        db.commit()
        st.session_state["user_id"] = user.id
        st.rerun()


def login_view(db):
    st.subheader("Log in")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        user = db.query(models.User).filter(models.User.email == email.lower().strip()).first()
        if not user or not auth.verify_password(password, user.password_hash):
            st.error("Invalid credentials.")
            return
        st.session_state["user_id"] = user.id
        st.rerun()


def save_reference(db, user: models.User, uploaded):
    if uploaded is None:
        return
    try:
        content = parse_reference_doc(uploaded.name, uploaded.getvalue())
    except ValueError as exc:
        st.error(str(exc))
        return
    if not content.strip():
        st.error("Reference file is empty.")
        return
    doc = models.ReferenceDocument(user_id=user.id, filename=uploaded.name, content=content)
    db.add(doc)
    db.flush()
    for idx, chunk in enumerate(chunk_text(content)):
        db.add(models.ReferenceChunk(document_id=doc.id, chunk_index=idx, text=chunk))
    db.commit()
    st.success(f"Uploaded reference: {uploaded.name}")


def save_questionnaire(db, user: models.User, title: str, uploaded):
    if uploaded is None:
        return
    try:
        questions = parse_questionnaire(uploaded.name, uploaded.getvalue())
    except ValueError as exc:
        st.error(str(exc))
        return
    if not questions:
        st.error("No questions found in uploaded questionnaire.")
        return

    run = models.QuestionnaireRun(
        user_id=user.id,
        title=title.strip() or "Questionnaire",
        original_filename=uploaded.name,
        original_format=Path(uploaded.name).suffix.lower(),
    )
    db.add(run)
    db.flush()
    for idx, text in enumerate(questions, start=1):
        db.add(models.Question(run_id=run.id, position=idx, text=text))
    db.commit()
    st.success(f"Created run: {run.title}")


def generate_for_question(db, user_id: int, question: models.Question):
    hits = retrieve_top_chunks(db, user_id=user_id, question=question.text, top_k=3)
    max_score = max((hit.score for hit in hits), default=0.0)
    if max_score < 0.35:
        hits = []
    generated = generate_grounded_answer(question.text, hits)

    if generated.strip() == NOT_FOUND:
        citations: List[str] = []
        evidence = []
        confidence = 0.0
        status = "not_found"
    else:
        citations = [hit.citation for hit in hits] or []
        evidence = [hit.chunk_text[:220] for hit in hits]
        confidence = round(min(0.99, max((hit.score for hit in hits), default=0.0)), 2)
        status = "answered"

    if question.answer:
        question.answer.generated_answer = generated
        question.answer.citations = citations
        question.answer.evidence_snippets = evidence
        question.answer.confidence = confidence
        question.answer.status = status
    else:
        db.add(
            models.Answer(
                question_id=question.id,
                generated_answer=generated,
                citations=citations,
                evidence_snippets=evidence,
                confidence=confidence,
                status=status,
            )
        )


def run_summary(questions: List[models.Question]):
    total = len(questions)
    answered = 0
    not_found = 0
    for q in questions:
        if not q.answer:
            continue
        if q.answer.status == "not_found":
            not_found += 1
        if q.answer.status == "answered" and q.answer.citations:
            answered += 1
    return total, answered, not_found


def main():
    st.set_page_config(page_title="ALMABASE Questionnaire Tool", page_icon=":clipboard:", layout="wide")
    st.title("ALMABASE Questionnaire Tool")
    st.caption("Structured Questionnaire Answering with Grounded Citations")

    db = db_session()
    try:
        user = current_user(db)
        if not user:
            tab_login, tab_signup = st.tabs(["Log in", "Sign up"])
            with tab_login:
                login_view(db)
            with tab_signup:
                signup_view(db)
            return

        with st.sidebar:
            st.write(f"Signed in as: `{user.email}`")
            if st.button("Logout"):
                st.session_state.pop("user_id", None)
                st.rerun()

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Upload reference document")
            ref_file = st.file_uploader(
                "Reference file",
                type=["txt", "md", "csv", "xlsx", "xlsm", "xltx", "xltm", "pdf"],
                key="ref_upload",
            )
            if st.button("Upload reference"):
                save_reference(db, user, ref_file)

        with col2:
            st.subheader("Upload questionnaire")
            run_title = st.text_input("Run title", value="Security Review - Q1")
            q_file = st.file_uploader(
                "Questionnaire file",
                type=["csv", "xlsx", "xlsm", "xltx", "xltm", "pdf", "txt", "md"],
                key="q_upload",
            )
            if st.button("Create run"):
                save_questionnaire(db, user, run_title, q_file)

        st.markdown("---")
        st.subheader("Current references")
        docs = (
            db.query(models.ReferenceDocument)
            .filter(models.ReferenceDocument.user_id == user.id)
            .order_by(models.ReferenceDocument.created_at.desc())
            .all()
        )
        if not docs:
            st.info("No reference documents uploaded yet.")
        for doc in docs:
            c1, c2, c3 = st.columns([6, 3, 2])
            c1.write(doc.filename)
            c2.caption(doc.created_at.strftime("%Y-%m-%d %H:%M"))
            if c3.button("Delete", key=f"del_doc_{doc.id}"):
                db.delete(doc)
                db.commit()
                st.rerun()

        st.markdown("---")
        st.subheader("Runs")
        runs = (
            db.query(models.QuestionnaireRun)
            .filter(models.QuestionnaireRun.user_id == user.id)
            .order_by(models.QuestionnaireRun.created_at.desc())
            .all()
        )
        if not runs:
            st.info("No questionnaire runs yet.")
            return

        run_options = {f"{r.title} ({r.created_at.strftime('%Y-%m-%d %H:%M')})": r.id for r in runs}
        selected_label = st.selectbox("Select run", list(run_options.keys()))
        run_id = run_options[selected_label]

        run = (
            db.query(models.QuestionnaireRun)
            .filter(models.QuestionnaireRun.id == run_id, models.QuestionnaireRun.user_id == user.id)
            .first()
        )
        if not run:
            st.error("Run not found.")
            return

        questions = (
            db.query(models.Question)
            .options(joinedload(models.Question.answer))
            .filter(models.Question.run_id == run.id)
            .order_by(models.Question.position.asc())
            .all()
        )
        total, answered, not_found = run_summary(questions)
        s1, s2, s3 = st.columns(3)
        s1.metric("Total questions", total)
        s2.metric("Answered w/ citations", answered)
        s3.metric("Not found", not_found)

        a1, a2, a3, a4 = st.columns(4)
        if a1.button("Generate all answers"):
            for q in questions:
                generate_for_question(db, user.id, q)
            db.commit()
            st.success("Generated answers.")
            st.rerun()

        if a2.button("Reuse this questionnaire"):
            ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            new_run = models.QuestionnaireRun(
                user_id=user.id,
                title=f"{run.title} (Reuse {ts})",
                original_filename=run.original_filename,
                original_format=run.original_format,
            )
            db.add(new_run)
            db.flush()
            for q in questions:
                db.add(models.Question(run_id=new_run.id, position=q.position, text=q.text))
            db.commit()
            st.success("Questionnaire reused.")
            st.rerun()

        if a3.button("Delete this run"):
            db.delete(run)
            db.commit()
            st.rerun()

        export_questions = (
            db.query(models.Question)
            .options(joinedload(models.Question.answer))
            .filter(models.Question.run_id == run.id)
            .order_by(models.Question.position.asc())
            .all()
        )
        if run.original_format == ".csv":
            csv_content = to_csv_rows(export_questions)
            a4.download_button(
                "Export CSV",
                data=csv_content,
                file_name=f"{run.title}_answered.csv",
                mime="text/csv",
            )
        else:
            xlsx_bytes = to_xlsx_bytes(export_questions)
            a4.download_button(
                "Export XLSX",
                data=io.BytesIO(xlsx_bytes),
                file_name=f"{run.title}_answered.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        st.markdown("### Review and edit answers")
        selected_for_regen = []
        save_changes = False
        regen = False
        with st.form("review_form"):
            for q in export_questions:
                st.markdown(f"**Q{q.position}. {q.text}**")
                ans = q.answer.generated_answer if q.answer else ""
                edited = q.answer.edited_answer if (q.answer and q.answer.edited_answer) else ans
                value = st.text_area("Answer", value=edited, key=f"answer_{q.id}", height=100)
                if q.answer:
                    st.caption(f"Confidence: {q.answer.confidence}")
                    st.caption("Citations: " + ("; ".join(q.answer.citations or []) or "-"))
                    if q.answer.evidence_snippets:
                        with st.expander("Evidence snippets"):
                            for snip in q.answer.evidence_snippets:
                                st.write(f"- {snip}")
                if st.checkbox("Regenerate this question", key=f"regen_{q.id}"):
                    selected_for_regen.append(q.id)
                if q.answer:
                    q.answer.edited_answer = value.strip()
                st.markdown("---")

            c1, c2 = st.columns(2)
            save_changes = c1.form_submit_button("Save edits")
            regen = c2.form_submit_button("Regenerate selected")

        if save_changes:
            db.commit()
            st.success("Edits saved.")
            st.rerun()

        if regen:
            targets = (
                db.query(models.Question)
                .options(joinedload(models.Question.answer))
                .filter(models.Question.run_id == run.id, models.Question.id.in_(selected_for_regen))
                .all()
            )
            for q in targets:
                generate_for_question(db, user.id, q)
            db.commit()
            st.success("Selected answers regenerated.")
            st.rerun()
    finally:
        db.close()


if __name__ == "__main__":
    main()
