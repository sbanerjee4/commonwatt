"""The one end-to-end event story: size -> ask -> decide -> confirm.

1. The utility needs a reduction. ``size_requests`` turns the planner's
   portfolio into per-building asks: every building is asked for its full
   curtailable capacity EXCEPT the last one, which is asked only for the
   remaining gap (no over-asking). ``recent_burden`` feeds the planner the
   buildings that delivered in the last confirmed event (cooldown) and counts
   recent calls per zip so the operator sees which neighborhoods were leaned on.
2. A facility manager answers with ``POST /inbox/{id}/decision``: accept,
   decline, or a counteroffer that can never exceed what was asked or the
   building's capacity (422 with a plain explanation otherwise).
3. The operator reads ``GET /event/current`` (asked vs committed per building)
   and confirms with ``POST /event/{id}/confirm``; each committed building gets
   a confirmation notice in its thread.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.db import get_db
from app.deps import current_user, require_role
from app.routes._chat_helpers import (
    current_plan_building,
    get_or_create_thread,
    open_event_for_building,
    post_message,
)
from db.models import AuditLog, CallHistory, Event, PlanBuilding, Reply, User
from server.data import buildings_by_id

router = APIRouter(tags=["event"])

# How many recent events count toward a neighborhood's "recent calls" figure.
RECENT_EVENTS_WINDOW = 5


# ---------------------------------------------------------------------------
# Helpers used by the planner routes (portfolio.py)
# ---------------------------------------------------------------------------

def size_requests(portfolio: list[dict], target_mw: float) -> list[dict]:
    """Per-building ask: full capacity, except the marginal building gets the gap."""
    remaining = target_mw * 1000
    sized = []
    for row in portfolio:
        capacity = float(row.get("curtailable_load_kw") or 0.0)
        ask = round(max(0.0, min(capacity, remaining)), 1)
        remaining -= ask
        sized.append({**row, "capacity_kw": capacity, "kw_requested": ask})
    return [r for r in sized if r["kw_requested"] > 0]


def recent_burden(db) -> tuple[list[str], dict[str, int]]:
    """(cooldown building ids, recent call count per zip).

    Cooldown = buildings that committed (accepted or countered) in the most
    recent operator-approved event, if that event was confirmed. That is the
    "never two events in a row" rule: once a newer event is approved, the
    rested buildings are eligible again. Merely being asked, or declining,
    never triggers cooldown.
    """
    cooldown: list[str] = []
    latest = db.execute(
        select(Event.id).where(Event.status == "approved", Event.approved_by.is_not(None))
        .order_by(Event.id.desc())
    ).scalars().first()
    if latest is not None and is_confirmed(db, latest):
        cooldown = sorted(set(db.execute(
            select(Reply.building_id).where(
                Reply.event_id == latest, Reply.kind.in_(("yes", "counter"))
            )
        ).scalars().all()))

    recent_events = db.execute(
        select(Event.id).where(Event.status == "approved")
        .order_by(Event.id.desc()).limit(RECENT_EVENTS_WINDOW)
    ).scalars().all()
    by_id = buildings_by_id()
    zip_calls: dict[str, int] = {}
    if recent_events:
        for bid in db.execute(
            select(CallHistory.building_id).where(CallHistory.event_id.in_(recent_events))
        ).scalars():
            b = by_id.get(bid)
            if b is not None and b.zip:
                zip_calls[b.zip] = zip_calls.get(b.zip, 0) + 1
    return cooldown, zip_calls


def neighborhood_summary(requests: list[dict], zip_calls: dict[str, int]) -> list[dict]:
    """Group the sized asks by zip so the operator sees where the burden lands."""
    by_zip: dict[str, dict] = {}
    for r in requests:
        z = r.get("zip") or "unknown"
        n = by_zip.setdefault(z, {"zip": z, "isEj": bool(r.get("is_ej")),
                                  "buildings": 0, "kwRequested": 0.0,
                                  "recentCalls": zip_calls.get(z, 0)})
        n["buildings"] += 1
        n["kwRequested"] = round(n["kwRequested"] + r["kw_requested"], 1)
    return sorted(by_zip.values(), key=lambda n: n["kwRequested"], reverse=True)


def ej_share_pct(requests: list[dict]) -> float:
    total = sum(r["kw_requested"] for r in requests)
    ej = sum(r["kw_requested"] for r in requests if r.get("is_ej"))
    return round(100 * ej / total, 1) if total else 0.0


# ---------------------------------------------------------------------------
# Facility decision
# ---------------------------------------------------------------------------

def building_capacity_kw(building_id: str, requested_kw: float | None) -> float | None:
    """The building's curtailable capacity (same figure the planner sizes from)."""
    b = buildings_by_id().get(building_id)
    if b is not None and b.curtailable_load_kw:
        return round(b.curtailable_load_kw, 1)
    return requested_kw


def latest_decision(db, event_id: int, building_id: str) -> dict | None:
    r = db.execute(
        select(Reply).where(Reply.event_id == event_id, Reply.building_id == building_id)
        .order_by(Reply.id.desc())
    ).scalars().first()
    if r is None:
        return None
    return {"kind": r.kind, "kw": r.kw}


def is_confirmed(db, event_id: int) -> bool:
    return db.execute(
        select(AuditLog.id).where(AuditLog.event_id == event_id, AuditLog.action == "confirmed")
    ).first() is not None


class DecisionRequest(BaseModel):
    decision: str  # "accept" | "decline" | "counter"
    kw: float | None = None


