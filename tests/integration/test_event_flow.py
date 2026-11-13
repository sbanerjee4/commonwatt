"""End-to-end event story: size -> approve -> facility decides -> operator confirms."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.routes.event_flow import size_requests
from db.models import Base, Message, PlanBuilding
from tests.conftest import make_building, make_user, make_utility

# 129860 has 137 kW curtailable capacity in fixtures/berdo.json.
BLD = "129860"
CAPACITY = 137.0


class _FakePlan:
    version = 1
    achieved_mw = 0.137
    building_count = 1
    ej_share_pct = 0.0
    ej_cap_pct = 35.0
    reachable = True
    tradeoff = None
    source_id = "src-test"

    def __init__(self, target_mw: float):
        self.target_mw = target_mw
        self.portfolio = [{"building_id": BLD, "address": "730 Border St.", "zip": "02128",
                           "curtailable_load_kw": CAPACITY, "is_ej": True}]


class _FakeResult:
    approved = True
    iterations = 1
    critic_reason = None
    trace: list = []

    def __init__(self, target_mw: float):
        self.final_plan = _FakePlan(target_mw)


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("COMMONWATT_INSECURE_COOKIES", "1")
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    util = make_utility(db)
    make_building(db, id=BLD)
    make_user(db, email="m@x.test", role="building_manager", building_id=BLD,
              password_hash=hash_password("pw-mgr"))
    make_user(db, email="op@x.test", role="utility", utility_id=util.id,
              password_hash=hash_password("pw-op"))

    calls: list[dict] = []

    def fake_run_planner(**kw):
        calls.append(kw)
        return _FakeResult(kw["target_mw"])

    import agent.planner as planner_mod
    monkeypatch.setattr(planner_mod, "run_planner", fake_run_planner, raising=False)

    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: (yield db)
    yield TestClient(app), db, calls
    app.dependency_overrides.clear()
    db.close()


def _login(c, email, pw):
    assert c.post("/auth/login", json={"email": email, "password": pw}).status_code == 200


def test_size_requests_asks_marginal_building_only_for_the_gap():
    rows = [{"building_id": str(i), "curtailable_load_kw": 1000.0} for i in range(3)]
    assert [r["kw_requested"] for r in size_requests(rows, 2.5)] == [1000.0, 1000.0, 500.0]


def test_full_story_and_capacity_guard(ctx):
    c, db, calls = ctx
    _login(c, "op@x.test", "pw-op")
    # 0.1 MW target: the 137 kW building is asked for only 100 kW.
    assert c.post("/event/approve", json={"target_mw": 0.1}).status_code == 200
    assert db.query(PlanBuilding).one().kw_requested == 100.0

    _login(c, "m@x.test", "pw-mgr")
    inbox = c.get(f"/inbox/{BLD}").json()
    assert inbox["requested_kw"] == 100.0 and inbox["capacity_kw"] == CAPACITY
    assert inbox["decision"] is None

    # Counteroffers at or above the ask (or capacity) are rejected with a reason.
    for bad in (100, 250, 0):
        r = c.post(f"/inbox/{BLD}/decision", json={"decision": "counter", "kw": bad})
        assert r.status_code == 422, bad
    r = c.post(f"/inbox/{BLD}/decision", json={"decision": "counter", "kw": 60})
    assert r.status_code == 200
    assert c.get(f"/inbox/{BLD}").json()["decision"] == {"kind": "counter", "kw": 60.0}

    _login(c, "op@x.test", "pw-op")
    ev = c.get("/event/current").json()["event"]
    assert ev["committedMw"] == 0.06 and ev["responded"] == 1 and not ev["confirmed"]
    r = c.post(f"/event/{ev['id']}/confirm")
    assert r.status_code == 200 and r.json()["building_count"] == 1
    assert c.post(f"/event/{ev['id']}/confirm").status_code == 409
    assert any(m.body.startswith("Confirmed:") for m in
               db.query(Message).filter_by(building_id=BLD, sender_role="system"))

    # Decisions lock once confirmed.
    _login(c, "m@x.test", "pw-mgr")
    assert c.post(f"/inbox/{BLD}/decision", json={"decision": "accept"}).status_code == 409

    # The building that carried the confirmed event is on cooldown next draft.
    _login(c, "op@x.test", "pw-op")
    draft = c.post("/event/draft", json={"target_mw": 0.1}).json()
    assert calls[-1]["prev_event_building_ids"] == [BLD]
    assert draft["equity"]["cooldownExcluded"] == [BLD]
    assert draft["equity"]["neighborhoods"][0]["recentCalls"] == 1

    # Once a newer event is approved, the rested building is eligible again.
    c.post("/event/approve", json={"target_mw": 0.1})
    c.post("/event/draft", json={"target_mw": 0.1})
    assert calls[-1]["prev_event_building_ids"] == []


def test_confirm_needs_a_commitment(ctx):
    c, db, _ = ctx
    _login(c, "op@x.test", "pw-op")
    c.post("/event/approve", json={"target_mw": 0.1})
    ev = c.get("/event/current").json()["event"]
    assert c.post(f"/event/{ev['id']}/confirm").status_code == 409

    _login(c, "m@x.test", "pw-mgr")
    assert c.post(f"/inbox/{BLD}/decision", json={"decision": "decline"}).status_code == 200
    _login(c, "op@x.test", "pw-op")
    assert c.post(f"/event/{ev['id']}/confirm").status_code == 409
