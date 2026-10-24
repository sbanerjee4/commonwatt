"""
BFF endpoint tests.

Data endpoints (no LLM) are tested directly against the FastAPI app via
TestClient. The two LLM endpoints (/event/draft, /building/{id}/chat) are
tested with the planner/chat calls monkeypatched, so these run without Bedrock.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bff.app import app

client = TestClient(app)


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
    r = client.get("/buildings/129860")
    assert r.status_code == 200
    body = r.json()
    assert body["building_id"] == "129860"
    assert "curtailable_load_kw" in body
    assert "is_ej" in body


def test_building_not_found():
    r = client.get("/buildings/does-not-exist")
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

def test_event_draft_mocked(monkeypatch):
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

    r = client.post("/event/draft", json={"target_mw": 20.0, "ej_cap_pct": 0.35})
    assert r.status_code == 200
    body = r.json()
    assert body["approved"] is True
    assert body["plan"]["achievedMw"] == 20.8
    assert len(body["trace"]) == 1


def test_building_chat_mocked(monkeypatch):
    from agent import chat as chat_mod

    class _Session:
        def chat(self, msg):
            return "Your building is Shore Plaza East."

    monkeypatch.setattr(chat_mod, "make_session", lambda bid, event_context=None: _Session())

    r = client.post("/building/129860/chat", json={"message": "what is my building?"})
    assert r.status_code == 200
    body = r.json()
    assert body["buildingId"] == "129860"
    assert "Shore Plaza" in body["reply"]
