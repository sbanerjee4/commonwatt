# Implementation Plan: Commonwatt — Dashboards, Data Model, MCP Tools & Agent Loop

## Overview

Build bottom-up: data model and seed first, then the pure MCP tools, then the
agent loop and simulator, then the FastAPI BFF that enforces scope, then the
React SPA. Python 3.12 (FastAPI, SQLAlchemy 2, Alembic, Hypothesis) for the
backend; React 18 + TypeScript (strict) + Vite for `web/`. Auth exists in task 1
only as data (`users` rows, bcrypt hashes); the login routes are part of task 4.
Each of tasks 1–4 ends with a `make test` checkpoint.

## Tasks

- [ ] 1. Data model + seed (roles: `utility`, `building_manager`)
  - [ ] 1.1 Scaffold the Python project
    - `pyproject.toml` (Python 3.12; fastapi, sqlalchemy>=2, alembic, psycopg2-binary, bcrypt, pydantic, fastmcp, pytest, hypothesis, httpx) with `packages = [{ include = "commonwatt_mcp", from = "mcp" }]` plus `app`, `db`, `agent`, `sim`; no `mcp/__init__.py`
    - pytest config (testpaths `tests`, Hypothesis profile with `max_examples=100`), empty `tests/properties/`
    - `db/config.py`: read `DATABASE_URL`, default `sqlite:///./commonwatt.db`; engine/session factory
    - _Requirements: AC-49, AC-55_
  - [ ] 1.2 Define SQLAlchemy models in `db/models.py`
    - Tables from design "Data Models": `utilities`, `zips`, `zip_utility`, `buildings`, `users`, `sessions`, `events`, `plan_buildings`, `call_history`, `replies`, `meter_reads`, `heat_day_intervals`, `trace_steps`, `audit_log`
    - `users` CHECK constraint tying `role` to `utility_id` / `building_id`; `simulated` columns; `audit_log.action` enum
    - _Requirements: AC-49, AC-50, AC-32, AC-48_
  - [ ] 1.3 Add Alembic environment and the initial migration
    - `db/migrations/` reading `DATABASE_URL`; one revision creating every table, running on SQLite and Postgres
    - _Requirements: AC-49_
  - [ ] 1.4 Write the offline fixture-builder scripts in `scripts/`
    - `build_berdo_subset.py` (BERDO resource `43e4abc9-…`, covers every Boston zip, keeps rows missing EUI/electricity share), `geocode_berdo.py`, `build_zip_utility.py`, `build_ej_zips.py` (rule: any EJ block-group centroid in zip), `build_zip_hexes.py`, `build_heat_day.py`
    - Each writes source id + URL into its output header; never invoked by `make setup`
    - _Requirements: AC-50, AC-11c, AC-12b, AC-34_
  - [ ] 1.5 Commit fixtures under `fixtures/`
    - `berdo_subset.csv`, `berdo_geocodes.csv` (failed rows kept with null coords), `zip_utility.csv`, `ej_zips.csv`, `zip_hexes.geojson`, `heat_day.csv` (simulated)
    - _Requirements: AC-50, AC-11c, AC-12, AC-12b, AC-34_
  - [ ] 1.6 Implement territory and building seeding in `db/seed.py`
    - Load fixtures into `utilities`, `zips`, `zip_utility`, `buildings` (seeded enrollment/capacity `simulated=true`), `heat_day_intervals`; abort naming the row on CHECK/FK violation; networkless
    - _Requirements: AC-50, AC-12b, AC-32_
  - [ ] 1.7 Seed demo accounts in `db/seed.py`
    - `utility@demo` / `demo-utility-pass` for the Boston BERDO utility; `building1..3@demo` / `demo-building-pass` on three buildings in different zips, one in an EJ zip, one flagged protected; bcrypt hashes generated at seed time; no sign-up/reset data
    - _Requirements: AC-51, AC-52, AC-54, AC-49_
  - [ ] 1.8 Wire `make setup` / `make test` and document demo accounts
    - `Makefile`: `setup` installs deps, runs `alembic upgrade head`, runs `db/seed.py`; `test` runs pytest
    - `README.md` "Demo accounts" table (email, password, role, scope)
    - _Requirements: AC-51, AC-52, AC-53_
  - [ ]* 1.9 Write schema-constraint unit tests (`tests/test_schema.py`)
    - `users` CHECK rejects mismatched role/ids; FKs enforced; `utility_id` derivable for building managers
    - _Requirements: AC-49_
  - [ ]* 1.10 Write seed-invariant tests (`tests/test_seed.py`)
    - Demo accounts exist and bcrypt-verify; three distinct zips, one EJ, one protected; every zip mapped to a utility with source id; null-geocode buildings retained; seeded rows `simulated=true`
    - _Requirements: AC-50, AC-51, AC-52, AC-54, AC-12b, AC-32_
  - [ ] 1.11 Checkpoint: Run `make test` and report the test summary to the user before continuing.

