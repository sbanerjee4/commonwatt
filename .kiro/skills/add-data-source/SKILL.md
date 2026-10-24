---
name: add-data-source
description: Add a new public dataset to Commonwatt as a committed fixture plus typed access, following the BERDO pattern.
---

# Add a data source

Use this when wiring a new public dataset (another city's benchmarking data, an
EJ layer, a utility-by-town table, a weather feed) into Commonwatt.

Commonwatt's rule: data is pulled once, cleaned, and committed as a fixture, so
the app runs offline and in tests. The model never reads the raw file — it goes
through typed access and tools, which keeps numbers sourced.

## Steps

1. **Pull a sample and inspect the shape.**
   Fetch a few records and audit which fields are populated and what fraction
   are null. Note the identifier field and whether it is reliably present.

2. **Clean and commit the fixture.**
   Write the cleaned records to `fixtures/<name>.json` with a top-level
   `source` string (dataset name + resource id + URL). Coerce numeric strings
   to numbers; map only the fields you need.
   - Give every record a stable id. If the source id is missing on many rows,
     synthesize one from a hash of a stable field (e.g. address), as BERDO does.
   - Normalize join keys (zip to 5 digits, etc.). Drop or flag malformed rows
     rather than letting them crash sorts/joins.
   - Guard against data-entry outliers (e.g. clamp implausible values) so they
     do not produce absurd downstream numbers.

3. **Add typed access in `server/data.py`.**
   Add a dataclass and cached loader (`@lru_cache`) mirroring the Building
   pattern. Compute derived fields in `__post_init__`.

4. **Record provenance.**
   Add a `*_SOURCE_ID` constant and any rates/factors to `server/constants.py`,
   one citation per constant. Every value the UI shows must trace to a source.

5. **Expose it through a tool, not raw.**
   Add an MCP tool in `server/tools.py` that returns the data with its
   `source_id`. Write a Hypothesis property test in `tests/properties/` BEFORE
   wiring the tool into the agent or BFF.

6. **Surface via the BFF if the front-end needs it.**
   Add a read endpoint in `bff/app.py` shaping the data into a view-model with
   `source_id` on every number.

7. **Log the decision.**
   Add a row to `.kiro/DECISIONS.md` (what, why, what you tried first).

## Reference

The BERDO wiring is the canonical example: `fixtures/berdo.json`,
`server/data.py` (Building, EJ_ZIPS, load estimation with the EUI guard),
`server/tools.py` (building_info), and the PBT in
`tests/properties/test_mcp_invariants.py`.
