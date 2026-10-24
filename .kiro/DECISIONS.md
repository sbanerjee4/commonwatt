# Decisions log

| Time | Decision | Why | What we tried first |
| ---- | -------- | --- | ------------------- |
| Oct 24 | Commit BERDO data as `fixtures/berdo.json` instead of fetching live | Public, static annual dataset (1.2 MB); lets the app run offline and in tests, and judges run `make demo` with no network | Fetching the datastore API at runtime |
| Oct 24 | Rename the tools package `mcp/` -> `server/` | Our folder named `mcp` shadowed the installed `mcp` pip package that FastMCP depends on, breaking imports | Keeping it as `mcp/` |
| Oct 24 | Use Amazon Bedrock (not the direct Anthropic API) for Claude | Team is on AWS; single credential, AWS-native path | Direct Anthropic `sk-ant-` key |
| Oct 24 | Use a cross-region inference profile id (`us.anthropic.claude-haiku-4-5-...`) | Bedrock retired bare model ids and the old 3.5 Haiku; new models require an inference profile | `anthropic.claude-3-5-haiku-20241022-v1:0` (404 end-of-life) |
| Oct 24 | `load_dotenv(override=True)` | An empty `AWS_BEARER_TOKEN_BEDROCK` in the shell was shadowing the real key in `.env` | Plain `load_dotenv()` |
| Oct 24 | Guard Site EUI at <=1000 kBtu/ft2 | BERDO has data-entry errors (EUI of 50000) producing absurd 288 MW single-building load estimates | Trusting all metered EUI values |
| Oct 24 | Synthetic stable ids for rows missing BUILDING_ID | 2077 of 2472 rows have no BUILDING_ID but all have an address; every building must be addressable for chat + markers | Dropping rows without an id |
| Oct 24 | Deterministic planner scaffold, LLM narrates | The LLM inconsistently skipped the naive v1, so the critic-rejection arc did not always show; the demo needs it every run | Fully LLM-driven tool choice |
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
| Oct 24 | This Kiro version has no manual hook trigger; deterministic checks moved to scripts/ as make targets and a pre-commit hook; evidence snapshot runs on SessionStart; fix-proposal folded into the on-save test hook with an approval gate. | Only the supported triggers can run hooks, and scripts run the same way with or without the agent | Manual-trigger hooks (fix-failing-property, evidence-snapshot, pre-submit-check) |
| Oct 24 | Merge branches: MCP tools live in `server/` (from main), not `mcp/commonwatt_mcp/` | Both branches independently hit the `mcp` shadowing problem; one name, `server/`, is used everywhere | Keeping both layouts |
