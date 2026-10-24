---
inclusion: always
---

# Stack and conventions

## Language and tooling
- Use Python 3.12, FastMCP, pytest, Hypothesis.
- Use React + TypeScript + MapLibre for the UI; SQLite for state.

## Project layout
- Put the server in mcp/, planner and critic in agent/, the simulator in sim/.
- Put the UI in web/, seeded data in fixtures/, Hypothesis tests in tests/properties/.

## Testing
- Keep every MCP tool deterministic and pure given its inputs; no model calls inside tools.
- Give every new tool a property-based test before wiring it to the agent.

## Running
- Keep make setup, make test, make demo working; they are the only entry points.

## Geography
- Use the zip-code choropleth as the primary aggregate layer; the equity and burden story is zip-level.
- Drill into a zip to plot its buildings as markers at their geocoded address points (AC-11b).
- Geocoding each address to a point is a backend concern; the front-end consumes already-geocoded buildings.
- List zips missing geometry and buildings that fail geocoding in a side panel; never silently drop them (AC-12, AC-12b).

## Style
- Write trace events as JSON lines: ts, step, tool, args, result_summary, version.
- Use Conventional Commits; never commit with failing tests.
