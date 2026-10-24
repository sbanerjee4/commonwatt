---
inclusion: fileMatch
fileMatchPattern: ["server/**", "agent/**", "bff/**", "tests/**"]
---

# Backend conventions (server / agent / bff)

## Tools (server/)
- Every tool is deterministic and pure given its inputs. No model calls, no
  randomness, no network inside a tool.
- Every returned number carries a `source_id`. If a value is unavailable,
  return it as `null` with a basis flag ("unknown"), never a fabricated number.
- Give every new tool a Hypothesis property test in `tests/properties/` before
  wiring it into the agent.
- Keep rates, prices, and emissions factors in `server/constants.py`, one
  citation per constant. Never inline a magic number in tool logic.

## Agents (agent/)
- The model plans, calls tools, and explains. It never produces a dispatch
  number itself — numbers come from tool results.
- The planner/critic control flow is deterministic (naive v1 -> critic ->
  equity-corrected v2); the LLM narrates each step. Do not let the LLM decide
  whether the rejection path runs — that must be reliable for the demo.
- Trace steps are structured (ts, kind, summary, plan_version, tool_name,
  rejected_by). Keep both rejected and accepted plan versions in the trace.
- Strip model boilerplate (labels, code fences, JSON) out of any text that
  lands in a user-facing trace summary.

## BFF (bff/)
- The SPA never calls the MCP server or the model directly; it only calls the
  BFF. The BFF shapes tool output into the view-model contracts in
  `design.md`.
- LLM-dependent endpoints import the agent lazily so the data endpoints work
  even when Bedrock is not configured.
- Bind the dev server to 127.0.0.1.

## LLM access
- Claude via Amazon Bedrock (`agent/llm.py`), model id is a cross-region
  inference profile (us.anthropic.*). Auth is a Bedrock API key in `.env`
  (`AWS_BEARER_TOKEN_BEDROCK`), loaded with override=True.
- Never commit a key. `.env`, `*.pdf`, and `key*` are git-ignored.
