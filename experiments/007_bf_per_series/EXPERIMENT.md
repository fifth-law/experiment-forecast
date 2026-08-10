# 007_bf_per_series — per-series Black Friday multipliers

## Hypothesis

Nov-13/20 are the #2/#3 worst cutoffs (both 0.39) with near-zero bias:
after 004 the network aggregate is right but the composition is wrong. A
pooled factor gives every series the same relative spike, and customers
differ wildly in BF appetite. Per-series multipliers learned from the
2021/2022 BF weeks should convert composition error into signal.

## Mechanism

`mult[s] = (Σ actual_s + k) / (Σ expected_s + k)`, summed over all past
BF-week days, where `expected_s` = the series' own 28-day clean base
before each day × the pooled offset factor; k = 500 shipments shrinks
thin series toward the pooled behavior; clip [0.2, 3.0]. Applied on
bf-type days only: `yhat = special_level × factor[offset] × mult[s]`.
One change vs 006.

## Expected behavior

Nov-13/20 wMAPE drops materially while their bias stays ≈0; Nov-27
unchanged (its horizon holds no bf days); everything else byte-identical.
Risk: only two BF observations per series — k too small lets 2021/2022
noise through, k too large mutes the effect. If the result is flat but
the mechanism looks right, sweep k in the next experiment rather than
declaring the idea dead.

## Out of scope / next candidates

- Same per-series treatment for the Christmas window / holidays generally.
- December run-up regime at the Nov-27 cutoff (bias −0.26).
- January intra-month decay (Jan-09 bias +0.18).
