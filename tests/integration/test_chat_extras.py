"""Tests for unread count, thread close, and push subscription."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db.models import (Base, Building, Event, EventBuilding, Message,
                       PushSubscription, User, Utility)
from notify.models import send_sms
from notify.provider import InAppProvider
from notify.push import notify_user


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def ctx():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    util = Utility(name="MA")
    bld = Building(name="Elm", kw_enrolled=100, kw_requested=20)
    db.add_all([util, bld]); db.commit()
    mgr = User(email="m@x.test", role="building_manager", building_id=bld.id)
    op = User(email="op@x.test", role="utility", utility_id=util.id)
    ev = Event(utility_id=util.id, status="approved", window_label="Tue")
    db.add_all([mgr, op, ev]); db.commit()
    db.add(EventBuilding(event_id=ev.id, building_id=bld.id)); db.commit()
    from app.main import app
    from app.db import get_db
    def _override():
        yield db
    app.dependency_overrides[get_db] = _override
    yield TestClient(app), db, dict(bld=bld.id, ev=ev.id, mgr=mgr.id, op=op.id)
    app.dependency_overrides.clear(); db.close()


def _ask(db, ids):
    run(send_sms(ids["mgr"], "building_ask",
                 dict(window="Tue", building_name="Elm", kw_requested=20,
                      kw_enrolled=100, reason="peak", payment=200),
                 ids["ev"], db, InAppProvider(db)))


def test_unread_count_since(ctx):
    c, db, ids = ctx
    _ask(db, ids)  # one system message, id 1
    r = c.get(f"/inbox/{ids['bld']}/unread?since=0",
              headers={"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"})
    assert r.json()["unread"] == 1
    r2 = c.get(f"/inbox/{ids['bld']}/unread?since=1",
               headers={"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"})
    assert r2.json()["unread"] == 0


def test_close_thread_blocks_replies(ctx):
    c, db, ids = ctx
    _ask(db, ids)
    r = c.post(f"/inbox/{ids['bld']}/close",
               headers={"X-User-Id": str(ids["op"]), "X-Role": "operator"})
    assert r.status_code == 200 and r.json()["closed"] is True
    # After close, no open event → reply refused.
    r2 = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "YES"},
                headers={"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"})
    assert r2.status_code == 409


def test_close_requires_operator(ctx):
    c, db, ids = ctx
    _ask(db, ids)
    r = c.post(f"/inbox/{ids['bld']}/close",
               headers={"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"})
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
    # No VAPID keys in env → skipped, not crashed.
    result = notify_user(db, ids["mgr"], "T", "B")
    assert result["sent"] == 0 and result["skipped"] >= 1


def test_notify_user_no_subscription(ctx):
    c, db, ids = ctx
    result = notify_user(db, ids["mgr"], "T", "B")
    assert result["sent"] == 0 and "no subscriptions" in result["reason"]