- [ ] 2. MCP tools + property tests
  - [ ] 2.1 Implement `mcp/commonwatt_mcp/constants.py`
    - `Constant(value, unit, source_id, source_url, retrieved, note)` for rates, capacity prices, LMPs, emissions factors; uncited constants carry no value
    - _Requirements: AC-62_
  - [ ] 2.2 Implement typed I/O in `mcp/commonwatt_mcp/schemas.py`
    - pydantic `Sourced`, `Unavailable`, and input/output models for every tool, incl. `unreachable{tradeoff[]}` and `criticRejection`
    - _Requirements: AC-61, AC-62, AC-57_
  - [ ] 2.3 Implement `tools/estimate_load.py`
    - Returns sourced value with `basis` (`metered` | `estimated_from_type`) or `unavailable` with reason; never unlabeled
    - _Requirements: AC-61, AC-62, AC-11c_
  - [ ] 2.4 Implement `tools/rank_candidates.py` and `tools/score_equity.py`
    - Greedy load-first ranking with stable `building_id` tie-break; sourced EJ share; sorted inputs, fixed rounding
    - _Requirements: AC-55, AC-56_
  - [ ] 2.5 Implement `tools/check_constraints.py`
    - Returns `[{constraint, building_ids}]` for EJ cap, previous-event exclusion, protected-under-heat
    - _Requirements: AC-60, AC-56, AC-58, AC-59_
  - [ ] 2.6 Implement `tools/plan_event.py`
    - Enforces cap, previous-event, protected rules; honors include/exclude lists; returns `unreachable` with cap-vs-achievable-MW trade-off and label instead of an over-cap plan
    - _Requirements: AC-56, AC-57, AC-58, AC-59, AC-20_
  - [ ] 2.7 Implement `tools/backfill.py`
    - Tops up after declines/shortfalls under `plan_event` constraints; returns new plan + sourced delta (added, removed, deltaMw)
    - _Requirements: AC-38, AC-56, AC-58, AC-59_
  - [ ] 2.8 Implement `reconcile`, `estimate_savings`, `recruitment_list`, `notify` (mock)
    - Decimal per-building delivered kW summing to total; three estimated figures with assumptions (zero when nothing delivered); high-load unenrolled EJ-zip buildings
    - _Requirements: AC-64, AC-63, AC-24, AC-25, AC-62_
  - [ ] 2.9 Register tools in `mcp/commonwatt_mcp/server.py`
    - FastMCP thin wrappers over each pure function
    - _Requirements: AC-17, AC-55_
  - [ ]* 2.10 Write Hypothesis world generators in `tests/properties/strategies.py`
    - Utilities, zips with EJ flags, buildings with optional EUI/electricity, protected flags/kinds, previous-event sets, events, calls, replies, meter reads
    - _Requirements: AC-47, AC-55_
  - [ ]* 2.11 Write property test for tool determinism
    - **Property 3: Tool determinism**
    - **Validates: Requirements AC-55**
  - [ ]* 2.12 Write property test for the EJ cap
    - **Property 4: EJ share never exceeds the cap**
    - **Validates: Requirements AC-56, AC-57, AC-20**
  - [ ]* 2.13 Write property test for previous-event exclusion
    - **Property 5: Previous-event buildings excluded**
    - **Validates: Requirements AC-58**
  - [ ]* 2.14 Write property test for protected facilities
    - **Property 6: Protected facilities excluded under heat**
    - **Validates: Requirements AC-59, AC-36**
  - [ ]* 2.15 Write property test for reconcile
    - **Property 7: Reconcile sums**
    - **Validates: Requirements AC-64**
  - [ ]* 2.16 Write property test for the critic oracle
    - **Property 8: Critic matches a reference oracle**
    - **Validates: Requirements AC-60**
  - [ ]* 2.17 Write property test for labeled numbers
    - **Property 9: No unlabeled numbers from tools**
    - **Validates: Requirements AC-61, AC-62, AC-63**
  - [ ]* 2.18 Write tool unit tests (`tests/test_tools.py`)
    - Violation names constraint + offenders; `estimate_from_type` / `unavailable` cases; every `Constant` has `source_url`; no float literals other than 0/1 in `tools/`; savings labeled estimated and zero when no load reduced
    - _Requirements: AC-60, AC-61, AC-62, AC-63, AC-24_
  - [ ] 2.19 Checkpoint: Run `make test` and report the test summary to the user before continuing.

