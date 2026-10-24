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
- Use zip-level geography only; never place a building at a street address.

## Style
- Write trace events as JSON lines: ts, step, tool, args, result_summary, version.
- Use Conventional Commits; never commit with failing tests.
