# 012_vac_per_series — per-series vacation multipliers

## Hypothesis

After 010/011 the May/summer cutoffs keep residual wMAPE (0.25–0.29 in
May) with much-reduced bias — the 007 composition signature again.
Vacation appetite is series-specific and persistent (a B2B-ish account
collapses in weeks 28–30, a consumer webshop barely dips), so per-series
multipliers learned from the 2021/2022 clusters should convert the
residual into signal.

## Mechanism

Exactly the 007 mechanism over all damp days (asc + summer):
`vac_mult[s] = (Σ actual + k) / (Σ expected + k)`, expected = per-series
clean non-damp base before each cluster anchor × pooled damp factor;
k=500, clip [0.3, 2.0]. Applied on damp-day targets only. Level-window
deflation stays pooled (per-series deflation would reintroduce 009's
drift-import for extreme series). One change vs 011.

## Expected behavior

May and summer cutoffs improve with bias roughly unchanged (composition
gain). Everything outside damp weeks is byte-identical. Risk: unlike a
one-week event, vacation weeks span a quarter of the year's weeks — if
appetite is NOT stable across years the multipliers add noise across many
cutoffs, so a negative result here is informative about persistence.

## Out of scope / next candidates

- December run-up weeks with up-factors (Nov-27 bias −0.26).
- January intra-month decay (Jan-09 bias +0.18).
