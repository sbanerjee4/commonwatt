.PHONY: setup db test mcp chat demo serve check-bedrock sms presubmit evidence

PY ?= python3

# Install Python dependencies
setup:
	pip install -e .

# Create/upgrade the database schema and seed placeholder territory + demo accounts
db:
	PYTHONPATH=. $(PY) -m alembic upgrade head
	PYTHONPATH=. $(PY) -m db.seed

# Run all tests (MCP tool properties, BFF, SMS/chat; no LLM calls, no real SMS)
test:
	PYTHONPATH=. $(PY) -m pytest tests/ -v

# Start the Commonwatt MCP server (stdio mode — the same server Kiro registers)
mcp:
	PYTHONPATH=. $(PY) -m server.tools

# Start the API the front-end talks to (single FastAPI app, binds to 127.0.0.1)
serve:
	PYTHONPATH=. $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port 8000

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

# Start the SMS/chat app (Twilio webhook at /sms/inbound, chat + push routes) on :8001
sms:
	SMS_PROVIDER=$${SMS_PROVIDER:-simulated} PYTHONPATH=. $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Deterministic pre-submit checks (read-only)
presubmit:
	./scripts/presubmit.sh

# Append an evidence snapshot to KIRO.md
evidence:
	./scripts/evidence.sh
