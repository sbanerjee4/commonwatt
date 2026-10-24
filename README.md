# Commonwatt

> Keep the grid up without leaning on the same neighborhoods twice.

## Track

Climate

## One-line description

An equity-constrained demand-response planner for Massachusetts utilities: it
decides which buildings to ask to reduce load on a peak day, leans on the ones that can most afford it, spares lower-income neighborhoods, keeps the burden
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

- **`server/`** — the Commonwatt MCP server: 11 deterministic, property-tested
  tools. No model calls inside; every number carries a `source_id`.
- **`agent/`** — the planner/critic loop and the building chat agent (Claude via
  Amazon Bedrock).
- **`bff/`** — the single FastAPI app (app/main.py) the SPA talks to; portfolio/map/planner routes live in app/routes/portfolio.py.
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
make serve      # serves on http://127.0.0.1:8000
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
| GET  | `/portfolio/buildings/{id}` | one building's full profile |
| GET  | `/savings?shed_mw=&hours=` | three savings counters (estimated, sourced) |
| GET  | `/recruitment?top_n=` | high-load unenrolled EJ buildings |
| POST | `/event/draft` | run the planner/critic loop (needs Bedrock) |
| POST | `/portfolio/building/{id}/chat` | one facility-manager chat turn (needs Bedrock) |

## Tests

```
make test       # 58 tests: 16 property-based + BFF + auth/chat/SMS
```

The suite runs without Bedrock (the two LLM endpoints are mocked). Property
tests encode the spec invariants: EJ share never exceeds the cap, portfolios
meet the target or return an explicit "unreachable", savings are monotonic in MW
shed and zero at zero, and backfill never re-adds a declined building.

## Data source

Boston BERDO 2021 building emissions dataset, resource
`43e4abc9-1fae-40d9-a02e-ff950bd0e732` on data.boston.gov (public, keyless).
Socioeconomic weighting uses US Census ACS median household income by zip (table B19013); the map uses the US Census Geocoder for building lat/long. Program rates, capacity prices, and emissions factors are cited one-per-constant
in `server/constants.py`.

## Demo URL

https://commonwatt.vercel.app/

## Video

TODO

## Team and Representative

Sanchali Banerjee
Sophie Cheung
Nicole Zheng

---

## SMS Notifications (Twilio)

Outbound asks to building managers and alerts to operators, plus an inbound
reply webhook. Two providers behind one interface: **simulated** (default — no
network, used by tests and `make demo`) and **twilio** (real send).

### Setup

```bash
make setup     # venv + deps
make test      # runs with the simulated provider; no SMS sent
```

### Configuration

Copy `.env.example` to `.env` (git-ignored) and fill it in. Never commit `.env`.

| Variable | Meaning |
|---|---|
| `SMS_PROVIDER` | `simulated` (default) or `twilio` |
| `SMS_DEMO_MODE` | `true` → real sends go ONLY to `SMS_DEMO_ALLOWLIST` |
| `SMS_DEMO_ALLOWLIST` | Comma-separated E.164 numbers (e.g. `+15551234567`) |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID (`AC...`) |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token |
| `TWILIO_FROM_NUMBER` | Your Twilio number, E.164 |
| `SMS_WEBHOOK_URL` | Public URL of `/sms/inbound`, for signature validation |

Keep `SMS_DEMO_MODE=true` until you trust the flow: real Twilio sends, but a
bug cannot text anyone outside the allowlist.

### Templates

Four plain-text templates (`notify/templates.py`), each ≤160 chars and checked
at import for forbidden language:

- `building_ask` — asks a building manager to reduce load for an event
- `operator_draft_ready` — a draft event is ready to approve
- `operator_backfill` — declines dropped capacity, backfill proposed
- `operator_unreachable` — target not reachable under the EJ cap

**Safety:** no template or rendered body may contain `cut`, `shut off`,
`curtail`, or `disconnect`. Enforced by `validate_templates()` and re-checked
after substitution; the import fails fast if violated.

### Sending

`notify.send_sms(user_id, template, params, event_id=None)` is the one choke
point. It skips (with an audit row, never calling the provider) when the user
has no phone, has opted out, or — for `building_ask` — is not in the event.

### Inbound webhook

`POST /sms/inbound` (`app/routes/sms.py`) validates the `X-Twilio-Signature`
(rejects with 403 on mismatch), looks up the sender by phone, then:

- `STOP` / `START` → toggles `sms_opted_out`
- `YES` / `NO` / a number of kW → records a reply against the building's open
  approved event
- unknown sender / unknown body / no active event → a safe reply, always 200

Every branch writes an `audit_log` row. Run the app with
`uvicorn app.main:app`.

