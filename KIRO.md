# How we used Kiro

## Kiro tools used (IDE, CLI, Web, Crew)

TODO (team: compare IDE / CLI / Web / Crew with screenshots)

Evidence: TODO (screenshot path)

## Spec-driven development

The project spec was committed before implementation under
`.kiro/specs/project/` (`requirements.md`, `design.md`, `tasks.md`). The LLM
backend was built against that spec: the BFF view-model contracts in
`design.md` (ZipAggregate, BuildingMarker, EventPlan, TraceStep,
SavingsCounter) are implemented in `app/routes/portfolio.py`, and the equity/safety rules in
the spec are enforced by `server/tools.py`.

Evidence: `git log`; the spec files were committed before the implementation commits.

## Agent hooks

`.kiro/hooks/run-tests-on-save.kiro.hook` runs the property-based + BFF test
suite whenever a file under `server/`, `agent/`, `app/`, or `tests/` is saved,
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

The Commonwatt MCP server (`server/tools.py`, FastMCP) exposes 11 deterministic
tools: estimate_load, rank_candidates, check_constraints, score_equity,
plan_event, backfill, estimate_savings, recruitment_list, building_info, score_socioeconomic, local_conditions. It is
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
threshold. 16 property tests plus BFF, auth, chat, and SMS tests: 58 total, all green.

Evidence: `make test` -> 58 passed.

## Kiro powers

TODO (team: list the bundled powers used and what each saved)

Evidence: TODO (screenshot path)

## Demo script (for the 2:30 video)

A reliable end-to-end run that shows the whole story:

1. **Utility dashboard** (`/utility`): the Boston map with ~2,289 building
   circles. Switch "Group by" to **Equity (income)** — amber downtown
   (high-income, asked first), teal in Roxbury / Dorchester / Mattapan
   (low-income, protected). Click a circle to show its real data (address,
   income tier, curtailable load, EJ flag).
2. **Draft an event**: set a target on the operator card and hit **Draft
   event**. The agent trace shows plan v1 over-calling the EJ cap, the critic
   rejecting it, and the corrected v2 that shifts load to commercial /
   higher-income buildings — then **Approve**.
3. **Facility manager** (`/building`): open the chat and ask "how much could we
   reduce?" — the assistant answers from the building's real metered data.
4. **Kiro cut**: the committed spec, a hook firing, the property tests passing
   (`make test` -> 58), and the Commonwatt MCP server in both Kiro and the app.

Headless fallback if the UI is flaky on the day: `make demo` prints the full
v1-rejected -> v2-approved equity trace in the terminal.
