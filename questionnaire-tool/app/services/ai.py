import os
from typing import List

from .retrieval import RetrievalHit


NOT_FOUND = "Not found in references."


def generate_grounded_answer(question: str, hits: List[RetrievalHit]) -> str:
    if not hits:
        return NOT_FOUND

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    if api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            context_blocks = []
            for idx, hit in enumerate(hits, start=1):
                context_blocks.append(
                    f"[{idx}] Source: {hit.document_name}\n{hit.chunk_text}"
                )
            context = "\n\n".join(context_blocks)
            prompt = (
                "You answer questionnaire questions using ONLY the supplied reference context.\n"
                "If the context does not contain the answer, respond exactly: Not found in references.\n"
                "Keep answers concise and factual.\n\n"
                f"Question: {question}\n\n"
                f"Reference context:\n{context}"
            )
            resp = client.responses.create(
                model=model,
                input=prompt,
                temperature=0.1,
            )
            text = (resp.output_text or "").strip()
            return text if text else NOT_FOUND
        except Exception:
            return _heuristic_answer(question, hits)

    return _heuristic_answer(question, hits)


def _heuristic_answer(question: str, hits: List[RetrievalHit]) -> str:
    if not hits:
        return NOT_FOUND
    top = hits[0].chunk_text.strip()
    if len(top) > 350:
        top = top[:347] + "..."
    if not top:
        return NOT_FOUND
    return f"Based on reference documentation: {top}"
