# Tasks — Front-end: Visualization Map & Dashboards

Ordered, checkable implementation plan. Each task names the acceptance criteria
(AC-*) it satisfies. Front-end work assumes the BFF contracts in `design.md`;
where the live BFF is not ready, build against fixtures that mirror those
contracts so the UI is testable in isolation.

## 0. Project scaffold

- [ ] **0.1** Scaffold the SPA: Vite + React 18 + TypeScript in `web/`, with
      React Router, TanStack Query, Zustand, and ESLint/Prettier.
- [ ] **0.2** Wire `make setup` / `make demo` / `make test` to the `web/` build,
      dev server (bound to `127.0.0.1`), and Vitest run.
- [ ] **0.3** Add the typed API client and zod schemas for every contract in
      `design.md` (`ZipAggregate`, `BuildingMarker`, `EventPlan`, `TraceStep`,
      `SavingsCounter`); add fixtures mirroring them under `fixtures/`.
- [ ] **0.4** Add the "no `source_id` → do not render a number" guard as a shared
      render helper, with a unit test. (AC-30)

## 1. Public page & routing

- [ ] **1.1** Build `PublicLanding` at `/`: tagline, promo copy (voluntary,
      paid, equity-constrained, human-approved), Sign in button; no auth, no
      fetch. (AC-1)
- [ ] **1.2** Set up routes: `/`, `/signin`, guarded `/utility`, `/building`.
- [ ] **1.3** Test: `/` renders without auth and exposes the Sign in entry
      point. (AC-1, AC-2)

## 2. Authentication & role boundary

- [ ] **2.1** Build `SignInForm` with a Utility/Building role toggle; POST
      `/auth/login`. (AC-2)
- [ ] **2.2** Route by role on success: utility → `/utility`, building →
      `/building` scoped to the session building id. (AC-3, AC-4)
- [ ] **2.3** Show an inline error and stay on `/signin` on invalid credentials.
      (AC-5)
- [ ] **2.4** Build `RequireAuth`: redirect unauthenticated users to `/signin`;
      block a building session from `/utility`. (AC-6, AC-7)
- [ ] **2.5** Build sign-out: end session, return to `/`. (AC-8)
- [ ] **2.6** Tests: guard redirects, building-session 403 on utility routes,
      sign-out clears session. (AC-6, AC-7, AC-8)

## 3. Portfolio map — aggregate layer

- [ ] **3.1** Add the MA zip-boundary GeoJSON static asset and load it into a
      MapLibre `PortfolioMap`.
- [ ] **3.2** Render the zip choropleth from `/zips`, colored by the default
      metric; show `MapLegend`. (AC-9)
- [ ] **3.3** Add `MetricSelect` (curtailable load / EJ status / cumulative
      calls); recolor + update legend without refetch. (AC-10)
- [ ] **3.4** Zip click → side panel with building count, curtailable load, EJ
      status, cumulative calls. (AC-11)
- [ ] **3.5** `OrphanPanel`: list zips present in data but missing geometry.
      (AC-12)
- [ ] **3.6** Tests (Playwright): choropleth renders, metric change recolors,
      zip click populates the panel. (AC-9, AC-10, AC-11, AC-12)

## 4. Portfolio map — building drill-in

- [ ] **4.1** Zip drill-in → fetch `/zips/:zip/buildings`, render a marker layer
      at each `lngLat`. (AC-11b)
- [ ] **4.2** `BuildingPopover` on marker click: address, type, gross area, EUI,
      estimated curtailable load. (AC-11b)
- [ ] **4.3** "Load estimated from type / unknown" badge for buildings with no
      EUI/electricity data; never fabricate a number. (AC-11c)
- [ ] **4.4** Buildings with `lngLat: null` listed in the zip's building panel,
      not dropped. (AC-12b)
- [ ] **4.5** Tests: marker render, badge logic for missing load, ungeocodable
      building appears in the panel. (AC-11b, AC-11c, AC-12b)

## 5. Knowledge graph

- [ ] **5.1** Build `KnowledgeGraph` (Cytoscape) from `/graph`: nodes for zip,
      building, EJ block group, utility, event; edges for their relationships.
      (AC-13)
