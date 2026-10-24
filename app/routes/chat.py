"""In-app event chat with an automated agent + human handoff.

When an approved event asks a building to reduce load, a thread keyed by
``(event, building)`` carries the conversation. By default it is in ``auto``
mode and an automated agent (``agent/chat.py`` ChatSession, Bedrock) answers
the building manager from tool-grounded data. The manager can press "Contact a
human rep" (``request-human``), which flips the thread to ``human`` mode,
alerts the operator, and silences the agent; from then a ``utility`` operator
posts free text.

Polling model: the SPA calls ``GET /inbox/{building_id}`` every few seconds.

Demo identity is passed with ``X-User-Id`` / ``X-Role`` headers
(``building_manager`` | ``utility``). A building session may only touch its own
building; a ``utility`` user may read any thread and post operator messages.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select

from app.db import get_db
from app.routes._chat_agent import agent_reply_or_fallback, build_event_context
from app.routes._chat_helpers import (
    call_history_for,
    get_or_create_thread,
    open_event_for_building,
    post_message,
    thread_for,
)
from db.models import AuditLog, Message, Reply, User
from notify.templates import _contains_forbidden
from notify.validation import parse_reply_body

router = APIRouter()


def _load_caller(db, user_id: int | None) -> User | None:
    return db.get(User, user_id) if user_id is not None else None


def _require_building_access(role: str, user: User | None, building_id: str) -> None:
    """A building session may only touch its own building; utility may touch any."""
    if role == "utility":
        return
    if role == "building_manager" and user is not None and user.building_id == building_id:
        return
    raise HTTPException(status_code=403, detail="not authorized for this building")


@router.get("/inbox/{building_id}", tags=["chat"])
async def get_thread(
    building_id: str,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="building_manager"),
):
    caller = _load_caller(db, x_user_id)
    _require_building_access(x_role, caller, building_id)

    rows = db.execute(
        select(Message).where(Message.building_id == building_id).order_by(Message.id.asc())
    ).scalars().all()
    event = open_event_for_building(db, building_id)
    thread = thread_for(db, event.id, building_id) if event is not None else None
    return {
        "building_id": building_id,
        "event_id": event.id if event else None,
        "handoff_mode": thread.handoff_mode if thread else "auto",
        "needs_human": bool(thread.needs_human) if thread else False,
        "messages": [
            {
                "id": m.id,
                "event_id": m.event_id,
                "sender_role": m.sender_role,
                "sender_user_id": m.sender_user_id,
                "body": m.body,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ],
    }


@router.get("/inbox/{building_id}/unread", tags=["chat"])
async def unread_count(
    building_id: str,
    since: int = 0,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="building_manager"),
):
    caller = _load_caller(db, x_user_id)
    _require_building_access(x_role, caller, building_id)
    count = db.execute(
        select(func.count())
        .select_from(Message)
        .where(Message.building_id == building_id, Message.id > since)
    ).scalar_one()
    return {"building_id": building_id, "since": since, "unread": count}


@router.post("/inbox/{building_id}/reply", tags=["chat"])
async def building_reply(
    building_id: str,
    request: Request,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="building_manager"),
):
    caller = _load_caller(db, x_user_id)
    _require_building_access(x_role, caller, building_id)

    payload = await request.json()
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="empty body")

    event = open_event_for_building(db, building_id)
    if event is None:
        raise HTTPException(status_code=409, detail="no active event for building")

    thread = get_or_create_thread(db, event.id, building_id)
    post_message(db, event_id=event.id, building_id=building_id,
                 sender_role="building_manager", sender_user_id=x_user_id, body=body)

    # Structured decision -> replies row tied to the building's call_history.
    parsed = parse_reply_body(body)
    recorded = None
    call = call_history_for(db, event.id, building_id)
    if call is not None and parsed in ("yes", "no"):
        db.add(Reply(call_id=call.id, building_id=building_id, kind=parsed))
        recorded = {"kind": parsed, "kw": None}
    elif call is not None and isinstance(parsed, int):
        db.add(Reply(call_id=call.id, building_id=building_id, kind="offer", offer_kw=parsed))
        recorded = {"kind": "offer", "kw": parsed}

    db.add(AuditLog(user_id=x_user_id, event_id=event.id, building_id=building_id,
                    action="chat_building_reply",
                    detail=(recorded["kind"] if recorded else "free_text"),
                    provider="inapp"))

    agent_replied = False
    if thread.handoff_mode == "auto":
        ctx = build_event_context(db, event, building_id)
        reply_text, fell_back = agent_reply_or_fallback(db, thread, ctx, body)
        post_message(db, event_id=event.id, building_id=building_id,
                     sender_role="agent", body=reply_text)
        agent_replied = True
        if fell_back:
            thread.needs_human = True
        db.add(AuditLog(user_id=x_user_id, event_id=event.id, building_id=building_id,
                        action="chat_agent_reply",
                        detail=("fallback" if fell_back else "agent"), provider="inapp"))

    db.commit()
    return {"ok": True, "parsed_reply": recorded,
            "agent_replied": agent_replied, "handoff_mode": thread.handoff_mode}


@router.post("/inbox/{building_id}/request-human", tags=["chat"])
async def request_human(
    building_id: str,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="building_manager"),
):
    caller = _load_caller(db, x_user_id)
    if not (x_role == "building_manager" and caller is not None
            and caller.building_id == building_id):
        raise HTTPException(status_code=403, detail="owning building manager only")

    event = open_event_for_building(db, building_id)
    if event is None:
        raise HTTPException(status_code=409, detail="no active event for building")

    thread = get_or_create_thread(db, event.id, building_id)
    if thread.handoff_mode == "human":
        db.commit()
        return {"ok": True, "handoff_mode": "human"}

    thread.handoff_mode = "human"
    post_message(db, event_id=event.id, building_id=building_id, sender_role="system",
                 body="A human representative has been requested and will join shortly.")
    db.add(AuditLog(user_id=x_user_id, event_id=event.id, building_id=building_id,
                    action="chat_handoff_requested",
                    detail="manager requested a human", provider="inapp"))
    db.commit()

    from notify.push import notify_user
    for op in db.execute(select(User).where(User.role == "utility")).scalars():
        notify_user(db, op.id, "CommonWatt", f"Building {building_id} requested a human rep.")
    return {"ok": True, "handoff_mode": "human"}


@router.post("/inbox/{building_id}/operator-message", tags=["chat"])
async def operator_message(
    building_id: str,
    request: Request,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="utility"),
):
    if x_role != "utility":
        raise HTTPException(status_code=403, detail="utility operators only")

    payload = await request.json()
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="empty body")

    forbidden = _contains_forbidden(body)
    if forbidden is not None:
        raise HTTPException(status_code=422,
                            detail=f"message contains forbidden word {forbidden!r}")

    event = open_event_for_building(db, building_id)
    if event is None:
        raise HTTPException(status_code=409, detail="no active event for building")

    thread = get_or_create_thread(db, event.id, building_id)
    post_message(db, event_id=event.id, building_id=building_id,
                 sender_role="operator", sender_user_id=x_user_id, body=body)
    thread.needs_human = False
    db.add(AuditLog(user_id=x_user_id, event_id=event.id, building_id=building_id,
                    action="chat_operator_message", detail="takeover", provider="inapp"))
    db.commit()

    mgr = db.execute(
        select(User).where(User.building_id == building_id,
                           User.role == "building_manager")
    ).scalars().first()
    if mgr is not None:
        from notify.push import notify_user
        notify_user(db, mgr.id, "CommonWatt", "Your operator sent a message.")
    return {"ok": True}


@router.post("/inbox/{building_id}/close", tags=["chat"])
async def close_thread(
    building_id: str,
    db=Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="utility"),
):
    if x_role != "utility":
        raise HTTPException(status_code=403, detail="utility operators only")
    event = open_event_for_building(db, building_id)
    if event is None:
        raise HTTPException(status_code=409, detail="no open event for building")
    thread = get_or_create_thread(db, event.id, building_id)
    thread.closed_at = datetime.now(timezone.utc)
    db.add(AuditLog(user_id=x_user_id, event_id=event.id, building_id=building_id,
                    action="chat_thread_closed", detail=None, provider="inapp"))
    db.commit()
    return {"ok": True, "event_id": event.id, "closed": True}
