# Requirements — Front-end: Visualization Map & Dashboards

## Overview

Commonwatt is an equity-constrained demand-response planner for Massachusetts
utilities. This spec covers the **web front-end**: the public surface, the
sign-in flow, and the two authenticated dashboards.

There are three audiences and three screens:

1. **Public page** — anyone. Promotional and explanatory. Explains what
   Commonwatt is (voluntary, paid, equity-constrained, human-approved) and
   routes visitors to sign in.
2. **Utility dashboard** — the demand-response operator and the city
   building-performance office. The whole portfolio: a map of all buildings
   (zip-choropleth aggregate with building-marker drill-in), a knowledge graph
   of how zips / buildings / EJ status / events relate, the agent trace, the
   operator event card, and the savings counters.
3. **Building account** — a single enrolled building's facility manager. Only
   that building's status: its load, its event history, its payments, and the
   current ask when an event is live.

The map has two layers. The **aggregate layer** is a zip-code choropleth — the
equity and burden story is inherently zip-level (EJ join, cumulative calls per
season), so this stays the primary view. The **building layer** is individual
building markers, drilled into on click: the building dataset now carries a
street `Address` and `Zip` for all 2,472 buildings (Boston BERDO datastore
resource `43e4abc9-1fae-40d9-a02e-ff950bd0e732`), so the backend can geocode
each address to a point and the front-end can plot and inspect specific
buildings — not just zips.

The front-end only reads and displays; every number comes from the backend (the
Commonwatt MCP tools and the Mongo store, which holds the geocoded buildings).
The front-end never computes a dispatch number itself.

## Users and goals

| User | Screen | Goal |
| --- | --- | --- |
| Visitor (public) | Public page | Understand Commonwatt; decide to sign in |
| DR operator (primary) | Utility dashboard | See the portfolio, read the agent's plan and trade-offs, approve/edit/reject an event |
| City building-performance office | Utility dashboard | Read the recruitment list and the season equity report |
| Facility manager | Building account | See this building's status, history, payments, and the live ask |

## User Stories

### Public page
- **US-1** As a visitor, I want a public landing page with general promotional
  information about Commonwatt so that I understand the product before signing in.
- **US-2** As a visitor, I want a clear sign-in entry point where I choose my
  role (utility or building) so that I land on the correct dashboard.

### Authentication
- **US-3** As a utility operator, I want to sign in with a utility account so
  that I reach the full portfolio dashboard.
- **US-4** As a facility manager, I want to sign in with a building account so
  that I see only my building's status.
- **US-5** As any signed-in user, I want to sign out so that my session ends.

### Utility dashboard — map
- **US-6** As an operator, I want a map of all buildings with a zip-choropleth
  aggregate layer so that I can see where load and equity burden sit
  geographically.
- **US-7** As an operator, I want to color the map by metric (curtailable load,
  EJ status, cumulative calls this season) so that I can read the trade-off
  visually.
- **US-8** As an operator, I want to click a zip to see its buildings, load, and
  EJ status so that I can inspect a candidate area.
