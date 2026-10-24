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
from app.auth import hash_password
from tests.conftest import (
    make_building,
    make_call_history,
    make_event,
    make_user,
    make_utility,
)

REPO = pathlib.Path(__file__).resolve().parents[2]


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
    op = make_user(db, email="op@x.test", role="utility", utility_id=util.id,
                   password_hash=hash_password("pw-op"))
    ev = make_event(db, building_ids=[bld.id])
    make_call_history(db, event=ev, building_id=bld.id)

    from app.main import app
    from app.db import get_db
    import app.routes._chat_agent as agent_mod
    agent_mod.make_session = lambda bid, event_context=None: type(
        "S", (), {"chat": lambda self, b: "ok (source_id: x)"})()

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app), db, dict(bld=bld.id, ev=ev.id, mgr=mgr.id, op=op.id)
    app.dependency_overrides.clear()
    agent_mod.make_session = None
    db.close()


def login_mgr(c):
    assert c.post("/auth/login",
                  json={"email": "m@x.test", "password": "pw-mgr"}).status_code == 200


def login_op(c):
    assert c.post("/auth/login",
                  json={"email": "op@x.test", "password": "pw-op"}).status_code == 200


def test_unread_count_since(ctx):
    c, db, ids = ctx
    login_mgr(c)
    c.post(f"/inbox/{ids['bld']}/reply", json={"body": "hello"})
    n = db.query(Message).count()
    assert c.get(f"/inbox/{ids['bld']}/unread?since=0").json()["unread"] == n
    assert c.get(f"/inbox/{ids['bld']}/unread?since={n}").json()["unread"] == 0


def test_close_blocks_replies(ctx):
    c, db, ids = ctx
    login_op(c)
    r = c.post(f"/inbox/{ids['bld']}/close")
    assert r.status_code == 200 and r.json()["closed"] is True
    assert db.query(Thread).one().closed_at is not None
    login_mgr(c)
    assert c.post(f"/inbox/{ids['bld']}/reply", json={"body": "YES"}).status_code == 409


def test_close_requires_utility(ctx):
    c, db, ids = ctx
    login_mgr(c)
    assert c.post(f"/inbox/{ids['bld']}/close").status_code == 403


def test_push_subscribe_stores(ctx):
    c, db, ids = ctx
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
    login_mgr(c)
    assert c.post("/push/subscribe", json=sub).status_code == 200
    assert db.query(PushSubscription).filter_by(user_id=ids["mgr"]).count() == 1


def test_notify_skips_without_keys(ctx):
    c, db, ids = ctx
    db.add(PushSubscription(user_id=ids["mgr"], endpoint="e", p256dh="p", auth="a"))
    db.commit()
    assert notify_user(db, ids["mgr"], "T", "B")["sent"] == 0


def test_notify_no_subscription(ctx):
    c, db, ids = ctx
    assert "no subscriptions" in notify_user(db, ids["mgr"], "T", "B")["reason"]


def test_app_boots_no_sms():
    from app.main import app
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
    out = subprocess.run(["grep", "-rnE", dead, "--include=*.py",
                          "app", "notify", "db", "server", "agent", "bff"],
                         cwd=REPO, capture_output=True, text=True)
    hits = [l for l in out.stdout.splitlines() if "/migrations/" not in l]
    assert hits == [], "dead SMS refs:\n" + "\n".join(hits)
