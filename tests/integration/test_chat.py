"""Integration tests for the in-app chat + automated-agent + handoff layer."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db.models import Base, Message, Reply, Thread
from tests.conftest import (
    make_building,
    make_call_history,
    make_event,
    make_user,
    make_utility,
)

SOURCED_REPLY = "Your building could reduce about 20 kW (source_id: conn_solutions)."


class _FakeSession:
    """Stand-in for agent.chat.ChatSession — no Bedrock, no network."""

    def __init__(self, reply=SOURCED_REPLY, raises=False):
        self._reply = reply
        self._raises = raises

    def chat(self, body):
        if self._raises:
            raise RuntimeError("bedrock unavailable")
        return self._reply


def _install_agent(monkeypatch, *, reply=SOURCED_REPLY, raises=False):
    import app.routes._chat_agent as agent_mod

    monkeypatch.setattr(
        agent_mod, "make_session",
        lambda bid, event_context=None: _FakeSession(reply=reply, raises=raises),
        raising=False,
    )


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

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app), db, dict(bld=bld.id, ev=ev.id, mgr=mgr.id, op=op.id)
    app.dependency_overrides.clear()
    db.close()


def _mgr_headers(ids):
    return {"X-User-Id": str(ids["mgr"]), "X-Role": "building_manager"}


def _op_headers(ids):
    return {"X-User-Id": str(ids["op"]), "X-Role": "utility"}


# --- auto agent reply (AC-6, AC-7, AC-9) ---

def test_manager_message_gets_agent_reply(ctx, monkeypatch):
    c, db, ids = ctx
    _install_agent(monkeypatch)
    r = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "how much?"},
               headers=_mgr_headers(ids))
    assert r.status_code == 200 and r.json()["agent_replied"] is True
    roles = [m.sender_role for m in db.query(Message).order_by(Message.id).all()]
    assert "building_manager" in roles and "agent" in roles


# --- structured decision + conversational reply (AC-8) ---

def test_yes_writes_reply_and_agent_message(ctx, monkeypatch):
    c, db, ids = ctx
    _install_agent(monkeypatch)
    r = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "YES"},
               headers=_mgr_headers(ids))
    assert r.json()["parsed_reply"]["kind"] == "yes"
    assert db.query(Reply).count() == 1
    assert db.query(Message).filter_by(sender_role="agent").count() == 1


def test_kw_counter_is_offer(ctx, monkeypatch):
    c, db, ids = ctx
    _install_agent(monkeypatch)
    c.post(f"/inbox/{ids['bld']}/reply", json={"body": "40 kW"},
           headers=_mgr_headers(ids))
    reply = db.query(Reply).one()
    assert reply.kind == "offer" and reply.offer_kw == 40


# --- handoff flip + silence (AC-18, AC-20, AC-4) ---

def test_request_human_flips_and_is_idempotent(ctx, monkeypatch):
    c, db, ids = ctx
    _install_agent(monkeypatch)
    r = c.post(f"/inbox/{ids['bld']}/request-human", headers=_mgr_headers(ids))
    assert r.json()["handoff_mode"] == "human"
    thread = db.query(Thread).one()
    assert thread.handoff_mode == "human"
    sys_count = db.query(Message).filter_by(sender_role="system").count()
    # idempotent second call
    r2 = c.post(f"/inbox/{ids['bld']}/request-human", headers=_mgr_headers(ids))
    assert r2.json()["handoff_mode"] == "human"
    assert db.query(Message).filter_by(sender_role="system").count() == sys_count


def test_agent_silent_in_human_mode(ctx, monkeypatch):
    c, db, ids = ctx
    _install_agent(monkeypatch)
    c.post(f"/inbox/{ids['bld']}/request-human", headers=_mgr_headers(ids))
    before = db.query(Message).filter_by(sender_role="agent").count()
    r = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "still there?"},
               headers=_mgr_headers(ids))
    assert r.json()["agent_replied"] is False
    assert db.query(Message).filter_by(sender_role="agent").count() == before


# --- operator takeover (AC-21) + banned word (AC-15) ---

def test_operator_takeover_free_text(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/operator-message",
               json={"body": "Hi, operator here — happy to adjust your ask."},
               headers=_op_headers(ids))
    assert r.status_code == 200
    assert db.query(Message).filter_by(sender_role="operator").count() == 1
    assert db.query(Message).filter_by(sender_role="agent").count() == 0


def test_operator_forbidden_word_rejected(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/operator-message",
               json={"body": "We will disconnect your power."},
               headers=_op_headers(ids))
    assert r.status_code == 422
    assert db.query(Message).filter_by(sender_role="operator").count() == 0


# --- agent fallback: banned word (AC-16) and bedrock error (AC-10) ---

def test_agent_banned_word_suppressed(ctx, monkeypatch):
    c, db, ids = ctx
    _install_agent(monkeypatch, reply="We will disconnect you.")
    c.post(f"/inbox/{ids['bld']}/reply", json={"body": "hi"}, headers=_mgr_headers(ids))
    agent_msgs = db.query(Message).filter_by(sender_role="agent").all()
    assert len(agent_msgs) == 1
    assert "disconnect" not in agent_msgs[0].body.lower()
    assert db.query(Thread).one().needs_human is True


def test_agent_bedrock_error_fallback(ctx, monkeypatch):
    c, db, ids = ctx
    _install_agent(monkeypatch, raises=True)
    r = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "hi"},
               headers=_mgr_headers(ids))
    assert r.status_code == 200
    assert db.query(Message).filter_by(sender_role="building_manager").count() == 1
    assert db.query(Message).filter_by(sender_role="agent").count() == 1
    assert db.query(Thread).one().needs_human is True


# --- access + lifecycle (AC-23, AC-24, AC-25) ---

def test_other_building_read_forbidden(ctx):
    c, db, ids = ctx
    r = c.get(f"/inbox/{ids['bld']}-other", headers=_mgr_headers(ids))
    assert r.status_code == 403


def test_request_human_by_utility_forbidden(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/request-human", headers=_op_headers(ids))
    assert r.status_code == 403


def test_operator_message_by_manager_forbidden(ctx):
    c, db, ids = ctx
    r = c.post(f"/inbox/{ids['bld']}/operator-message", json={"body": "hi"},
               headers=_mgr_headers(ids))
    assert r.status_code == 403


def test_reply_with_no_open_event_409(ctx, monkeypatch):
    c, db, ids = ctx
    _install_agent(monkeypatch)
    c.post(f"/inbox/{ids['bld']}/close", headers=_op_headers(ids))
    r = c.post(f"/inbox/{ids['bld']}/reply", json={"body": "YES"},
               headers=_mgr_headers(ids))
    assert r.status_code == 409


# --- provenance (AC-11) ---

def test_chat_tools_are_sourced_only():
    # The agent must be wired only to the tool-grounded building_info +
    # estimate_savings. Prefer the real import; fall back to reading the source
    # when the environment's `mcp/` package shadow blocks server.tools (a known
    # pre-existing repo issue unrelated to this feature).
    try:
        from agent.chat import CHAT_TOOLS

        names = {t["name"] for t in CHAT_TOOLS}
    except Exception:
        import pathlib
        import re

        src = pathlib.Path("agent/chat.py").read_text()
        block = src.split("CHAT_TOOLS", 1)[1].split("TOOL_FN_MAP", 1)[0]
        names = set(re.findall(r'"name":\s*"([^"]+)"', block))
    assert names == {"building_info", "estimate_savings"}
