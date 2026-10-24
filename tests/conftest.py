"""Shared test fixtures: in-memory SQLite session + seed helpers."""

from __future__ import annotations

import pytest

# The DB schema moved from notify.schema to db.models in the auth refactor.
# Import defensively so a schema mismatch does not break unrelated test suites
# (LLM tools, BFF). DB-dependent fixtures skip when the models are unavailable.
try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from db.models import Base, Building, Event, User, Utility, Zip
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


import datetime as _dt
import itertools as _itertools

_ids = _itertools.count(1)


def _ensure_zip(db, zip_code="00001"):
    """Create the zip row buildings/events hang off, once per session."""
    z = db.get(Zip, zip_code)
    if z is None:
        z = Zip(zip=zip_code, ej=False)
        db.add(z)
        db.commit()
    return z


def _ensure_utility(db, uid="util-test"):
    u = db.get(Utility, uid)
    if u is None:
        u = Utility(id=uid, name="MA Util", source_id="sim:util-test")
        db.add(u)
        db.commit()
    return u


def make_user(db, **kw):
    """Create a login user satisfying the role-scope CHECK constraint.

    A building_manager (the default role) must carry a building_id and no
    utility_id; a utility user the reverse. When the caller does not pass the
    matching scope id, we provision one so the row is always valid.
    """
    defaults = dict(email=f"u{next(_ids)}@x.test", role="building_manager",
                    password_hash="x")
    defaults.update(kw)
    role = defaults["role"]
    if role == "building_manager" and defaults.get("building_id") is None:
        defaults["building_id"] = make_building(db).id
        defaults["utility_id"] = None
    elif role == "utility" and defaults.get("utility_id") is None:
        defaults["utility_id"] = _ensure_utility(db).id
        defaults["building_id"] = None
    u = User(**defaults)
    db.add(u)
    db.commit()
    return u


def make_event(db, building_ids=(), status="approved", **kw):
    util = _ensure_utility(db)
    now = _dt.datetime(2026, 7, 1, 14, 0, tzinfo=_dt.timezone.utc)
    fields = dict(
        utility_id=util.id,
        status=status,
        window_start=now,
        window_end=now + _dt.timedelta(hours=4),
        window_label="Tue 2-6PM",
        target_mw=150,
        cap_pct=25,
        current_version=1,
    )
    fields.update(kw)
    e = Event(**fields)
    db.add(e)
    db.commit()
    for bid in building_ids:
        db.add(EventBuilding(event_id=e.id, plan_version=e.current_version,
                             building_id=bid, kw_requested=20))
    db.commit()
    return e


def make_building(db, **kw):
    _ensure_zip(db)
    defaults = dict(
        id=f"bld-{next(_ids)}",
        zip="00001",
        address="1 Test St",
        enrolled=True,
        enrolled_capacity_kw=100,
        offered_capacity_kw=20,
    )
    defaults.update(kw)
    b = Building(**defaults)
    db.add(b)
    db.commit()
    return b


# Hypothesis profile shared by all property tests.
from hypothesis import settings  # noqa: E402

settings.register_profile("default", max_examples=100)
settings.load_profile("default")
