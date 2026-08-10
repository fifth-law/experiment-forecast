# Monthly sales-invoiced snapshot extraction (provenance)

`data/snapshot_sales/` was pulled from Snowflake `MARTS.ANALYTICS.SALES_INVOICE_DETAILS`
on **2026-08-10** through the MCP connector, which cannot return large result sets
and times out after 60s. The pipeline works around both limits without any
hand-copying of data.

## Pipeline

1. **Membership is reused, not re-derived.** `gen_sales_sql.py` reads the shipment
   track's frozen `data/extract/membership.csv` and compiles it into a compact
   `CASE` over account-id lists, so both tracks score the identical 105 series and
   the mapping cannot drift with the live mart.

2. **Probe first.** `sql/probe.sql` sizes the extraction and measures the
   creation-offset distribution per year — that is where the `MAX_OFFSET = 120`
   clip is justified (0.000% of DKK is created beyond +120 days in any year) and
   where the era findings in `results_sales/JOURNAL.md` come from.

3. **Payload queries.** Per window, a CTE pipeline builds one deterministic text
   payload: a header, one line per (series, posting month) holding sparse
   `offset:øre` cells, and a `#M` trailer of per-month totals. Amounts are integer
   øre because a float `SUM` is order-dependent — a rounded float total is not
   reproducible run to run, which would make the payload MD5 worthless as a
   transport check.

4. **Windows, not years.** `WINDOWS` in `gen_sales_sql.py` tiles 2021-01..2026-06.
   2025 is split into halves: the source table is ~262M rows and a single query
   covering the whole range exceeds the connector's 60s budget even with both
   aggregation levels coming out of one scan via `GROUPING SETS`.

5. **Sliced transfer, no transcription.** Each slice query returns
   `SUBSTR(payload, off, 200000)` *plus* the whole payload's `LENGTH` and `MD5`
   from the same run, plus 200k characters of `PAD`. The pad is load-bearing: a
   result that large is written to a file by the harness verbatim instead of being
   rendered into the model's context, so payload bytes never pass through a model
   and never have to be re-typed. `capture_slice.py` copies the `CHUNK` column out
   of that file into `data/raw_sales/mcp_results/`.

6. **Assembly + validation.** `build_sales_snapshot.py` refuses to write unless
   every check passes:
   - reassembled length and MD5 equal what Snowflake reported for the payload;
   - the header's declared line counts and window match the parsed content;
   - the windows tile the month range exactly, no gap, no overlap;
   - per-month totals summed over the 105 series equal the `#M` trailer totals,
     which Snowflake computed *without* the series mapping — this is what proves
     the series partition the network exactly. Integer øre make it exact equality,
     not a tolerance;
   - every series id belongs to the frozen 105-series split.

## Outputs

```
data/snapshot_sales/monthly_sales_triangle.parquet   series_id, posting_month, create_offset, ore
data/snapshot_sales/series_meta.json                 catalogue, target definition, limitations
data/snapshot_sales/MANIFEST.json                    checksums, per-window provenance, month totals
```

59,108 cells, 66 posting months, 103 of 105 series (`c_397088` and `c_405616` had
invoiced nothing by 2026-06).

## Re-extracting

Move `LAST_MONTH` forward as months settle, bump `EXTRACT_VERSION`, re-run steps
3-6. **Do not include a month before it has settled**: this snapshot stops at
2026-06 because on 2026-08-10 the month 2026-07 was still roughly a third short of
its final total (27.1M DKK against 41.0M for June) — the +8..+15 day creation wave
had not landed. Including it would train and score models against a target that
does not exist yet.

**A new snapshot is a new eval**: `eval_sales/EVAL_LOCK` must be rewritten
deliberately (`EVAL_UNLOCK=1 uv run python -m eval_sales.eval --write-lock`) and
the leaderboard restarts. Never splice results across snapshots.

Retroactive-data caveat: the as-of reconstruction comes from a single point-in-time
snapshot, so invoice lines that existed on a past night but were deleted later are
absent from the mart entirely, and the reconstruction can slightly understate what
was visible at the time.
