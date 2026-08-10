# 026_blend3_recency — recency-weighted learned responses (stage2)

## Hypothesis

Dec-16 still runs +0.20 bias with three observed year-boundaries: the
wind-down dip deepens monotonically year over year and a flat average
lags it. The same drift hit May in stage1. Exponentially down-weighting
old years (half-life 1 year: last year counts double the year before)
tracks monotone drift while keeping n>1 effective observations.

## Mechanism

One mechanism, both heads, vs the 025 champion (0.2480):
- hand head: every learned ratio (special-day factors, damp factors,
  bf/xmas series multipliers) becomes Σw·actual / Σw·expected with
  w = 0.5^(age/365.25);
- GBM heads: training-row weight becomes L14 × 0.5^(age/365.25).

## Expected behavior

Dec-16 bias +0.20 shrinks; May cluster and BF weeks may improve for the
same reason. Risk: halving the effective history adds variance to every
learned response — if the drift is noise, this loses broadly. Bar:
≤ 0.247240.

## Out of scope / next candidates

- Long-lead step handling in the GBM (lags start 14 days back for
  leads 8–14).
- g5_tail churn composition (irreducible at series granularity).
