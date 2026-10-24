"""Integration tests for POST /sms/inbound."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db.models import Base, Building, EventBuilding, Reply, User, Utility, Event

AUTH_TOKEN = "test_token"
URL = "https://commonwatt.example.com/sms/inbound"


@pytest.fixture
def client(monkeypatch):
    os.environ["TWILIO_AUTH_TOKEN"] = AUTH_TOKEN
    os.environ["SMS_WEBHOOK_URL"] = URL

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)

    # Seed: utility, building, manager with a phone, an approved open event.
    util = Utility(name="MA")
    bld = Building(name="Elm", kw_enrolled=100, kw_requested=20)
    session.add_all([util, bld])
    session.commit()
    mgr = User(email="m@x.test", role="building_manager",
               building_id=bld.id, phone="+12025550100")
    session.add(mgr)
    ev = Event(utility_id=util.id, status="approved", window_label="Tue")
    session.add(ev)
    session.commit()
    session.add(EventBuilding(event_id=ev.id, building_id=bld.id))
    session.commit()

    from app.main import app
    from app.db import get_db

    def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db

    yield TestClient(app), session
    app.dependency_overrides.clear()
    session.close()


def _sign(params: dict) -> tuple[bytes, str]:
    body = urlencode(params).encode()
    ordered = sorted(params.items())
    payload = URL + "".join(k + v for k, v in ordered)
    sig = base64.b64encode(
        hmac.new(AUTH_TOKEN.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()
    return body, sig


def _post(c, params, sign=True):
    body, sig = _sign(params)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if sign:
        headers["X-Twilio-Signature"] = sig
    else:
        headers["X-Twilio-Signature"] = "wrong"
    return c.post("/sms/inbound", content=body, headers=headers)


def test_invalid_signature_403(client):
    c, _ = client
    r = _post(c, {"From": "+12025550100", "Body": "YES"}, sign=False)
    assert r.status_code == 403


def test_yes_writes_reply(client):
    c, db = client
    r = _post(c, {"From": "+12025550100", "Body": "YES"})
    assert r.status_code == 200
    assert "Got it" in r.text
    reply = db.query(Reply).one()
    assert reply.kind == "yes"


def test_kw_counter_writes_reply(client):
    c, db = client
    r = _post(c, {"From": "+12025550100", "Body": "40 kW"})
    assert r.status_code == 200
    reply = db.query(Reply).one()
    assert reply.kind == "counter" and reply.kw == 40


def test_unregistered_number(client):
    c, _ = client
    r = _post(c, {"From": "+19998887777", "Body": "YES"})
    assert r.status_code == 200
    assert "isn't registered" in r.text


def test_stop_opts_out(client):
    c, db = client
    r = _post(c, {"From": "+12025550100", "Body": "STOP"})
    assert r.status_code == 200
    assert db.query(User).filter_by(phone="+12025550100").one().sms_opted_out is True


def test_start_opts_in(client):
    c, db = client
    db.query(User).filter_by(phone="+12025550100").one().sms_opted_out = True
    db.commit()
    r = _post(c, {"From": "+12025550100", "Body": "START"})
    assert db.query(User).filter_by(phone="+12025550100").one().sms_opted_out is False


def test_unrecognized_body(client):
    c, _ = client
    r = _post(c, {"From": "+12025550100", "Body": "maybe later"})
    assert r.status_code == 200
    assert "Didn't catch that" in r.text
