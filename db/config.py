"""Database configuration: one DATABASE_URL drives SQLite (local, tests) and Postgres (deployed demo)."""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./commonwatt.db"


def get_database_url() -> str:
    """Return DATABASE_URL from the environment, or the SQLite default when unset or empty."""
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def make_engine(url: str | None = None) -> Engine:
    """Build an engine. SQLite connections are allowed across threads for FastAPI handlers."""
    resolved = url or get_database_url()
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    return create_engine(resolved, connect_args=connect_args)


engine: Engine = make_engine()
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False
)
