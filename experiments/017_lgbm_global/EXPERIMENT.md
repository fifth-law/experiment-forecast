# 017_lgbm_global — global LightGBM over the calendar feature space

## Hypothesis

The hand stack's remaining error is interaction-shaped (series ×
day-type appetite, series × lead, type × recent level) and factor-drift
that pooled ratios with n=2 cannot fix. A gradient-boosted model trained
per cutoff on simulated forecast rows over the SAME knowledge — day-type
ids, lead, weekday, month, series identity, clean rolling levels,
same-weekday lag ratios — learns those interactions directly and should
beat the multiplicative stack (0.2232).

## Mechanism

Per cutoff: training rows = every past Monday (≥ start+120d,
≤ cutoff−14d) × lead 1..14 × series, features strictly from data ≤ that
Monday. Target `y / L14(ref)` (clipped at 15), weight `L14(ref)` so the
L1 objective approximates pooled wMAPE. 300 rounds, lr 0.06, 63 leaves,
deterministic (seed 42, force_row_wise, fixed threads, no early
stopping). Categorical features: series, day_type (vocabulary fixed
across train/predict). Rows with L14 ≤ 1 are dropped from training and
predicted as 0 (dead or masked series).

## Expected behavior

If interactions carry real signal, gains should concentrate where the
hand stack is composition-blind: November event weeks and Dec-18, plus
series-specific weekday/level subtleties everywhere. Risks: (a) 2 years
× weekly refs may be too little data for stable series-level splits —
watch for noise regressions on quiet cutoffs; (b) runtime ~51 trainings
(kept lean deliberately).

## Justification for the heavier model

Journal 016: the cheap single-mechanism well is exhausted; remaining
rocks are n=2 drift and interactions. lightgbm is already an installed
project extra; determinism pinned via seed + force_row_wise + fixed
rounds.
