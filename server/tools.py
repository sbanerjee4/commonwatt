"""
Commonwatt MCP tool server.

All tools are deterministic and pure given their inputs — no LLM calls inside.
Every returned number carries a source_id.

Tools:
  estimate_load       — curtailable kW for one building
  rank_candidates     — rank buildings for a DR event
  check_constraints   — validate EJ cap, cooldown, protected facilities
  score_equity        — EJ share % for a proposed portfolio
  plan_event          — assemble a portfolio to a target MW
  backfill            — fill gap after declines
  estimate_savings    — three savings counters with source ids
  recruitment_list    — high-load unenrolled buildings in EJ zips
  building_info       — full profile for one building (for the chat agent)
"""

from __future__ import annotations

import math
from typing import Any

import fastmcp

from server.constants import (
    ASSUMPTIONS,
    CONN_SOLUTIONS_RATE_USD_PER_KW,
    CONN_SOLUTIONS_SOURCE_ID,
    EJ_CAP_DEFAULT_PCT,
    EJ_SOURCE_ID,
    EMISSIONS_SOURCE_ID,
    EXTREME_HEAT_TEMP_F,
    ISO_NE_AVG_LMP_USD_PER_MWH,
    ISO_NE_CAPACITY_PRICE_USD_PER_KW_MONTH,
    ISO_NE_PEAK_LMP_USD_PER_MWH,
    ISO_NE_SOURCE_ID,
    LOAD_TYPE_SOURCE_ID,
    MARGINAL_EMISSIONS_FACTOR_KG_CO2_PER_MWH,
)
from server.data import (
    Building,
    EJ_ZIPS,
    buildings_by_id,
    buildings_by_zip,
    load_buildings,
)

mcp = fastmcp.FastMCP("commonwatt")


# ---------------------------------------------------------------------------
# estimate_load
# ---------------------------------------------------------------------------

@mcp.tool()
def estimate_load(building_id: str) -> dict[str, Any]:
    """
    Return the estimated curtailable load (kW) for a single building.

    Returns:
        building_id, curtailable_load_kw (or null), load_basis
        ("metered" | "estimated_from_type" | "unknown"), source_id.
    """
    b = buildings_by_id().get(building_id)
    if b is None:
        return {"error": f"building_id {building_id!r} not found"}

    source_id = CONN_SOLUTIONS_SOURCE_ID if b.load_basis == "metered" else LOAD_TYPE_SOURCE_ID

    return {
        "building_id": building_id,
        "curtailable_load_kw": b.curtailable_load_kw,
        "load_basis": b.load_basis,
        "source_id": source_id,
        "estimated": True,
    }


# ---------------------------------------------------------------------------
# rank_candidates
# ---------------------------------------------------------------------------

