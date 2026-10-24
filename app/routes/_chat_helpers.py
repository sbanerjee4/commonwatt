"""Helpers for the in-app chat / handoff routes.

Planned against the merged real schema (``db/models.py``): String(64) building
ids, event membership in ``plan_buildings``, the ``replies`` / ``call_history``
model, messages keyed by ``(event_id, building_id)`` (no ``thread_id``), and a
separate ``threads`` row that carries only the handoff state for that pair.
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


def thread_for(db, event_id: int, building_id: str) -> Thread | None:
    return db.execute(
        select(Thread).where(
            Thread.event_id == event_id, Thread.building_id == building_id
        )
    ).scalar_one_or_none()


def open_event_for_building(db, building_id: str) -> Event | None:
    """Return the open approved event asking this building, or None.

    "Open" = approved, the building is in its current plan version, and the
    thread (if one exists) is not closed. Newest event wins.
    """
    stmt = select(Event).where(Event.status == "approved").order_by(Event.id.desc())
    for event in db.execute(stmt).scalars():
        if current_plan_building(db, event, building_id) is None:
            continue
        thread = thread_for(db, event.id, building_id)
        if thread is not None and thread.closed_at is not None:
            continue
        return event
    return None


def get_or_create_thread(db, event_id: int, building_id: str) -> Thread:
    """Return the (event, building) thread, creating it in ``auto`` mode if new."""
    thread = thread_for(db, event_id, building_id)
    if thread is None:
        thread = Thread(event_id=event_id, building_id=building_id, handoff_mode="auto")
        db.add(thread)
        db.flush()
    return thread


def call_history_for(db, event_id: int, building_id: str) -> CallHistory | None:
    """The building's most recent ``call_history`` row for the event, or None."""
    return db.execute(
        select(CallHistory)
        .where(CallHistory.event_id == event_id, CallHistory.building_id == building_id)
        .order_by(CallHistory.id.desc())
    ).scalars().first()


def post_message(
    db,
    *,
    event_id: int,
    building_id: str,
    sender_role: str,
    body: str,
    sender_user_id: int | None = None,
) -> Message:
    """Append one message to the (event, building) thread. Does not commit."""
    msg = Message(
        event_id=event_id,
        building_id=building_id,
        sender_role=sender_role,
        sender_user_id=sender_user_id,
        body=body,
    )
    db.add(msg)
    db.flush()
    return msg