- [ ] 3. Agent loop + simulator
  - [ ] 3.1 Implement `agent/planner.py`
    - Forecast via `estimate_load`; v1 via unconstrained `rank_candidates`; self-correct via `plan_event` with exclusions; templated summaries
    - _Requirements: AC-65, AC-66_
  - [ ] 3.2 Implement `agent/critic.py`
    - `check_constraints` + `score_equity`; returns pass or named violations with rejected/replacement zips
    - _Requirements: AC-60, AC-65, AC-22_
  - [ ] 3.3 Implement `agent/loop.py`
    - forecast → v1 → critic → self-correct → v(n+1) until pass, `unreachable`, or `MAX_PLAN_ITERATIONS` (config, default 3; trade-off mode at limit)
    - Writes `trace_steps` (ts, kind, summary, plan_version, tool_name, rejected_by) and `plan_buildings` per version; publish callback for streaming; ends `status=draft`, no `call_history`
    - _Requirements: AC-65, AC-66, AC-67, AC-68, AC-57, AC-15, AC-16_
  - [ ] 3.4 Implement `sim/simulator.py`
    - `simulate(event, calls, seed)` with `random.Random`, default seed SHA-256 of `event_id`; YES/NO/offer replies and interval meter reads, all `simulated=True`
    - _Requirements: AC-69, AC-32_
  - [ ] 3.5 Implement event actions in `agent/actions.py`
    - `resolve`/`edit` (slider values or include/exclude list → `plan_event` + critic, new version, `resolve` trace steps); `approve` (requires reachable draft; copies `plan_buildings` to `call_history`, audit line, `notify`, persists simulator rows); `reject` (audit line only); `set_protected` (persist flag + audit)
    - _Requirements: AC-19, AC-21, AC-35, AC-36, AC-48, AC-67, AC-69_
  - [ ]* 3.6 Write property test for the human gate
    - **Property 10: Agent loop keeps versions and contacts no one** (loop + resolve/edit/reject sequences; ask-route clause added in 4.12)
    - **Validates: Requirements AC-48, AC-65, AC-66, AC-67, AC-68, AC-35**
  - [ ]* 3.7 Write property test for the simulator
    - **Property 11: Simulator determinism**
    - **Validates: Requirements AC-69, AC-32**
  - [ ]* 3.8 Write agent unit tests (`tests/test_agent.py`)
    - Trace order and `rejected_by`; both versions retained; approve rejects non-draft/unreachable; reject writes only audit
    - _Requirements: AC-15, AC-16, AC-21, AC-35, AC-68_
  - [ ] 3.9 Checkpoint: Run `make test` and report the test summary to the user before continuing.

