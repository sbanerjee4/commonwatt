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
