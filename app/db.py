"""SQLite engine + session for the app and its FastAPI dependency."""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base

_DB_URL = os.environ.get("COMMONWATT_DB_URL", "sqlite:///./commonwatt.db")

engine = create_engine(_DB_URL)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
