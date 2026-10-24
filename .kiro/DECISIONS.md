# Decisions log

| Time | Decision | Why | What we tried first |
| ---- | -------- | --- | ------------------- |
| Oct 24 | Cut Mongo and Supabase Auth; one Postgres with seeded users so judges can run from a clean clone | Simplify demo setup, single source of truth, faster iteration, real foreign keys for role boundary | Separate Mongo for state + Supabase managed auth |
| Oct 24 | Two roles only: `utility` and `building_manager`; city views moved into the utility account | User-defined role model; one account per utility and per building | Separate `operator`, `city`, `facility_manager` roles |
| Oct 24 | Wrong role or mismatched building id returns 404, not 403 | Building ids must not be enumerable | 403 on mismatch |
| Oct 24 | Scope enforced through `UtilityRepo`/`BuildingRepo`, a boot check that every route has a role, and an import ban on raw DB sessions in routes | Makes the utility_id/building_id filter impossible to skip without RLS | Per-route `id == session.buildingId` checks plus Postgres RLS |
| Oct 24 | Cookie carries an opaque token hashed in `sessions`; role read from the server row | Role must come only from the server session | Role and buildingId stored in the cookie |
| Oct 24 | Zip map rendered as zip-centroid hexes from a committed GeoJSON | User asked for a zip-hex map; removes runtime zip-boundary dependency | Zip-polygon choropleth from MassGIS/TIGER |
| Oct 24 | `call_history` written only on Approve; per-version membership in `plan_buildings` | A contact can exist only behind the human gate; all versions retained | Plans and calls in one table |
| Oct 24 | Tool package named `commonwatt_mcp` under `mcp/` | A top-level `mcp` package would shadow the MCP SDK FastMCP imports | Top-level `mcp/` package |
| Oct 24 | Planner and critic are deterministic code; v1 is unconstrained greedy, corrections go through `plan_event` | Keeps tools deterministic while giving the critic a real rejection to show | Model-driven planner |
| Oct 24 | Trace streamed over SSE with replay from `trace_steps` | Reconnects must not lose steps | Unspecified stream |
| Oct 24 | Seed from a committed BERDO subset with pre-geocoded coordinates | Clean clone must run `make setup` with no network | Geocode all 2,472 rows at ingest |
| Oct 24 | Zip is EJ if any EJ block-group centroid falls inside it | The join rule was unstated; recorded with its source | None |
| Oct 24 | Uncited constants carry no value; dependent figures return "unavailable" | Provenance rule forbids invented rates | Placeholder values |
| Oct 24 | Edit list is a constrained re-solve; Approve disabled on unreachable plans | An edited or short plan cannot bypass the critic | Free-form list edit |
| Oct 24 | design.md headings renamed to "Components and Interfaces" and "Data Models" | Spec format validator requires those names | "Components", "Data Sources" |
