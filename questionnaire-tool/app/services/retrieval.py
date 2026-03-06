import re
from dataclasses import dataclass
from typing import Iterable, List

from sqlalchemy.orm import Session

from .. import models


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "with",
}


@dataclass
class RetrievalHit:
    chunk_id: int
    document_name: str
    chunk_text: str
    score: float

    @property
    def citation(self) -> str:
        return f"{self.document_name}#chunk-{self.chunk_id}"


def tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def overlap_score(query_tokens: Iterable[str], text_tokens: Iterable[str]) -> float:
    qset = set(query_tokens)
    if not qset:
        return 0.0
    tset = set(text_tokens)
    overlap = len(qset.intersection(tset))
    return overlap / len(qset)


def retrieve_top_chunks(db: Session, user_id: int, question: str, top_k: int = 3) -> List[RetrievalHit]:
    q_tokens = tokenize(question)
    if not q_tokens:
        return []

    chunks = (
        db.query(models.ReferenceChunk, models.ReferenceDocument.filename)
        .join(models.ReferenceDocument, models.ReferenceChunk.document_id == models.ReferenceDocument.id)
        .filter(models.ReferenceDocument.user_id == user_id)
        .all()
    )

    hits = []
    for chunk, filename in chunks:
        t_tokens = tokenize(chunk.text)
        qset = set(q_tokens)
        overlap_count = len(qset.intersection(set(t_tokens)))
        score = overlap_score(q_tokens, t_tokens)
        if score > 0 and overlap_count >= 2:
            hits.append(
                RetrievalHit(
                    chunk_id=chunk.id,
                    document_name=filename,
                    chunk_text=chunk.text,
                    score=score,
                )
            )

    hits.sort(key=lambda h: h.score, reverse=True)
    if not hits:
        return []

    threshold = 0.2
    filtered = [h for h in hits[:top_k] if h.score >= threshold]
    return filtered
