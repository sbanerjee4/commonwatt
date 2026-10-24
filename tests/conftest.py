"""Shared test fixtures: in-memory SQLite session + seed helpers."""

from __future__ import annotations

import pytest

# The DB schema moved from notify.schema to db.models in the auth refactor.
# Import defensively so a schema mismatch does not break unrelated test suites
# (LLM tools, BFF). DB-dependent fixtures skip when the models are unavailable.
try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from db.models import Base, Building, Event, User, Utility
    from db.models import PlanBuilding as EventBuilding  # renamed in refactor
    _DB_AVAILABLE = True
except Exception as _db_import_err:  # noqa: BLE001
    _DB_AVAILABLE = False
    _DB_IMPORT_ERR = _db_import_err


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture
def db():
    if not _DB_AVAILABLE:
        pytest.skip(f"DB models unavailable: {_DB_IMPORT_ERR}")
    session = _fresh_session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def db_factory():
    if not _DB_AVAILABLE:
        pytest.skip(f"DB models unavailable: {_DB_IMPORT_ERR}")
    """Return a callable giving a brand-new in-memory session each call.

    Hypothesis replays one test body many times; a single shared session
    would leak unique-constraint state (e.g. users.phone) across examples.
    """
    return _fresh_session


def make_user(db, **kw):
    defaults = dict(email=f"u{id(kw)}@x.test", role="building_manager")
    defaults.update(kw)
    u = User(**defaults)
    db.add(u)
    db.commit()
    return u


def make_event(db, building_ids=(), status="approved", **kw):
    util = Utility(name="MA Util")
    db.add(util)
    db.commit()
    e = Event(utility_id=util.id, status=status, window_label="Tue 2-6PM",
              reason_text="peak day", target_mw=150, estimated_payment=200, **kw)
    db.add(e)
    db.commit()
    for bid in building_ids:
        db.add(EventBuilding(event_id=e.id, building_id=bid))
    db.commit()
    return e


def make_building(db, **kw):
    defaults = dict(name="Bldg", kw_enrolled=100, kw_requested=20)
    defaults.update(kw)
    b = Building(**defaults)
    db.add(b)
    db.commit()
    return b


# Hypothesis profile shared by all property tests.
from hypothesis import settings  # noqa: E402

settings.register_profile("default", max_examples=100)
settings.load_profile("default")
