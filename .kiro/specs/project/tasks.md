# Tasks — CommonWatt: Full Stack (BFF + Front-end)

Ordered, checkable implementation plan. Each task names the acceptance criteria
(AC-*) it satisfies. Backend tasks set up the FastAPI BFF with Postgres; frontend
tasks build React components against the BFF contracts. Auth is part of Task 1.

## Task 1: Auth + BFF setup

- [ ] **1.1** Initialize FastAPI project: `app/`, `requirements.txt` (FastAPI,
      SQLAlchemy, psycopg2, bcrypt, alembic for migrations), basic `app.py`.
- [ ] **1.2** Create Postgres schema (alembic migrations): `users`, `buildings`,
      `events`, `call_history`, `replies`, `trace_steps`, `audit_log`, `sessions`.
- [ ] **1.3** Implement `/auth/login` POST: validate bcrypt hash against `users`
      table, set HTTP-only SameSite session cookie (session stored in `sessions`
      table).
- [ ] **1.4** Implement `/auth/me` GET: return `{role, buildingId?}` from session
      cookie.
- [ ] **1.5** Implement `/auth/logout` POST: clear session cookie.
- [ ] **1.6** Create FastAPI role-check dependencies: `require_operator`,
      `require_utility`, `require_facility_manager`.
- [ ] **1.7** Seed three demo users: operator (no building_id), city office
      (no building_id), facility_manager (building_id = 1). Generate bcrypt
      hashes at setup time.
- [ ] **1.8** Document demo credentials in `README.md` (email, password, role).
- [ ] **1.9** Verify: `curl -X POST localhost:8000/auth/login ...` sets session
      cookie, `/auth/me` returns role, role guards work.

## Task 2: Data model and seed

- [ ] **2.1** Define SQLAlchemy models: User, Building, Event, CallHistory,
      Reply, TraceStep, AuditLog, Session.
- [ ] **2.2** Ingest Boston BERDO 2,472 buildings: address, zip, property_type,
      gross_area_sf, site_eui_kBtuft2, per_electricity, and geocoded (lng, lat).
      Mark `simulated=false`.
- [ ] **2.3** Geocode buildings at ingest (third-party or mock geocoder); log
      buildings with `lngLat = null` (AC-12b).
- [ ] **2.4** Create seed script: 3–4 sample events with different target MW /
      equity cap combinations.
- [ ] **2.5** Create seed script: demo call history for 2–3 buildings across 1–2
      events. Mark `simulated=true`.
- [ ] **2.6** Create seed script: demo replies (YES/NO/numeric offers). Mark
      `simulated=true`.
- [ ] **2.7** Verify: `SELECT COUNT(*) FROM buildings;` returns 2472,
      geocoding logs show count of failures.

## Task 3: Public page + auth UI

- [ ] **3.1** Scaffold React SPA: Vite + React 18 + TypeScript, React Router,
      TanStack Query, Zustand, in `web/`.
- [ ] **3.2** Build `PublicLanding` at `/`: tagline, promo (voluntary, paid,
      equity-constrained, human-approved), Sign In button. No auth, static. (AC-1)
- [ ] **3.3** Build `SignInForm`: role toggle (Utility / Building), email +
      password fields, POST to `/auth/login`. (AC-2)
- [ ] **3.4** On successful login, redirect by role: utility → `/utility`,
      building → `/building`. (AC-3, AC-4)
- [ ] **3.5** On invalid credentials, show inline error, stay on form. (AC-5)
- [ ] **3.6** Build `RequireAuth` route guard: fetch `/auth/me` on app load,
      redirect unauthenticated to `/signin`, block building user from `/utility`
      (403). (AC-6, AC-7)
- [ ] **3.7** Build sign-out: POST `/auth/logout`, clear local session state,
      redirect to `/`. (AC-8)
- [ ] **3.8** Add API client + zod schemas for all BFF contracts (`ZipAggregate`,
      `BuildingMarker`, `EventPlan`, `TraceStep`, `SavingsCounter`).
- [ ] **3.9** Tests (Vitest + React Testing Library): guard redirects, role
      check, sign-out clears state.

## Task 4: Utility dashboard — map core

- [ ] **4.1** Implement GET `/zips` (BFF): query aggregates (zip, buildingCount,
      curtailableLoadKw, ejStatus, cumulativeCalls, hasGeometry), return JSON.
      Every numeric field includes `source_id`. (AC-9, AC-30)
- [ ] **4.2** Implement GET `/zips/:zip/buildings` (BFF): query buildings for
      a zip, return markers with address, lngLat, propertyType, curtailableLoadKw
      (`basis: "metered" | "estimated_from_type"`), `simulated` flag. (AC-11b)