- [ ] 4. BFF with enforcement
  - [ ] 4.1 Create the FastAPI app in `app/main.py`
    - App factory, DB dependency, `/health`; include routers from `routes/auth.py`, `routes/utility.py`, `routes/building.py`, `stream.py` (stub routers created here)
    - _Requirements: AC-44_
  - [ ] 4.2 Implement auth in `app/auth.py` and `app/routes/auth.py`
    - `POST /auth/login` (bcrypt verify, 256-bit token stored hashed in `sessions` with expiry, `cw_session` HttpOnly/SameSite=Lax/Secure except localhost, generic 401); `GET /auth/me` (`{role, utilityId, buildingId?}`, utilityId derived for building managers); `POST /auth/logout`; no sign-up/reset routes
    - _Requirements: AC-3, AC-4, AC-5, AC-8, AC-33, AC-54_
  - [ ] 4.3 Implement `require_role` in `app/deps.py` and the startup route check
    - No session → 401; wrong role → 404 with the shared body; attach to utility/building routers; boot fails if a non-allowlisted route lacks `require_role`
    - _Requirements: AC-44, AC-7, AC-33_
  - [ ] 4.4 Implement scoped repositories in `app/scope.py`
    - `UtilityRepo._scoped(Model)` filtering through `zip_utility` or `events.utility_id`; `BuildingRepo` raising 404 on id mismatch before any query, plus `territory_median_calls()`
    - _Requirements: AC-45, AC-46, AC-27_
  - [ ] 4.5 Implement utility map, replay, and graph routes in `app/routes/utility.py`
    - `/utility/zips`, `/zips/geometry`, `/zips/{zip}/buildings`, `/replay/{day}`, `/graph`; all numbers `Sourced`; out-of-territory params → 404
    - _Requirements: AC-9, AC-10, AC-11, AC-11b, AC-11c, AC-12, AC-12b, AC-13, AC-34, AC-30_
  - [ ] 4.6 Implement utility event routes in `app/routes/utility.py`
    - `POST /utility/events` (runs loop with stream publisher), `GET /events/{id}`, `/trace`, `POST /resolve`, `/edit`, `/approve` (409 on non-draft/unreachable), `/reject`, `GET /backfill`, `PUT /utility/buildings/{id}/protected`
    - _Requirements: AC-18, AC-19, AC-20, AC-21, AC-22, AC-35, AC-36, AC-38, AC-48_
  - [ ] 4.7 Implement the SSE trace stream in `app/stream.py`
    - `/utility/events/{id}/trace/stream` with `Last-Event-ID` replay from `trace_steps`; publisher used by the loop
    - _Requirements: AC-15, AC-65_
  - [ ] 4.8 Implement utility panel and report routes in `app/routes/utility.py`
    - `/utility/audit`, `/replies` (simulated flag), `/savings`, `/recruitment`, `/season?cap=on|off`, `/season/export` CSV with source id per number
    - _Requirements: AC-23, AC-24, AC-25, AC-26, AC-37, AC-39_
  - [ ] 4.9 Implement building routes in `app/routes/building.py`
    - `/building/{id}/status`, `/history`, `/ask` (approved live event only, else `null`), `POST /reply` (422 on malformed, audit), `PUT /capacity` (positive kW, audit)
    - _Requirements: AC-27, AC-28, AC-29, AC-40, AC-41, AC-42, AC-43_
  - [ ]* 4.10 Write property test for scope isolation
    - **Property 1: Scope isolation** (every repo method and route, via `app.routes`)
    - **Validates: Requirements AC-45, AC-47, AC-25, AC-39, AC-43**
  - [ ]* 4.11 Write property test for 404 non-enumeration
    - **Property 2: 404 non-enumeration**
    - **Validates: Requirements AC-46, AC-7, AC-44**
  - [ ]* 4.12 Extend Property 10 to the BFF
    - **Property 10: Agent loop keeps versions and contacts no one** (`/building/{id}/ask` returns `null` for every building without approval)
    - **Validates: Requirements AC-48, AC-40**
  - [ ]* 4.13 Write BFF unit tests (`tests/test_bff.py`)
    - Import ban on `Session`/`db.engine` in `app/routes`; boot route-role check; login/logout/me; 401 vs 404; 409 approve; 422 bodies; `unavailable` passthrough
    - _Requirements: AC-3, AC-4, AC-5, AC-8, AC-44, AC-54_
  - [ ] 4.14 Checkpoint: Run `make test` and report the test summary to the user before continuing.

