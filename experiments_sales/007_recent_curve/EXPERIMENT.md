# 007_recent_curve

## Hypothesis

006 fixed the settlement window and still came out 11.6% low on stage3, so what
remains is drift in the development curve itself. The share of a month's DKK created
*before* its posting month fell from 34% (2025) to 0.3% (2026) as billing moved from
arrears to same-month, which means the accrual now happens later in the month than
it used to. A curve pooled evenly over six months claims more of the month is
visible than really is, so `mtd / f(d)` lands low every night.

## Method

Single change from 006: pool the curve's months with exponential recency weights
(half-life 2 months) instead of weighting six months equally.

## Expected behaviour

- stage3 bias moves towards zero and pooled wMAPE improves, most visibly in the
  middle of the month where the curve does the most work.
- stage1 close to unchanged: that era's curve was stable, so reweighting it should
  neither help nor hurt much.
- If the bias survives this too, the cause is not the curve and the next suspect is
  the anchor (level, not completion) or per-series curve heterogeneity.
