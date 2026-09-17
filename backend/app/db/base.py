"""SQLAlchemy engine, session factory, and declarative base.

Uses one central dataset (Requirement 12.3). SQLite for dev; PostgreSQL (RDS)
in production via DATABASE_URL.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator:
    """FastAPI dependency that yields a database session and closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. For production, use Alembic migrations instead."""
    from app import models  # noqa: F401  ensure models are imported/registered

    Base.metadata.create_all(bind=engine)