- [ ] **5.2** Node select → highlight direct neighbors + show attributes.
      (AC-14)
- [ ] **5.3** Tests: node/edge render, neighbor highlight on select. (AC-13,
      AC-14)

## 6. Agent trace panel

- [ ] **6.1** Build `TracePanel` from `/event/trace`: ordered steps with
      timestamp + one-line summary (forecast → v1 → constraint check →
      self-correct → v2). (AC-15)
- [ ] **6.2** Keep every plan version visible; mark the constraint that caused
      each revision. (AC-16)
- [ ] **6.3** Render any MCP tool name in a step verbatim. (AC-17)
- [ ] **6.4** Tests: ordered render, multi-version retention, tool-name
      passthrough. (AC-15, AC-16, AC-17)

## 7. Operator card & re-solve

- [ ] **7.1** Build `OperatorCard`: window, MW target, building count, EJ share;
      Approve / Edit list / Reject buttons. (AC-18)
- [ ] **7.2** `TargetSlider` + `EquityCapSlider` → `/event/resolve?target=&cap=`;
      update card, `EquityGauge`, and map without a page reload. (AC-19)
- [ ] **7.3** Unreachable result → render the explicit trade-off string, never a
      silent shortfall. (AC-20)
- [ ] **7.4** Approve → POST `/event/approve`, append `AuditLine`. (AC-21)
- [ ] **7.5** Critic-rejection re-solve → animate map load shift from rejected to
      replacement zips, gated by `prefers-reduced-motion`. (AC-22, AC-31)
- [ ] **7.6** Tests (Playwright): slider re-solve updates all panels, unreachable
      shows trade-off, Approve appends audit line. (AC-19, AC-20, AC-21)

## 8. Savings counters & city-office reports

- [ ] **8.1** Build `SavingsCounters` from `/savings`: three counters, each with
      an **estimated** label, assumptions tooltip, and `source_id`. (AC-23)
- [ ] **8.2** All counters read zero when nothing is shed. (AC-24)
- [ ] **8.3** Build `RecruitmentList` from `/recruitment`: high-load, unenrolled
      buildings in EJ zips. (AC-25)
- [ ] **8.4** Build `SeasonReport` from `/season` with a cap-on / cap-off toggle
      that redraws cumulative-calls-by-zip. (AC-26)
- [ ] **8.5** Tests: estimated label + source present, zero-at-zero, cap toggle
      redraw. (AC-23, AC-24, AC-26)

## 9. Building account

- [ ] **9.1** Build `BuildingStatus`: enrolled capacity, recent load, "asked
      today?" flag, scoped to the session building. (AC-27)
- [ ] **9.2** Build `BuildingHistory`: past events + total payments for this
      building. (AC-27)
- [ ] **9.3** Build `LiveAsk` (shown only on a live event asking this building):
      kW requested, reason, estimated payment, YES / NO / numeric-offer reply.
      (AC-28)
- [ ] **9.4** Submit reply → POST `/building/:id/reply`, reflect the submitted
      reply in the UI. (AC-29)
- [ ] **9.5** Tests: building-scoped data only, live-ask reply states and submit.
      (AC-27, AC-28, AC-29)

## 10. Cross-cutting: provenance, motion, simulated labels

- [ ] **10.1** Audit every numeric surface for a `source_id`; fail the build on a
      number with no source. (AC-30)
- [ ] **10.2** Respect `prefers-reduced-motion` across map tween and counter
      roll-ups; always show the static end state. (AC-31)
- [ ] **10.3** Label simulated data (enrollment, replies, meter reads) as
      simulated across the UI. (AC-32)
- [ ] **10.4** Accessibility: axe pass per screen, keyboard-only walkthrough of
      sign-in and the operator card, colorblind-safe map scales with legend.

## 11. Demo wiring

- [ ] **11.1** Seed the fixtures/demo data path so `make demo` serves the public
      page, both logins, and the heat-day replay against the operator card.
- [ ] **11.2** Verify the public demo URL loads the public page with no auth and
      that both roles sign in. (AC-1, AC-3, AC-4)
- [ ] **11.3** Update `README.md` so `make demo` and the demo URL are documented
      (keeps the pre-commit `make demo` check green).
