"""Helpers for the in-app chat / handoff routes.

Everything here is planned against main's real schema (``db/models.py``):
String(64) building ids, event membership in ``plan_buildings``, and the
``replies`` / ``call_history`` model — no integer building ids and no
stand-in models from the pre-merge branch.
"""

from __future__ import annotations

from sqlalchemy import select

from db.models import (
    CallHistory,
    Event,
    Message,
    PlanBuilding,
    Thread,
)


def current_plan_building(db, event: Event, building_id: str) -> PlanBuilding | None:
    """The building's row in the event's CURRENT plan version, or None."""
    return db.execute(
        select(PlanBuilding).where(
            PlanBuilding.event_id == event.id,
            PlanBuilding.plan_version == event.current_version,
            PlanBuilding.building_id == building_id,
        )
    ).scalar_one_or_none()


def _thread_for(db, event_id: int, building_id: str) -> Thread | None:
    return db.execute(
        select(Thread).where(
            Thread.event_id == event_id,
            Thread.building_id == building_id,
        )
    ).scalar_one_or_none()


def open_event_for_building(db, building_id: str) -> Event | None:
    """Return the open approved event asking this building, or None.

    "Open" = the event is approved, the building is in its current plan
    version, and the thread (if one exists) is not closed. Newest event wins.
    """
    stmt = (
        select(Event)
        .where(Event.status == "approved")
        .order_by(Event.id.desc())
    )
    for event in db.execute(stmt).scalars():
        if current_plan_building(db, event, building_id) is None:
            continue
        thread = _thread_for(db, event.id, building_id)
        if thread is not None and thread.closed_at is not None:
            continue
        return event
    return None


def get_or_create_thread(db, event_id: int, building_id: str) -> Thread:
    """Return the (event, building) thread, creating it in ``auto`` mode if new.

    Thread creation itself writes no audit row: ``audit_log.user_id`` is
    NOT NULL and a thread may be opened by the system "ask" path, which has no
    acting user. AC-26's required audit rows (agent reply, handoff requested,
    operator takeover, thread closed) are all written by their routes, which
    always have a caller.
    """
    thread = _thread_for(db, event_id, building_id)
    if thread is None:
        thread = Thread(event_id=event_id, building_id=building_id, handoff_mode="auto")
        db.add(thread)
        db.flush()  # assign thread.id
    return thread


def call_history_for(db, event_id: int, building_id: str) -> CallHistory | None:
    """The building's ``call_history`` row for the event (most recent), or None.

    A parsed YES/NO/kW reply attaches to this row via ``Reply.call_id``.
    """
    return db.execute(
        select(CallHistory)
        .where(
            CallHistory.event_id == event_id,
            CallHistory.building_id == building_id,
        )
        .order_by(CallHistory.id.desc())
    ).scalars().first()


def post_message(
    db,
    thread: Thread,
    *,
    sender_role: str,
    body: str,
    sender_user_id: int | None = None,
) -> Message:
    """Append one message to a thread. Does not commit."""
    msg = Message(
        thread_id=thread.id,
        event_id=thread.event_id,
        building_id=thread.building_id,
        sender_role=sender_role,
        sender_user_id=sender_user_id,
        body=body,
    )
    db.add(msg)
    db.flush()
    return msg


def post_system_ask(db, event: Event, building_id: str, body: str) -> Message:
    """Post the opening "ask" into the (event, building) thread as a system
    message, creating the thread in ``auto`` mode if needed.

    Replaces the old SMS-era ask entry point now that SMS is removed. The ask
    is plain in-app text (no SMS length cap); the caller renders it (e.g. via
    ``notify.templates``) and is responsible for the forbidden-word check on
    operator-authored text. Does not commit.
    """
    thread = get_or_create_thread(db, event.id, building_id)
    return post_message(db, thread, sender_role="system", body=body)
