"""Integration tests for the auth layer: login, me, logout, role gate, expiry."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import COOKIE_NAME, hash_password
from db.models import (Base, Building, Session as SessionRow, User, Utility,
                       Zip, ZipUtility)


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("COMMONWATT_INSECURE_COOKIES", "1")
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)

    db.add(Zip(zip="00001", ej=False))
    util = Utility(id="util-ma", name="MA", source_id="sim:util")
    bld = Building(id="bld-1", zip="00001", address="1 Elm St", enrolled=True)
    db.add_all([util, bld])
    db.commit()
    db.add(ZipUtility(zip="00001", utility_id=util.id, source_id="sim:zu"))
    mgr = User(email="building1@demo", role="building_manager", building_id=bld.id,
               password_hash=hash_password("pw-building"))
    op = User(email="utility@demo", role="utility", utility_id=util.id,
              password_hash=hash_password("pw-utility"))
    db.add_all([mgr, op])
    db.commit()

    from app.main import app
    from app.db import get_db

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app), db, dict(bld=bld.id, util=util.id, mgr=mgr.id, op=op.id)
    app.dependency_overrides.clear()
    db.close()


def test_login_sets_cookie_and_returns_identity(ctx):
    c, db, ids = ctx
    r = c.post("/auth/login", json={"email": "building1@demo", "password": "pw-building"})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "building_manager"
    assert body["buildingId"] == ids["bld"]
    assert body["utilityId"] == ids["util"]  # derived via building -> zip -> zip_utility
    assert COOKIE_NAME in r.cookies


def test_me_requires_cookie(ctx):
    c, db, ids = ctx
    assert c.get("/auth/me").status_code == 401
    c.post("/auth/login", json={"email": "utility@demo", "password": "pw-utility"})
    me = c.get("/auth/me")
    assert me.status_code == 200 and me.json()["role"] == "utility"


def test_wrong_password_is_401(ctx):
    c, db, ids = ctx
    r = c.post("/auth/login", json={"email": "building1@demo", "password": "nope"})
    assert r.status_code == 401
    assert "invalid" in r.json()["detail"].lower()


def test_unknown_email_is_401_same_message(ctx):
    c, db, ids = ctx
    r = c.post("/auth/login", json={"email": "ghost@demo", "password": "whatever"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid email or password"  # no account enumeration


def test_logout_clears_session(ctx):
    c, db, ids = ctx
    c.post("/auth/login", json={"email": "utility@demo", "password": "pw-utility"})
    assert c.get("/auth/me").status_code == 200
    assert c.post("/auth/logout").status_code == 200
    assert db.query(SessionRow).count() == 0
    assert c.get("/auth/me").status_code == 401


def test_expired_session_is_rejected_and_pruned(ctx):
    c, db, ids = ctx
    c.post("/auth/login", json={"email": "utility@demo", "password": "pw-utility"})
    row = db.execute(select(SessionRow)).scalar_one()
    row.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    db.commit()
    assert c.get("/auth/me").status_code == 401
    assert db.query(SessionRow).count() == 0  # expired row self-prunes


def test_operator_route_rejects_building_manager(ctx):
    c, db, ids = ctx
    c.post("/auth/login", json={"email": "building1@demo", "password": "pw-building"})
    # close is utility-only
    r = c.post(f"/inbox/{ids['bld']}/close")
    assert r.status_code == 403