- [ ] 5. React scaffold, public page, login, and guards
  - [ ] 5.1 Scaffold `web/`
    - Vite + React 18 + TS strict, React Router, TanStack Query, Zustand, zod, Vitest + RTL, Playwright config; dev proxy to :8000; `App.tsx` routes `/`, `/login`, `/utility`, `/building/:id` to page stubs
    - _Requirements: AC-1, AC-2, AC-33_
  - [ ] 5.2 Add the API client and zod contracts (`web/src/api/`)
    - Schemas for `Sourced`, `Me`, `ZipAggregate`, `BuildingMarker`, `EventPlan`, `TraceStep`, `BackfillDelta`, `SavingsCounter`, `BuildingStatus`, `LiveAsk`; fetchers with `credentials: "include"`
    - _Requirements: AC-30_
  - [ ] 5.3 Build shared UI primitives (`web/src/ui/`)
    - `<Num>` (refuses to render without `source_id`, shows it on hover/focus), `SimulatedBadge`, `EstimatedBadge`, `useReducedMotion`
    - _Requirements: AC-30, AC-32, AC-31_
  - [ ] 5.4 Build `PublicLanding` at `/`
    - Tagline, voluntary/paid/equity-constrained/human-approved description, Log in link; no fetch
    - _Requirements: AC-1, AC-70_
  - [ ] 5.5 Build `LoginForm` at `/login`
    - Email + password only; redirect by response role (`/utility` or `/building/{buildingId}`); inline error on 401
    - _Requirements: AC-2, AC-3, AC-4, AC-5, AC-33_
  - [ ] 5.6 Add `RequireAuth`, `RequireRole`, and sign-out in `App.tsx`
    - `/auth/me` → 401 redirects to `/login`; building manager on `/utility` sent to own page; sign-out posts `/auth/logout`, clears query cache, goes to `/`
    - _Requirements: AC-6, AC-7, AC-8, AC-33_
  - [ ]* 5.7 Write Vitest tests for login and guards
    - No role control rendered; redirects per role; 401 error; guard redirects; sign-out clears state
    - _Requirements: AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-33_

- [ ] 6. Utility dashboard: map, drill-in, replay
  - [ ] 6.1 Build the `UtilityDashboard` shell
    - Layout with `MapSection`, `AgentSection`, `EventSection`, `ReportsSection` components (initially empty)
    - _Requirements: AC-9_
  - [ ] 6.2 Build `PortfolioMap`, `MetricSelect`, `MapLegend` in `MapSection`
    - MapLibre hex `fill` layer from `/utility/zips/geometry` + `/utility/zips`; colorblind-safe data-driven paint; metric switch repaints without refetch and updates legend
    - _Requirements: AC-9, AC-10_
  - [ ] 6.3 Build `ZipPopover`, building marker layer, `BuildingPopover`
    - Zip click shows count, load available to reduce, EJ, calls; drill-in `circle` layer from `/zips/{zip}/buildings`; popover shows address, type, area, EUI, load; "estimated from type" / "load unknown" badge
    - _Requirements: AC-11, AC-11b, AC-11c, AC-30_
  - [ ] 6.4 Build `OrphanPanel` in `MapSection`
    - Zips without geometry; buildings with `lngLat: null` in the zip's building list
    - _Requirements: AC-12, AC-12b_
  - [ ] 6.5 Build `HeatDayReplay`
    - Day picker, play/pause, scrubber over `/utility/replay/{day}`; repaints hexes per interval and shows timestamp; no autoplay under reduced motion
    - _Requirements: AC-34, AC-31, AC-32_
  - [ ]* 6.6 Write Vitest tests for the map components
    - Metric recolor + legend; popover fields; load badges; orphan listing; replay order and reduced-motion behavior
    - _Requirements: AC-10, AC-11, AC-11b, AC-11c, AC-12, AC-12b, AC-34, AC-31_

- [ ] 7. Utility dashboard: knowledge graph and trace
  - [ ] 7.1 Build `KnowledgeGraph` in `AgentSection`
    - Cytoscape from `/utility/graph`; select highlights neighbors and shows attributes; table fallback
    - _Requirements: AC-13, AC-14_
  - [ ] 7.2 Build `TracePanel` in `AgentSection`
    - Loads `/trace`, subscribes to SSE stream; shows ts, kind, summary, version, tool name, rejecting constraint; keeps all versions
    - _Requirements: AC-15, AC-16, AC-17_
  - [ ]* 7.3 Write Vitest tests for graph and trace
    - Neighbor highlight; trace ordering, version retention, `rejectedBy` marker, tool names
    - _Requirements: AC-13, AC-14, AC-15, AC-16, AC-17_

