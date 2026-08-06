# Shipment Forecaster — Agentic Optimization Loop

You are (probably) a Claude session whose job is to **improve the forecast
model against a fixed eval**. Read this file fully before doing anything.

## The one number

```
uv run python -m eval.eval --experiment <name> --stage <current_stage>
```

Primary metric: **pooled wMAPE** (lower is better) on the current stage.
The leaderboard (`results/leaderboard.csv`) is sorted truth; the best wMAPE
on the current stage is the number to beat.

## Hard rules

1. **The eval is frozen.** Never edit `eval/`, `eval/stages.yaml`,
   `data/snapshot/`, or `eval/EVAL_LOCK`. The eval refuses to run if their
   hashes change. If you believe the eval is wrong, write your case in
   `results/JOURNAL.md` and stop — the human owner decides.
2. **Never run the `holdout` stage.** It is the final exam for the single
   chosen model, run once by the human owner (HOLDOUT_OK=1). Running it
   during optimization destroys its value.
3. **Experiments may only learn from the `history` frame handed to them**
   (plus timeless knowledge: weekday, month, public-holiday calendars via
   the `holidays` package). Never read `data/snapshot/` from an experiment,
   never use information dated after the cutoff, never hardcode facts you
   learned from post-cutoff data (that includes eyeballing the snapshot and
   baking what you saw into the model).
4. **One experiment = one folder** `experiments/NNN_short_name/` (copy
   `experiments/template/`). Never modify a previously-run experiment's
   `model.py`; make a new numbered folder. History must stay reproducible.
5. **Every run gets journaled.** Append to `results/JOURNAL.md`: hypothesis,
   result vs. best, what you learned. Commit experiments + results together.

## The loop

1. Read `results/leaderboard.csv` and the tail of `results/JOURNAL.md`.
2. Pick ONE hypothesis — the smallest change with a plausible mechanism.
   Mine `worst_series` and `per_cutoff` in the latest best run's JSON under
   `results/runs/` to see where the error actually lives before choosing.
3. Create `experiments/NNN_short_name/` with `model.py` + `EXPERIMENT.md`
   (hypothesis, expected behavior).
4. Run it on the **current stage**. Compare against the stage best.
5. Journal the outcome (improvements AND failures — failed hypotheses are
   information). Commit.
6. Repeat.

Current stage: **stage1** (see `eval/stages.yaml`). The stages implement
"start back in time, then jump forward and widen the window".

## Stage promotion

Promote when stage progress stalls: **3 consecutive experiments each fail to
improve the stage-best wMAPE by at least 0.3% relative**. On promotion:

1. Re-run the top 3 experiments (by current-stage wMAPE) on the next stage.
2. Note the rank stability in the journal — if ranks reshuffle badly, the
   models are overfitting the era, which is itself a finding to journal.
3. Continue the loop on the new stage. Do not go back and tune on earlier
   stages afterwards.

Order: stage1 (2023) → stage2 (2024) → stage3 (2025 – mid-2026) → STOP.
After stage3 stalls, write a summary in the journal recommending the final
model and leave holdout to the human owner.

## Modeling guardrails

- Beat the baselines first (`000_seasonal_naive`, `001_weekday_profile`).
- Prefer boring, fast, deterministic models. LightGBM and statsmodels are
  installed (`uv sync --extra models`); adding heavier deps needs a written
  justification in the journal.
- Runtime budget: a stage run should stay under ~10 minutes. If your model
  is slower, sub-sample cutoffs during your own development runs (that's
  fine for exploration, but only leaderboard-eligible runs — the full fixed
  eval — count).
- Determinism is part of the contract: fix seeds; a rerun must reproduce
  the same wMAPE.

## Facts about the data (so you don't rediscover them)

- 105 series: `c_<account_id>` × 100 (the top-100 customers of the reference
  window 2025-08 → 2026-08, ~94% of network volume) + `g1_tail`..`g5_tail`
  (cumulative-volume quintile bands of everyone else, ~320k shipments/yr
  each). Series partition total network volume exactly.
- Danish e-commerce logistics: strong weekday rhythm (weekend lows), public
  holidays matter, November peak (Black Friday) is enormous, customers
  onboard and churn mid-history (the eval masks series before their
  `first_date`; churn-to-zero is scored).
- Snapshot: daily counts 2021-01-01 → 2026-08-05, outbound non-cancelled
  shipments only (`IS_BOOKED_RETURN=FALSE, RETURN_AT IS NULL,
  CANCEL_AT IS NULL`).

## Setup

```
uv sync --extra models
uv run python -m eval.eval --experiment 000_seasonal_naive --stage stage1
```
