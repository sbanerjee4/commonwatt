"""Integration test for POST /event/approve — approval fans out to buildings."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db.models import Base, Event, Message, PlanBuilding
from app.auth import hash_password
from tests.conftest import make_building, make_user, make_utility


class _FakePlan:
    version = 1
    target_mw = 20.0
    achieved_mw = 20.3
    building_count = 1
    ej_share_pct = 10.0
    ej_cap_pct = 35.0
    reachable = True
    tradeoff = None
    source_id = "src-test"

    def __init__(self, building_id: str):
        self.portfolio = [
            {"building_id": building_id, "address": "1 Test St", "zip": "00001",
             "curtailable_load_kw": 320.0, "load_basis": "metered", "is_ej": False}
        ]


class _FakeResult:
    approved = True
    iterations = 1
    critic_reason = None
    trace: list = []

    def __init__(self, building_id: str):
        self.final_plan = _FakePlan(building_id)


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("COMMONWATT_INSECURE_COOKIES", "1")
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)

    util = make_utility(db)
    bld = make_building(db, id="129860")
    mgr = make_user(db, email="m@x.test", role="building_manager", building_id=bld.id,
                    password_hash=hash_password("pw-mgr"))
    make_user(db, email="op@x.test", role="utility", utility_id=util.id,
              password_hash=hash_password("pw-op"))

    # Stub the planner so no Bedrock call is made.
    import agent.planner as planner_mod
    monkeypatch.setattr(planner_mod, "run_planner",
                        lambda **kw: _FakeResult(bld.id), raising=False)

    from app.main import app
    from app.db import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app), db, dict(bld=bld.id, mgr=mgr.id)
    app.dependency_overrides.clear()
    db.close()


def _login(c, email, pw):
    assert c.post("/auth/login", json={"email": email, "password": pw}).status_code == 200


def test_approve_creates_event_and_contacts_buildings(ctx):
    c, db, ids = ctx
    _login(c, "op@x.test", "pw-op")

    r = c.post("/event/approve", json={"target_mw": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["building_count"] == 1
    assert ids["bld"] in body["contacted"]

    # Event persisted as approved, with a plan-building row.
    assert db.query(Event).filter_by(status="approved").count() == 1
    assert db.query(PlanBuilding).filter_by(building_id=ids["bld"]).count() == 1

    # A system notice was posted to the building's thread.
    sys_msgs = db.query(Message).filter_by(building_id=ids["bld"], sender_role="system").all()
    assert len(sys_msgs) == 1
    assert "reduce" in sys_msgs[0].body.lower()


def test_manager_reads_the_approval_notice(ctx):
    c, db, ids = ctx
    _login(c, "op@x.test", "pw-op")
    c.post("/event/approve", json={"target_mw": 20})

    # Switch to the building manager and read their inbox.
    _login(c, "m@x.test", "pw-mgr")
    r = c.get(f"/inbox/{ids['bld']}")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert any(m["sender_role"] == "system" and "reduce" in m["body"].lower() for m in msgs)


def test_approve_requires_operator(ctx):
    c, db, ids = ctx
    _login(c, "m@x.test", "pw-mgr")  # building manager, not operator
    r = c.post("/event/approve", json={"target_mw": 20})
    assert r.status_code == 403
