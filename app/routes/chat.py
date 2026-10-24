"""In-app chat routes for the event conversation.

Free alternative to SMS. The system posts a building_ask into a thread keyed
by (event, building); the building manager replies on their own page; an
operator can post free text to take over. Reuses parse_reply_body so a reply
that parses (YES/NO/kW) also writes a structured `replies` row for backfill.

Polling model: the SPA calls GET /inbox/{building_id} every few seconds.

Identity for this demo is passed with headers the BFF would normally set from
the session: X-User-Id and X-Role. A building session may only read/post to its
own building; an operator may post to any thread for the demo utility.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select

from app.db import get_db
from db.models import AuditLog, Building, Event, Message, Reply, User
from notify.validation import parse_reply_body

router = APIRouter()


def _require_building_access(role: str, user: User, building_id: int) -> None:
    """A building session may only touch its own building; operators may touch any."""
    if role == "operator":
        return
    if role == "building_manager" and user is not None and user.building_id == building_id:
        return
    raise HTTPException(status_code=403, detail="not authorized for this building")


def _load_caller(db, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    return db.get(User, user_id)


@router.get("/inbox/{building_id}", tags=["chat"])
async def get_thread(
    building_id: int,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="building_manager"),
):
    caller = _load_caller(db, x_user_id)
    _require_building_access(x_role, caller, building_id)

    rows = db.execute(
        select(Message)
        .where(Message.building_id == building_id)
        .order_by(Message.id.asc())
    ).scalars().all()
    return {
        "building_id": building_id,
        "messages": [
            {
                "id": m.id,
                "event_id": m.event_id,
                "sender_role": m.sender_role,
                "sender_user_id": m.sender_user_id,
                "body": m.body,
                "created_at": m.created_at.isoformat(),
            }
            for m in rows
        ],
    }


@router.get("/inbox/{building_id}/unread", tags=["chat"])
async def unread_count(
    building_id: int,
    since: int = 0,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="building_manager"),
):
    """Count messages in this building's thread with id > `since`.

    The client tracks the highest message id it has shown and passes it as
    `since`; the result drives the unread badge. Stateless — no per-user read
    marker table for the demo.
    """
    caller = _load_caller(db, x_user_id)
    _require_building_access(x_role, caller, building_id)
    count = db.execute(
        select(func.count())
        .select_from(Message)
        .where(Message.building_id == building_id, Message.id > since)
    ).scalar_one()
    return {"building_id": building_id, "since": since, "unread": count}


@router.post("/inbox/{building_id}/close", tags=["chat"])
async def close_thread(
    building_id: int,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="operator"),
):
    """Operator closes the building's open event thread. After this, replies
    are refused (no active event) and the ask is considered settled."""
    if x_role != "operator":
        raise HTTPException(status_code=403, detail="operators only")
    event = _open_event_for_building(db, building_id)
    if event is None:
        raise HTTPException(status_code=409, detail="no open event for building")
    from datetime import datetime, timezone
    event.closed_at = datetime.now(timezone.utc)
    db.add(AuditLog(user_id=x_user_id, event_id=event.id,
                    action="chat_thread_closed", reason=None, provider="inapp"))
    db.commit()
    return {"ok": True, "event_id": event.id, "closed": True}


def _open_event_for_building(db, building_id: int):
    stmt = (
        select(Event)
        .where(Event.status == "approved", Event.closed_at.is_(None))
        .order_by(Event.id.desc())
    )
    for event in db.execute(stmt).scalars():
        if building_id in event.building_ids:
            return event
    return None


@router.post("/inbox/{building_id}/reply", tags=["chat"])
async def building_reply(
    building_id: int,
    request: Request,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="building_manager"),
):
    """Building manager replies in the thread. Always recorded as a message;
    if it parses to YES/NO/kW it also writes a structured `replies` row."""
    caller = _load_caller(db, x_user_id)
    _require_building_access(x_role, caller, building_id)

    payload = await request.json()
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="empty body")

    event = _open_event_for_building(db, building_id)
    if event is None:
        raise HTTPException(status_code=409, detail="no active event for building")

    db.add(Message(event_id=event.id, building_id=building_id,
                   sender_role="building_manager",
                   sender_user_id=x_user_id, body=body))

    parsed = parse_reply_body(body)
    recorded = None
    if parsed in ("yes", "no"):
        db.add(Reply(building_id=building_id, event_id=event.id, kind=parsed))
        recorded = {"kind": parsed, "kw": None}
    elif isinstance(parsed, int):
        db.add(Reply(building_id=building_id, event_id=event.id,
                     kind="counter", kw=parsed))
        recorded = {"kind": "counter", "kw": parsed}

    db.add(AuditLog(user_id=x_user_id, event_id=event.id,
                    action="chat_building_reply",
                    reason=(recorded["kind"] if recorded else "free_text"),
                    provider="inapp"))
    db.commit()
    return {"ok": True, "parsed_reply": recorded}


@router.post("/inbox/{building_id}/operator-message", tags=["chat"])
async def operator_message(
    building_id: int,
    request: Request,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="operator"),
):
    """Operator posts FREE TEXT into the thread to take over. No template,
    no length limit — this is in-app, not SMS. Still safety-checked for
    forbidden language, since it is user-facing."""
    if x_role != "operator":
        raise HTTPException(status_code=403, detail="operators only")

    payload = await request.json()
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="empty body")

    # Reuse the template safety check on operator free text.
    from notify.templates import _contains_forbidden
    forbidden = _contains_forbidden(body)
    if forbidden is not None:
        raise HTTPException(status_code=422,
                            detail=f"message contains forbidden word {forbidden!r}")

    event = _open_event_for_building(db, building_id)
    if event is None:
        raise HTTPException(status_code=409, detail="no active event for building")

    db.add(Message(event_id=event.id, building_id=building_id,
                   sender_role="operator", sender_user_id=x_user_id, body=body))
    db.add(AuditLog(user_id=x_user_id, event_id=event.id,
                    action="chat_operator_message", reason="takeover",
                    provider="inapp"))
    db.commit()

    # Nudge the building manager (free; no-op without push subscription/keys).
    mgr = db.execute(
        select(User).where(User.building_id == building_id,
                           User.role == "building_manager")
    ).scalars().first()
    if mgr is not None:
        from notify.push import notify_user
        notify_user(db, mgr.id, "CommonWatt", "Your operator sent a message.")
    return {"ok": True}
