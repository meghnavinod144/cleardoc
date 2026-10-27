"""Database connection setup.

One place decides WHICH database we talk to. Today: SQLite (a simple
file on disk — zero setup, perfect for development). In the cloud phase
we change ONE line (DATABASE_URL) to point at PostgreSQL — the rest of
the code never knows the difference. That's the point of this file.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# sqlite:///./data/cleardoc.db  →  "a SQLite database, stored in this file"
# Later becomes:  postgresql://user:password@host:5432/cleardoc
DATABASE_URL = "sqlite:///./data/cleardoc.db"

# The engine manages the actual connection to the database.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# A Session is one conversation with the database: read, write, commit.
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """All our table-models inherit from this; it collects them
    so create_all() can create every table at startup."""