- **US-8b** As an operator, I want to drill from a zip into individual building
  markers (placed from each building's geocoded address) and click a building to
  see its address, type, area, EUI, and estimated curtailable load so that I can
  inspect a specific building.

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

### Utility dashboard — counters & reports
- **US-14** As an operator, I want three savings counters (paid to buildings,
  avoided system cost, CO₂ avoided), each labeled **estimated** with its
  assumptions and source on screen, so that I can trust the numbers.
- **US-15** As the city office, I want a recruitment list of high-load,
  unenrolled buildings in EJ zips so that I know who to recruit.
- **US-16** As the city office, I want a season report of cumulative calls by
  zip, with a cap-on / cap-off toggle, so that I can see the equity effect over
  time.

### Building account
- **US-17** As a facility manager, I want to see my building's current status
  (enrolled capacity, recent load, whether I'm being asked today) so that I know
  where I stand.
- **US-18** As a facility manager, I want to see my building's event history and
  payments so that I can track what I've earned.
- **US-19** As a facility manager, when an event is live I want to see the ask
  (kW requested, why me, estimated payment) and reply YES / NO / a number so
  that I can respond.

## Acceptance Criteria

Written in EARS form. "The data" means values read from the backend (Mongo /
MCP tools); the front-end renders them, it does not compute them.

### Public page
- **AC-1** WHEN a visitor loads the site root THEN the system SHALL display the
  public page with the Commonwatt tagline and a short promotional description,
  and SHALL NOT require authentication.
- **AC-2** WHEN a visitor clicks sign in THEN the system SHALL present a choice
  of role: utility or building.

### Authentication
- **AC-3** WHEN a user signs in as utility with valid credentials THEN the
  system SHALL route to the utility dashboard.
- **AC-4** WHEN a user signs in as building with valid credentials THEN the
  system SHALL route to that building's account page and SHALL scope all data to
  that one building.
- **AC-5** WHEN sign-in credentials are invalid THEN the system SHALL show an
  error and remain on the sign-in screen.
- **AC-6** WHEN an unauthenticated user requests the utility dashboard or a
  building account THEN the system SHALL redirect to sign-in.
- **AC-7** WHEN a building user requests the utility dashboard THEN the system
  SHALL deny access and SHALL NOT reveal other buildings' data.
- **AC-8** WHEN a signed-in user signs out THEN the system SHALL end the session
  and return to the public page.

### Map
- **AC-9** WHEN the utility dashboard loads THEN the system SHALL render a
  MapLibre choropleth of Massachusetts zip codes as the aggregate layer, each
  zip colored by the selected metric.
- **AC-10** WHEN the operator changes the map metric (curtailable load / EJ
  status / cumulative calls) THEN the system SHALL recolor every zip from the
  data for that metric and SHALL update the legend.
- **AC-11** WHEN the operator clicks a zip THEN the system SHALL display that
  zip's building count, estimated curtailable load, EJ status, and cumulative
  calls this season.
- **AC-11b** WHEN the operator drills into a zip THEN the system SHALL plot that
  zip's buildings as markers at their geocoded address positions, and WHEN a
  marker is clicked THEN the system SHALL show that building's address, property
  type, gross area, EUI, and estimated curtailable load.
- **AC-11c** WHEN a building's load inputs (EUI or electricity share) are missing
  from the data — which is the case for roughly half the dataset — THEN the
  system SHALL display the building with an explicit "load unknown / estimated
  from type" indicator rather than a fabricated number or a blank.
- **AC-12** WHEN the map has no geometry for a zip present in the data THEN the
  system SHALL list that zip in a side panel rather than silently dropping it.
- **AC-12b** WHEN a building's address cannot be geocoded to a point THEN the
  system SHALL still list it in the zip's building panel rather than silently
  dropping it.

### Knowledge graph
- **AC-13** WHEN the operator opens the knowledge-graph view THEN the system
  SHALL render nodes for zips, buildings, EJ block groups, utilities, and
  events, with edges for their relationships, from the data.
- **AC-14** WHEN the operator selects a graph node THEN the system SHALL
  highlight its direct neighbors and show that node's attributes.

### Agent trace
- **AC-15** WHEN a plan is generated THEN the system SHALL display, in order,
  each agent step with its timestamp and a one-line summary (forecast, plan v1,
  constraint check, self-correction, plan v2).
- **AC-16** WHEN a plan has more than one version THEN the system SHALL keep
  every version visible in the trace and SHALL mark which constraint caused each
  revision.
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

### Counters & reports
- **AC-23** WHEN a savings counter is shown THEN the system SHALL label it
  **estimated**, SHALL show its assumptions in a tooltip, and SHALL show the
  source id for its value.
- **AC-24** WHEN no load has been shed THEN every savings counter SHALL read
  zero.
- **AC-25** WHEN the city office opens the recruitment list THEN the system
  SHALL show high-load, unenrolled buildings located in EJ zips, from the data.
- **AC-26** WHEN the city office toggles cap-on / cap-off on the season report
  THEN the system SHALL redraw the cumulative-calls-by-zip view for that setting.

### Building account
- **AC-27** WHEN a facility manager views their account THEN the system SHALL
  show that building's enrolled capacity, recent load, event history, and total
  payments, scoped to that building only.
- **AC-28** WHEN an event is live and this building is asked THEN the system
  SHALL show the kW requested, the reason, and the estimated payment, and SHALL
  offer YES / NO / a numeric-offer reply control.
- **AC-29** WHEN the facility manager submits a reply THEN the system SHALL send
  it to the backend and SHALL reflect the submitted reply in the UI.

### Cross-cutting
- **AC-30** WHEN any user-facing number is displayed THEN the system SHALL be
  able to show its source id (per the provenance steering rule), and no number
  SHALL appear without a backing source.
- **AC-31** WHEN the user's system requests reduced motion THEN the map load-shift
  and counter animations SHALL be disabled or reduced.
- **AC-32** WHEN simulated data (enrollment, replies, meter readings) is
  displayed THEN the system SHALL label it as simulated for the demo.

## Out of Scope

- The dispatch math itself (load estimation, ranking, constraint checking,
  equity scoring, savings formulas) — that is the MCP server and the agent
  loop, covered by other specs. This front-end only reads their results.
- Equity info on the per-building account view — **later step** per the project
  brief. The utility-side equity views (gauge, season report, recruitment list)
  are in scope; the building-facing equity breakdown is not.
- Linking a phone number / email to set up alerts, and the alert messages
  themselves — **later step**.
- Real SMS delivery (Twilio). The building-reply flow is in the web UI; the SMS
  panel on the operator side is a scripted mockup, not a live integration.
- Writing to or seeding Mongo, data ingestion (BERDO / EJ / buoy pulls),
  geocoding each building `Address` to a point, and the simulator — backend
  concerns, not this spec. The front-end consumes the already-geocoded buildings
  from the store.
- CSS-level visual design system / branding beyond a clean, accessible,
  theme-consistent layout.