_DECISION_KIND = {"accept": "yes", "decline": "no", "counter": "counter"}


@router.post("/inbox/{building_id}/decision")
def post_decision(
    building_id: str,
    req: DecisionRequest,
    db=Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    if not (user.role == "building_manager" and user.building_id == building_id):
        raise HTTPException(status_code=403, detail="owning building manager only")
    kind = _DECISION_KIND.get(req.decision)
    if kind is None:
        raise HTTPException(status_code=422, detail="decision must be accept, decline, or counter")

    event = open_event_for_building(db, building_id)
    if event is None:
        raise HTTPException(status_code=409, detail="no active event for building")
    if is_confirmed(db, event.id):
        raise HTTPException(status_code=409, detail="event already confirmed by the utility")

    pb = current_plan_building(db, event, building_id)
    requested = round(pb.kw_requested, 1) if pb is not None else None
    capacity = building_capacity_kw(building_id, requested)

    kw: float | None
    if kind == "yes":
        kw = requested
    elif kind == "no":
        kw = 0.0
    else:
        ceiling = min(v for v in (requested, capacity) if v is not None)
        if req.kw is None or req.kw <= 0:
            raise HTTPException(status_code=422, detail="a counteroffer needs a kW amount above 0")
        if req.kw >= ceiling:
            raise HTTPException(
                status_code=422,
                detail=(f"A counteroffer must be below {ceiling:,.0f} kW — the amount asked"
                        f" (your capacity is {capacity:,.0f} kW). To commit the full ask, accept."),
            )
        kw = round(req.kw, 1)

    db.add(Reply(event_id=event.id, building_id=building_id, kind=kind, kw=kw))
    get_or_create_thread(db, event.id, building_id)
    summary = {"yes": f"Accepted: {kw:,.0f} kW", "no": "Declined this event",
               "counter": f"Counteroffer: {kw:,.0f} kW"}[kind]
    post_message(db, event_id=event.id, building_id=building_id,
                 sender_role="building_manager", sender_user_id=user.id, body=summary)
    db.add(AuditLog(user_id=user.id, event_id=event.id, building_id=building_id,
                    action="reply_submitted", detail=summary, provider="inapp"))
    db.commit()
    return {"ok": True, "decision": {"kind": kind, "kw": kw}}


# ---------------------------------------------------------------------------
# Operator: responses + confirm
# ---------------------------------------------------------------------------

@router.get("/event/current")
def get_current_event(
    db=Depends(get_db),
    user: User = Depends(require_role("utility")),
) -> dict[str, Any]:
    event = db.execute(
        select(Event).where(Event.status == "approved", Event.approved_by.is_not(None))
        .order_by(Event.id.desc())
    ).scalars().first()
    if event is None:
        return {"event": None}

    by_id = buildings_by_id()
    rows = []
    for pb in db.execute(
        select(PlanBuilding).where(PlanBuilding.event_id == event.id,
                                   PlanBuilding.plan_version == event.current_version)
        .order_by(PlanBuilding.kw_requested.desc())
    ).scalars():
        b = by_id.get(pb.building_id)
        rows.append({
            "buildingId": pb.building_id,
            "address": b.address if b else pb.building_id,
            "zip": b.zip if b else None,
            "isEj": bool(b.is_ej) if b else False,
            "kwRequested": round(pb.kw_requested, 1),
            "decision": latest_decision(db, event.id, pb.building_id),
        })
    committed = sum((r["decision"] or {}).get("kw") or 0 for r in rows
                    if r["decision"] and r["decision"]["kind"] in ("yes", "counter"))
    return {"event": {
        "id": event.id,
        "windowLabel": event.window_label,
        "targetMw": event.target_mw,
        "requestedMw": round(sum(r["kwRequested"] for r in rows) / 1000, 2),
        "committedMw": round(committed / 1000, 2),
        "responded": sum(1 for r in rows if r["decision"]),
        "confirmed": is_confirmed(db, event.id),
        "buildings": rows,
    }}


@router.post("/event/{event_id}/confirm")
def confirm_event(
    event_id: int,
    db=Depends(get_db),
    user: User = Depends(require_role("utility")),
) -> dict[str, Any]:
    event = db.get(Event, event_id)
    if event is None or event.status != "approved":
        raise HTTPException(status_code=404, detail="no approved event with that id")
    if is_confirmed(db, event.id):
        raise HTTPException(status_code=409, detail="event already confirmed")

    committed: list[tuple[str, float]] = []
    for pb in db.execute(
        select(PlanBuilding).where(PlanBuilding.event_id == event.id,
                                   PlanBuilding.plan_version == event.current_version)
    ).scalars():
        d = latest_decision(db, event.id, pb.building_id)
        if d and d["kind"] in ("yes", "counter") and d["kw"]:
            committed.append((pb.building_id, d["kw"]))
    if not committed:
        raise HTTPException(status_code=409, detail="no building has committed yet")

    for bid, kw in committed:
        post_message(db, event_id=event.id, building_id=bid, sender_role="system",
                     body=(f"Confirmed: the utility is counting on {kw:,.0f} kW from your "
                           f"building during {event.window_label}. Thank you."))
    total_kw = sum(kw for _, kw in committed)
    db.add(AuditLog(user_id=user.id, event_id=event.id, building_id=None, action="confirmed",
                    detail=f"{len(committed)} buildings, {total_kw:,.0f} kW committed",
                    provider="inapp"))
    db.commit()
    return {"ok": True, "event_id": event.id, "committed_mw": round(total_kw / 1000, 2),
            "building_count": len(committed)}
