.PHONY: setup demo test mcp chat

# Install Python dependencies
setup:
	pip install -e ".[dev]" 2>/dev/null || pip install fastmcp anthropic hypothesis pytest pytest-asyncio python-dotenv

# Run property-based tests (no LLM calls — pure tool tests)
test:
	PYTHONPATH=. pytest tests/properties/ -v

# Start the MCP server (stdio mode for Kiro integration)
mcp:
	PYTHONPATH=. python -m mcp.tools

# Run the building chat agent interactively (requires ANTHROPIC_API_KEY)
# Usage: make chat BUILDING=129860
BUILDING ?= 129860
chat:
	PYTHONPATH=. python -m agent.chat $(BUILDING)

# Demo: run a planner loop against the fixture data (requires ANTHROPIC_API_KEY)
demo:
	PYTHONPATH=. python -c "\
import os, json; \
from agent.planner import run_planner; \
result = run_planner(target_mw=10.0, ej_cap_pct=0.35, current_temp_f=88.0); \
print('Approved:', result.approved); \
print('Iterations:', result.iterations); \
plan = result.final_plan; \
print(f'Plan: {plan.achieved_mw:.1f} MW, {plan.building_count} buildings, EJ share {plan.ej_share_pct:.1f}%') if plan else print('No plan'); \
print('\\nTrace:'); \
[print(f'  [{s.kind}] {s.summary}') for s in result.trace] \
"
