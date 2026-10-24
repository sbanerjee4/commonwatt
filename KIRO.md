# How we used Kiro

## Kiro tools used (IDE, CLI, Web, Crew)

TODO (team: compare IDE / CLI / Web / Crew with screenshots)

Evidence: TODO (screenshot path)

## Spec-driven development

The project spec was committed before implementation under
`.kiro/specs/project/` (`requirements.md`, `design.md`, `tasks.md`). The LLM
backend was built against that spec: the BFF view-model contracts in
`design.md` (ZipAggregate, BuildingMarker, EventPlan, TraceStep,
SavingsCounter) are implemented in `bff/app.py`, and the equity/safety rules in
the spec are enforced by `server/tools.py`.

Evidence: `git log` on branch `nicole-llm`; spec files predate the code commits.

## Agent hooks

`.kiro/hooks/run-tests-on-save.kiro.hook` runs the property-based + BFF test
suite whenever a file under `server/`, `agent/`, `bff/`, or `tests/` is saved,
so a broken invariant (EJ cap, savings monotonicity, etc.) is caught the moment
it is introduced.

Evidence: `.kiro/hooks/run-tests-on-save.kiro.hook`; screenshot of it firing TODO.

## Steering docs

Three always-on steering files shaped the backend:
- `safety.md` changed output most — it banned "curtail/cut/shut off" wording, so
  the building chat agent and planner say "asked to reduce" / "event
  participation" instead. Verified live in the chat agent's responses.
- `provenance.md` drove the rule that every tool result carries a `source_id`
  and that savings are always labeled "estimated"; enforced in `server/tools.py`
  and surfaced through the BFF.
- `stack.md` set the layout (`server/` tools, `agent/` planner+critic, PBT in
  `tests/properties/`) and the "property test before wiring a tool" rule.

Evidence: chat transcript (Shore Plaza East reply uses "reduce", never "cut");
`server/constants.py` keeps every rate with one citation.

## MCP

The Commonwatt MCP server (`server/tools.py`, FastMCP) exposes 9 deterministic
tools: estimate_load, rank_candidates, check_constraints, score_equity,
plan_event, backfill, estimate_savings, recruitment_list, building_info. It is
registered in `.kiro/settings/mcp.json` for use during development, and the same
tools are called by the app at runtime through the BFF and the planner loop.

Evidence: `.kiro/settings/mcp.json`; the trace panel shows the same tool names
(plan_event, check_constraints) that Kiro sees.

## Property-based testing

`tests/properties/test_mcp_invariants.py` encodes the spec invariants with
Hypothesis: portfolio >= target or an explicit "unreachable" (never silently
short), EJ share <= cap on every plan, savings monotonic in MW shed and zero at
zero, every savings counter carries a source_id, backfill never re-adds a
declined building, and protected facilities are excluded above the heat
threshold. 9 property tests + 11 BFF tests, all green.

Evidence: `make test` -> 20 passed.

## Kiro powers

TODO (team: list the bundled powers used and what each saved)

Evidence: TODO (screenshot path)
