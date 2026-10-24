"""Shared test fixtures: in-memory SQLite session + seed helpers (real schema)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import (
    Base,
    Building,
    CallHistory,
    Event,
    PlanBuilding,
    User,
    Utility,
    Zip,
)


def _fresh_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture
def db():
    session = _fresh_session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def db_factory():
    """Return a callable giving a brand-new in-memory session each call."""
    return _fresh_session


_UTIL_SEQ = 0


def make_utility(db, **kw):
    global _UTIL_SEQ
    _UTIL_SEQ += 1
    defaults = dict(id=f"util-{_UTIL_SEQ}", name="MA Util", source_id="seed")
    defaults.update(kw)
    u = Utility(**defaults)
    db.add(u)
    db.commit()
    return u


def make_building(db, *, zip_code="02128", **kw):
    """Seed a Zip (if needed) and a Building with a String(64) id."""
    if db.get(Zip, zip_code) is None:
        db.add(Zip(zip=zip_code, ej=False))
        db.commit()
    bid = kw.pop("id", None) or f"bld-{id(kw) & 0xffffff}"
    defaults = dict(id=bid, zip=zip_code, address="1 Elm St",
                    enrolled=True, enrolled_capacity_kw=100.0)
    defaults.update(kw)
    b = Building(**defaults)
    db.add(b)
    db.commit()
    return b


def make_user(db, **kw):
    defaults = dict(email=f"u{id(kw)}@x.test", role="building_manager",
                    password_hash="x")
    defaults.update(kw)
    u = User(**defaults)
    db.add(u)
    db.commit()
    return u


def make_event(db, *, utility, building_ids=(), status="approved", version=1, **kw):
    """Approved event + a PlanBuilding row per building in the current version."""
    import datetime as dt

    now = dt.datetime(2026, 7, 1, 18, 0, tzinfo=dt.timezone.utc)
    defaults = dict(
        utility_id=utility.id, status=status, window_label="Tue 2-6PM",
        window_start=now, window_end=now, target_mw=150.0, cap_pct=0.35,
        current_version=version,
    )
    defaults.update(kw)
    e = Event(**defaults)
    db.add(e)
    db.commit()
    for bid in building_ids:
        db.add(PlanBuilding(event_id=e.id, plan_version=version,
                            building_id=bid, kw_requested=20.0, reason="peak"))
    db.commit()
    return e


def make_call_history(db, *, event, building_id, kw_requested=20.0):
    c = CallHistory(event_id=event.id, building_id=building_id,
                    kw_requested=kw_requested, reason="peak")
    db.add(c)
    db.commit()
    return c


# Hypothesis profile shared by all property tests.
from hypothesis import settings  # noqa: E402

settings.register_profile("default", max_examples=100)
settings.load_profile("default")
