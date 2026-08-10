# Monthly Sales-Invoiced Forecaster — the second track

Sibling of the shipment forecaster described in `CLAUDE.md`, same agentic loop,
same 105-series split, different metric. Read `CLAUDE.md` first for the loop
philosophy; this file records only what differs.

## The metric

**Net sales invoiced, excl. VAT, in DKK, for a whole calendar month, per series,
re-forecast every night.**

Source: `MARTS.ANALYTICS.SALES_INVOICE_DETAILS`, `SUM(SALES_PRICE_EXCL_VAT_IN_DKK)`
attributed to the calendar month of `POSTING_DATE` (the invoice posting date).
Credit notes and corrections net out; deleted invoices and lines are excluded
upstream by the mart. Amounts are stored as integer øre so the extract is exactly
reproducible.

On the night of day `c`, for each of the 105 series, predict what the month
containing `c` will total **once it has settled**. The same month is forecast
~30 times, from a cold start on the 1st to a near-nowcast on the last night.

## The one number

```
uv run python -m eval_sales.eval --experiment <name> --stage <current_stage>
```

Primary metric: **pooled wMAPE** = `sum|yhat - y| / sum|y|` (the denominator uses
`|y|` because a series-month can net negative). `results_sales/leaderboard.csv` is
sorted truth. Diagnostics worth mining before picking a hypothesis: `per_dom`
(the error-decay curve across the month), `per_cutoff`, `worst_series` in
`results_sales/runs/`.

## What makes this problem different from the shipment one

1. **~90% of a month's invoice lines post on the last day of the month.** The
   metric is a month-end event, not a daily flow.
2. **A month's total is not knowable at month end.** For 2026-06, ~27% of the
   month's DKK was created 8-15 days *after* the month ended. So a nightly job
   cannot see the settled total of the month it forecasts, nor of last month.
3. **Billing moved from arrears to same-month during 2025** (previous-month
   shipment share: 83% in 2023 → 6% in 2026), so the metric does not mean quite
   the same thing across eras. Expect ranks to reshuffle between stages; that is
   a finding, not a bug.

Because of (2) the snapshot is a **reporting triangle**, not a monthly series:

```
data/snapshot_sales/monthly_sales_triangle.parquet
    series_id, posting_month, create_offset, ore
```

`create_offset` = days from the first of the posting month to
`DATE(INVOICE_LINE_CREATED_AT)`, clipped to [0, 120]. Summing increments with
`create_offset <= (cutoff - month start)` reproduces exactly what was visible on
that night; summing all of them gives the settled total. The eval does this for
you — models never see the future.

## Hard rules (same spirit as CLAUDE.md)

1. **The eval is frozen.** Never edit `eval_sales/`, `eval_sales/stages.yaml`,
   `data/snapshot_sales/`, `data/snapshot/`, or either `EVAL_LOCK`. The run
   aborts if their joint hash changes. Disagree in `results_sales/JOURNAL.md`
   and stop — the human owner decides.
2. **Never run the `holdout` stage** (2026-05..06). Final exam, run once by the
   owner with `HOLDOUT_OK=1`.
3. **Experiments learn only from the two frames they are handed** — the as-of
   invoice `history` and `shipments` — plus timeless knowledge (weekday, month,
   public holidays via `holidays`). Never read `data/` from an experiment, never
   hardcode a fact learned by eyeballing the snapshot.
4. **One experiment = one folder** `experiments_sales/NNN_short_name/` (copy
   `experiments_sales/template/`), never modified after it has been run.
5. **Every run gets journaled** in `results_sales/JOURNAL.md`: hypothesis, result
   vs. best, what was learned. Failures are information — 001 and 004 both earned
   their entries. Commit experiments and results together.

## The experiment contract

```python
class Forecaster:
    def fit_predict(self, history, shipments, cutoff, target_month, series_meta):
        """history:   DataFrame(series_id, posting_month, create_date, dkk)
                      invoiced increments visible on the night of `cutoff`
           shipments: DataFrame(date, series_id, y), daily counts, date <= cutoff
                      (the frozen shipment snapshot — volume leads revenue and
                      has no reporting lag)
           returns:   DataFrame(series_id, yhat), one row per series, DKK for the
                      whole target month. Negatives allowed, not clipped."""
```

A fresh `Forecaster` per cutoff. Cutoffs run chronologically, so module-level
caching of work derived from frames already handed in is allowed; anything else
is leakage. Determinism is part of the contract.

## Stages

`stage1` (every night of 2023) → `stage2` (2024) → `stage3` (2025-01..2026-04)
→ STOP. `holdout` = 2026-05..06, locked. History starts 2021-01.

**stage3 is the production-relevant era.** Promotion rule as in `CLAUDE.md`: three
consecutive experiments each failing to improve the stage best by 0.3% relative.

## Where it stands

| | stage1 | stage3 (production era) |
|---|---|---|
| best | **005_seasonal_anchor** 0.1066 | **007_recent_curve** 0.2416 |
| baseline (`000_prev_month`) | 0.2132 | 0.3638 |

The two stages disagree on the winner, and the reason is structural: on stage1 the
month is fully visible by month end (late-month wMAPE 0.015), so the problem is
level and seasonality; on stage3 a quarter of the month is still invisible on the
last night (late-month wMAPE 0.163), so the problem is completing what cannot be
seen. See `results_sales/JOURNAL.md` for the full log and the ranked list of next
hypotheses.

## Re-extracting

`data/extract_sales/README.md` documents the pipeline. A new snapshot is a new
eval: `eval_sales/EVAL_LOCK` must be rewritten deliberately and the leaderboard
restarts. The natural reason to re-extract is to move `LAST_MONTH` forward as
months settle — every added month is one more month of targets.
