"""Database models: each class = one table, each attribute = one column.

This is the ORM (Object-Relational Mapper) style: we describe tables as
Python classes, and SQLAlchemy translates our Python into SQL commands.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Document(Base):
    """One row per uploaded document — the app's memory of what exists.

    The file's bytes live on disk (later: cloud storage); this row holds
    everything ABOUT the file, so we can find, list, and track it.
    """

    __tablename__ = "documents"

    # Primary key: the unique handle for this row — the same document_id
    # we return to the user at upload time. (Your "contact ID 3" idea.)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    stored_path: Mapped[str] = mapped_column(String(500))

    # Tracks the document through the pipeline:
    # received → ocr_done → extracted → ready  (we add stages as we build)
    status: Mapped[str] = mapped_column(String(30), default="received")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