@mcp.tool()
def rank_candidates(
    target_mw: float,
    ej_cap_pct: float = EJ_CAP_DEFAULT_PCT,
    current_temp_f: float = 85.0,
    exclude_building_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Rank all eligible buildings by curtailable load (descending).

    Applies:
      - exclude_building_ids: buildings that declined or were called last event
      - protected-facility exclusion when current_temp_f >= EXTREME_HEAT_TEMP_F

    Returns a ranked list with load, EJ status, and load_basis for each.
    Does NOT assemble a final portfolio — that is plan_event's job.
    """
    exclude = set(exclude_building_ids or [])
    heat_threshold_exceeded = current_temp_f >= EXTREME_HEAT_TEMP_F

    candidates = []
    for b in load_buildings():
        if b.building_id in exclude:
            continue
        if b.curtailable_load_kw is None:
            continue
        if heat_threshold_exceeded and b.is_protected:
            continue
        candidates.append(b)

    # Sort by curtailable load descending
    candidates.sort(key=lambda b: b.curtailable_load_kw or 0, reverse=True)

    return {
        "target_mw": target_mw,
        "ej_cap_pct": ej_cap_pct,
        "heat_threshold_exceeded": heat_threshold_exceeded,
        "excluded_count": len(exclude),
        "candidates": [
            {
                "building_id": b.building_id,
                "address": b.address,
                "zip": b.zip,
                "property_type": b.property_type,
                "curtailable_load_kw": b.curtailable_load_kw,
                "load_basis": b.load_basis,
                "is_ej": b.is_ej,
                "is_protected": b.is_protected,
            }
            for b in candidates[:200]  # top 200 candidates returned to agent
        ],
        "source_id": LOAD_TYPE_SOURCE_ID,
    }


# ---------------------------------------------------------------------------
# score_equity
# ---------------------------------------------------------------------------

@mcp.tool()
def score_equity(building_ids: list[str]) -> dict[str, Any]:
    """
    Compute the EJ share for a proposed portfolio of building ids.

    Returns:
        total_load_kw, ej_load_kw, ej_share_pct, ej_building_count,
        non_ej_building_count, source_id.
    """
    bid_map = buildings_by_id()
    total_kw = 0.0
    ej_kw = 0.0
    ej_count = 0
    non_ej_count = 0

    for bid in building_ids:
        b = bid_map.get(bid)
        if b is None or b.curtailable_load_kw is None:
            continue
        kw = b.curtailable_load_kw
        total_kw += kw
        if b.is_ej:
            ej_kw += kw
            ej_count += 1
        else:
            non_ej_count += 1

    ej_share = (ej_kw / total_kw) if total_kw > 0 else 0.0

    return {
        "building_count": len(building_ids),
        "total_load_kw": round(total_kw, 1),
        "ej_load_kw": round(ej_kw, 1),
        "ej_share_pct": round(ej_share * 100, 1),
        "ej_building_count": ej_count,
        "non_ej_building_count": non_ej_count,
        "source_id": EJ_SOURCE_ID,
    }


# ---------------------------------------------------------------------------
# check_constraints
# ---------------------------------------------------------------------------

@mcp.tool()
def check_constraints(
    building_ids: list[str],
    target_mw: float,
    ej_cap_pct: float = EJ_CAP_DEFAULT_PCT,
    current_temp_f: float = 85.0,
    prev_event_building_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Validate a proposed portfolio against all equity and safety constraints.

    Checks:
      1. EJ share ≤ ej_cap_pct
      2. No building called in prev_event (cooldown)
      3. No protected facility when heat threshold exceeded
      4. Portfolio load ≥ target_mw (or returns explicit unreachable)

    Returns:
        passed (bool), violations list, equity score, total_load_mw.
    """
    prev = set(prev_event_building_ids or [])
    heat_exceeded = current_temp_f >= EXTREME_HEAT_TEMP_F
    bid_map = buildings_by_id()

    violations: list[dict] = []
    total_kw = 0.0
    ej_kw = 0.0

    for bid in building_ids:
        b = bid_map.get(bid)
        if b is None:
            violations.append({"type": "unknown_building", "building_id": bid})
            continue

        kw = b.curtailable_load_kw or 0.0
        total_kw += kw
        if b.is_ej:
            ej_kw += kw

        if bid in prev:
            violations.append({
                "type": "cooldown_violation",
                "building_id": bid,
                "address": b.address,
                "detail": "called in previous event",
            })

        if heat_exceeded and b.is_protected:
            violations.append({
                "type": "protected_facility_violation",
                "building_id": bid,
                "address": b.address,
                "property_type": b.property_type,
                "detail": f"protected facility excluded above {EXTREME_HEAT_TEMP_F}°F",
            })

    ej_share = (ej_kw / total_kw) if total_kw > 0 else 0.0
    if ej_share > ej_cap_pct:
        violations.append({
            "type": "ej_cap_exceeded",
            "ej_share_pct": round(ej_share * 100, 1),
            "cap_pct": round(ej_cap_pct * 100, 1),
            "detail": f"EJ share {ej_share*100:.1f}% exceeds cap {ej_cap_pct*100:.1f}%",
        })

    total_mw = total_kw / 1000
    reachable = total_mw >= target_mw

    return {
        "passed": len(violations) == 0 and reachable,
        "violations": violations,
        "total_load_mw": round(total_mw, 2),
        "target_mw": target_mw,
        "reachable": reachable,
        "ej_share_pct": round(ej_share * 100, 1),
        "ej_cap_pct": round(ej_cap_pct * 100, 1),
        "source_id": EJ_SOURCE_ID,
    }


# ---------------------------------------------------------------------------
# plan_event
# ---------------------------------------------------------------------------

@mcp.tool()
def plan_event(
    target_mw: float,
    ej_cap_pct: float = EJ_CAP_DEFAULT_PCT,
    current_temp_f: float = 85.0,
    exclude_building_ids: list[str] | None = None,
    prev_event_building_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Assemble a demand-response portfolio meeting target_mw under the EJ cap.

    Algorithm:
      1. Rank all eligible buildings by curtailable load.
      2. Greedily add non-EJ buildings first until EJ headroom is clear.
      3. Fill remaining with EJ buildings up to cap.
      4. If target unreachable under cap, return explicit trade-off.

    Returns portfolio + equity score, or an unreachable result with trade-off.
    This is v1 of the plan; the critic will check it and may request v2.
    """
    exclude = set(exclude_building_ids or [])
    prev = set(prev_event_building_ids or [])
    heat_exceeded = current_temp_f >= EXTREME_HEAT_TEMP_F
    all_exclude = exclude | prev

    # Get eligible buildings
    eligible: list[Building] = []
    for b in load_buildings():
        if b.building_id in all_exclude:
            continue
        if b.curtailable_load_kw is None or b.curtailable_load_kw <= 0:
            continue
        if heat_exceeded and b.is_protected:
            continue
        eligible.append(b)

    # Sort by curtailable load desc
    eligible.sort(key=lambda b: b.curtailable_load_kw or 0, reverse=True)

    target_kw = target_mw * 1000
    non_ej = [b for b in eligible if not b.is_ej]
    ej = [b for b in eligible if b.is_ej]

    selected: list[Building] = []
    total_kw = 0.0
    ej_kw = 0.0

    # Add non-EJ first
    for b in non_ej:
        kw = b.curtailable_load_kw or 0.0
        selected.append(b)
        total_kw += kw
        if total_kw >= target_kw:
            break

    # If still short, fill from EJ up to cap
    if total_kw < target_kw:
        for b in ej:
            kw = b.curtailable_load_kw or 0.0
            projected_ej_kw = ej_kw + kw
            projected_total_kw = total_kw + kw
            projected_ej_share = projected_ej_kw / projected_total_kw if projected_total_kw > 0 else 0
            if projected_ej_share > ej_cap_pct:
                continue  # skip — would bust the cap
            selected.append(b)
            total_kw += kw
            ej_kw += kw
            if total_kw >= target_kw:
                break

    # Recalculate final equity share
    final_ej_kw = sum(b.curtailable_load_kw or 0 for b in selected if b.is_ej)
    final_total_kw = sum(b.curtailable_load_kw or 0 for b in selected)
    final_ej_share = (final_ej_kw / final_total_kw) if final_total_kw > 0 else 0.0
    final_mw = final_total_kw / 1000

    reachable = final_mw >= target_mw

    result: dict[str, Any] = {
        "reachable": reachable,
        "target_mw": target_mw,
        "achieved_mw": round(final_mw, 2),
        "building_count": len(selected),
        "ej_share_pct": round(final_ej_share * 100, 1),
        "ej_cap_pct": round(ej_cap_pct * 100, 1),
        "portfolio": [
            {
                "building_id": b.building_id,
                "address": b.address,
                "zip": b.zip,
                "property_type": b.property_type,
                "curtailable_load_kw": b.curtailable_load_kw,
                "load_basis": b.load_basis,
                "is_ej": b.is_ej,
            }
            for b in selected
        ],
        "source_id": EJ_SOURCE_ID,
    }

    if not reachable:
        # Compute what EJ cap would be needed to hit target
        all_kw = sum(b.curtailable_load_kw or 0 for b in eligible)
        all_mw = all_kw / 1000
        all_ej_kw = sum(b.curtailable_load_kw or 0 for b in eligible if b.is_ej)
        min_ej_share_needed = max(0, (target_kw - (all_kw - all_ej_kw)) / target_kw)
        result["tradeoff"] = (
            f"{ej_cap_pct*100:.0f}% cap → {final_mw:.1f} MW; "
            f"{min_ej_share_needed*100:.0f}% cap → {min(all_mw, target_mw):.1f} MW"
        )

    return result


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------

@mcp.tool()
def backfill(
    gap_mw: float,
    current_portfolio_building_ids: list[str],
    declined_building_ids: list[str],
    ej_cap_pct: float = EJ_CAP_DEFAULT_PCT,
    current_temp_f: float = 85.0,
    prev_event_building_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Fill a gap (in MW) left by declining buildings.

    Never adds a building that declined.
    Applies the same EJ cap against the combined (existing + backfill) portfolio.
    Returns the backfill additions or an explicit unreachable result.
    """
    exclude = (
        set(current_portfolio_building_ids)
        | set(declined_building_ids)
        | set(prev_event_building_ids or [])
    )

    # Current portfolio equity baseline
    bid_map = buildings_by_id()
    current_ej_kw = sum(
        (bid_map[bid].curtailable_load_kw or 0)
        for bid in current_portfolio_building_ids
        if bid in bid_map and bid_map[bid].is_ej
    )
    current_total_kw = sum(
        (bid_map[bid].curtailable_load_kw or 0)
        for bid in current_portfolio_building_ids
        if bid in bid_map
    )

    heat_exceeded = current_temp_f >= EXTREME_HEAT_TEMP_F
    gap_kw = gap_mw * 1000

    additions: list[Building] = []
    added_kw = 0.0

    eligible = [
        b for b in load_buildings()
        if b.building_id not in exclude
        and b.curtailable_load_kw is not None
        and b.curtailable_load_kw > 0
        and not (heat_exceeded and b.is_protected)
    ]
    eligible.sort(key=lambda b: b.curtailable_load_kw or 0, reverse=True)

    running_ej_kw = current_ej_kw
    running_total_kw = current_total_kw

    for b in eligible:
        kw = b.curtailable_load_kw or 0.0
        new_ej = running_ej_kw + (kw if b.is_ej else 0)
        new_total = running_total_kw + kw
        new_share = new_ej / new_total if new_total > 0 else 0.0
        if new_share > ej_cap_pct:
            continue
        additions.append(b)
        added_kw += kw
        running_ej_kw = new_ej
        running_total_kw = new_total
        if added_kw >= gap_kw:
            break

    reachable = added_kw >= gap_kw
    final_ej_share = (running_ej_kw / running_total_kw) if running_total_kw > 0 else 0.0

    result: dict[str, Any] = {
        "reachable": reachable,
        "gap_mw": gap_mw,
        "filled_mw": round(added_kw / 1000, 2),
        "additions": [
            {
                "building_id": b.building_id,
                "address": b.address,
                "zip": b.zip,
                "curtailable_load_kw": b.curtailable_load_kw,
                "is_ej": b.is_ej,
            }
            for b in additions
        ],
        "combined_ej_share_pct": round(final_ej_share * 100, 1),
        "source_id": EJ_SOURCE_ID,
    }

    if not reachable:
        result["tradeoff"] = (
            f"Gap of {gap_mw:.1f} MW cannot be filled under {ej_cap_pct*100:.0f}% EJ cap. "
            f"Filled {added_kw/1000:.1f} MW. Operator must raise cap or reduce target."
        )

    return result


# ---------------------------------------------------------------------------
# estimate_savings
# ---------------------------------------------------------------------------

@mcp.tool()
def estimate_savings(
    shed_mw: float,
    event_duration_hours: float = 3.0,
) -> dict[str, Any]:
    """
    Estimate three savings counters for a demand-response event.

    All values are ESTIMATED. Every number carries source_id and assumptions.
    Returns zero for all counters when shed_mw == 0 (monotonicity invariant).
    """
    if shed_mw < 0:
        return {"error": "shed_mw must be non-negative"}

    shed_kw = shed_mw * 1000
    shed_kwh = shed_kw * event_duration_hours

    # Paid to buildings
    paid_usd = shed_kw * CONN_SOLUTIONS_RATE_USD_PER_KW / 12  # per-event share of monthly rate

    # Avoided system cost
    capacity_value = shed_kw * ISO_NE_CAPACITY_PRICE_USD_PER_KW_MONTH * 12
    energy_value = shed_kwh * (ISO_NE_PEAK_LMP_USD_PER_MWH - ISO_NE_AVG_LMP_USD_PER_MWH) / 1000
    avoided_cost_usd = capacity_value + energy_value

    # CO2 avoided
    co2_kg = shed_kwh * MARGINAL_EMISSIONS_FACTOR_KG_CO2_PER_MWH / 1000
    co2_mt = co2_kg / 1000

    return {
        "shed_mw": shed_mw,
        "event_duration_hours": event_duration_hours,
        "counters": [
            {
                "key": "paid_to_buildings",
                "value_usd": round(paid_usd, 2),
                "value_label": f"${paid_usd:,.0f}",
                "estimated": True,
                "assumptions": ASSUMPTIONS["paid_to_buildings"],
                "source_id": CONN_SOLUTIONS_SOURCE_ID,
            },
            {
                "key": "avoided_system_cost",
                "value_usd": round(avoided_cost_usd, 2),
                "value_label": f"${avoided_cost_usd:,.0f}",
                "estimated": True,
                "assumptions": ASSUMPTIONS["avoided_system_cost"],
                "source_id": ISO_NE_SOURCE_ID,
            },
            {
                "key": "co2_avoided",
                "value_mt": round(co2_mt, 2),
                "value_label": f"{co2_mt:,.1f} metric tons CO₂",
                "estimated": True,
                "assumptions": ASSUMPTIONS["co2_avoided"],
                "source_id": EMISSIONS_SOURCE_ID,
            },
        ],
    }


# ---------------------------------------------------------------------------
# recruitment_list
# ---------------------------------------------------------------------------

@mcp.tool()
def recruitment_list(top_n: int = 50) -> dict[str, Any]:
    """
    Return the top N high-load, unenrolled buildings in EJ zips.

    In the demo, all buildings are "unenrolled" (simulated enrollment).
    Returns buildings sorted by curtailable load descending.
    """
    ej_buildings = [
        b for b in load_buildings()
        if b.is_ej and b.curtailable_load_kw is not None
    ]
    ej_buildings.sort(key=lambda b: b.curtailable_load_kw or 0, reverse=True)

    return {
        "simulated_enrollment": True,  # AC-32: label simulated data
        "ej_zip_count": len(set(b.zip for b in ej_buildings)),
        "total_ej_buildings": len(ej_buildings),
        "top_candidates": [
            {
                "building_id": b.building_id,
                "address": b.address,
                "zip": b.zip,
                "property_type": b.property_type,
                "curtailable_load_kw": b.curtailable_load_kw,
                "load_basis": b.load_basis,
                "is_ej": b.is_ej,
            }
            for b in ej_buildings[:top_n]
        ],
        "source_id": EJ_SOURCE_ID,
    }


# ---------------------------------------------------------------------------
# building_info  (used by the building chat agent)
# ---------------------------------------------------------------------------

@mcp.tool()
def building_info(building_id: str) -> dict[str, Any]:
    """
    Return the full profile for one building.
    Used by the facility-manager chat agent to answer questions about a building.
    """
    b = buildings_by_id().get(building_id)
    if b is None:
        return {"error": f"building_id {building_id!r} not found"}
    return b.to_dict()


if __name__ == "__main__":
    mcp.run()
