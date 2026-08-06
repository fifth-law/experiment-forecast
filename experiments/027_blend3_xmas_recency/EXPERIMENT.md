# 027_blend3_xmas_recency — recency weighting scoped to the year boundary

## Hypothesis

026's split verdict: recency weighting fixed Dec-16 (drift is real at
the year boundary) but cost more on stable responses (BF weeks). Scoping
the half-life-1y weights to the year-boundary family only — dec-types,
runup blocks, xmas holidays, New Year, jan_wk1, and the xmas series
multiplier — keeps the Dec-16 gain without the broad variance tax. GBM
heads stay flat-weighted (their 026 weighting was part of the loss).

## Mechanism

`_drifting(name)` gates the weight in the hand head's three estimation
sites; everything else identical to the 025 champion (0.2480). One
change.

## Expected behavior

Dec-16 improves as in 026 (0.401→~0.38); November and the rest stay at
025 levels. Bar: ≤ 0.247240. If this fails, the counter reaches 2/3.

## Out of scope / next candidates

- Long-lead step handling in the GBM.
- Anything outside the drift family.
