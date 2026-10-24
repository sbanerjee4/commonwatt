"""
BFF endpoint tests.

Data endpoints (no LLM) are tested directly against the FastAPI app via
TestClient. The two LLM endpoints (/event/draft, /building/{id}/chat) are
tested with the planner/chat calls monkeypatched, so these run without Bedrock.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.auth import hash_password
from app.db import get_db
from db.models import Base, User, Utility, Zip

client = TestClient(app)


@pytest.fixture
def operator_client(monkeypatch):
    """A TestClient logged in as a utility operator, over an in-memory DB.

    Used by the auth-gated LLM endpoints (/event/draft, building chat). Read
    endpoints need no auth and use the module-level `client`.
    """
    monkeypatch.setenv("COMMONWATT_INSECURE_COOKIES", "1")
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    db.add(Zip(zip="00001", ej=False))
    util = Utility(id="util-ma", name="MA", source_id="sim:util")
    db.add(util)
    db.commit()
    db.add(User(email="utility@demo", role="utility", utility_id=util.id,
                password_hash=hash_password("pw-op")))
    db.commit()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    c = TestClient(app)
    assert c.post("/auth/login",
                  json={"email": "utility@demo", "password": "pw-op"}).status_code == 200
    yield c
    app.dependency_overrides.clear()
    db.close()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["buildings"] == 2472


def test_zips_shape():
    r = client.get("/zips")
    assert r.status_code == 200
    zips = r.json()["zips"]
    assert len(zips) > 0
    z = zips[0]
    # contract fields present
    for key in ("zip", "buildingCount", "curtailableLoadKw", "ejStatus",
                "cumulativeCalls", "hasGeometry"):
        assert key in z
    # provenance: load carries a source_id when present
    if z["curtailableLoadKw"] is not None:
        assert "source_id" in z["curtailableLoadKw"]


def test_zip_buildings_markers():
    r = client.get("/zips/02128/buildings")
    assert r.status_code == 200
    buildings = r.json()["buildings"]
    assert len(buildings) > 0
    b = buildings[0]
    for key in ("buildingId", "address", "zip", "lngLat",
                "propertyType", "grossAreaSf", "curtailableLoadKw"):
        assert key in b
    # load, when present, carries source_id and a basis
    if b["curtailableLoadKw"] is not None:
        assert "source_id" in b["curtailableLoadKw"]
        assert b["curtailableLoadKw"]["basis"] in (
            "metered", "estimated_from_type", "unknown"
        )


def test_zip_not_found():
    r = client.get("/zips/99999/buildings")
    assert r.status_code == 404


def test_building_profile():
    r = client.get("/portfolio/buildings/129860")
    assert r.status_code == 200
    body = r.json()
    assert body["building_id"] == "129860"
    assert "curtailable_load_kw" in body
    assert "is_ej" in body


def test_building_not_found():
    r = client.get("/portfolio/buildings/does-not-exist")
    assert r.status_code == 404


def test_savings_has_source_and_estimated():
    r = client.get("/savings?shed_mw=10")
    assert r.status_code == 200
    for counter in r.json()["counters"]:
        assert counter["source_id"]
        assert counter["estimated"] is True


def test_savings_zero_at_zero():
    r = client.get("/savings?shed_mw=0")
    assert r.status_code == 200
    for counter in r.json()["counters"]:
        val = counter.get("value_usd", counter.get("value_mt"))
        assert val == 0.0


def test_recruitment_labeled_simulated():
    r = client.get("/recruitment?top_n=5")
    assert r.status_code == 200
    body = r.json()
    assert body["simulated_enrollment"] is True
    assert len(body["top_candidates"]) <= 5


# --- LLM endpoints, mocked so no Bedrock call is made ---

def test_event_draft_mocked(monkeypatch, operator_client):
    from agent import planner as planner_mod

    class _Plan:
        version = 2
        target_mw = 20.0
        achieved_mw = 20.8
        building_count = 5
        ej_share_pct = 0.0
        ej_cap_pct = 35.0
        reachable = True
        tradeoff = None
        portfolio = [{"building_id": "x", "is_ej": False}]
        source_id = "massgis_ej_2020"

    class _Step:
        ts = "t"
        kind = "plan"
        summary = "ok"
        plan_version = 2
        tool_name = "plan_event"
        rejected_by = None

    class _Result:
        approved = True
        iterations = 2
        critic_reason = None
        final_plan = _Plan()
        trace = [_Step()]

    monkeypatch.setattr(planner_mod, "run_planner", lambda **kw: _Result())

    r = operator_client.post("/event/draft", json={"target_mw": 20.0, "ej_cap_pct": 0.35})
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] is True
    assert body["plan"]["achievedMw"] == 20.8
    assert len(body["trace"]) == 1


def test_building_chat_mocked(monkeypatch, operator_client):
    from agent import chat as chat_mod

    class _Session:
        def chat(self, msg):
            return "Your building is Shore Plaza East."

    monkeypatch.setattr(chat_mod, "make_session", lambda bid, event_context=None: _Session())

    r = operator_client.post("/portfolio/building/129860/chat", json={"message": "what is my building?"})
    assert r.status_code == 200
    body = r.json()
    assert body["buildingId"] == "129860"
    assert "Shore Plaza" in body["reply"]


def test_all_building_markers_have_coords_and_equity():
    """The map endpoint returns markers with real coords for most buildings and
    exposes affluence context; unplaced buildings keep lngLat=null (not dropped)."""
    r = client.get("/portfolio/buildings")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2472
    assert body["placed"] > 2000  # ~93% geocoded
    placed = [b for b in body["buildings"] if b["lngLat"]]
    assert placed, "expected geocoded buildings"
    b = placed[0]
    lng, lat = b["lngLat"]
    assert -72 < lng < -70 and 42 < lat < 43  # Greater Boston bbox
    assert b["affluenceTier"] in ("low", "middle", "high", "unknown")
    # unplaced buildings are present with null coords, not dropped
    assert len(body["buildings"]) == body["total"]
