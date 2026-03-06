import io
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from . import auth, models
from .db import Base, engine, get_db
from .services.ai import NOT_FOUND, generate_grounded_answer
from .services.exporter import to_csv_rows, to_xlsx_bytes
from .services.parsing import chunk_text, parse_questionnaire, parse_reference_doc
from .services.retrieval import retrieve_top_chunks


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Structured Questionnaire Answering Tool")
app.add_middleware(SessionMiddleware, secret_key=auth.app_secret())

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def get_user_or_redirect(request: Request, db: Session) -> models.User:
    user = auth.get_current_user(request.session, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = auth.get_current_user(request.session, db)
    if not user:
        return templates.TemplateResponse("index.html", {"request": request})
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/design-previews", response_class=HTMLResponse)
def design_previews(request: Request):
    return templates.TemplateResponse("design_previews.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@app.post("/signup", response_class=HTMLResponse)
def signup(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == email.lower().strip()).first()
    if existing:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": "Email already exists."}, status_code=400
        )
    user = models.User(email=email.lower().strip(), password_hash=auth.hash_password(password))
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email.lower().strip()).first()
    if not user or not auth.verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Invalid credentials."}, status_code=400
        )
    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    docs = (
        db.query(models.ReferenceDocument)
        .filter(models.ReferenceDocument.user_id == user.id)
        .order_by(models.ReferenceDocument.created_at.desc())
        .all()
    )
    runs = (
        db.query(models.QuestionnaireRun)
        .filter(models.QuestionnaireRun.user_id == user.id)
        .order_by(models.QuestionnaireRun.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, "docs": docs, "runs": runs, "error": None}
    )


