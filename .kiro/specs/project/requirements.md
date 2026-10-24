# Requirements Document

Commonwatt: Dashboards, Data Model, MCP Tools & Agent Loop

## Overview

Commonwatt is an equity-constrained demand-response planner for Massachusetts
utilities. This spec covers the **web front-end** (the public surface, the
login flow, and the two authenticated dashboards) and the **backend it depends
on**: the Postgres data model and demo seed, the deterministic Commonwatt MCP
tools, the agent loop (planner + critic), and the simulator for replies and
meter reads.

There is one public surface and exactly **two account types**:

1. **Public page** — anyone. Promotional and explanatory. Explains what
   Commonwatt is (voluntary, paid, equity-constrained, human-approved) and
   links to `/login`.
2. **Utility account** (`role = "utility"`, one account per utility company) —
   the whole service territory of that utility: a zip-level map with building
   drill-in and heat-day replay, a knowledge graph, the agent trace, the
   operator event card with target and equity-cap sliders, the audit log, the
   SMS/reply stream, the backfill delta card, the savings counters, the season
   replay with cap toggle, and the recruitment list.
3. **Building account** (`role = "building_manager"`, one account per
   building) — a single enrolled building's facility manager. Only that
   building's status, its event history, its payments, and the current ask
   when an approved event includes the building.

Roles come only from the session. There is no role toggle anywhere in the UI.

The map has two layers. The **aggregate layer** is zip-level — the equity and
burden story is inherently zip-level (EJ join, cumulative calls per season), so
this stays the primary view. The **building layer** is individual building
markers, drilled into on click: the building dataset carries a street `Address`
and `Zip` for all 2,472 buildings (Boston BERDO datastore resource
`43e4abc9-1fae-40d9-a02e-ff950bd0e732`), so the backend geocodes each address to
a point and the front-end plots and inspects specific buildings.

The front-end only reads and displays; every number comes from the backend (the
Commonwatt MCP tools and the Postgres store, which holds the geocoded
buildings). The front-end never computes a dispatch number itself. Access
control is enforced in the BFF only (no database row-level security).

## Users and goals

| User | Account type | Screen | Goal |
| --- | --- | --- | --- |
| Visitor (public) | none | Public page | Understand Commonwatt; decide to log in |
| Utility DR operator | `utility` | Utility dashboard | See the territory, read the agent's plan and trade-offs, approve/edit/reject an event, review recruitment and season equity |
| Facility manager | `building_manager` | Building account | See this building's status, history, payments, and the live ask; reply |

## User Stories

### Public page
- **US-1** As a visitor, I want a public landing page with general promotional
  information about Commonwatt so that I understand the product before logging in.
- **US-2** As a visitor, I want a clear login entry point so that I land on the
  dashboard for my account without choosing a role myself.

### Authentication
- **US-3** As a utility operator, I want to log in with my utility account so
  that I reach my utility's territory dashboard.
- **US-4** As a facility manager, I want to log in with a building account so
  that I see only my building's status.
- **US-5** As any signed-in user, I want to sign out so that my session ends.

### Utility dashboard — map
- **US-6** As an operator, I want a map of my territory's buildings with a
  zip-level aggregate layer so that I can see where load and equity burden sit
  geographically.
- **US-7** As an operator, I want to color the map by metric (load available to
  reduce, EJ status, cumulative calls this season) so that I can read the
  trade-off visually.
- **US-8** As an operator, I want to click a zip to see its buildings, load, and
  EJ status so that I can inspect a candidate area.
