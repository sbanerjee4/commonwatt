# Commonwatt

> Keep the grid up without leaning on the same neighborhoods twice.

## Track

Climate

## One-line description

An equity-constrained demand-response planner for Massachusetts utilities: it
decides which buildings to ask to reduce load on a peak day, keeps the burden
off the same neighborhoods, and leaves every call to a human.

## What it does

On a peak heat day, utilities ask enrolled buildings to reduce electricity load
for a few hours. Commonwatt puts an equity constraint into that dispatch
decision: no more than a set share of the load may come from Environmental
Justice (EJ) zip codes, no building is called two events in a row, and
protected facilities (schools, nursing homes) are shielded on the hottest days.
An AI planner proposes a portfolio, a critic checks it against those rules, and
the operator approves, edits, or rejects. Nothing leaves the system without a
human.

## Architecture

```
Browser SPA  ──HTTP──>  BFF (FastAPI)  ──calls──>  Commonwatt MCP tools  ──reads──>  BERDO data
  (web/)                 (bff/app.py)              (server/tools.py)              (fixtures/berdo.json)
                              │
                              └── Planner + Critic agents (agent/) ── Claude via Amazon Bedrock
```

- **`server/`** — the Commonwatt MCP server: 9 deterministic, property-tested
  tools. No model calls inside; every number carries a `source_id`.
- **`agent/`** — the planner/critic loop and the building chat agent (Claude via
  Amazon Bedrock).
- **`bff/`** — a thin FastAPI backend-for-frontend the SPA talks to.
- **`fixtures/berdo.json`** — 2,472 Boston BERDO buildings, pulled once from the
  public datastore and committed so the app runs offline.
- **`.kiro/`** — specs, steering, hooks, MCP registration, decisions log.

## Setup

Requires Python 3.12+.

```
make setup
```

For the LLM features (building chat, planner loop) you need Amazon Bedrock
access. Copy `.env.example` to `.env` and fill in a Bedrock API key:

```
cp .env.example .env
# edit .env: set AWS_BEARER_TOKEN_BEDROCK and AWS_REGION
make check-bedrock      # prints PASS when the key + region + model work
```

The map and data endpoints work without any key; only chat + planner need Bedrock.

## Run the demo

Run the planner/critic loop and watch the equity self-correction in the trace:

```
make demo
```

This plans a 20 MW event under a 35% EJ cap. The naive first plan (v1) over-calls
EJ zips at 38.7%, the critic rejects it, and the planner shifts load to produce a
compliant v2 — the full "v1 rejected -> v2 approved" story, printed as a trace.

Start the BFF API the front-end talks to:

```
make bff        # serves on http://127.0.0.1:8000
```

Chat with a building's assistant:

```
make chat BUILDING=129860
```

## API endpoints (BFF)

Read-only unless noted. Every numeric field carries a `source_id`.

| Method | Path | Returns |
| ------ | ---- | ------- |
| GET  | `/health` | status + building count |
| GET  | `/zips` | per-zip aggregates for the choropleth |
| GET  | `/zips/{zip}/buildings` | building markers for a zip drill-in |
| GET  | `/buildings/{id}` | one building's full profile |
| GET  | `/savings?shed_mw=&hours=` | three savings counters (estimated, sourced) |
| GET  | `/recruitment?top_n=` | high-load unenrolled EJ buildings |
| POST | `/event/draft` | run the planner/critic loop (needs Bedrock) |
| POST | `/building/{id}/chat` | one facility-manager chat turn (needs Bedrock) |

## Tests

```
make test       # 20 tests: 9 property-based + 11 BFF endpoint tests
```

The suite runs without Bedrock (the two LLM endpoints are mocked). Property
tests encode the spec invariants: EJ share never exceeds the cap, portfolios
meet the target or return an explicit "unreachable", savings are monotonic in MW
shed and zero at zero, and backfill never re-adds a declined building.

## Data source

Boston BERDO 2021 building emissions dataset, resource
`43e4abc9-1fae-40d9-a02e-ff950bd0e732` on data.boston.gov (public, keyless).
Program rates, capacity prices, and emissions factors are cited one-per-constant
in `server/constants.py`.

## Demo URL

TODO

## Video

TODO

## Team and Representative

TODO
