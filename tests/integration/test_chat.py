"""Integration tests for the in-app chat channel."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db.models import (Base, Building, Event, Message, Reply,
                       User, Utility, Zip)
from db.models import PlanBuilding as EventBuilding
from notify.models import send_sms
from notify.provider import InAppProvider


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def ctx():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)

    db.add(Zip(zip="00001", ej=False))
    util = Utility(id="util-ma", name="MA", source_id="sim:util-ma")
    bld = Building(id="bld-elm", zip="00001", address="1 Elm St",
                   enrolled=True, enrolled_capacity_kw=100, offered_capacity_kw=20)
    db.add_all([util, bld])
    db.commit()
    mgr = User(email="m@x.test", role="building_manager", building_id=bld.id,
               password_hash="x")
    op = User(email="op@x.test", role="utility", utility_id=util.id,
              password_hash="x")
    import datetime as _dt
    _now = _dt.datetime(2026, 7, 1, 14, 0, tzinfo=_dt.timezone.utc)
    ev = Event(utility_id=util.id, status="approved", window_label="Tue",
               window_start=_now, window_end=_now + _dt.timedelta(hours=4),
               target_mw=150, cap_pct=25, current_version=1)
    db.add_all([mgr, op, ev])
    db.commit()
    db.add(EventBuilding(event_id=ev.id, plan_version=ev.current_version,
                         building_id=bld.id, kw_requested=20))
    db.commit()

    from app.main import app
    from app.db import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app), db, dict(bld=bld.id, ev=ev.id, mgr=mgr.id, op=op.id)
    app.dependency_overrides.clear()
    db.close()


def test_system_ask_posts_into_thread(ctx):
    c, db, ids = ctx
    provider = InAppProvider(db)
    res = run(send_sms(
        user_id=ids["mgr"], template="building_ask",
        params=dict(window="Tue", building_name="Elm", kw_requested=20,
                    kw_enrolled=100, reason="peak", payment=200),
        event_id=ids["ev"], db_session=db, provider=provider,
    ))
    assert res["sent"] is True
    msgs = db.query(Message).all()
    assert len(msgs) == 1 and msgs[0].sender_role == "system"


def test_manager_yes_writes_message_and_reply(ctx):
    c, db, ids = ctx
    # Seed the system ask first.
    run(send_sms(ids["mgr"], "building_ask",
                 dict(window="Tue", building_name="Elm", kw_requested=20,
                      kw_enrolled=100, reason="peak", payment=200),
                 ids["ev"], db, InAppProvider(db)))

    r = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "YES"},
               headers={"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"})
    assert r.status_code == 200
    assert r.json()["parsed_reply"]["kind"] == "yes"
    assert db.query(Reply).count() == 1
    assert db.query(Message).filter_by(sender_role="building_manager").count() == 1


def test_manager_kw_counter(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "40 kW"},
               headers={"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"})
    assert r.status_code == 200
    reply = db.query(Reply).one()
    assert reply.kind == "counter" and reply.kw == 40


def test_manager_free_text_is_message_only(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "can we talk?"},
               headers={"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"})
    assert r.status_code == 200
    assert r.json()["parsed_reply"] is None
    assert db.query(Reply).count() == 0
    assert db.query(Message).count() == 1


def test_operator_takeover_free_text(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/operator-message",
               json={"body": "Hi, operator here — happy to adjust your ask."},
               headers={"X-User-Id": str(ids["op"]), "X-Role": "operator"})
    assert r.status_code == 200
    assert db.query(Message).filter_by(sender_role="operator").count() == 1


def test_operator_forbidden_word_rejected(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/operator-message",
               json={"body": "We will disconnect your power."},
               headers={"X-User-Id": str(ids["op"]), "X-Role": "operator"})
    assert r.status_code == 422


def test_building_cannot_read_other_building(ctx):
    c, db, ids = ctx
    r = c.get(f"/inbox/{ids['bld'] + 999}",
              headers={"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"})
    assert r.status_code == 403