- [ ] 8. Utility dashboard: operator card and event panels
  - [ ] 8.1 Build `OperatorCard` in `EventSection`
    - Window, MW target, building count, EJ share; Approve / Edit list / Reject; `AuditLine` on approve and reject
    - _Requirements: AC-18, AC-21, AC-35_
  - [ ] 8.2 Add `TargetSlider`, `EquityCapSlider`, `EquityGauge`
    - Debounced POST `/resolve`; update card, gauge, and shared plan cache in place; unreachable shows trade-off label and disables Approve
    - _Requirements: AC-19, AC-20_
  - [ ] 8.3 Build `PlanListEditor`
    - Opened from Edit list; include/exclude edits POST `/edit` as constrained re-solves
    - _Requirements: AC-18, AC-19_
  - [ ] 8.4 Add plan highlight and load-shift animation to `PortfolioMap`
    - Recolor from the current plan; on `criticRejection` tween from `rejectedZips` to `replacementZips`; end state only under reduced motion
    - _Requirements: AC-19, AC-22, AC-31_
  - [ ] 8.5 Add `ProtectedToggle` to `BuildingPopover`
    - PUT `/utility/buildings/{id}/protected` with reason; invalidate draft so next re-solve applies it
    - _Requirements: AC-36_
  - [ ] 8.6 Build `AuditLogPanel` and `ReplyStream` in `EventSection`
    - Audit user/event/action/ts; replies newest first, each `SimulatedBadge`, polling while an event is live
    - _Requirements: AC-37, AC-32_
  - [ ] 8.7 Build `BackfillDeltaCard` in `EventSection`
    - Added/removed buildings and MW change via `<Num>`
    - _Requirements: AC-38, AC-30_
  - [ ]* 8.8 Write Vitest tests for operator flows
    - Slider re-solve updates; unreachable disables Approve; audit lines; reduced-motion end state; protected toggle; simulated tags; delta card
    - _Requirements: AC-18, AC-19, AC-20, AC-21, AC-22, AC-35, AC-36, AC-37, AC-38_

- [ ] 9. Utility dashboard: counters, recruitment, season
  - [ ] 9.1 Build `SavingsCounters` in `ReportsSection`
    - Three counters labeled estimated, assumptions tooltip, source id; roll-up off under reduced motion
    - _Requirements: AC-23, AC-24, AC-31_
  - [ ] 9.2 Build `RecruitmentList` in `ReportsSection`
    - Table from `/utility/recruitment`
    - _Requirements: AC-25_
  - [ ] 9.3 Build `SeasonReport` in `ReportsSection`
    - Cumulative-calls-by-zip bar chart; cap-on/off toggle refetches; Export downloads CSV
    - _Requirements: AC-26, AC-39_
  - [ ]* 9.4 Write Vitest tests for reports
    - Estimated labels and zero state; toggle refetch; export link params
    - _Requirements: AC-23, AC-24, AC-25, AC-26, AC-39_

- [ ] 10. Building account
  - [ ] 10.1 Build `BuildingAccount` page with `BuildingStatus`
    - Capacity, zip, EJ flag, protected flag, last called, season calls vs territory median; no utility panels
    - _Requirements: AC-27, AC-43, AC-32_
  - [ ] 10.2 Build `BuildingHistory`
    - Past asks, replies, delivered kW, payments
    - _Requirements: AC-41_
  - [ ] 10.3 Build `LiveAsk`
    - Rendered only when `/ask` is non-null; kW, window, why you, estimated payment; YES/NO/offer reply shows stored reply
    - _Requirements: AC-28, AC-29, AC-40_
  - [ ] 10.4 Build `OfferedCapacityForm`
    - PUT `/capacity` with positive kW; shows stored value; field error on 422
    - _Requirements: AC-42_
  - [ ]* 10.5 Write Vitest tests for the building account
    - No map/trace/operator controls; `LiveAsk` hidden for `null`; reply and capacity submit
    - _Requirements: AC-27, AC-28, AC-29, AC-40, AC-41, AC-42, AC-43_

