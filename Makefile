.PHONY: setup test mcp chat demo bff check-bedrock

PY ?= python3

# Install Python dependencies
setup:
	pip install -e . 2>/dev/null || pip install fastmcp anthropic hypothesis pytest pytest-asyncio python-dotenv fastapi "uvicorn[standard]" httpx

# Run all tests (property-based tool tests + BFF endpoint tests; no LLM calls)
test:
	PYTHONPATH=. $(PY) -m pytest tests/ -v

# Start the Commonwatt MCP server (stdio mode — the same server Kiro registers)
mcp:
	PYTHONPATH=. $(PY) -m server.tools

# Start the BFF API the front-end talks to (binds to 127.0.0.1)
bff:
	PYTHONPATH=. $(PY) -m uvicorn bff.app:app --host 127.0.0.1 --port 8000

# Verify the Bedrock key + region + model access are working
check-bedrock:
	PYTHONPATH=. $(PY) -m agent.check_bedrock

# Chat with the building agent (requires Bedrock). Usage: make chat BUILDING=129860
BUILDING ?= 129860
chat:
	PYTHONPATH=. $(PY) -m agent.chat $(BUILDING)

# Demo: run the planner/critic loop and print the trace (requires Bedrock).
# Uses a target+cap that triggers the v1-rejected -> v2-approved equity story.
demo:
	PYTHONPATH=. $(PY) -c "\
from agent.planner import run_planner; \
r = run_planner(target_mw=20.0, ej_cap_pct=0.35, current_temp_f=88.0); \
print('Approved:', r.approved, '| iterations:', r.iterations); \
p = r.final_plan; \
print(f'Final plan v{p.version}: {p.achieved_mw:.1f} MW, {p.building_count} buildings, EJ share {p.ej_share_pct:.1f}%') if p else print('No plan'); \
print(); print('Trace:'); \
[print(f'  [{s.kind}] {s.summary}') for s in r.trace]"