- [ ] **4.3** Build `PortfolioMap` component: MapLibre choropleth from MA zip
      GeoJSON, colored by the default metric; render `MapLegend`. Load `/zips`
      on mount. (AC-9)
- [ ] **4.4** Add `MetricSelect` (curtailable load / EJ status / cumulative
      calls); recolor from the loaded data without a refetch. (AC-10)
- [ ] **4.5** Zip click → fetch `/zips/:zip/buildings`, render marker layer,
      show side panel with building count, load, EJ, calls. (AC-11)
- [ ] **4.6** Marker click → `BuildingPopover`: address, type, gross area, EUI,
      curtailable load. (AC-11b)
- [ ] **4.7** "Load estimated from type" or "load unknown" badge for buildings
      with missing EUI/electricity; never fabricate a number. (AC-11c)
- [ ] **4.8** Implement `OrphanPanel`: list zips with no geometry, list buildings
      with `lngLat = null`. (AC-12, AC-12b)
- [ ] **4.9** Tests (Playwright): `/utility` loads, choropleth renders, metric
      change recolors, zip click shows markers, orphan panel surfaces. (AC-9–AC-12)

## Task 5: Knowledge graph + trace panel

- [ ] **5.1** Implement GET `/graph` (BFF): query nodes (zips, buildings, events,
      EJ block groups, utilities) and edges, return as JSON. Each node includes
      `type` and attributes. (AC-13)
- [ ] **5.2** Implement GET `/event/trace` (BFF): query `trace_steps` for an
      event, ordered by ts, return as JSON: {ts, kind, summary, planVersion,
      toolName, rejectedBy}. (AC-15, AC-16, AC-17)
- [ ] **5.3** Build `KnowledgeGraph` component: Cytoscape canvas from `/graph`,
      render nodes/edges. (AC-13)
- [ ] **5.4** Node select → highlight direct neighbors, show node attributes.
      (AC-14)
- [ ] **5.5** Build `TracePanel` component: ordered list from `/event/trace`,
      show timestamp + summary + tool name. Keep all versions visible, mark the
      constraint that caused revisions. (AC-15, AC-16, AC-17)
- [ ] **5.6** Tests: node/edge render, neighbor highlight, trace order/retention.
      (AC-13–AC-17)

## Task 6: Operator card + re-solve flow

- [ ] **6.1** Implement GET `/event/draft` (BFF): query the current event,
      calculate plan {version, windowLabel, targetMw, capPct, buildingCount,
      ejSharePct, reachable}, return JSON. (AC-18, AC-30)
