"""Core send_sms orchestration.

send_sms is the single choke point for every outbound message. It enforces
the safety invariants the spec's property tests check:
  - never send to a user with no phone or sms_opted_out=True (skip + audit);
  - never send a building_ask for a building not in the given event;
  - never call the provider when skipping;
  - every send and every skip writes exactly one audit_log row.
"""

from __future__ import annotations

from typing import Optional

from db.models import AuditLog, Event, OutboundMessage, User
from notify.provider import Provider, resolve_provider
from notify.templates import render_template, TEMPLATES

BUILDING_SCOPED = {"building_ask"}


def _audit(db, *, user_id, event_id, action, reason, provider):
    db.add(
        AuditLog(
            user_id=user_id,
            event_id=event_id,
            action=action,
            reason=reason,
            provider=provider,
        )
    )


async def send_sms(
    user_id: int,
    template: str,
    params: dict,
    event_id: Optional[int] = None,
    db_session=None,
    provider: Optional[Provider] = None,
) -> dict:
    """Send one SMS if the user is eligible. See module docstring for invariants.

    Returns {"sent": bool, "reason_skipped": str|None, "provider_sid": str|None}.
    Raises ValueError for an unknown template, a missing required event_id,
    or an unresolvable provider.
    """
    if template not in TEMPLATES:
        raise ValueError(f"unknown template: {template!r}")
    if template in BUILDING_SCOPED and event_id is None:
        raise ValueError(f"template {template!r} requires event_id")
    if db_session is None:
        raise ValueError("db_session is required")
    if provider is None:
        provider = resolve_provider(db_session=db_session)
    if provider is None:
        raise ValueError("no provider resolved")

    user = db_session.get(User, user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")

    def skip(reason: str) -> dict:
        _audit(
            db_session,
            user_id=user_id,
            event_id=event_id,
            action="sms_skipped",
            reason=reason,
            provider=provider.name,
        )
        db_session.commit()
        return {"sent": False, "reason_skipped": reason, "provider_sid": None}

    # Eligibility. In-app delivery needs no phone (it posts to a page);
    # SMS/simulated channels do.
    from notify.provider import InAppProvider
    is_inapp = isinstance(provider, InAppProvider)
    if not is_inapp and not user.phone:
        return skip("no_phone")
    if user.sms_opted_out:
        return skip("opted_out")

    # Access control for building-scoped templates.
    if template in BUILDING_SCOPED:
        event = db_session.get(Event, event_id)
        if event is None:
            return skip("event_not_found")
        if user.building_id is None or user.building_id not in event.building_ids:
            return skip("building_not_in_event")

    # Render (may raise KeyError/ValueError for bad params — caller's bug).
    body = render_template(template, params)

    msg = OutboundMessage(
        user_id=user_id,
        event_id=event_id,
        template=template,
        body=body,
        provider=provider.name,
        status="pending",
    )
    db_session.add(msg)
    db_session.commit()

    # In-app channel posts into the (event, building) thread; give it context.
    from notify.provider import InAppProvider
    if isinstance(provider, InAppProvider):
        provider.bind(event_id=event_id, building_id=user.building_id)

    result = await provider.send(user.phone, body)

    if result.success:
        msg.status = "sent"
        msg.provider_sid = result.provider_sid
        _audit(
            db_session,
            user_id=user_id,
            event_id=event_id,
            action="sms_sent",
            reason=None,
            provider=provider.name,
        )
        db_session.commit()
        return {
            "sent": True,
            "reason_skipped": None,
            "provider_sid": result.provider_sid,
        }

    msg.status = "failed"
    msg.error = result.error
    _audit(
        db_session,
        user_id=user_id,
        event_id=event_id,
        action="sms_failed",
        reason=result.error,
        provider=provider.name,
    )
    db_session.commit()
    return {"sent": False, "reason_skipped": result.error, "provider_sid": None}
