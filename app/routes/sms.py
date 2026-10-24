"""Inbound SMS webhook: POST /sms/inbound.

Twilio POSTs a reply here. We validate the signature, find the sender,
parse the body, and act: opt out/in, record a YES/NO/kW reply against the
building's open event, or answer that we did not understand. Every branch
writes an audit_log row and returns TwiML. Only a bad signature returns
non-200 (403); everything else is 200 so Twilio does not retry.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.config import twilio_auth_token, webhook_url
from app.db import get_db
from db.models import AuditLog, Event, Reply, User
from notify.validation import parse_reply_body, validate_signature

router = APIRouter()

# Reply bodies (safety: no cut / shut off / curtail / disconnect).
MSG_NOT_REGISTERED = "This number isn't registered with CommonWatt."
MSG_OPTED_OUT = "You've opted out. Reply START to opt back in."
MSG_OPTED_IN = "You're opted back in. Reply STOP to opt out anytime."
MSG_GOT_IT = "Got it. Your response has been recorded."
MSG_NO_EVENT = "No active event for your building."
MSG_UNRECOGNIZED = "Didn't catch that. Reply YES, NO, or a number of kW."


def _twiml(message: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{message}</Message></Response>"
    )


def _xml(message: str, status: int = 200) -> Response:
    return Response(content=_twiml(message), media_type="application/xml",
                    status_code=status)


def _audit(db, *, user_id, event_id, action, reason):
    db.add(AuditLog(user_id=user_id, event_id=event_id, action=action,
                    reason=reason, provider="twilio"))


@router.post("/sms/inbound", tags=["sms"])
async def inbound_webhook(request: Request, db=Depends(get_db)) -> Response:
    raw = await request.body()
    signature = request.headers.get("X-Twilio-Signature", "")

    if not validate_signature(raw, signature, twilio_auth_token(), webhook_url()):
        _audit(db, user_id=None, event_id=None,
               action="sms_webhook_invalid_signature", reason="bad signature")
        db.commit()
        # 403: the only non-200. A tampered request is not retried.
        return _xml("Forbidden", status=403)

    form = await request.form()
    from_number = (form.get("From") or "").strip()
    body = form.get("Body") or ""

    user = db.execute(
        select(User).where(User.phone == from_number)
    ).scalar_one_or_none()

    if user is None:
        _audit(db, user_id=None, event_id=None,
               action="sms_unregistered_sender", reason=from_number)
        db.commit()
        return _xml(MSG_NOT_REGISTERED)

    parsed = parse_reply_body(body)

    if parsed == "STOP":
        user.sms_opted_out = True
        _audit(db, user_id=user.id, event_id=None,
               action="sms_opted_out", reason=None)
        db.commit()
        return _xml(MSG_OPTED_OUT)

    if parsed == "START":
        user.sms_opted_out = False
        _audit(db, user_id=user.id, event_id=None,
               action="sms_opted_in", reason=None)
        db.commit()
        return _xml(MSG_OPTED_IN)

    if parsed is None:
        _audit(db, user_id=user.id, event_id=None,
               action="sms_unrecognized_body", reason=body[:120])
        db.commit()
        return _xml(MSG_UNRECOGNIZED)

    # YES / NO / positive int → record against the building's open event.
    if user.building_id is None:
        _audit(db, user_id=user.id, event_id=None,
               action="sms_no_active_event", reason="user has no building")
        db.commit()
        return _xml(MSG_NO_EVENT)

    event = _open_event_for_building(db, user.building_id)
    if event is None:
        _audit(db, user_id=user.id, event_id=None,
               action="sms_no_active_event", reason=None)
        db.commit()
        return _xml(MSG_NO_EVENT)

    if isinstance(parsed, int):
        kind, kw = "counter", parsed
    else:
        kind, kw = parsed, None  # "yes" | "no"

    db.add(Reply(building_id=user.building_id, event_id=event.id,
                 kind=kind, kw=kw))
    _audit(db, user_id=user.id, event_id=event.id,
           action="sms_received", reason=kind)
    db.commit()
    return _xml(MSG_GOT_IT)


def _open_event_for_building(db, building_id: int):
    """Most recent approved, not-yet-closed event asking this building."""
    stmt = (
        select(Event)
        .where(Event.status == "approved", Event.closed_at.is_(None))
        .order_by(Event.id.desc())
    )
    for event in db.execute(stmt).scalars():
        if building_id in event.building_ids:
            return event
    return None
