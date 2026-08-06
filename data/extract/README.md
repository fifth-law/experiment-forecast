# Snapshot extraction (provenance)

The frozen snapshot in `data/snapshot/` was pulled from Snowflake
`MARTS.ANALYTICS.SHIPMENTS` on 2026-08-06 through the MCP connector, which
cannot return large result sets. The pipeline works around that without any
hand-copying of data:

1. **Membership freeze.** Three marked queries (`/*SNAPMETA .../`) captured
   the top-100 accounts (+ names, ref-window volumes, first shipment dates)
   and the ranked tail (ranks 101–270). `gen_extract_sql.py
   --emit-membership` turns the captures into `membership.csv`; every later
   query embeds this mapping as literals, so series definitions cannot
   drift with the live mart.
2. **Payload queries.** Per year, a CTE pipeline builds one deterministic
   text payload: a header line plus one line per series with 365/366 dense
   daily counts (`gen_extract_sql.py --emit-year-sql`). `meta_<year>.sql`
   returns the payload's LENGTH + MD5; `totals_<year>.sql` returns
   independent per-series totals.
3. **Sliced transfer.** `--emit-slices <year> <plen>` writes
   `SUBSTR(payload, off, 40000)` queries. Subagents execute them; a
   `PostToolUse` hook (`scripts/hooks/save_snowflake_result.py`, wired in
   `.claude/settings.json`) saves every MCP result verbatim to
   `data/raw/mcp_results/` — no model ever re-types payload bytes.
4. **Assembly + validation.** `build_snapshot.py` reassembles slices by
   offset and refuses to write unless (a) length and MD5 match the
   in-warehouse values, and (b) parsed per-series yearly totals equal the
   independent totals query. Output: `daily_shipments.parquet`,
   `series_meta.json`, `MANIFEST.json`.

## Re-extracting (e.g. to widen the window later)

Adjust `SNAPSHOT_START`/`SNAPSHOT_END`/`YEARS` in `gen_extract_sql.py`, bump
`EXTRACT_VERSION`, and repeat phases 2–4. **A new snapshot is a new eval**:
`eval/EVAL_LOCK` must be deliberately re-written (`EVAL_UNLOCK=1 uv run
python -m eval.eval --write-lock`) and the leaderboard restarts — never
splice results across snapshots. Keep the membership freeze unchanged unless
the product decision itself changes.

Retro-active data caveat: `CANCEL_AT` can be set long after booking, so a
re-extract of the same window will differ slightly from this snapshot. That
is expected and exactly why the parquet, not the query, is the source of
truth.
