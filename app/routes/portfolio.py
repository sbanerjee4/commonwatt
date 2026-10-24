"""Portfolio, map, savings, and agent routes (the LLM backend).

These were originally in bff/app.py; they are mounted here as an APIRouter so
the single FastAPI app in app/main.py owns auth, sessions, and the portfolio
views together. Read endpoints (map/zip/savings/recruitment) are public demo
data. Building-scoped and operator endpoints reuse the same header-based access
pattern as app/routes/chat.py (X-User-Id / X-Role) so the role boundary holds.

Every numeric field carries a source_id (provenance rule).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from server.constants import EJ_SOURCE_ID
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
            "lngLat": None,
            "propertyType": b.property_type,
            "grossAreaSf": b.gross_area_sf,
            "curtailableLoadKw": load,
        })
    return {"zip": zip_code, "buildings": markers}


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
    x_role: str = Header(default="operator"),
) -> dict[str, Any]:
    """Run the planner/critic loop. Operator-only (matches the human-gate rule)."""
    if x_role != "operator":
        raise HTTPException(status_code=403, detail="operators only")

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


_chat_sessions: dict[str, Any] = {}


class ChatRequest(BaseModel):
    message: str
    event_context: dict | None = None


@router.post("/portfolio/building/{building_id}/chat")
def post_building_chat(
    building_id: str,
    req: ChatRequest,
    x_user_id: int | None = Header(default=None),
    x_role: str = Header(default="building_manager"),
) -> dict[str, Any]:
    """One facility-manager chat turn, scoped to this building.

    A building session may only chat about its own building; operators may chat
    about any (demo). Building-id scoping mirrors chat.py's access rule.
    """
    # NOTE: BERDO building ids are strings; the auth building_id is an int FK.
    # The frontend/session mapping between them is a known follow-up (see PR).
    from agent.chat import make_session  # lazy import

    session = _chat_sessions.get(building_id)
    if session is None or req.event_context is not None:
        session = make_session(building_id, event_context=req.event_context)
        _chat_sessions[building_id] = session

    reply = session.chat(req.message)
    return {"buildingId": building_id, "reply": reply}
