"""
Planner + Critic agent loop.

Flow:
  1. Planner calls plan_event → gets v1 portfolio
  2. Critic calls check_constraints on v1
  3. If violations → planner revises (builds v2 by swapping EJ buildings)
  4. Loop until: critic approves OR max_iterations reached
  5. Each iteration appended to trace

The planner and critic are separate LLM calls with different system prompts,
simulating a two-agent review loop without requiring a framework.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent.llm import get_client, get_model_id

from server.tools import (
    backfill,
    check_constraints,
    estimate_savings,
    plan_event,
    rank_candidates,
    score_equity,
    score_socioeconomic,
)
from agent.prompts import CRITIC_SYSTEM, PLANNER_SYSTEM

MAX_ITERATIONS = 3  # planner tries at most 3 revisions before giving up

# Build the tool definitions the LLM will call
# (In production these come from the MCP server registry; here we define them inline
#  since we're calling the Python functions directly in the same process.)
PLANNER_TOOLS = [
    {
        "name": "plan_event",
        "description": (
            "Assemble a demand-response portfolio meeting target_mw under the EJ cap. "
            "Returns portfolio, achieved_mw, ej_share_pct, and reachable flag."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_mw": {"type": "number"},
                "ej_cap_pct": {"type": "number", "default": 0.35},
                "current_temp_f": {"type": "number", "default": 85.0},
                "exclude_building_ids": {"type": "array", "items": {"type": "string"}},
                "prev_event_building_ids": {"type": "array", "items": {"type": "string"}},
                "respect_ej_cap": {"type": "boolean", "description": "False for the naive first pass (ignores EJ cap); True for the equity-corrected re-plan."},
            },
            "required": ["target_mw"],
        },
    },
    {
        "name": "check_constraints",
        "description": (
            "Validate a portfolio against equity cap, cooldown, and protected-facility rules. "
            "Returns passed (bool) and a violations list."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "building_ids": {"type": "array", "items": {"type": "string"}},
                "target_mw": {"type": "number"},
                "ej_cap_pct": {"type": "number", "default": 0.35},
                "current_temp_f": {"type": "number", "default": 85.0},
                "prev_event_building_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["building_ids", "target_mw"],
        },
    },
    {
        "name": "score_equity",
        "description": "Compute EJ share % for a list of building ids.",
        "input_schema": {
            "type": "object",
            "properties": {
                "building_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["building_ids"],
        },
    },
    {
        "name": "score_socioeconomic",
        "description": (
            "Summarize the socioeconomic makeup of a portfolio: load share by "
            "affluence tier, commercial share, and low-income residential share "
            "with a fairness_read. Use this to confirm the plan leans on those "
            "who can afford a reduction and spares low-income residents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "building_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["building_ids"],
        },
    },
    {
        "name": "rank_candidates",
        "description": "Rank eligible buildings by socioeconomic priority then load.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_mw": {"type": "number"},
                "ej_cap_pct": {"type": "number"},
                "current_temp_f": {"type": "number"},
                "exclude_building_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["target_mw"],
        },
    },
]

TOOL_FN_MAP: dict[str, Any] = {
    "plan_event": plan_event,
    "check_constraints": check_constraints,
    "score_equity": score_equity,
    "score_socioeconomic": score_socioeconomic,
    "rank_candidates": rank_candidates,
}


def _clean_narration(text: str) -> str:
    """Strip code fences / JSON blocks so only prose lands in the trace."""
    t = text.strip()
    if "```" in t:
        # drop fenced blocks; keep any prose outside them
        parts = t.split("```")
        prose = "".join(p for i, p in enumerate(parts) if i % 2 == 0).strip()
        t = prose or ""
    # if it still looks like JSON, discard it
    if t.startswith("{") or t.startswith("["):
        return ""
    # collapse to a single line
    t = " ".join(t.split())
    # strip leading markdown-bold labels like **Trace entry for v1:**
    import re as _re
    t = _re.sub(r"^\*\*[^*]+\*\*:?\s*", "", t)
    # strip a leading "Something:" label up to ~40 chars
    t = _re.sub(r"^[A-Z][A-Za-z0-9 ]{0,40}:\s*", "", t)
    t = t.strip('"').strip("'").strip()
    return t


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _call_tool(name: str, args: dict) -> dict:
    fn = TOOL_FN_MAP.get(name)
    if fn is None:
        return {"error": f"unknown tool {name!r}"}
    return fn(**args)


@dataclass
class TraceStep:
    ts: str
    kind: str  # "forecast" | "plan" | "constraint_check" | "self_correct"
    summary: str
    plan_version: int | None = None
    tool_name: str | None = None
    tool_args: dict | None = None
    tool_result: dict | None = None
    rejected_by: str | None = None


@dataclass
class EventPlan:
    version: int
    target_mw: float
    achieved_mw: float
    building_count: int
    ej_share_pct: float
    ej_cap_pct: float
    reachable: bool
    tradeoff: str | None
    portfolio: list[dict]
    source_id: str


@dataclass
class PlanResult:
    approved: bool
    final_plan: EventPlan | None
    trace: list[TraceStep]
    iterations: int
    critic_reason: str | None = None


def run_planner(
    target_mw: float,
    ej_cap_pct: float = 0.35,
    current_temp_f: float = 85.0,
    exclude_building_ids: list[str] | None = None,
    prev_event_building_ids: list[str] | None = None,
    window_label: str = "today 3:30\u20136:30 PM",
) -> PlanResult:
    """
    Run the planner -> critic loop and return a PlanResult with a full trace.

    Deterministic scaffold (reliable for the demo):
      Phase 1  naive plan (respect_ej_cap=False) -> critic check
      Phase 2  if v1 violated the cap, equity-corrected plan
               (respect_ej_cap=True) -> critic check

    The LLM narrates each plan and the critic's verdict (so the trace carries
    real model reasoning), but the control flow is fixed so the v1-rejected ->
    v2-approved arc appears on every run where the naive plan busts the cap.
    """
    client = get_client()
    trace: list[TraceStep] = []

    excl = list(exclude_building_ids or [])
    prev = list(prev_event_building_ids or [])

    # Forecast step
    trace.append(TraceStep(
        ts=_ts(),
        kind="forecast",
        summary=f"Peak forecast for {window_label}. Target {target_mw} MW. Planning.",
    ))

    def _narrate(system: str, prompt: str) -> str:
        """Ask the LLM for a one-line narration; never fatal if it fails."""
        try:
            resp = client.messages.create(
                model=get_model_id(),
                max_tokens=300,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
            return _clean_narration(text)
        except Exception:  # noqa: BLE001 — narration is best-effort
            return ""

    def _to_plan(raw: dict, version: int) -> EventPlan:
        return EventPlan(
            version=version,
            target_mw=target_mw,
            achieved_mw=raw.get("achieved_mw", 0),
            building_count=raw.get("building_count", 0),
            ej_share_pct=raw.get("ej_share_pct", 0),
            ej_cap_pct=ej_cap_pct * 100,
            reachable=raw.get("reachable", False),
            tradeoff=raw.get("tradeoff"),
            portfolio=raw.get("portfolio", []),
            source_id=raw.get("source_id", ""),
        )

    def _check(plan: EventPlan) -> dict:
        return check_constraints(
            building_ids=[b["building_id"] for b in plan.portfolio],
            target_mw=target_mw,
            ej_cap_pct=ej_cap_pct,
            current_temp_f=current_temp_f,
            prev_event_building_ids=prev,
        )

    def _run_phase(version: int, respect_cap: bool) -> tuple[EventPlan, dict]:
        raw = plan_event(
            target_mw=target_mw,
            ej_cap_pct=ej_cap_pct,
            current_temp_f=current_temp_f,
            exclude_building_ids=excl,
            prev_event_building_ids=prev,
            respect_ej_cap=respect_cap,
        )
        plan = _to_plan(raw, version)
        narration = _narrate(
            PLANNER_SYSTEM,
            f"You produced plan v{version} via the plan_event tool: "
            f"{plan.building_count} buildings, {plan.achieved_mw:.1f} MW, "
            f"EJ share {plan.ej_share_pct:.1f}% against a {ej_cap_pct*100:.0f}% cap. "
            f"Respond with ONLY one plain sentence for the operator trace \u2014 "
            f"no label, no preamble, no quotes, no markdown.",
        )
        trace.append(TraceStep(
            ts=_ts(),
            kind="plan",
            summary=(
                narration
                or f"Plan v{version}: {plan.building_count} buildings, "
                   f"{plan.achieved_mw:.1f} MW, EJ share {plan.ej_share_pct:.1f}%"
            ),
            plan_version=version,
            tool_name="plan_event",
            tool_args={"target_mw": target_mw, "ej_cap_pct": ej_cap_pct,
                       "respect_ej_cap": respect_cap},
            tool_result=raw,
        ))
        result = _check(plan)
        passed = result.get("passed", False) and plan.reachable
        trace.append(TraceStep(
            ts=_ts(),
            kind="constraint_check",
            summary=(
                f"Constraint check v{version}: {'PASSED' if passed else 'FAILED'} \u2014 "
                + ("; ".join(v.get("detail", v.get("type", ""))
                             for v in result.get("violations", [])) or "no violations")
            ),
            plan_version=version,
            tool_name="check_constraints",
            tool_result=result,
        ))
        return plan, result

    # --- Phase 1: naive plan (ignores EJ cap) ---
    v1, v1_result = _run_phase(version=1, respect_cap=False)
    v1_violations = v1_result.get("violations", [])
    v1_ok = v1_result.get("passed", False) and v1.reachable

    if v1_ok:
        trace.append(TraceStep(
            ts=_ts(), kind="plan", plan_version=1,
            summary=(f"Critic approved v1. EJ share {v1.ej_share_pct:.1f}%, "
                     f"{v1.achieved_mw:.1f} MW."),
        ))
        return PlanResult(approved=True, final_plan=v1, trace=trace, iterations=1)

    # Critic rejects v1
    reason = "; ".join(v.get("detail", v.get("type", "")) for v in v1_violations) \
             or "unreachable under current cap"
    rejected_by = v1_violations[0].get("type", "constraint") if v1_violations else "unreachable"
    critic_note = _narrate(
        CRITIC_SYSTEM,
        f"Plan v1 has EJ share {v1.ej_share_pct:.1f}% against a "
        f"{ej_cap_pct*100:.0f}% cap and these violations: {reason}. "
        f"Reply with ONE plain-English sentence only \u2014 no JSON, no code "
        f"blocks \u2014 rejecting it and saying load should shift off EJ zips.",
    )
    trace.append(TraceStep(
        ts=_ts(), kind="self_correct", plan_version=1, rejected_by=rejected_by,
        summary=(critic_note
                 or f"Critic rejected v1: {reason}. Shifting load off EJ zips; planning v2."),
    ))

    # --- Phase 2: equity-corrected plan ---
    v2, v2_result = _run_phase(version=2, respect_cap=True)
    v2_ok = v2_result.get("passed", False) and v2.reachable

    if v2_ok:
        trace.append(TraceStep(
            ts=_ts(), kind="plan", plan_version=2,
            summary=(f"Critic approved v2. EJ share {v2.ej_share_pct:.1f}%, "
                     f"{v2.achieved_mw:.1f} MW."),
        ))
        return PlanResult(approved=True, final_plan=v2, trace=trace, iterations=2)

    # v2 still not acceptable -> explicit unreachable / trade-off
    v2_reason = "; ".join(v.get("detail", v.get("type", "")) for v in v2_result.get("violations", [])) \
                or (v2.tradeoff or "target unreachable under the equity cap")
    trace.append(TraceStep(
        ts=_ts(), kind="self_correct", plan_version=2,
        summary=f"v2 cannot satisfy the target under the cap: {v2_reason}",
    ))
    return PlanResult(
        approved=False, final_plan=v2, trace=trace, iterations=2,
        critic_reason=v2_reason,
    )
