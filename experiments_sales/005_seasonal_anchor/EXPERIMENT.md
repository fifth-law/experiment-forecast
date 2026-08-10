# 005_seasonal_anchor

## Hypothesis

002's error is all in days 1-11 and its per-month bias is seasonal, not random
(stage1: January -7%, March +8%, May +9%). The cause is the anchor: a flat mean of
the last 3 settled months still carries the Christmas peak into March. Replacing it
with same-month-last-year carried forward by recent growth should remove that bias
and cut the early-month error.

## Method

Single change from 002 — the anchor becomes

    anchor = dkk(series, target_month - 12) * g(series)
    g      = (recent 3 settled months) / (the same 3 months a year earlier),
             clipped to [0.4, 2.5] and shrunk towards the network growth rate with
             a 500k DKK half-weight

with 002's flat mean as the fallback when a series has no non-zero year-ago month.
The completion half of the model is untouched.

## Expected behaviour

- Per-month bias much closer to zero, especially January/March/May.
- `wmape_dom_1_10` down from 0.250; `wmape_dom_21_end` unchanged (0.015).
- Risk: a year-ago month is a single noisy observation, so small and bursty series
  may get worse even as the seasonal months get better. If pooled wMAPE improves
  but `wmape_customers` degrades, the next step is shrinking the anchor towards
  the flat level rather than choosing one or the other.
