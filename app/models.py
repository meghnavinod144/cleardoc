"""Database models: each class = one table, each attribute = one column.

This is the ORM (Object-Relational Mapper) style: we describe tables as
Python classes, and SQLAlchemy translates our Python into SQL commands.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """One registered person. We store the bcrypt HASH, never the password."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Document(Base):
    """One row per uploaded document — the app's memory of what exists.

    The file's bytes live on disk (later: cloud storage); this row holds
    everything ABOUT the file, so we can find, list, and track it.
    """

    __tablename__ = "documents"

    # Primary key: the unique handle for this row — the same document_id
    # we return to the user at upload time. (Your "contact ID 3" idea.)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Who owns this document. Every query MUST filter by this —
    # user A must never see user B's documents.
    owner_id: Mapped[str] = mapped_column(String(36), index=True)

    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    stored_path: Mapped[str] = mapped_column(String(500))

    # Filled by the OCR step (nullable=True: empty until OCR runs).
    raw_text: Mapped[str | None] = mapped_column(String, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(nullable=True)

    # Filled by the extraction step: the labeled fields, stored as JSON text.
    extracted_fields: Mapped[str | None] = mapped_column(String, nullable=True)

    # Tracks the document through the pipeline:
    # received → ocr_done → extracted → ready  (we add stages as we build)
    status: Mapped[str] = mapped_column(String(30), default="received")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Chunk(Base):
    """One retrieval-sized piece of a document, with its embedding vector.

    This table IS our vector store for now (embeddings as JSON text,
    similarity computed in Python — fine for one user's documents).
    The cloud phase swaps it for pgvector, which does the same thing
    at database speed. Same socket pattern again.
    """

    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String)
    embedding: Mapped[str] = mapped_column(String)  # JSON list of floats
