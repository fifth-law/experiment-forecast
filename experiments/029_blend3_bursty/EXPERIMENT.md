# 029_blend3_bursty — burstiness-aware per-series blend weights

## Hypothesis

Stage3's error mass sits in a few erratic high-volume customers
(c_387459 ≈ 10% of all error, bias ≈ 0): spike-timing volatility, where
the |err|-optimal forecast is the conditional median — the L1 head's
calibration, which equal thirds dilutes exactly there. Per-series
weights leaning bursty series toward the L1 head cut that error without
touching smooth series.

## Mechanism

ρ = median/mean over clean days in the last 84 days (history-only).
Weights slide linearly from equal thirds (ρ ≥ 0.75) to (0.15, 0.70,
0.15) at ρ ≤ 0.25. Constants are mechanism-derived, not eval-fitted.
Components byte-identical to 027 (0.237190). One change.

## Expected behavior

c_387459 / c_399062 / c_397088-class series improve; smooth series see
weights ≈ unchanged (mature customer medians sit near means). Bar:
≤ 0.236478. Failure mode: bursty series' L1 predictions may ALREADY be
pulled toward the blend's level by the ratio target scaling — if so the
weight shift moves little and this is a sub-bar no-op (counter 1/3).

## Out of scope / next candidates

- Per-series December composition depth (12-22/12-29 at 0.34–0.39,
  bias ≈ 0).
- Final-summary prep once the stall rule fires.