@app.post("/reference/upload", response_class=HTMLResponse)
async def upload_reference(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    file_bytes = await file.read()
    try:
        content = parse_reference_doc(file.filename, file_bytes)
    except ValueError as exc:
        return await _dashboard_with_error(request, db, str(exc))

    if not content.strip():
        return await _dashboard_with_error(request, db, "Reference file is empty.")

    doc = models.ReferenceDocument(user_id=user.id, filename=file.filename, content=content)
    db.add(doc)
    db.flush()

    for idx, chunk in enumerate(chunk_text(content)):
        db.add(models.ReferenceChunk(document_id=doc.id, chunk_index=idx, text=chunk))

    db.commit()
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/reference/{doc_id}/delete")
def delete_reference(doc_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    doc = (
        db.query(models.ReferenceDocument)
        .filter(models.ReferenceDocument.id == doc_id, models.ReferenceDocument.user_id == user.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Reference document not found")
    db.delete(doc)
    db.commit()
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/questionnaire/upload")
async def upload_questionnaire(
    request: Request,
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = get_user_or_redirect(request, db)
    file_bytes = await file.read()
    try:
        questions = parse_questionnaire(file.filename, file_bytes)
    except ValueError as exc:
        return await _dashboard_with_error(request, db, str(exc))

    if not questions:
        return await _dashboard_with_error(request, db, "No questions found in uploaded questionnaire.")

    ext = Path(file.filename).suffix.lower()
    run = models.QuestionnaireRun(
        user_id=user.id,
        title=title.strip() or "Questionnaire",
        original_filename=file.filename,
        original_format=ext,
    )
    db.add(run)
    db.flush()

    for idx, question_text in enumerate(questions, start=1):
        db.add(models.Question(run_id=run.id, position=idx, text=question_text))
    db.commit()
    return RedirectResponse(f"/runs/{run.id}", status_code=302)


@app.post("/runs/{run_id}/delete")
def delete_run(run_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    run = (
        db.query(models.QuestionnaireRun)
        .filter(models.QuestionnaireRun.id == run_id, models.QuestionnaireRun.user_id == user.id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    db.delete(run)
    db.commit()
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/runs/{run_id}/reuse")
def reuse_run(run_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    source_run = _load_run_or_404(db, user.id, run_id)
    source_questions = (
        db.query(models.Question)
        .filter(models.Question.run_id == source_run.id)
        .order_by(models.Question.position.asc())
        .all()
    )
    if not source_questions:
        return RedirectResponse("/dashboard", status_code=302)

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    new_run = models.QuestionnaireRun(
        user_id=user.id,
        title=f"{source_run.title} (Reuse {timestamp})",
        original_filename=source_run.original_filename,
        original_format=source_run.original_format,
    )
    db.add(new_run)
    db.flush()

    for question in source_questions:
        db.add(models.Question(run_id=new_run.id, position=question.position, text=question.text))

    db.commit()
    return RedirectResponse(f"/runs/{new_run.id}", status_code=302)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(run_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    run = _load_run_or_404(db, user.id, run_id)

    questions = (
        db.query(models.Question)
        .options(joinedload(models.Question.answer))
        .filter(models.Question.run_id == run.id)
        .order_by(models.Question.position.asc())
        .all()
    )
    summary = _coverage_summary(questions)
    return templates.TemplateResponse(
        "run_detail.html",
        {"request": request, "run": run, "questions": questions, "summary": summary},
    )


@app.post("/runs/{run_id}/generate")
def generate_all_answers(run_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    run = _load_run_or_404(db, user.id, run_id)
    questions = (
        db.query(models.Question)
        .options(joinedload(models.Question.answer))
        .filter(models.Question.run_id == run.id)
        .order_by(models.Question.position.asc())
        .all()
    )

    for question in questions:
        _generate_for_question(db, user.id, question)

    db.commit()
    return RedirectResponse(f"/runs/{run.id}/review", status_code=302)


@app.get("/runs/{run_id}/review", response_class=HTMLResponse)
def review_page(run_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    run = _load_run_or_404(db, user.id, run_id)
    questions = (
        db.query(models.Question)
        .options(joinedload(models.Question.answer))
        .filter(models.Question.run_id == run.id)
        .order_by(models.Question.position.asc())
        .all()
    )
    summary = _coverage_summary(questions)
    return templates.TemplateResponse(
        "review.html",
        {"request": request, "run": run, "questions": questions, "summary": summary},
    )


@app.post("/runs/{run_id}/review/save")
async def save_review(run_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    run = _load_run_or_404(db, user.id, run_id)
    form = await request.form()

    questions = db.query(models.Question).options(joinedload(models.Question.answer)).filter(models.Question.run_id == run.id).all()
    for question in questions:
        answer = question.answer
        if not answer:
            continue
        key = f"answer_{question.id}"
        if key in form:
            answer.edited_answer = str(form.get(key)).strip()
    db.commit()
    return RedirectResponse(f"/runs/{run.id}/review", status_code=302)


@app.post("/runs/{run_id}/regenerate")
async def regenerate_selected(run_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    run = _load_run_or_404(db, user.id, run_id)
    form = await request.form()
    selected_ids = [int(v) for v in form.getlist("question_ids") if str(v).isdigit()]

    if not selected_ids:
        return RedirectResponse(f"/runs/{run.id}/review", status_code=302)

    questions = (
        db.query(models.Question)
        .options(joinedload(models.Question.answer))
        .filter(models.Question.run_id == run.id, models.Question.id.in_(selected_ids))
        .all()
    )
    for question in questions:
        _generate_for_question(db, user.id, question)
    db.commit()
    return RedirectResponse(f"/runs/{run.id}/review", status_code=302)


@app.get("/runs/{run_id}/export")
def export_run(run_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_user_or_redirect(request, db)
    run = _load_run_or_404(db, user.id, run_id)
    questions = (
        db.query(models.Question)
        .options(joinedload(models.Question.answer))
        .filter(models.Question.run_id == run.id)
        .order_by(models.Question.position.asc())
        .all()
    )

    if run.original_format == ".csv":
        csv_content = to_csv_rows(questions)
        headers = {"Content-Disposition": f'attachment; filename="{run.title}_answered.csv"'}
        return Response(content=csv_content, media_type="text/csv", headers=headers)

    xlsx_bytes = to_xlsx_bytes(questions)
    headers = {"Content-Disposition": f'attachment; filename="{run.title}_answered.xlsx"'}
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


async def _dashboard_with_error(request: Request, db: Session, error: str):
    user = get_user_or_redirect(request, db)
    docs = (
        db.query(models.ReferenceDocument)
        .filter(models.ReferenceDocument.user_id == user.id)
        .order_by(models.ReferenceDocument.created_at.desc())
        .all()
    )
    runs = (
        db.query(models.QuestionnaireRun)
        .filter(models.QuestionnaireRun.user_id == user.id)
        .order_by(models.QuestionnaireRun.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": user, "docs": docs, "runs": runs, "error": error}, status_code=400
    )


def _load_run_or_404(db: Session, user_id: int, run_id: int) -> models.QuestionnaireRun:
    run = (
        db.query(models.QuestionnaireRun)
        .filter(models.QuestionnaireRun.id == run_id, models.QuestionnaireRun.user_id == user_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _generate_for_question(db: Session, user_id: int, question: models.Question):
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
        confidence = round(min(0.99, max(hit.score for hit in hits)), 2) if hits else 0.0
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


def _coverage_summary(questions: List[models.Question]):
    total = len(questions)
    answered_with_citations = 0
    not_found = 0
    for question in questions:
        ans = question.answer
        if not ans:
            continue
        if ans.status == "not_found":
            not_found += 1
        if ans.status == "answered" and ans.citations:
            answered_with_citations += 1
    return {
        "total": total,
        "answered_with_citations": answered_with_citations,
        "not_found": not_found,
    }
