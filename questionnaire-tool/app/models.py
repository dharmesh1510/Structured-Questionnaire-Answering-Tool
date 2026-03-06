from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    reference_documents = relationship("ReferenceDocument", back_populates="user", cascade="all,delete")
    questionnaire_runs = relationship("QuestionnaireRun", back_populates="user", cascade="all,delete")


class ReferenceDocument(Base):
    __tablename__ = "reference_documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="reference_documents")
    chunks = relationship("ReferenceChunk", back_populates="document", cascade="all,delete")


class ReferenceChunk(Base):
    __tablename__ = "reference_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_doc_chunk"),)

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("reference_documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)

    document = relationship("ReferenceDocument", back_populates="chunks")


class QuestionnaireRun(Base):
    __tablename__ = "questionnaire_runs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    original_format = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="questionnaire_runs")
    questions = relationship("Question", back_populates="run", cascade="all,delete")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("run_id", "position", name="uq_run_position"),)

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("questionnaire_runs.id"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)

    run = relationship("QuestionnaireRun", back_populates="questions")
    answer = relationship("Answer", uselist=False, back_populates="question", cascade="all,delete")


class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, unique=True, index=True)
    generated_answer = Column(Text, nullable=False)
    edited_answer = Column(Text, nullable=True)
    citations = Column(JSON, nullable=False, default=list)
    evidence_snippets = Column(JSON, nullable=False, default=list)
    confidence = Column(Float, nullable=False, default=0.0)
    status = Column(String(30), nullable=False, default="answered")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    question = relationship("Question", back_populates="answer")
