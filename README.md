# experiment-forecast

Agentic optimization loop for forecasting Homerunner **daily shipment
volumes per customer**. A fixed, hash-locked eval is the optimization goal;
an agent (or human) iterates experiments against it and climbs the
leaderboard. The loop protocol lives in [CLAUDE.md](CLAUDE.md).

## Decisions

| Decision | Value | Where |
|---|---|---|
| Data source | Snowflake `MARTS.ANALYTICS.SHIPMENTS` (frozen extract) | `data/extract/` |
| Target | Daily shipment count per series, outbound non-cancelled (`IS_BOOKED_RETURN=FALSE, CANCEL_AT IS NULL`; passive returns still count — the outbound leg shipped) | `data/snapshot/series_meta.json` |
| Series | Top-100 customers (94% of volume) + 5 tail groups (volume-quintile bands of the rest) = 105 series partitioning network volume | `data/extract/membership.csv` |
| Horizon | 14 days, from weekly Monday cutoffs | `eval/stages.yaml` |
| Primary metric | Pooled wMAPE (Σ\|err\| / Σactual over all scored series-days) | `eval/metrics.py` |
| Backtest | Staged, back-in-time first: stage1=2023 → stage2=2024 → stage3=2025–mid-2026; train data from 2021 | `eval/stages.yaml` |
| Holdout | Jun–Jul 2026 cutoffs, locked (`HOLDOUT_OK=1`, human only) | `eval/stages.yaml` |

Target rows, horizon, metric and stage layout were set to the recommended
defaults after source + series design were chosen; each is a one-line config
change **before** optimization starts (changing any of them later
invalidates the leaderboard and requires re-writing `eval/EVAL_LOCK`).

Known caveat (deliberate): top-100 membership is defined on the trailing
year 2025-08 → 2026-08, which overlaps the later eval windows. Membership is
a product decision ("today's largest 100 customers"), not model input, so
this does not leak target values — but stage1/stage2 score only the subset
of those customers already active at each cutoff (the eval masks series
before their `first_date`).

## Layout

```
CLAUDE.md                     loop protocol (read first)
eval/                         FROZEN: eval.py, metrics.py, stages.yaml, EVAL_LOCK
data/snapshot/                FROZEN: daily_shipments.parquet, series_meta.json, MANIFEST.json
data/extract/                 provenance: how the snapshot was pulled from Snowflake
experiments/                  one folder per experiment (copy template/)
results/leaderboard.csv       append-only run history (wMAPE = sort key)
results/runs/                 full per-run records incl. per-cutoff + worst-series
results/JOURNAL.md            hypothesis → outcome log
```

## Quickstart

```bash
uv sync --extra models
uv run python -m eval.eval --experiment 000_seasonal_naive --stage stage1
```

## Data provenance

The snapshot was extracted once (2026-08-06) from `MARTS.ANALYTICS.SHIPMENTS`
via the Snowflake MCP connector: deterministic payload queries sliced with
`SUBSTR`, captured verbatim to disk by a `PostToolUse` hook
(`scripts/hooks/save_snowflake_result.py`), reassembled and validated by
`data/extract/build_snapshot.py` against in-warehouse `LENGTH`/`MD5` and an
independent per-series totals query. Membership (account → series) was
frozen as literals in `data/extract/membership.csv` before extraction so the
mapping cannot drift. See `data/extract/README.md`.