- [ ] 11. Cross-cutting provenance, wording, motion, accessibility
  - [ ] 11.1 Add the copy linter test (`web/tests/copyLint.test.ts`)
    - Fails on "cut", "shut off", "curtail", "disconnect" in user-facing strings under `web/src`
    - _Requirements: AC-70_
  - [ ] 11.2 Accessibility pass
    - Keyboard reachability for login, map, graph, operator card; ARIA labels; table fallback for map; legend + numbers alongside every color
    - _Requirements: AC-31, AC-10_
  - [ ]* 11.3 Write provenance and contract tests
    - `<Num>` refusal; zod schemas validated against recorded BFF responses; simulated badges present
    - _Requirements: AC-30, AC-32, AC-11c_
  - [ ]* 11.4 Write Playwright axe and reduced-motion tests
    - axe on each screen; `reducedMotion: "reduce"` disables tween, replay autoplay, counter roll-up
    - _Requirements: AC-31_

- [ ] 12. Demo wiring and deploy configuration
  - [ ] 12.1 Complete the `Makefile`
    - `demo` runs uvicorn on :8000 and Vite on :3000; `test` runs pytest + Vitest + Playwright
    - _Requirements: AC-1, AC-3, AC-4_
  - [ ] 12.2 Add production serving and container config
    - FastAPI serves `web/dist`; `Dockerfile`; Supabase `DATABASE_URL` with `sslmode=require`; Secure cookies outside localhost
    - _Requirements: AC-33, AC-51_
  - [ ] 12.3 Update `README.md`
    - `make setup`, `make demo`, `make test`, deploy steps with `DATABASE_URL`; keep "Demo accounts"
    - _Requirements: AC-53_
  - [ ]* 12.4 Write the Playwright end-to-end suite
    - Each demo login; map metric, drill-in, orphan panel, replay; slider re-solve with trade-off; approve → audit line, simulated replies, building live ask; reject → no ask; protected toggle + re-solve; season CSV export
    - _Requirements: AC-1, AC-3, AC-4, AC-9, AC-19, AC-20, AC-21, AC-28, AC-34, AC-35, AC-36, AC-37, AC-39, AC-40_

- [ ] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP.
- Auth appears in task 1 only as seeded `users` rows with bcrypt hashes; login, logout, and session handling are in task 4.2.
- Checkpoints 1.11, 2.19, 3.9, and 4.14 are not in the dependency graph.
- Property tests use the generators from 2.10 and are tagged `# Feature: project, Property N: ...`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.4"] },
    { "id": 2, "tasks": ["1.3", "1.5"] },
    { "id": 3, "tasks": ["1.6"] },
    { "id": 4, "tasks": ["1.7", "2.1", "2.2"] },
    { "id": 5, "tasks": ["1.8", "1.9", "2.3", "2.4", "2.5"] },
    { "id": 6, "tasks": ["1.10", "2.6", "2.8", "2.10"] },
    { "id": 7, "tasks": ["2.7", "2.15", "2.16", "2.17"] },
    { "id": 8, "tasks": ["2.9", "2.11", "2.12", "2.13", "2.14", "2.18", "3.1", "3.2", "3.4"] },
    { "id": 9, "tasks": ["3.3", "3.7"] },
    { "id": 10, "tasks": ["3.5", "4.1"] },
    { "id": 11, "tasks": ["3.6", "3.8", "4.2", "4.4"] },
    { "id": 12, "tasks": ["4.3", "5.1"] },
    { "id": 13, "tasks": ["4.5", "4.7", "4.9", "5.2"] },
    { "id": 14, "tasks": ["4.6", "5.3"] },
    { "id": 15, "tasks": ["4.8", "5.4", "5.5"] },
    { "id": 16, "tasks": ["4.10", "4.11", "4.12", "4.13", "5.6"] },
    { "id": 17, "tasks": ["5.7", "6.1", "10.1"] },
    { "id": 18, "tasks": ["6.2", "7.1", "8.1", "9.1", "10.2"] },
    { "id": 19, "tasks": ["6.3", "7.2", "8.2", "9.2", "10.3"] },
    { "id": 20, "tasks": ["6.4", "7.3", "8.3", "9.3", "10.4"] },
    { "id": 21, "tasks": ["6.5", "8.6", "9.4", "10.5"] },
    { "id": 22, "tasks": ["6.6", "8.4", "8.7"] },
    { "id": 23, "tasks": ["8.5", "11.1", "12.1"] },
    { "id": 24, "tasks": ["8.8", "11.2", "12.2"] },
    { "id": 25, "tasks": ["11.3", "11.4", "12.3"] },
    { "id": 26, "tasks": ["12.4"] }
  ]
}
```
