"""Unread count, thread close, browser push kept, and SMS-removed assertions."""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db.models import Base, Message, PushSubscription, Thread
from notify.push import notify_user
from tests.conftest import (
    make_building,
    make_call_history,
    make_event,
    make_user,
    make_utility,
)

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def ctx():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    util = make_utility(db)
    bld = make_building(db, id="129860")
    mgr = make_user(db, email="m@x.test", role="building_manager", building_id=bld.id)
    op = make_user(db, email="op@x.test", role="utility", utility_id=util.id)
    ev = make_event(db, utility=util, building_ids=[bld.id])
    make_call_history(db, event=ev, building_id=bld.id)

    from app.main import app
    from app.db import get_db
    import app.routes._chat_agent as agent_mod

    # Stub the agent so a manager reply does not touch Bedrock.
    agent_mod.make_session = lambda bid, event_context=None: type(
        "S", (), {"chat": lambda self, b: "ok (source_id: x)"}
    )()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app), db, dict(bld=bld.id, ev=ev.id, mgr=mgr.id, op=op.id)
    app.dependency_overrides.clear()
    agent_mod.make_session = None
    db.close()


def _mgr(ids):
    return {"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"}


def _op(ids):
    return {"X-User-Id": str(ids["op"]), "X-Role": "utility"}


def test_unread_count_since(ctx):
    c, db, ids = ctx
    c.post(f"/inbox/{ids['bld']}/reply", json={"body": "hello"}, headers=_mgr(ids))
    n = db.query(Message).count()
    r = c.get(f"/inbox/{ids['bld']}/unread?since=0", headers=_mgr(ids))
    assert r.json()["unread"] == n
    r2 = c.get(f"/inbox/{ids['bld']}/unread?since={n}", headers=_mgr(ids))
    assert r2.json()["unread"] == 0


def test_close_thread_blocks_replies(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/close", headers=_op(ids))
    assert r.status_code == 200 and r.json()["closed"] is True
    assert db.query(Thread).one().closed_at is not None
    r2 = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "YES"}, headers=_mgr(ids))
    assert r2.status_code == 409


def test_close_requires_utility(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/close", headers=_mgr(ids))
    assert r.status_code == 403


def test_push_subscribe_stores(ctx):
    c, db, ids = ctx
    sub = {"endpoint": "https://push.example/abc",
           "keys": {"p256dh": "key1", "auth": "auth1"}}
    r = c.post("/push/subscribe", json=sub, headers={"X-User-Id": str(ids["mgr"])})
    assert r.status_code == 200
    assert db.query(PushSubscription).filter_by(user_id=ids["mgr"]).count() == 1


def test_notify_user_skips_without_keys(ctx):
    c, db, ids = ctx
    db.add(PushSubscription(user_id=ids["mgr"], endpoint="e", p256dh="p", auth="a"))
    db.commit()
    result = notify_user(db, ids["mgr"], "T", "B")
    assert result["sent"] == 0 and result["skipped"] >= 1


def test_notify_user_no_subscription(ctx):
    c, db, ids = ctx
    result = notify_user(db, ids["mgr"], "T", "B")
    assert result["sent"] == 0 and "no subscriptions" in result["reason"]


# --- SMS is gone (AC-29, AC-30, AC-31) ---

def test_app_boots():
    from app.main import app

    assert app.title == "CommonWatt"
    paths = set(app.openapi()["paths"])
    assert "/inbox/{building_id}/request-human" in paths
    assert not any(p.startswith("/sms") for p in paths)


def test_no_sms_files_remain():
    for rel in ("app/routes/sms.py", "notify/models.py", "notify/provider.py",
                "scripts/send_test_sms.py"):
        assert not (REPO / rel).exists(), f"{rel} should be deleted"


def test_no_sms_symbols_in_source():
    import subprocess

    dead = "send_sms|OutboundMessage|TwilioProvider|validate_signature|sms_opted_out"
    out = subprocess.run(
        ["grep", "-rnE", dead, "--include=*.py",
         "app", "notify", "db", "server", "agent", "bff"],
        cwd=REPO, capture_output=True, text=True,
    )
    hits = [l for l in out.stdout.splitlines() if "/migrations/" not in l]
    assert hits == [], "dead SMS references:\n" + "\n".join(hits)
