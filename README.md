# CommonWatt

**An equity-constrained demand-response planner for the grid — an AI proposes, a human approves, and no neighborhood gets asked twice.**

🔗 **Live demo:** [commonwatt.vercel.app](https://commonwatt.vercel.app/) · **Track:** Climate · **Built end-to-end with [Kiro](https://kiro.dev)**

> On a peak heat day the grid strains, and utilities have two bad options: fire up a fossil peaker plant, or shed load on neighborhoods — and that burden has historically fallen hardest on low-income and environmental-justice communities. CommonWatt makes demand response *fair and auditable*: it asks buildings to voluntarily reduce load, leans on the ones that can most afford it, spares the ones a reduction would hurt most, pays participants, and leaves every decision to a human operator.

---

## Table of contents
- [What it does](#what-it-does)
- [Why it's different](#why-its-different)
- [Demo accounts](#demo-accounts)
- [Built with Kiro](#built-with-kiro)
- [Architecture](#architecture)
- [Stack](#stack)
- [The equity engine](#the-equity-engine)
- [In-app chat with human handoff](#in-app-chat-with-human-handoff)
- [Provenance & safety invariants](#provenance--safety-invariants)
- [Setup & run](#setup--run)
- [API](#api)
- [Tests](#tests)
- [Data sources](#data-sources)
- [Team](#team)

---

## What it does

A utility operator opens a map of Greater Boston built from the **public BERDO building-emissions dataset** (~2,200 real buildings), sets a target (e.g. *reduce 20 MW during the 5–7 PM peak*), and clicks **Draft proposal**. A planner agent assembles a portfolio of buildings to ask; a critic agent checks it against hard equity and safety rules; if the first plan over-burdens protected communities, the planner **self-corrects** and only the corrected plan becomes the proposal. The operator reviews a fully traceable reasoning log and **approves, rejects, or edits** — nothing is sent without that human decision.

On approval, each selected building's manager is contacted in-app. They can reply **yes / no / counter-offer**, ask questions of an assistant that answers **only from their building's real data**, and at any point **ask for a human** — handing the conversation to the operator.

## Why it's different

- **Equity is a hard constraint, not a dashboard metric.** The dispatch optimizer refuses any plan whose environmental-justice load share exceeds the configured cap; when the target is unreachable under the cap, it returns an explicit *"unreachable"* trade-off instead of quietly violating it.
- **The model never invents a number.** Every rate, emissions factor, and building value comes from a deterministic, property-tested tool layer with a citation — the LLM orchestrates, it doesn't fabricate.
- **Human-in-the-loop by construction.** The agent proposes; the operator decides. The system is physically unable to contact a building or export an event without operator approval.

## Demo accounts

Sign in at `/signin` (passwords are demo-only):

| Role | Email | Password | Lands on |
| ---- | ----- | -------- | -------- |
| Utility operator | `utility@demo` | `demo-utility-pass` | Operator workspace — map, planner, approvals, facility conversations |
| Building manager | `building1@demo` | `demo-building-pass` | That building's event + conversation |
| Building manager | `building2@demo` | `demo-building-pass` | " |
| Building manager | `building3@demo` | `demo-building-pass` | " |

> Cold-start note: the backend runs on a free Render instance that sleeps after idle, so the first request after a quiet period may take ~30–60s to wake.

## Built with Kiro

CommonWatt was built **spec-first** with Kiro, across the whole dev lifecycle:

- **Spec-driven development** — requirements, design, and tasks were committed to `.kiro/specs/` *before* implementation. Every feature traces to an acceptance criterion; working from the task list let the team build auth, map, equity dispatch, and chat/handoff in parallel without collisions.
- **Steering as guardrails** — `.kiro/steering/{safety,provenance,stack}.md` are rules the agent never crossed: every user-facing number carries a `source_id`, no message may say "cut" / "shut off" / "curtail" / "disconnect" (it's a *voluntary, paid* program), and generated code stays on the chosen stack.
- **MCP (Model Context Protocol)** — the heart of the app is the **CommonWatt MCP server**: 11 deterministic, property-tested tools (FastMCP). The *same* server Kiro called during development is what the running planner/critic call at runtime — so results are reproducible, explainable, and auditable, with no model calls hidden inside the tools.
- **Agent hooks** — ran the property-based test suite on every save, so a broken equity invariant was caught the instant it appeared rather than in the demo.
- **Property-based testing** — spec invariants became Hypothesis properties (see [below](#tests)).
- **Skills** — the BERDO + Census data-wrangling workflow was crystallized into a reusable Kiro skill for fast re-seeding.
- **Decisions log** — `.kiro/DECISIONS.md` records design trade-offs (e.g. dropping SMS in favor of in-app chat with human handoff).

## Architecture

```
┌─────────────────────┐   HTTP (cookie auth)   ┌──────────────────────┐
│  React 18 SPA (web/)│ ─────────────────────▶ │  FastAPI  (app/)     │
│  MapLibre · TanStack│ ◀───────────────────── │  routes: portfolio,  │
└─────────────────────┘      JSON (sourced)     │  auth, chat, push    │
                                                 └──────────┬───────────┘
                                   planner / critic loop     │ calls
                                   ┌───────────────────────▼───────────────┐
                                   │ agent/  (Claude via Amazon Bedrock)    │
                                   │  planner → critic → self-correct       │
                                   └───────────────────────┬───────────────┘
                                                            │ tool calls (MCP)
                                   ┌───────────────────────▼───────────────┐
                                   │ server/  CommonWatt MCP server          │
                                   │  11 deterministic, property-tested tools│
                                   └───────────────────────┬───────────────┘
                                                            │ reads
                                   ┌───────────────────────▼───────────────┐
                                   │ fixtures/berdo.json  + Census ACS      │
                                   │  (committed public data; runs offline) │
                                   └─────────────────────────────────────────┘
       state: SQLAlchemy 2.0 ORM + Alembic migrations · SQLite (dev) / Postgres (prod)
```

- **`server/`** — the MCP server: 11 pure tools (`plan_event`, `rank_candidates`, `check_constraints`, `estimate_savings`, `score_socioeconomic`, `building_info`, …). No model calls inside; every number carries a `source_id`.
- **`agent/`** — the planner/critic loop and the building-chat agent (Claude via Amazon Bedrock), restricted to the tool-grounded MCP surface.
- **`app/`** — the FastAPI application: cookie-session auth (bcrypt), portfolio/map/savings routes, the planner route, and the in-app chat/handoff routes. SQLAlchemy 2.0 models in `db/`, Alembic migrations in `db/migrations/`.
- **`web/`** — the React + MapLibre SPA (operator workspace and building-manager view).
- **`fixtures/berdo.json`** — real Boston BERDO buildings, pulled once and committed so the app runs offline.
- **`.kiro/`** — specs, steering, hooks, MCP registration, decisions log.

## Stack

| Layer | Tech |
| ----- | ---- |
| Frontend | React 18, TypeScript (strict), Vite, React Router, TanStack Query, MapLibre GL |
| API | FastAPI (Python 3.12), Pydantic, Uvicorn |
| Auth | bcrypt password hashing, HTTP-only `cw_session` cookie (`SameSite=None; Secure` cross-site) |
| Agents | Claude via Amazon Bedrock — planner, critic, and building-chat, tool-grounded |
| Tools | CommonWatt MCP server (FastMCP) — 11 deterministic tools |
| Persistence | SQLAlchemy 2.0 ORM + Alembic; SQLite (dev) / PostgreSQL (prod) |
| Data | Committed public fixtures: BERDO buildings, Census ACS income, Census geocodes |
| Testing | pytest + Hypothesis (property-based) + Vitest; 61 backend tests |
| Deploy | Render (FastAPI + managed Postgres), Vercel (SPA) |
| Built with | **Kiro** — spec-driven dev, MCP, steering, agent hooks, property-based testing, skills |

## The equity engine

The planner ranks candidate buildings by a **socioeconomic priority score** (ask those who can most afford a reduction first — higher-income areas, large commercial/institutional buildings) and assembles a portfolio to hit the MW target. The critic then validates it against hard rules:

1. **EJ cap** — environmental-justice load share must not exceed the configured cap (default 35%).
2. **Cooldown** — no building called in the immediately preceding event.
3. **Protected facilities** — schools in session, cooling centers, and nursing homes are excluded when the heat threshold (95°F) is exceeded.
4. **Reachability** — the portfolio must meet the target, or the system returns an explicit *"unreachable under cap"* trade-off (achievable MW vs. cap) and stops.

Both the **rejected** and **accepted** plan versions are retained in the trace, so the operator can see exactly how and why the agent self-corrected.

## In-app chat with human handoff

Each approved event opens one conversation per building, keyed to `(event, building)`:

- **Auto mode (default):** the building manager's questions are answered by a Bedrock agent grounded strictly in that building's real data — it cannot invent numbers. To the manager, it speaks as the utility (one unified voice).
- **Human handoff:** the manager can request a person at any time (`request-human`); the thread flips to **human** mode, the operator is notified, picks up from the operator console, and the agent falls silent.
- **Safety filter:** on every message, in both modes, banned load-shedding language (`cut`, `disconnect`, …) is rejected — the program is voluntary and paid, and the language reflects that.

Routes: `GET /inbox/{id}`, `POST /inbox/{id}/reply`, `POST /inbox/{id}/request-human`, `POST /inbox/{id}/operator-message`, `POST /inbox/{id}/close`.

## Provenance & safety invariants

- Every user-facing number carries a `source_id`; the frontend refuses to render a value without one.
- Program rates, capacity prices, LMPs, and emissions factors live one-per-constant with a single citation each in `server/constants.py` — never inlined.
- Savings figures are labeled **estimated** with retrievable assumptions; simulated data (enrollment, meter reads, replies) is explicitly marked **simulated** in both code and UI.

## Setup & run

Requires **Python 3.12+** and Node 20+ (for the SPA).

```bash
make setup                       # venv + deps + migrations + seed demo data
```

The map and data endpoints work with **no API key**. For the LLM features (planner loop, building chat) you need Amazon Bedrock access:

```bash
cp .env.example .env             # set AWS_BEARER_TOKEN_BEDROCK and AWS_REGION
make check-bedrock               # prints PASS when key + region + model work
```

Run the demo (watch the equity self-correction in the trace):

```bash
make demo                        # plans a 20 MW event under a 35% EJ cap:
                                 # v1 over-calls EJ zips at 38.7% → critic rejects
                                 # → planner shifts load → v2 approved
```

Serve the API the SPA talks to, and run the frontend:

```bash
make serve                       # FastAPI on http://127.0.0.1:8000
cd web && npm install && npm run dev   # Vite dev server
```

## API

Read-only unless noted. Every numeric field carries a `source_id`.

| Method | Path | Returns |
| ------ | ---- | ------- |
| GET  | `/health` | status + building count |
| GET  | `/zips` | per-zip aggregates for the choropleth |
| GET  | `/zips/{zip}/buildings` | building markers for a zip drill-in |
| GET  | `/portfolio/buildings` | all buildings (map + conversations list) |
| GET  | `/portfolio/buildings/{id}` | one building's full profile |
| GET  | `/savings?shed_mw=&hours=` | three savings counters (estimated, sourced) |
| GET  | `/recruitment?top_n=` | high-load unenrolled EJ buildings, ranked |
| POST | `/event/draft` | run the planner/critic loop (needs Bedrock) |
| POST | `/event/approve` | approve an event; opens a thread + contacts each building |
| GET  | `/inbox/{id}` | the building's conversation + active-event ask |
| POST | `/inbox/{id}/reply` | building manager reply (auto-mode agent answers) |
| POST | `/inbox/{id}/request-human` | flip the thread to human mode |
| POST | `/inbox/{id}/operator-message` | operator takes over (operator-only) |
| POST | `/auth/login` · `/auth/logout` · `GET /auth/me` | cookie-session auth |

## Tests

```bash
make test        # 61 backend tests: property-based + unit + integration
```

The suite runs without Bedrock (LLM endpoints are mocked). Property-based tests (Hypothesis) encode the spec invariants directly:

- EJ load share **never** exceeds the configured cap.
- A portfolio either meets the target **or** returns an explicit *"unreachable"* — never a silent violation.
- Savings are **monotonic** in MW shed and **zero at zero**.
- Backfill **never** re-adds a building that already declined.

## Data sources

- **Buildings:** Boston BERDO 2021 building-emissions dataset (resource `43e4abc9-1fae-40d9-a02e-ff950bd0e732`, data.boston.gov — public, keyless). ~2,200 buildings after de-duplicating multi-record campuses.
- **Socioeconomic weighting:** US Census ACS median household income by zip (table B19013).
- **Geocoding:** US Census Geocoder for building lat/long.
- **Constants:** program rates (Mass Save ConnectedSolutions), capacity prices/LMPs (ISO-NE), emissions factors (EPA eGRID) — one citation per constant in `server/constants.py`.

## Team

Sanchali Banerjee · Sophie Cheung · Nicole Zheng
