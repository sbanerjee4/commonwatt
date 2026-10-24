"""Unit tests for send_sms, providers, and signature round-trip."""

from __future__ import annotations

import asyncio

import pytest

from db.models import AuditLog, OutboundMessage
from notify.models import send_sms
from notify.provider import SimulatedProvider, TwilioProvider
from notify.validation import validate_signature
from tests.conftest import make_building, make_event, make_user

PARAMS = dict(window="Tue", building_name="B", kw_requested=20,
              kw_enrolled=100, reason="peak", payment=200)


def run(coro):
    return asyncio.run(coro)


def test_send_success_writes_message_and_audit(db):
    bld = make_building(db)
    event = make_event(db, building_ids=[bld.id])
    user = make_user(db, building_id=bld.id, phone="+12025550100")
    provider = SimulatedProvider(db)

    res = run(send_sms(user.id, "building_ask", PARAMS, event.id, db, provider))

    assert res["sent"] is True
    assert res["provider_sid"].startswith("SIM")
    msg = db.query(OutboundMessage).one()
    assert msg.status == "sent"
    assert db.query(AuditLog).filter_by(action="sms_sent").count() == 1


def test_skip_no_phone(db):
    bld = make_building(db)
    event = make_event(db, building_ids=[bld.id])
    user = make_user(db, building_id=bld.id, phone=None)
    provider = SimulatedProvider(db)

    res = run(send_sms(user.id, "building_ask", PARAMS, event.id, db, provider))

    assert res == {"sent": False, "reason_skipped": "no_phone", "provider_sid": None}
    assert db.query(OutboundMessage).count() == 0
    assert db.query(AuditLog).filter_by(action="sms_skipped").count() == 1
    assert provider.sent == []


def test_skip_opted_out(db):
    bld = make_building(db)
    event = make_event(db, building_ids=[bld.id])
    user = make_user(db, building_id=bld.id, phone="+12025550101",
                     sms_opted_out=True)
    provider = SimulatedProvider(db)

    res = run(send_sms(user.id, "building_ask", PARAMS, event.id, db, provider))
    assert res["reason_skipped"] == "opted_out"
    assert provider.sent == []


def test_unknown_template_raises(db):
    user = make_user(db, phone="+12025550102")
    with pytest.raises(ValueError):
        run(send_sms(user.id, "nope", {}, None, db, SimulatedProvider(db)))


def test_building_ask_requires_event_id(db):
    user = make_user(db, phone="+12025550103")
    with pytest.raises(ValueError):
        run(send_sms(user.id, "building_ask", PARAMS, None, db, SimulatedProvider(db)))


def test_operator_alert_needs_no_event(db):
    user = make_user(db, role="utility", phone="+12025550104")
    res = run(send_sms(
        user.id, "operator_backfill",
        dict(decline_count=3, shortfall_mw=12), None, db, SimulatedProvider(db),
    ))
    assert res["sent"] is True


def test_twilio_demo_mode_blocks_unlisted():
    p = TwilioProvider("AC", "tok", "+1555", demo_mode=True,
                       demo_allowlist=["+12025550000"])
    res = run(p.send("+19998887777", "hi"))
    assert res.success is False
    assert "allowlist" in res.error


def test_signature_round_trip():
    token = "my_auth_token"
    url = "https://commonwatt.example.com/sms/inbound"
    body = b"From=%2B12025550100&Body=YES"
    import base64, hashlib, hmac
    from urllib.parse import parse_qsl
    params = sorted(parse_qsl(body.decode(), keep_blank_values=True))
    payload = url + "".join(k + v for k, v in params)
    sig = base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()
    assert validate_signature(body, sig, token, url) is True
    assert validate_signature(body, sig, "wrong", url) is False