- [ ] **6.2** Implement POST `/event/resolve?target=X&cap=Y` (BFF):
      - Call MCP tools in-process (rank_candidates, check_constraints,
        score_equity, plan_event) to generate a new plan.
      - Log trace steps to `trace_steps` table.
      - On critic rejection, record `rejectedBy` in trace and call planner again.
      - Return updated EventPlan {version, ..., reachable, tradeoff?}.
      - If unreachable, include explicit trade-off string ("35% cap → 31 MW;
        45% → 40 MW"). (AC-19, AC-20)
- [ ] **6.3** Implement POST `/event/approve` (BFF, require_operator): write
      audit_log row, set event status to `approved`, return 200. (AC-21)
- [ ] **6.4** Implement POST `/event/reject` (BFF, require_operator): write
      audit_log row, set event status to `rejected`, return 200.
- [ ] **6.5** Build `OperatorCard` component: fetch `/event/draft` on mount,
      show window, target, building count, EJ share. (AC-18)
- [ ] **6.6** Add `TargetSlider` + `EquityCapSlider`: on drag, debounce and POST
      `/event/resolve?target=&cap=`, update card + `EquityGauge` + map recolor
      without page reload. (AC-19)
- [ ] **6.7** If reachable=false, show the tradeoff string; never silent
      shortfall. (AC-20)
- [ ] **6.8** Add Approve / Reject buttons; POST to BFF, show confirmation
      (append `AuditLine` in UI). (AC-21)
- [ ] **6.9** If trace includes a critic rejection, animate the map load shift
      from rejected zips to replacements, gated by `prefers-reduced-motion`.
      (AC-22, AC-31)
- [ ] **6.10** Tests (Playwright): slider re-solve, unreachable trade-off,
      Approve appends audit, map animation respects motion preference. (AC-19–AC-22)

## Task 7: Building account + reply flow

- [ ] **7.1** Implement GET `/building/:id` (BFF, role check: facility_manager →
      own building only): query building, return {buildingId, address, zip,
      enrolledCapacity, recentLoad, isAskedToday, simulated}. (AC-27, AC-30)
- [ ] **7.2** Implement GET `/building/:id/history` (BFF, role check): query
      call_history + replies + payments for this building, return {events: [{eventId,
      windowLabel, replyValue, payment, timestamp, simulated}], totalPayments}.
      (AC-27)
- [ ] **7.3** Implement POST `/building/:id/reply` (BFF, role check: facility_manager
      → own building only): store reply (yes/no/numeric) in `replies` table, write
      audit_log, return 200. (AC-29)
- [ ] **7.4** Build `BuildingStatus` component: show capacity, recent load,
      "asked today?" badge. Fetch `/building/:id` on mount. (AC-27)
- [ ] **7.5** Build `BuildingHistory` component: table of past events + total
      earnings. Fetch `/building/:id/history`. (AC-27)
- [ ] **7.6** Build `LiveAsk` component (conditionally shown if event live +
      building asked): kW requested, reason ("why you"), estimated payment,
      YES / NO / numeric-offer reply control. (AC-28)
- [ ] **7.7** Reply submit → POST `/building/:id/reply`, reflect the submitted
      reply in UI (show "waiting for confirmation" then hide LiveAsk). (AC-29)
- [ ] **7.8** Tests: building-scoped data only, role check blocks cross-building
      access, reply submit works. (AC-27–AC-29)

## Task 8: Counters, recruitment, season + polish

- [ ] **8.1** Implement GET `/savings` (BFF): calculate three counters (paid to
      buildings, avoided system cost, CO₂ avoided) using MCP estimate_savings tool,
      return {key, valueLabel, estimated, assumptions, source_id}. (AC-23, AC-30)
- [ ] **8.2** If no load shed, all counters read zero. (AC-24)
- [ ] **8.3** Implement GET `/recruitment` (BFF, require_utility): query high-load,
      unenrolled buildings in EJ zips, return list. (AC-25)
- [ ] **8.4** Implement GET `/season?cap=on|off` (BFF, require_utility): query
      cumulative calls by zip for the given cap setting, return for chart. (AC-26)
- [ ] **8.5** Build `SavingsCounters` component: three counters with **estimated**
      label, assumptions tooltip, source_id shown. (AC-23)
- [ ] **8.6** Build `RecruitmentList` component (city office view): fetch
      `/recruitment`, render table. (AC-25)
- [ ] **8.7** Build `SeasonReport` component: fetch `/season?cap=on`, render bar
      chart, add cap-on / cap-off toggle that refetches. (AC-26)
- [ ] **8.8** Implement `prefers-reduced-motion` across the app: disable map
      tween, counter roll-ups; always show static end state. (AC-31)
- [ ] **8.9** Map uses colorblind-safe palette; every metric has a legend +
      click-through numbers. No color-only signal. (AC-10)
- [ ] **8.10** Label all simulated data (enrollment, replies, meter reads) with
      a `simulated` badge. (AC-32)
- [ ] **8.11** Accessibility: axe pass on all screens, keyboard navigation for
      sign-in form, map, operator card. (AC-31)
- [ ] **8.12** Unit tests: source_id validation (AC-30), "load estimated from
      type" badge (AC-11c), "no source → no render" guard.
- [ ] **8.13** Tests (Playwright): end-to-end sign-in → utility → map → approval
      → building account → reply. (All ACs)

## Task 9: Demo wiring & deployment

- [ ] **9.1** Update `Makefile`: `make setup` creates Postgres, runs migrations,
      seeds demo data; `make demo` runs BFF on :8000 + React dev server on :3000;
      `make test` runs pytest + Vitest + Playwright.
- [ ] **9.2** Update `README.md`: describe `make setup`, `make demo`, link to demo
      URL, document demo credentials (operator/city/facility_manager emails +
      passwords), explain one-building enrollment for facility_manager. (Pre-commit
      `make demo` check passes.)
- [ ] **9.3** Verify `make demo` runs from a clean clone: Postgres starts, migrations
      run, demo data seeds, BFF + React start, `/` loads public page, both logins
      work. (AC-1, AC-3, AC-4)
- [ ] **9.4** Deploy: point DATABASE_URL to Supabase Postgres, run `make setup`,
      build React (`npm run build`), serve static + FastAPI (e.g., Heroku, Render,
      or Docker).
- [ ] **9.5** Verify deployed demo: public page, both logins, full end-to-end
      workflow (approve event, building reply). All routes scoped correctly by role.
      (All ACs)
