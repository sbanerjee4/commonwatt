# Design — Front-end: Visualization Map & Dashboards

This document states the technical approach for the Commonwatt web front-end
described in `requirements.md`. It covers the three screens (public page,
utility dashboard, building account), the auth boundary between the two roles,
the map, knowledge graph, agent trace, operator card, counters, and the
building-reply flow. It does **not** cover the dispatch math, data ingestion, or
the simulator — those live behind the API.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (React + TypeScript SPA, Vite)                       │
│                                                               │
│  Public page   Sign-in   Utility dashboard   Building account │
│       │           │             │                  │          │
│       └───────────┴──────┬──────┴──────────────────┘          │
│                          │  fetch (JSON over HTTPS)           │
└──────────────────────────┼────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│  BFF (FastAPI + SQLAlchemy)                                     │
│   • /auth/login           bcrypt verify, HTTP-only cookie      │
│   • /auth/me              session state {role, buildingId?}    │
│   • /buildings, /zips     aggregate + drill-in (read)          │
│   • /graph                knowledge-graph nodes/edges (read)   │
│   • /event/*              plan, re-solve, approve (calls MCP   │
│                            tools in-process, streams trace)    │
│   • /building/:id/*       one building's status/history/reply  │
│   • /savings              three counters + source_id           │
│   • /recruitment, /season city-office views                    │
└──────────────────────────┬─────────────────────────────────────┘
            │                          │
            │                          │  calls MCP tools
            │                          │  in-process
            ├─ Postgres ────────────┐  │  (estimate_load,
            │ (users, roles,        │  │  rank_candidates,
            │  building_id FK,      │  │  check_constraints,
            │  buildings, events,   │  │  score_equity,
            │  call_history,        │  │  plan_event, etc.)
            │  replies, trace,      │  │
            │  audit_log)           │  │
            │                       │  ◄──
            └─ Commonwatt MCP ──────┘
            │ (tools + simulator)
            │
```

All state lives in one Postgres database: `users`, `roles`, `buildings` (geocoded),
`events`, `call_history`, `replies`, `trace_steps`, `audit_log`. The BFF reads
from Postgres, calls MCP tools in-process, and returns shaped view models to the
SPA. Auth is a stub: three seeded demo accounts with bcrypt hashes, verified at
`/auth/login`, which mints an HTTP-only session cookie. The SPA never talks to
MCP or Postgres directly. Every number carries a `source_id`, satisfying the
provenance rule (AC-30).

### Why a BFF and not direct MCP calls

- **Auth boundary.** The building/utility split (AC-4, AC-7) must be enforced on
  the server; a building user's request can never be allowed to fan out to
  other buildings' data. The BFF scopes every `/building/:id` call to the
  session's building id.
- **Shaping.** The map needs zip aggregates; the graph needs nodes/edges; the
  counters need assumptions attached. The BFF composes these from tool outputs
  and Postgres queries so the client stays thin.
- **One MCP, two consumers.** Per the project brief the same Commonwatt MCP
  server is used by Kiro during development and by the app at runtime. The BFF
  is the app's consumer and calls MCP tools in-process.

### Why one Postgres database, not Mongo + Supabase Auth

All state (users, roles, buildings, events, call history, replies, trace,
audit log) lives in a single Postgres schema:

- **Referential integrity.** `users.building_id` is a real foreign key into
  `buildings`; the database rejects a write that violates this constraint.
- **Auth is a stub.** Three seeded demo accounts (`operator`, `city`,
  `facility_manager` tied to `building_id`) with bcrypt password hashes.
  `/auth/login` validates the hash and mints an HTTP-only session cookie.
  No sign-up, no password reset, no Supabase Auth service.
- **Audit trail.** `audit_log(user_id, event_id, action, timestamp)` is
  foreign-keyed and append-only — exactly what Postgres is built for.
- **Demo environment.** For local dev and tests, use a Postgres container or
  SQLite via SQLAlchemy. For the deployed demo, point DATABASE_URL at Supabase
  Postgres. The app code is unaffected; the schema and seeded data are the same.

The front-end is unaffected by where Postgres lives; it only ever talks to the
BFF. Demo credentials are seeded at setup and documented in README so judges can
log in from a clean clone.

## Components

### Front-end stack

| Concern | Choice | Why |
| --- | --- | --- |
| Framework | React 18 + TypeScript | Named in the project brief; component model fits the dashboard panels |
| Build | Vite | Fast dev server, simple static build for the public deploy |
| Routing | React Router | Public `/`, `/signin`, guarded `/utility`, `/building` |
| Map | MapLibre GL JS | Open-source, no token; zip choropleth via a GeoJSON fill layer + building markers via a circle/symbol layer |
| Graph | Cytoscape.js | Mature knowledge-graph layout/interaction; handles node highlight on select (AC-14) |
| Data fetching | TanStack Query | Caching, request dedupe, and re-fetch on slider re-solve (AC-19) |
| State | React Query cache + small local UI state (Zustand) | Avoids a heavy global store; most state is server state |
| Charts/counters | Lightweight (e.g. visx or hand-rolled SVG) | Three counters + a season bar chart; no need for a large charting dep |
| Styling | CSS modules or Tailwind | Theme tokens for light/dark; respects `prefers-reduced-motion` (AC-31) |

### Back-end stack

| Concern | Choice | Why |
| --- | --- | --- |
| Framework | FastAPI | Fast, async, supports streaming; calls MCP tools and simulator in-process |
| Database | Postgres (local or Supabase) | All state in one schema; foreign keys, audit trail, seeded demo users |
| ORM | SQLAlchemy | Declarative models, RLS-ready migrations, works with both local Postgres and Supabase |
| Auth | bcrypt + HTTP-only cookies | Stub: three seeded demo accounts, validated at login, role in session |
| Session | server-side (Postgres table) | HTTP-only, SameSite; role and buildingId stored in cookie, verified on each request |

The map uses **choropleth as the primary layer** with **building-marker
drill-in** (confirmed decision): statewide view shows zips colored by metric;
clicking a zip loads that zip's building markers from their geocoded points.
Parcel polygons are **not** rendered (dropped per decision), even where
`shape_wkt` exists.

### Screens and components

#### 1. Public page (`/`)
- `PublicLanding` — tagline ("Keep the grid up without leaning on the same
  neighborhoods twice"), a short promo section (voluntary, paid,
  equity-constrained, human-approved), and a **Sign in** button.
- No data fetch, no auth (AC-1). Static content; deployable as the public demo
  URL.

#### 2. Sign-in (`/signin`)
- `SignInForm` with a role toggle (Utility / Building) and credential fields
  (AC-2). Submits to `/auth/login`; on success the BFF sets an HTTP-only session
  cookie carrying the role (and, for building users, the building id) and the
  client routes by role (AC-3, AC-4). On failure, inline error, stay on page
  (AC-5).
- `RequireAuth` route guard reads session state from `/auth/me`; redirects
  unauthenticated users to `/signin` (AC-6) and blocks a building user from
  `/utility` (AC-7).

#### 3. Utility dashboard (`/utility`)
A single page with panels:

- **`PortfolioMap`** — MapLibre map.
  - Aggregate layer: a GeoJSON fill layer of MA zip polygons, colored by the
    active metric via a data-driven paint expression; a `MetricSelect`
    (curtailable load / EJ status / cumulative calls) recolors it and updates
    `MapLegend` (AC-9, AC-10).
  - Drill-in: clicking a zip fetches that zip's buildings and renders a marker
    layer at each building's `[lng, lat]`; a marker click opens `BuildingPopover`
    with address, type, area, EUI, estimated curtailable load (AC-11, AC-11b).
  - Missing data: buildings without EUI/electricity share render with a "load
    estimated from type" badge (AC-11c); zips present in data but missing
    geometry, and buildings that failed geocoding, are listed in `OrphanPanel`
    rather than dropped (AC-12, AC-12b).
- **`KnowledgeGraph`** — Cytoscape canvas. Nodes: zip, building, EJ block group,
  utility, event. Edges: building→zip, zip→EJ, zip→utility, event→building.
  Selecting a node highlights neighbors and shows attributes (AC-13, AC-14).
  Data from `/graph`.
- **`TracePanel`** — ordered list of agent steps with timestamp + one-line
  summary (forecast → plan v1 → constraint check → self-correct → plan v2).
  Every version stays visible; the step that caused each revision is marked, and
  any MCP tool name in a step is shown verbatim (AC-15, AC-16, AC-17). Data from
  `/event/trace`.
- **`OperatorCard`** — the human gate. Shows window, MW target, building count,
  EJ share, and **Approve / Edit list / Reject** (AC-18). `TargetSlider` and
  `EquityCapSlider` call `/event/resolve?target=&cap=`; the returned plan updates
  the card, `EquityGauge`, and the map markers without a page reload (AC-19).
  An unreachable result renders the explicit trade-off string from the API
  ("35% cap → 31 MW; 45% → 40 MW"), never a silent shortfall (AC-20). Approve
  POSTs to `/event/approve` and appends an `AuditLine` (AC-21). When a re-solve
  reports a critic rejection, the map animates the load shift from rejected zips
  to replacement zips (AC-22) — respecting reduced-motion (AC-31).
- **`SavingsCounters`** — three counters (paid to buildings, avoided system
  cost, CO₂ avoided). Each shows an **estimated** label, an assumptions tooltip,
  and its `source_id` (AC-23); all read zero when nothing is shed (AC-24).
- **`RecruitmentList`** (city office) — high-load, unenrolled buildings in EJ
  zips from `/recruitment` (AC-25).
- **`SeasonReport`** (city office) — cumulative-calls-by-zip bar/map view with a
  **cap-on / cap-off** toggle that re-requests `/season?cap=on|off` (AC-26).

#### 4. Building account (`/building`)
- **`BuildingStatus`** — enrolled capacity, recent load, "asked today?" flag;
  scoped to the session's building id only (AC-27).
- **`BuildingHistory`** — past events and total payments for this building
  (AC-27, from `/building/:id/history`).
- **`LiveAsk`** — shown only when an event is live and this building is asked:
  kW requested, the reason ("why you"), estimated payment, and a reply control
  offering **YES / NO / numeric offer** (AC-28). Submitting POSTs to
  `/building/:id/reply` and the UI reflects the submitted reply (AC-29).

## Data Sources

All state lives in a single Postgres database:

- **`users`** — id, email, role (`operator` / `city` / `facility_manager`),
  `building_id` (FK to `buildings`, nullable for operator/city), password_hash.
  Three seeded demo accounts; demo credentials in README.
- **`buildings`** — id, Address, Zip, Property_Type, Gross_Area_sf, Site_EUI_kBtuft2,
  per_Electricity, lngLat (geocoded point). 2,472 buildings from Boston BERDO
  datastore resource `43e4abc9-1fae-40d9-a02e-ff950bd0e732`, ingest geocoded
  to points.
- **`zips`** — zip, buildingCount, curtailableLoadKw, ejStatus, cumulativeCalls,
  computed from aggregates over buildings and events.
- **`events`** — id, windowLabel, targetMw, capPct, status (`draft` / `approved` /
  `rejected`), version (1, 2, etc.), timestamp.
- **`call_history`** — id, eventId, buildingId, kwRequested, timestamp.
- **`replies`** — id, callId, buildingId, reply (`yes` / `no` / numeric offer),
  timestamp.
- **`trace_steps`** — id, eventId, ts, kind (`forecast` / `plan` / `constraint_check` /
  `self_correct`), summary, planVersion, toolName, rejectedBy.
- **`audit_log`** — id, userId, eventId, action (`approved` / `rejected` / `resolved`),
  timestamp.

For local dev and tests, use a Postgres container or SQLite via SQLAlchemy. For
the deployed demo, DATABASE_URL points at Supabase Postgres. The schema and
seeded data are identical across both environments.

The BFF calls Commonwatt MCP tools in-process (estimate_load, rank_candidates,
check_constraints, score_equity, plan_event, estimate_savings, recruitment_list)
and reads from Postgres to compose view models for the front-end.

## Agent Loop

The front-end does not run the agent loop; it visualizes it. The BFF runs the
loop by calling Commonwatt MCP tools in-process (forecast → plan v1 → constraint
check → self-correct → plan v2). Each step is logged to `trace_steps` in Postgres,
and the trace arrives as a read-only stream from `/event/trace` and renders in
`TracePanel` (AC-15–AC-17). Operator interaction with the loop is mediated by
the operator card: the target and equity-cap sliders request a re-solved plan
from `/event/resolve`, and the **Approve / Edit list / Reject** gate posts the
human decision to `/event/approve` or `/event/reject`. Every event stays behind
this human gate — the front-end never auto-approves.

## Tools / MCP

The BFF is the runtime consumer of the Commonwatt MCP server (the same server
Kiro uses during development). The front-end surfaces, but does not call, these
tools; their names appear verbatim in the trace panel (AC-17) so the UI can be
matched to the registered tools:

`estimate_load`, `rank_candidates`, `check_constraints`, `score_equity`,
`plan_event`, `backfill`, `reconcile`, `estimate_savings`, `recruitment_list`
(plus `notify` on the backend/SMS-mockup side).

### View-model / API contracts

The front-end depends on these response shapes (the BFF produces them; field
names mirror the dataset where possible).

```ts
// GET /zips  → aggregate layer source
type ZipAggregate = {
  zip: string;
  buildingCount: number;
  curtailableLoadKw: { value: number; source_id: string } | null;
  ejStatus: "ej" | "non_ej" | "unknown";
  cumulativeCalls: number;
  hasGeometry: boolean;            // false → listed in OrphanPanel
};

// GET /zips/:zip/buildings  → marker layer (drill-in)
type BuildingMarker = {
  buildingId: string;              // dataset BUILDING_ID
  address: string;                 // dataset Address
  zip: string;
  lngLat: [number, number] | null; // null → OrphanPanel, not dropped
  propertyType: string;            // dataset Property_Type
  grossAreaSf: number;             // dataset Gross_Area_sf
  curtailableLoadKw:
    | { value: number; source_id: string; basis: "metered" | "estimated_from_type" }
    | null;                        // null → "load unknown" badge
};

// GET /event/draft and /event/resolve?target=&cap=
type EventPlan = {
  version: number;
  windowLabel: string;             // "Tue 3:30–6:30 PM"
  targetMw: number;
  capPct: number;
  buildingCount: number;
  ejSharePct: number;
  reachable: boolean;
  tradeoff?: string;               // when !reachable: "35% cap → 31 MW; 45% → 40 MW"
  changedFromPrev?: string;        // "shifted 18 MW to Seaport / Back Bay"
};

// GET /event/trace
type TraceStep = {
  ts: string;                      // real timestamp
  kind: "forecast" | "plan" | "constraint_check" | "self_correct";
  summary: string;
  planVersion?: number;
  toolName?: string;               // shown verbatim (AC-17)
  rejectedBy?: string;             // constraint that caused a revision
};

// GET /savings
type SavingsCounter = {
  key: "paid_to_buildings" | "avoided_system_cost" | "co2_avoided";
  valueLabel: string;              // formatted
  estimated: true;                 // always; drives the "estimated" tag
  assumptions: string;             // tooltip text
  source_id: string;               // AC-23, AC-30
};
```

Every numeric view model carries `source_id` (or a nested `{value, source_id}`);
the client refuses to render a number without one, which is how AC-30 /
provenance is enforced at the edge.

### Map data flow

1. On `/utility` load, fetch `/zips` → set the choropleth GeoJSON source (zip
   polygons joined to aggregate values) and paint by the default metric.
2. `MetricSelect` change → re-paint from already-loaded aggregates (no new
   fetch); update legend.
3. Zip click → fetch `/zips/:zip/buildings` → add a marker layer; markers with
   `basis: "estimated_from_type"` get a distinct style and a badge; `lngLat:
   null` rows go to `OrphanPanel`.
4. Operator slider re-solve → `/event/resolve` returns the plan and the set of
   buildings/zips in it; the map recolors the in-plan zips and, if the response
   carries a critic rejection, tweens marker/zip emphasis from the rejected set
   to the replacement set (AC-22), gated by `prefers-reduced-motion`.

## Constraints and Invariants

- **Provenance (AC-30).** No user-facing number renders without a `source_id`;
  the client treats a missing source as a bug, not a blank cell.
- **Role boundary (AC-4, AC-7).** A building session can read only its own
  building; the BFF asserts `id === session.buildingId` on every `/building/:id`
  endpoint and returns 403 on utility-only routes.
- **Human gate (AC-18, AC-21).** No event leaves the system without an explicit
  operator Approve; the front-end has no auto-approve path.
- **No silent shortfall (AC-20).** An unreachable plan renders the explicit
  trade-off string; it never shows a quietly-short target.
- **No fabricated load (AC-11c).** A building missing EUI/electricity data is
  shown with an "estimated from type" or "unknown" badge, never a made-up number.
- **No silent drops (AC-12, AC-12b).** Zips without geometry and buildings that
  fail geocoding are surfaced in a side panel, never discarded.
- **Simulated data labeled (AC-32).** Enrollment, replies, and meter readings
  are marked simulated for the demo.
- **Reduced motion (AC-31).** `prefers-reduced-motion` disables the load-shift
  tween and counter roll-ups; the end state is always shown statically.

### Auth and role boundary

- **Postgres schema.** `users` holds id, email, role, `building_id` (FK), and
  password_hash. Demo credentials seeded at setup; three accounts (operator,
  city, facility_manager tied to building_id). No sign-up, no password reset.
- **Session.** HTTP-only, SameSite cookie set by `/auth/login`. The BFF verifies
  credentials against Postgres bcrypt hash, stores session record in `sessions`
  table, and mints the cookie. The SPA holds no token.
- **Role boundary (AC-4, AC-7).** The BFF asserts role on every request:
  - `operator` and `city` can read `/zips`, `/buildings`, `/utility/*` (shared
    views).
  - `facility_manager` can read only `/building/:id/*` scoped to their own
    building_id; the BFF asserts `id === session.buildingId` and returns 403
    otherwise.
  - Utility-only endpoints (`/recruitment`, `/season`, `/graph`) are 403 for
    building sessions.
- **Audit trail.** Approvals (AC-21) and building replies (AC-29) write
  `audit_log(user_id, event_id, action, timestamp)` in Postgres, tying
  decisions and replies back to real users.
- **Demo.** Credentials and enrollment are seeded and labeled simulated (AC-32);
  the auth mechanism is real so the boundary is demonstrable from a clean clone.

### Accessibility and motion

- All interactive controls keyboard-reachable; map and graph have an accessible
  text/table fallback for the orphan/aggregate data.
- `prefers-reduced-motion` disables the load-shift tween and counter roll-ups
  (AC-31); the end state is always shown statically.
- Color scales on the map are colorblind-safe and paired with the legend and the
  click-through numbers, so color is never the only signal.

## Testing Strategy

- **Unit (Vitest + React Testing Library):** route guard redirects (AC-6, AC-7),
  the "no source_id → do not render number" rule (AC-30), the "load estimated
  from type" badge logic (AC-11c), reply control states (AC-28/29).
- **Contract:** the view-model types above are validated against BFF responses
  (zod schemas) so a backend shape change fails fast.
- **Map interaction (Playwright):** load `/utility`, assert choropleth renders,
  change metric recolors, zip click shows markers, a `lngLat:null` building
  appears in `OrphanPanel`.
- **Operator flow (Playwright):** drag target/cap sliders → card + gauge +
  map update; an unreachable response shows the trade-off string (AC-20);
  Approve appends the audit line (AC-21).
- **Reduced-motion:** emulate `prefers-reduced-motion: reduce` and assert the
  load-shift tween is skipped (AC-31).
- **Accessibility:** axe pass on each screen; keyboard-only walkthrough of
  sign-in and the operator card.

Front-end tests use mocked BFF responses (fixtures mirroring the contracts), so
they run without the MCP server or Mongo. End-to-end against a live BFF is a
separate integration concern.