- **US-8b** As an operator, I want to drill from a zip into individual building
  markers (placed from each building's geocoded address) and click a building to
  see its address, type, area, EUI, and estimated load available to reduce so
  that I can inspect a specific building.
- **US-20** As an operator, I want to replay a heat day on the map so that I can
  see how load and event participation moved across zips over that day.

### Utility dashboard — knowledge graph
- **US-9** As an operator, I want a knowledge-graph view relating zips,
  buildings, EJ block groups, utilities, and past events so that I can see how
  the entities connect rather than reading them as flat tables.

### Utility dashboard — agent trace
- **US-10** As an operator, I want a trace panel showing the agent's planning
  steps (forecast, plan v1, constraint check, self-correction to v2) so that I
  can follow its reasoning and see what changed between versions.

### Utility dashboard — operator card
- **US-11** As an operator, I want a draft-event card showing the window,
  target, building count, and EJ share with **Approve / Edit list / Reject**
  buttons so that every event stays behind a human gate.
- **US-12** As an operator, I want to drag a target slider and an equity-cap
  slider and watch the plan re-solve so that I can explore the trade-off before
  deciding.
- **US-13** As an operator, I want the map load to visibly move when the critic
  rejects a plan and the planner shifts load so that I can see the correction
  happen.
- **US-21** As an operator, I want to mark facilities as protected so that the
  planner excludes them when the heat threshold is exceeded.
- **US-22** As an operator, I want an audit log and an SMS/reply stream so that
  I can see who approved what and how buildings answered.
- **US-23** As an operator, I want a backfill delta card so that I can see how
  the plan was topped up when buildings declined or under-delivered.

### Utility dashboard — counters & reports
- **US-14** As an operator, I want three savings counters (paid to buildings,
  avoided system cost, CO₂ avoided), each labeled **estimated** with its
  assumptions and source on screen, so that I can trust the numbers.
- **US-15** As a utility user, I want a recruitment list of high-load,
  unenrolled buildings in EJ zips in my territory so that I know who to recruit.
- **US-16** As a utility user, I want a season replay of cumulative calls by
  zip, with a cap-on / cap-off toggle, and an export of the season equity report
  so that I can see and share the equity effect over time.

### Building account
- **US-17** As a facility manager, I want to see my building's current status
  (enrolled capacity, zip, EJ flag, protected flag, last called, season call
  count vs the territory median) so that I know where I stand.
- **US-18** As a facility manager, I want to see my building's past asks,
  replies, delivered kW, and payments so that I can track what I've earned.
- **US-19** As a facility manager, when an approved event includes my building I
  want to see the ask (kW requested, window, why me, estimated payment) and reply
  YES / NO / a number so that I can respond.
- **US-24** As a facility manager, I want to update my building's offered
  capacity so that future plans reflect what I can deliver.

### Access control
- **US-25** As a utility, I want my territory's data visible only to my account
  so that other utilities and building managers cannot read it.
- **US-26** As a facility manager, I want my building's data visible only to me
  and my utility so that other buildings cannot read it.

### Demo data
- **US-27** As a judge, I want seeded demo accounts documented in the README so
  that I can log in as each role from a clean clone.

### Backend — data model, tools, agent loop, simulator
- **US-28** As a developer, I want a Postgres data model and seed script for
  users, utilities, buildings, events, call history, replies, trace steps, and
  the audit log so that the app runs from a clean clone.
- **US-29** As an operator, I want deterministic MCP tools (`estimate_load`,
  `rank_candidates`, `check_constraints`, `score_equity`, `plan_event`,
  `backfill`, `reconcile`, `estimate_savings`, `recruitment_list`) so that the
  same inputs always produce the same plan and numbers.
- **US-30** As an operator, I want an agent loop where a planner proposes a
  plan, a critic checks it against the safety constraints, and the planner
  self-corrects from v1 to v2 so that I receive a plan that already satisfies
  the constraints.
- **US-31** As a developer, I want a simulator for building replies and meter
  reads so that the demo shows event participation without real buildings.

## Acceptance Criteria

Written in EARS form. "The data" means values read from the backend (Postgres /
MCP tools); the front-end renders them, it does not compute them.

### Public page
- **AC-1** WHEN a visitor loads the site root THEN the system SHALL display the
  public page with the Commonwatt tagline and a short promotional description,
  and SHALL NOT require authentication.
- **AC-2** WHEN a visitor clicks the login link on the public page THEN the
  system SHALL navigate to `/login`, which SHALL present credential fields only
  and SHALL offer no role choice.

### Authentication
- **AC-3** WHEN a user logs in with valid credentials for a `utility` account
  THEN the system SHALL redirect to `/utility`.
- **AC-4** WHEN a user logs in with valid credentials for a `building_manager`
  account THEN the system SHALL redirect to `/building/:id` for the session's
  building id and SHALL scope all data to that one building.
- **AC-5** WHEN login credentials are invalid THEN the system SHALL show an
  error and remain on `/login`.
- **AC-6** WHEN an unauthenticated user requests `/utility` or any
  `/building/:id` page THEN the system SHALL redirect to `/login`.
- **AC-7** WHEN a `building_manager` session requests a utility route THEN the
  system SHALL deny access and SHALL NOT reveal any other building's data or any
  zip aggregate.
- **AC-8** WHEN a signed-in user signs out THEN the system SHALL end the session
  and return to the public page.
- **AC-33** THE system SHALL derive the user's role only from the server
  session; no client-side control SHALL set or switch the role.

### Map
- **AC-9** WHEN the utility dashboard loads THEN the system SHALL render a
  MapLibre zip-level aggregate layer (zip choropleth/hex) of the session
  utility's territory, each zip colored by the selected metric.
- **AC-10** WHEN the operator changes the map metric (load available to reduce /
  EJ status / cumulative calls) THEN the system SHALL recolor every zip from the
  data for that metric and SHALL update the legend.
- **AC-11** WHEN the operator clicks a zip THEN the system SHALL display that
  zip's building count, estimated load available to reduce, EJ status, and
  cumulative calls this season.
- **AC-11b** WHEN the operator drills into a zip THEN the system SHALL plot that
  zip's buildings as markers at their geocoded address positions, and WHEN a
  marker is clicked THEN the system SHALL show that building's address, property
  type, gross area, EUI, and estimated load available to reduce.
- **AC-11c** WHEN a building's load inputs (EUI or electricity share) are missing
  from the data — which is the case for roughly half the dataset — THEN the
  system SHALL display the building with an explicit "load unknown / estimated
  from type" indicator rather than a fabricated number or a blank.
- **AC-12** WHEN the map has no geometry for a zip present in the data THEN the
  system SHALL list that zip in a side panel rather than silently dropping it.
- **AC-12b** WHEN a building's address cannot be geocoded to a point THEN the
  system SHALL still list it in the zip's building panel rather than silently
  dropping it.
- **AC-34** WHEN the operator starts a heat-day replay THEN the system SHALL
  step the map through that day's recorded intervals in time order, recoloring
  zips from the data for each interval, and SHALL show the current interval's
  timestamp.

### Knowledge graph
- **AC-13** WHEN the operator opens the knowledge-graph view THEN the system
  SHALL render nodes for zips, buildings, EJ block groups, utilities, and
  events within the session utility's territory, with edges for their
  relationships, from the data.
- **AC-14** WHEN the operator selects a graph node THEN the system SHALL
  highlight its direct neighbors and show that node's attributes.

### Agent trace
- **AC-15** WHEN a plan is generated THEN the system SHALL display, in order,
  each agent step with its timestamp and a one-line summary (forecast, plan v1,
  constraint check, self-correction, plan v2).
- **AC-16** WHEN a plan has more than one version THEN the system SHALL keep
  every version, rejected and accepted, visible in the trace and SHALL mark
  which constraint caused each revision.
- **AC-17** WHEN a trace step names an MCP tool THEN the system SHALL show the
  tool name so it can be matched to the registered tools.

### Operator card
- **AC-18** WHEN a draft event exists THEN the system SHALL display a card with
  the event window, MW target, building count, and EJ share, and the buttons
  Approve, Edit list, and Reject.
- **AC-19** WHEN the operator drags the target slider or the equity-cap slider
  THEN the system SHALL request a re-solved plan and SHALL update the card, the
  equity gauge, and the map without a full page reload.
- **AC-20** WHEN a re-solve returns an unreachable result under the current cap
  THEN the system SHALL display the explicit trade-off (e.g. "35% cap → 31 MW;
  45% → 40 MW") rather than silently shortfalling.
- **AC-21** WHEN the operator clicks Approve THEN the system SHALL send the
  approval to the backend and SHALL show an audit line confirming it.
- **AC-22** WHEN the critic rejects a plan version THEN the system SHALL animate
  the load shift on the map from the rejected zips to the replacement zips.
- **AC-35** WHEN the operator clicks Reject THEN the system SHALL record the
  rejection in the audit log, SHALL contact no building, and SHALL keep the
  rejected plan in the trace.
- **AC-36** WHEN the operator marks or unmarks a facility as protected THEN the
  system SHALL persist the flag, SHALL write an audit line, and SHALL apply the
  flag to the next re-solve.
- **AC-37** WHEN the utility dashboard is open THEN the system SHALL show the
  audit log (user, event, action, timestamp) and the SMS/reply stream of
  building replies for the session utility's events, with replies labeled
  simulated.
- **AC-38** WHEN `backfill` adds or swaps buildings after declines or
  under-delivery THEN the system SHALL show a backfill delta card listing the
  buildings added and removed and the change in MW, each number with its
  source id.

### Counters & reports
- **AC-23** WHEN a savings counter is shown THEN the system SHALL label it
  **estimated**, SHALL show its assumptions in a tooltip, and SHALL show the
  source id for its value.
- **AC-24** WHEN no load has been reduced THEN every savings counter SHALL read
  zero.
- **AC-25** WHEN a utility user opens the recruitment list THEN the system
  SHALL show high-load, unenrolled buildings located in EJ zips within the
  session utility's territory, from the data.
- **AC-26** WHEN a utility user toggles cap-on / cap-off on the season replay
  THEN the system SHALL redraw the cumulative-calls-by-zip view for that setting.
- **AC-39** WHEN a utility user exports the season equity report THEN the system
  SHALL produce a file containing cumulative calls by zip, EJ status, and the
  cap setting for the session utility's territory only, with a source id for
  every number.

### Building account
- **AC-27** WHEN a facility manager views their account THEN the system SHALL
  show that building's enrolled capacity, zip, EJ flag, protected flag, last
  called date, and season call count alongside the territory median, scoped to
  that building only.
- **AC-28** WHEN an approved event includes this building THEN the system SHALL
  show the kW requested, the window, the reason ("why you"), and the estimated
  payment, and SHALL offer YES / NO / a numeric-offer reply control.
- **AC-29** WHEN the facility manager submits a reply THEN the system SHALL send
  it to the backend and SHALL reflect the submitted reply in the UI.
- **AC-40** WHILE no approved event includes this building THEN the system
  SHALL show no live ask, including for draft or rejected events.
- **AC-41** WHEN a facility manager views their account THEN the system SHALL
  show the building's history of past asks, replies, delivered kW, and payments.
- **AC-42** WHEN a facility manager updates the building's offered capacity THEN
  the system SHALL persist the new value for that building only and SHALL show
  the updated value.
- **AC-43** THE building account SHALL show no map, zip aggregate, other
  building, trace, or operator control.

### Access control (BFF)
- **AC-44** THE BFF SHALL declare a required role on every non-public route and
  SHALL reject requests whose session role does not match.
- **AC-45** WHEN a `utility` session calls a utility route THEN the BFF SHALL
  filter every query by the session's `utility_id`.
- **AC-46** WHEN a `building_manager` session requests `/building/:id/*` with an
  `id` different from the session's `building_id` THEN the BFF SHALL return 404
  so that building ids cannot be enumerated.
- **AC-47** FOR ALL random sessions and random buildings, a `building_manager`
  session SHALL never read a row whose `building_id` differs from its own, and a
  `utility` session SHALL never read a row outside its `utility_id`
  (property-based test).
- **AC-48** WHEN an event is not approved THEN the system SHALL contact no
  building for that event, for any role.

### Data model and seed
- **AC-49** THE `users` table SHALL store `role` as `utility` or
  `building_manager`; a `utility` row SHALL carry a `utility_id` and a NULL
  `building_id`, and a `building_manager` row SHALL carry a `building_id`, with
  `utility_id` derived from that building.
- **AC-50** THE system SHALL assign each zip, and through it each building,
  event, reply, and trace step, to a utility from a utility-by-town dataset
  joined to zip, with the dataset's source id recorded.
- **AC-51** WHEN `make setup` runs THEN the seed SHALL create one utility
  account `utility@demo` / `demo-utility-pass` whose territory is the Boston zips
  in BERDO.
- **AC-52** WHEN `make setup` runs THEN the seed SHALL create three
  `building_manager` accounts `building1@demo`, `building2@demo`,
  `building3@demo`, all with password `demo-building-pass`, tied to three BERDO
  buildings in different zips, of which one is in an EJ zip and one is flagged
  protected.
- **AC-53** THE README SHALL document the demo credentials under a "Demo
  accounts" heading.
- **AC-54** THE system SHALL store passwords as bcrypt hashes and SHALL offer no
  sign-up or password-reset flow.

### MCP tools
- **AC-55** FOR ALL inputs, each MCP tool (`estimate_load`, `rank_candidates`,
  `check_constraints`, `score_equity`, `plan_event`, `backfill`, `reconcile`,
  `estimate_savings`, `recruitment_list`) SHALL return the same output for the
  same input (property-based test).
- **AC-56** FOR ALL plans returned by `plan_event` or `backfill`, the EJ share
  SHALL be at or below the configured cap (property-based test).
- **AC-57** IF the target cannot be met under the configured cap THEN
  `plan_event` SHALL return an "unreachable" result carrying the trade-off (cap
  value vs achievable MW) and SHALL return no over-cap plan.
- **AC-58** FOR ALL plans, no building called in the immediately previous event
  SHALL be included (property-based test).
- **AC-59** FOR ALL plans WHILE the heat threshold is exceeded, no protected
  facility (schools in session, cooling centers, nursing homes, or a facility the
  operator marked protected) SHALL be included (property-based test).
- **AC-60** WHEN `check_constraints` finds a violation THEN the tool SHALL name
  the violated constraint and the offending buildings.
- **AC-61** WHEN `estimate_load` has no EUI or electricity share for a building
  THEN the tool SHALL return either an estimate with `basis:
  "estimated_from_type"` or "unavailable" with the reason, and SHALL never
  return an unlabeled number.
- **AC-62** WHEN any tool returns a number THEN the result SHALL carry a source
  id and URL; rates, capacity prices, LMPs, and emissions factors SHALL come
  from the single constants file with one citation per constant.
- **AC-63** WHEN `estimate_savings` returns a figure THEN the figure SHALL be
  labeled estimated and its assumptions SHALL be retrievable.
- **AC-64** FOR ALL sets of building replies and meter reads, `reconcile` SHALL
  report delivered kW per building that sums to the event's total delivered kW
  (property-based test).

### Agent loop
- **AC-65** WHEN an event is drafted THEN the agent loop SHALL run forecast →
  plan v1 → critic constraint check → self-correction → plan v2 by calling the
  MCP tools, and SHALL log each step to `trace_steps` with timestamp, kind,
  summary, plan version, tool name, and the rejecting constraint.
- **AC-66** WHEN the critic rejects a plan version THEN the planner SHALL produce
  a revised version, and the trace SHALL retain both the rejected and the
  accepted versions.
- **AC-67** WHEN the agent loop finishes THEN the system SHALL hold the plan as
  a draft awaiting operator Approve, Edit list, or Reject, and SHALL contact no
  building before approval.
- **AC-68** IF the planner reaches its iteration limit without a plan that
  passes the critic THEN the agent loop SHALL return the unreachable trade-off
  and stop.

### Simulator
- **AC-69** WHEN an approved event is live THEN the simulator SHALL generate
  replies (YES / NO / numeric offer) and meter reads for the asked buildings,
  deterministically from a seed, and SHALL mark every generated row
  `simulated = true`.

### Cross-cutting
- **AC-30** WHEN any user-facing number is displayed THEN the system SHALL be
  able to show its source id (per the provenance steering rule), and no number
  SHALL appear without a backing source.
- **AC-31** WHEN the user's system requests reduced motion THEN the map load-shift,
  heat-day replay, and counter animations SHALL be disabled or reduced.
- **AC-32** WHEN simulated data (enrollment, replies, meter readings) is
  displayed THEN the system SHALL label it as simulated for the demo.
- **AC-70** THE system SHALL use "asked to reduce" or "event participation" in
  user-facing text and SHALL never display "cut", "shut off", "curtail", or
  "disconnect".

## Out of Scope

- A separate city building-performance office role. Recruitment and season
  equity views live inside the utility account.
- Equity info on the per-building account view beyond the EJ flag and the
  season call count vs territory median — **later step** per the project brief.
- Linking a phone number / email to set up alerts, alert opt-in, and the alert
  messages themselves — **later step**.
- Real SMS delivery (Twilio). The building-reply flow is in the web UI; the
  SMS/reply stream on the utility side shows simulated replies, not a live
  integration.
- Sign-up, password reset, and any real identity provider; auth is a seeded
  stub.
- Database row-level security; access control is enforced in the BFF.
- Live data ingestion pipelines beyond the one-time seed (BERDO, EJ, and
  utility-by-town loads are seed-time imports).
- CSS-level visual design system / branding beyond a clean, accessible,
  theme-consistent layout.
