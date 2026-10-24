"""Portfolio, map, savings, and agent routes (the LLM backend).

These were originally in bff/app.py; they are mounted here as an APIRouter so
the single FastAPI app in app/main.py owns auth, sessions, and the portfolio
views together. Read endpoints (map/zip/savings/recruitment) are public demo
data. Building-scoped and operator endpoints resolve identity from the session
cookie via app.deps (current_user / require_role), not request headers.

Every numeric field carries a source_id (provenance rule).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import current_user, require_role
from app.db import get_db
from db.models import User
from server.constants import EJ_SOURCE_ID
from server.data import INCOME_SOURCE_ID, affluence_tier_for_income, median_income_for_zip
from server.data import buildings_by_zip, load_buildings
from server.tools import building_info, estimate_savings, recruitment_list

router = APIRouter(tags=["portfolio"])


# ---------------------------------------------------------------------------
# Public read endpoints — map / aggregates / savings
# ---------------------------------------------------------------------------

@router.get("/zips")
def get_zips() -> dict[str, Any]:
    """Per-zip aggregates for the map choropleth (ZipAggregate contract)."""
    by_zip = buildings_by_zip()
    aggregates = []
    for zip_code, buildings in sorted(by_zip.items(), key=lambda kv: kv[0] or ""):
        if not zip_code:
            continue
        loads = [b.curtailable_load_kw for b in buildings if b.curtailable_load_kw]
        total_load = round(sum(loads), 1) if loads else None
        aggregates.append({
            "zip": zip_code,
            "buildingCount": len(buildings),
            "curtailableLoadKw": (
                {"value": total_load, "source_id": EJ_SOURCE_ID}
                if total_load is not None else None
            ),
            "ejStatus": "ej" if buildings[0].is_ej else "non_ej",
            "medianIncome": buildings[0].median_income,
            "affluenceTier": buildings[0].affluence_tier,
            "incomeSourceId": INCOME_SOURCE_ID if buildings[0].median_income else None,
            "cumulativeCalls": 0,
            "hasGeometry": True,
        })
    return {"zips": aggregates, "source_id": EJ_SOURCE_ID}


@router.get("/zips/{zip_code}/buildings")
def get_zip_buildings(zip_code: str) -> dict[str, Any]:
    """Buildings in a zip, shaped as BuildingMarker records."""
    buildings = buildings_by_zip().get(zip_code)
    if not buildings:
        raise HTTPException(status_code=404, detail=f"zip {zip_code} not found")
    markers = []
    for b in buildings:
        load = None
        if b.curtailable_load_kw is not None:
            load = {"value": b.curtailable_load_kw, "source_id": EJ_SOURCE_ID,
                    "basis": b.load_basis}
        markers.append({
            "buildingId": b.building_id,
            "address": b.address,
            "zip": b.zip,
            "lngLat": b.lng_lat,
            "propertyType": b.property_type,
            "grossAreaSf": b.gross_area_sf,
            "curtailableLoadKw": load,
            "affluenceTier": b.affluence_tier,
            "medianIncome": b.median_income,
            "canAbsorb": b.can_absorb,
            "shouldProtect": b.should_protect,
        })
    return {"zip": zip_code, "buildings": markers}


@router.get("/portfolio/buildings")
def get_all_building_markers() -> dict[str, Any]:
    """All geocoded buildings as map markers, for the portfolio map.

    Buildings without coordinates (failed geocoding) are returned with
    lngLat=null so the client can list them in an orphan panel rather than
    drop them (AC-12b).
    """
    markers = []
    for b in load_buildings():
        load = None
        if b.curtailable_load_kw is not None:
            load = {"value": b.curtailable_load_kw, "source_id": EJ_SOURCE_ID,
                    "basis": b.load_basis}
        markers.append({
            "buildingId": b.building_id,
            "address": b.address,
            "zip": b.zip,
            "lngLat": b.lng_lat,
            "propertyType": b.property_type,
            "grossAreaSf": b.gross_area_sf,
            "curtailableLoadKw": load,
            "affluenceTier": b.affluence_tier,
            "medianIncome": b.median_income,
            "isEj": b.is_ej,
            "canAbsorb": b.can_absorb,
            "shouldProtect": b.should_protect,
        })
    placed = sum(1 for m in markers if m["lngLat"])
    return {"buildings": markers, "placed": placed, "total": len(markers),
            "geocode_source_id": "census_geocoder"}


@router.get("/portfolio/buildings/{building_id}")
def get_building(building_id: str) -> dict[str, Any]:
    """Full profile for one building (public reference data)."""
    result = building_info(building_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/savings")
def get_savings(shed_mw: float = 0.0, hours: float = 3.0) -> dict[str, Any]:
    return estimate_savings(shed_mw=shed_mw, event_duration_hours=hours)


@router.get("/recruitment")
def get_recruitment(top_n: int = 50) -> dict[str, Any]:
    return recruitment_list(top_n=top_n)


# ---------------------------------------------------------------------------
# Agent endpoints (LLM — require Bedrock). Operator-only for the planner.
# ---------------------------------------------------------------------------

class DraftRequest(BaseModel):
    target_mw: float = 10.0
    ej_cap_pct: float = 0.35
    current_temp_f: float = 88.0
    window_label: str = "today 3:30–6:30 PM"


@router.post("/event/draft")
def post_event_draft(
    req: DraftRequest,
    user: User = Depends(require_role("utility")),
) -> dict[str, Any]:
    """Run the planner/critic loop. Operator-only (matches the human-gate rule)."""
    from agent.planner import run_planner  # lazy: data endpoints work without Bedrock

    result = run_planner(
        target_mw=req.target_mw,
        ej_cap_pct=req.ej_cap_pct,
        current_temp_f=req.current_temp_f,
        window_label=req.window_label,
    )
    plan = result.final_plan
    return {
        "approved": result.approved,
        "iterations": result.iterations,
        "criticReason": result.critic_reason,
        "plan": (
            {
                "version": plan.version,
                "targetMw": plan.target_mw,
                "achievedMw": plan.achieved_mw,
                "buildingCount": plan.building_count,
                "ejSharePct": plan.ej_share_pct,
                "ejCapPct": plan.ej_cap_pct,
                "reachable": plan.reachable,
                "tradeoff": plan.tradeoff,
                "portfolio": plan.portfolio,
                "source_id": plan.source_id,
            } if plan else None
        ),
        "trace": [
            {"ts": s.ts, "kind": s.kind, "summary": s.summary,
             "planVersion": s.plan_version, "toolName": s.tool_name,
             "rejectedBy": s.rejected_by}
            for s in result.trace
        ],
    }


class ApproveRequest(BaseModel):
    target_mw: float = 10.0
    ej_cap_pct: float = 0.35
    current_temp_f: float = 88.0
    window_label: str = "today 3:30–6:30 PM"


@router.post("/event/approve")
def post_event_approve(
    req: ApproveRequest,
    db=Depends(get_db),
    user: User = Depends(require_role("utility")),
) -> dict[str, Any]:
    """Approve an event: persist the plan, open a thread per building, and post a
    plain system notice to each so its manager is contacted automatically.

    The plan is re-run server-side from the same inputs (never trusted from the
    client). Each building gets an ``auto``-mode thread, so a manager reply is
    answered by the agent until they request a human. Operator-only (human gate).
    """
    from datetime import datetime, timedelta, timezone

    from agent.planner import run_planner
    from app.routes._chat_helpers import get_or_create_thread, post_message
    from db.models import AuditLog, CallHistory, Event, PlanBuilding
    from notify.push import notify_user

    result = run_planner(
        target_mw=req.target_mw,
        ej_cap_pct=req.ej_cap_pct,
        current_temp_f=req.current_temp_f,
        window_label=req.window_label,
    )
    plan = result.final_plan
    if plan is None or not result.approved:
        raise HTTPException(
            status_code=409,
            detail="plan not approvable by the critic; adjust target or cap",
        )

    now = datetime.now(timezone.utc)
    # Resolve the operator's utility; fall back to the first utility row.
    from sqlalchemy import select
    from db.models import Utility

    utility_id = user.utility_id or db.execute(
        select(Utility.id)
    ).scalars().first()
    if utility_id is None:
        raise HTTPException(status_code=409, detail="no utility configured")

    event = Event(
        utility_id=utility_id,
        window_start=now,
        window_end=now + timedelta(hours=2),
        window_label=req.window_label,
        target_mw=plan.target_mw,
        cap_pct=req.ej_cap_pct,
        status="approved",
        current_version=plan.version,
        approved_by=user.id,
        approved_at=now,
    )
    db.add(event)
    db.flush()  # assign event.id

    contacted: list[str] = []
    for row in plan.portfolio:
        bid = row.get("building_id")
        if not bid:
            continue
        kw = float(row.get("curtailable_load_kw") or 0.0)
        db.add(PlanBuilding(
            event_id=event.id,
            plan_version=plan.version,
            building_id=bid,
            kw_requested=kw,
            reason="Selected by the planner within the equity cap.",
        ))
        db.add(CallHistory(
            event_id=event.id, building_id=bid, kw_requested=kw,
            reason="Approved event contact.",
        ))
        get_or_create_thread(db, event.id, bid)
        post_message(
            db, event_id=event.id, building_id=bid, sender_role="system",
            body=(
                f"You've been asked to voluntarily reduce about {kw:,.0f} kW "
                f"during {req.window_label}. Reply here with yes, no, or an "
                f"amount you can offer. Participation is voluntary and paid."
            ),
        )
        contacted.append(bid)

    db.add(AuditLog(
        user_id=user.id, event_id=event.id, building_id=None,
        action="approved",
        detail=f"{len(contacted)} buildings contacted", provider="inapp",
    ))
    db.commit()

    # Notify each building's manager (best-effort; push is skipped w/o VAPID).
    from db.models import User as UserModel
    for bid in contacted:
        mgr = db.execute(
            select(UserModel).where(
                UserModel.building_id == bid, UserModel.role == "building_manager"
            )
        ).scalars().first()
        if mgr is not None:
            notify_user(db, mgr.id, "CommonWatt",
                        "You've been asked to participate in an event.")

    return {"ok": True, "event_id": event.id, "contacted": contacted,
            "building_count": len(contacted)}


_chat_sessions: dict[str, Any] = {}


class ChatRequest(BaseModel):
    message: str
    event_context: dict | None = None


@router.post("/portfolio/building/{building_id}/chat")
def post_building_chat(
    building_id: str,
    req: ChatRequest,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """One facility-manager chat turn, scoped to this building.

    A building manager may only chat about their own building; a utility
    operator may chat about any. Identity comes from the session cookie.
    """
    if user.role == "building_manager" and user.building_id != building_id:
        raise HTTPException(status_code=403, detail="not authorized for this building")

    from agent.chat import make_session  # lazy import

    session = _chat_sessions.get(building_id)
    if session is None or req.event_context is not None:
        session = make_session(building_id, event_context=req.event_context)
        _chat_sessions[building_id] = session

    reply = session.chat(req.message)
    return {"buildingId": building_id, "reply": reply}
