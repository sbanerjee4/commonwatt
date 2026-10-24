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

import anthropic

from server.tools import (
    backfill,
    check_constraints,
    estimate_savings,
    plan_event,
    rank_candidates,
    score_equity,
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
        "name": "rank_candidates",
        "description": "Rank eligible buildings by curtailable load.",
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
    "rank_candidates": rank_candidates,
}


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
    window_label: str = "today 3:30–6:30 PM",
) -> PlanResult:
    """
    Run the planner → critic loop and return a PlanResult with a full trace.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    trace: list[TraceStep] = []
    version = 0
    current_plan: EventPlan | None = None
    extra_exclude: list[str] = list(exclude_building_ids or [])

    # Forecast step
    trace.append(TraceStep(
        ts=_ts(),
        kind="forecast",
        summary=f"Peak forecast for {window_label}. Target {target_mw} MW. Planning.",
        tool_name=None,
    ))

    for iteration in range(MAX_ITERATIONS):
        version += 1

        # --- Planner call ---
        planner_messages = [
            {
                "role": "user",
                "content": (
                    f"Plan a demand-response event.\n"
                    f"Target: {target_mw} MW\n"
                    f"EJ cap: {ej_cap_pct*100:.0f}%\n"
                    f"Current temperature: {current_temp_f}°F\n"
                    f"Window: {window_label}\n"
                    f"Exclude buildings: {extra_exclude}\n"
                    f"Previous event buildings: {prev_event_building_ids or []}\n\n"
                    f"Call plan_event first, then check_constraints on the result."
                ),
            }
        ]

        plan_raw: dict | None = None
        constraint_raw: dict | None = None

        # Agentic loop: let planner call tools
        while True:
            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=4096,
                system=PLANNER_SYSTEM,
                tools=PLANNER_TOOLS,
                messages=planner_messages,
            )

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = _call_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                        # Capture plan and constraint results
                        if block.name == "plan_event":
                            plan_raw = result
                            trace.append(TraceStep(
                                ts=_ts(),
                                kind="plan",
                                summary=(
                                    f"Plan v{version}: {result.get('building_count', 0)} buildings, "
                                    f"{result.get('achieved_mw', 0):.1f} MW achieved, "
                                    f"EJ share {result.get('ej_share_pct', 0):.1f}%"
                                ),
                                plan_version=version,
                                tool_name="plan_event",
                                tool_args={"target_mw": target_mw, "ej_cap_pct": ej_cap_pct},
                                tool_result=result,
                            ))
                        elif block.name == "check_constraints":
                            constraint_raw = result
                            trace.append(TraceStep(
                                ts=_ts(),
                                kind="constraint_check",
                                summary=(
                                    f"Constraint check v{version}: "
                                    f"{'PASSED' if result.get('passed') else 'FAILED'} — "
                                    + (
                                        "; ".join(v.get("detail", v.get("type", "")) for v in result.get("violations", []))
                                        or "no violations"
                                    )
                                ),
                                plan_version=version,
                                tool_name="check_constraints",
                                tool_result=result,
                            ))

                planner_messages.append({"role": "assistant", "content": response.content})
                planner_messages.append({"role": "user", "content": tool_results})

            else:
                # end_turn — planner is done
                break

        if plan_raw is None:
            break  # planner failed to produce a plan

        current_plan = EventPlan(
            version=version,
            target_mw=target_mw,
            achieved_mw=plan_raw.get("achieved_mw", 0),
            building_count=plan_raw.get("building_count", 0),
            ej_share_pct=plan_raw.get("ej_share_pct", 0),
            ej_cap_pct=ej_cap_pct * 100,
            reachable=plan_raw.get("reachable", False),
            tradeoff=plan_raw.get("tradeoff"),
            portfolio=plan_raw.get("portfolio", []),
            source_id=plan_raw.get("source_id", ""),
        )

        # --- Critic call ---
        portfolio_ids = [b["building_id"] for b in current_plan.portfolio]
        critic_input = {
            "building_ids": portfolio_ids,
            "target_mw": target_mw,
            "ej_cap_pct": ej_cap_pct,
            "current_temp_f": current_temp_f,
            "prev_event_building_ids": prev_event_building_ids or [],
        }
        constraint_result = check_constraints(**critic_input)

        critic_messages = [
            {
                "role": "user",
                "content": (
                    f"Review this demand-response plan v{version}:\n"
                    f"Achieved: {current_plan.achieved_mw:.1f} MW / {target_mw} MW target\n"
                    f"EJ share: {current_plan.ej_share_pct:.1f}% (cap: {ej_cap_pct*100:.0f}%)\n"
                    f"Buildings: {current_plan.building_count}\n"
                    f"Reachable: {current_plan.reachable}\n"
                    f"Constraint check result: {json.dumps(constraint_result, indent=2)}\n\n"
                    f"Approve or reject with reason."
                ),
            }
        ]

        critic_response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=CRITIC_SYSTEM,
            messages=critic_messages,
        )

        critic_text = "".join(
            block.text for block in critic_response.content if hasattr(block, "text")
        )

        # Parse critic decision
        approved = constraint_result.get("passed", False) and current_plan.reachable
        violations = constraint_result.get("violations", [])
        critic_reason: str | None = None

        if violations:
            critic_reason = "; ".join(v.get("detail", v.get("type", "")) for v in violations)
            rejected_by = violations[0].get("type", "constraint") if violations else None
            trace.append(TraceStep(
                ts=_ts(),
                kind="self_correct",
                summary=f"Critic rejected v{version}: {critic_reason}. Planning v{version+1}.",
                plan_version=version,
                rejected_by=rejected_by,
            ))

            # Build revised exclusion list: remove EJ buildings from the plan
            ej_in_plan = [
                b["building_id"] for b in current_plan.portfolio if b.get("is_ej")
            ]
            # Remove a batch of EJ buildings to reduce EJ share on next iteration
            n_to_swap = max(1, len(ej_in_plan) // 2)
            extra_exclude = list(set(extra_exclude) | set(ej_in_plan[:n_to_swap]))

        else:
            trace.append(TraceStep(
                ts=_ts(),
                kind="plan",
                summary=f"Critic approved v{version}. EJ share {current_plan.ej_share_pct:.1f}%, {current_plan.achieved_mw:.1f} MW.",
                plan_version=version,
            ))
            return PlanResult(
                approved=True,
                final_plan=current_plan,
                trace=trace,
                iterations=iteration + 1,
                critic_reason=None,
            )

    # Exhausted iterations
    return PlanResult(
        approved=False,
        final_plan=current_plan,
        trace=trace,
        iterations=MAX_ITERATIONS,
        critic_reason=critic_reason or "max iterations reached",
    )
