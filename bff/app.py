"""
Commonwatt BFF (backend-for-frontend).

Thin FastAPI layer the SPA talks to. It composes Commonwatt tool outputs and
the building store into the view-model shapes the front-end expects (see
.kiro/specs/project/design.md). Every numeric field carries a source_id.

Endpoints (read-only unless noted):
  GET  /health
  GET  /zips                        zip aggregates for the choropleth
  GET  /zips/{zip}/buildings        building markers for a zip drill-in
  GET  /buildings/{building_id}     one building profile
  GET  /savings?shed_mw=&hours=     three savings counters
  GET  /recruitment?top_n=          high-load unenrolled EJ buildings
  POST /event/draft                 run the planner/critic loop (LLM)
  POST /building/{building_id}/chat facility-manager chat turn (LLM)

The LLM endpoints require Bedrock to be configured; the data endpoints do not.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from server.data import buildings_by_id, buildings_by_zip, load_buildings
from server.constants import EJ_SOURCE_ID
from server.tools import (
    building_info,
    estimate_savings,
    recruitment_list,
)

app = FastAPI(title="Commonwatt BFF", version="0.1.0")

# Allow the Vite dev server to call the BFF in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "buildings": len(load_buildings())}


# ---------------------------------------------------------------------------
# Zip aggregates — choropleth layer
# ---------------------------------------------------------------------------

@app.get("/zips")
def get_zips() -> dict[str, Any]:
    """
    Per-zip aggregates for the map choropleth.
    Shape mirrors the ZipAggregate contract in design.md.
    """
    by_zip = buildings_by_zip()
    aggregates = []
    for zip_code, buildings in sorted(by_zip.items(), key=lambda kv: kv[0] or ""):
        loads = [b.curtailable_load_kw for b in buildings if b.curtailable_load_kw]
        total_load = round(sum(loads), 1) if loads else None
        is_ej = buildings[0].is_ej  # zip-level EJ status
        aggregates.append({
            "zip": zip_code,
            "buildingCount": len(buildings),
            "curtailableLoadKw": (
                {"value": total_load, "source_id": EJ_SOURCE_ID}
                if total_load is not None else None
            ),
            "ejStatus": "ej" if is_ej else "non_ej",
            "cumulativeCalls": 0,  # simulated — no events run yet
            "hasGeometry": True,   # geometry handled client-side via static asset
        })
    return {"zips": aggregates, "source_id": EJ_SOURCE_ID}


# ---------------------------------------------------------------------------
# Building markers — drill-in
# ---------------------------------------------------------------------------

@app.get("/zips/{zip_code}/buildings")
def get_zip_buildings(zip_code: str) -> dict[str, Any]:
    """Buildings in a zip, shaped as BuildingMarker records."""
    buildings = buildings_by_zip().get(zip_code)
    if not buildings:
        raise HTTPException(status_code=404, detail=f"zip {zip_code} not found")

    markers = []
    for b in buildings:
        load = None
        if b.curtailable_load_kw is not None:
            load = {
                "value": b.curtailable_load_kw,
                "source_id": EJ_SOURCE_ID,
                "basis": b.load_basis,
            }
        markers.append({
            "buildingId": b.building_id,
            "address": b.address,
            "zip": b.zip,
            "lngLat": None,  # geocoding is a separate backend concern
            "propertyType": b.property_type,
            "grossAreaSf": b.gross_area_sf,
            "curtailableLoadKw": load,
        })
    return {"zip": zip_code, "buildings": markers}


@app.get("/buildings/{building_id}")
def get_building(building_id: str) -> dict[str, Any]:
    """Full profile for one building."""
    result = building_info(building_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Savings counters
# ---------------------------------------------------------------------------

@app.get("/savings")
def get_savings(shed_mw: float = 0.0, hours: float = 3.0) -> dict[str, Any]:
    """Three savings counters for a given shed amount. Zero at zero (AC-24)."""
    return estimate_savings(shed_mw=shed_mw, event_duration_hours=hours)


# ---------------------------------------------------------------------------
# Recruitment list (city office)
# ---------------------------------------------------------------------------

@app.get("/recruitment")
def get_recruitment(top_n: int = 50) -> dict[str, Any]:
    return recruitment_list(top_n=top_n)


# ---------------------------------------------------------------------------
# Agent endpoints (LLM — require Bedrock)
# ---------------------------------------------------------------------------

class DraftRequest(BaseModel):
    target_mw: float = 10.0
    ej_cap_pct: float = 0.35
    current_temp_f: float = 88.0
    window_label: str = "today 3:30–6:30 PM"


@app.post("/event/draft")
def post_event_draft(req: DraftRequest) -> dict[str, Any]:
    """Run the planner/critic loop and return the plan + trace."""
    # Imported lazily so the data endpoints work even if Bedrock is unset.
    from agent.planner import run_planner

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
            }
            if plan else None
        ),
        "trace": [
            {
                "ts": s.ts,
                "kind": s.kind,
                "summary": s.summary,
                "planVersion": s.plan_version,
                "toolName": s.tool_name,
                "rejectedBy": s.rejected_by,
            }
            for s in result.trace
        ],
    }


# Chat sessions kept in-process, keyed by building id. Demo-grade; not durable.
_chat_sessions: dict[str, Any] = {}


class ChatRequest(BaseModel):
    message: str
    event_context: dict | None = None


@app.post("/building/{building_id}/chat")
def post_building_chat(building_id: str, req: ChatRequest) -> dict[str, Any]:
    """One chat turn for a facility manager. Session is kept per building id."""
    from agent.chat import make_session

    key = building_id
    session = _chat_sessions.get(key)
    if session is None or req.event_context is not None:
        session = make_session(building_id, event_context=req.event_context)
        _chat_sessions[key] = session

    reply = session.chat(req.message)
    return {"buildingId": building_id, "reply": reply}
