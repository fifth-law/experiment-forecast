# Optimization Journal

Append-only log of the optimization loop: one entry per experiment run —
hypothesis, result vs. best, what was learned. Failed hypotheses are
information; record them.

Format:

```
## NNN_short_name @ stageX — YYYY-MM-DD
- hypothesis: ...
- result: wMAPE X.XXXX (best was X.XXXX) — improved/no change/worse
- learned: ...
```

---

## 000_seasonal_naive @ stage1 — 2026-08-06
- hypothesis: none — floor baseline (repeat last observed same weekday).
- result: wMAPE 0.2938 (first entry). Lead 1–7: 0.2714, lead 8–14: 0.3164.
  61/105 series active in 2023. Rerun reproduced 0.293827 exactly
  (determinism contract verified).
- learned: customer series (0.3226) are much harder than tail groups
  (0.2294) — aggregation smooths noise. Network-level wMAPE 0.1783 means
  most series-level error is idiosyncratic and cancels in the sum.

## 001_weekday_profile @ stage1 — 2026-08-06
- hypothesis: mean of last 4 same-weekday observations beats naive by
  smoothing one-off spikes.
- result: wMAPE 0.2654 vs 0.2938 — improved 9.7% relative. Current best.
- learned: smoothing helps everywhere (customers 0.2986, tail 0.1909), at
  the cost of slight under-forecast (bias −1.4%) — it lags the 2023 growth
  trend. Obvious next hypotheses: trend correction on the 4-week window,
  holiday calendar features, and November-peak handling.

## 002_holiday_weekday @ stage1 — 2026-08-06
- hypothesis: the worst cutoffs are calendar events (Dec-18 wMAPE 1.38 bias
  +1.30; Easter/May bias swings ±0.13–0.21): skip special days when building
  the weekday profile and predict special dates as learned per-type factors
  × recent clean level (DK holidays + Dec 24/31 + Jun 5).
- result: wMAPE 0.2529 vs 0.2654 — improved 4.7% relative. Current best.
- learned: worked where aimed (Dec-18 1.38→0.83, Dec-11 0.58→0.41, all
  Easter/May cutoffs better) **but regressed January** (Jan-02 0.37→0.45,
  bias +0.03→+0.23; Jan-09/16 similar): skipping specials makes the clean
  profile reach back into December-peak weeks, and January is a lower
  regime — 001 was accidentally protected by the holiday pollution 002
  removed. Dec-18 residual bias +0.60 comes from Dec 27–30 lull and
  Dec 19–23 wind-down still forecast at peak volume. Both are the same
  miss: the year-boundary window (≈Dec 20 – Jan 7) is a distinct low
  regime the trailing profile cannot see → next experiment: learned
  day-of-window factors for the year-boundary period. Black Friday
  under-forecast (Nov-13/20, bias −0.36) still untouched.

## 003_shape_level @ stage1 — 2026-08-06
- hypothesis: split the profile into weekday shape (last 4 clean obs,
  normalised) × recent level (shape-deflated 14-day mean) so January stops
  inheriting December-peak levels; specials unchanged from 002.
- result: wMAPE 0.2515 vs 0.2529 — improved 0.55% relative. Current best,
  but far below expectation.
- learned: the mechanism is right where aimed — Jan-02 0.45→0.34, Jan-09
  0.36→0.25, Dec-18 0.83→0.72, and even Nov-13/20 improved (level tracks
  the November ramp) — but only 20/51 cutoffs improved. The give-back has
  one signature: bias swings positive wherever the 14-day window contains
  a transient peak (cutoff 12-04, window = Black Friday week: bias
  −0.02→+0.20; 11-27 same; mid-August vacation rebound similar). Tail
  groups (big, smooth) pay the variance cost (0.1799→0.1859) while
  customers benefit (0.2855→0.2808). A naive 14-day mean level is too
  twitchy around spikes — and the biggest spike is calendar-known.
  Next: treat Black Friday week as learned special days (up-factors,
  wider clip), which both fixes the Nov-13/20 under-forecast and keeps
  BF week out of the level/profile windows that poison late-Nov/early-Dec
  cutoffs.

## 004_black_friday @ stage1 — 2026-08-06
- hypothesis: bf−4..bf+3 (calendar rule) as learned special-day types with
  up-clip (0,5) fixes both the Nov-13/20 spike under-forecast and the BF
  contamination of level windows at 11-27/12-04.
- result: wMAPE 0.2471 vs 0.2515 — improved 1.75% relative. Current best.
  Network wMAPE 0.1406→0.1212.
- learned: (1) 12-04 fully fixed (0.32→0.23, bias +0.20→+0.02). (2) At the
  BF cutoffs the bias collapsed (−0.36→−0.09, −0.30→+0.01) but wMAPE
  barely moved (0.39 both) — the pooled network factor gets the aggregate
  right and the composition wrong; customers differ in BF intensity →
  candidate: per-series BF factors shrunk toward pooled. (3) 11-27
  regressed (0.29→0.31, bias −0.26): with BF week excluded its level
  window is pre-BF only and cannot see the December run-up regime.
  (4) Dec-18 remains the worst cutoff (0.67, bias +0.41): Dec 20–23
  wind-down and Dec 27–30 lull still forecast at full volume → next:
  year-boundary day-type factors.

## 005_xmas_window @ stage1 — 2026-08-06
- hypothesis: dec20–23 (wind-down) and dec27–30 (lull) as learned
  day-types remove the Dec-18/Dec-11 over-forecast; accepted risk that
  Jan-02's level window keeps only one clean day.
- result: wMAPE 0.2417 vs 0.2471 — improved 2.2% relative. Current best.
  Fourth consecutive improvement.
- learned: Dec-18 0.67→0.49 (bias +0.41→+0.14), Dec-11 0.35→0.25, and the
  Jan-02 "risk" actually improved it (0.32→0.27) — Jan 2 alone is a decent
  January level proxy. Jan-09 slipped (bias +0.14→+0.18): January decays
  within the month, so even true early-January levels over-forecast
  mid-January. Remaining rocks, in rough size order: (a) Nov-13/20 both
  0.39 with bias ≈ 0 — per-series BF composition (pooled factor right in
  aggregate, wrong per customer); (b) Nov-27 0.31 bias −0.26 — December
  run-up regime invisible from a pre-BF level window; (c) May cluster
  biases ±0.16 — the Friday after Ascension (Danish bridge day,
  "indeklemt fredag") is not in the special set; (d) Dec-18 residual 0.49.
  Next: ascension bridge day (3-line change, proven mechanism), then
  per-series event multipliers for BF week.

## 006_ascension_bridge @ stage1 — 2026-08-06
- hypothesis: the Friday after Ascension is a de-facto Danish closing day;
  adding it as a learned day-type fixes the May bias oscillation.
- result: wMAPE 0.24166 vs 0.24169 — flat (+0.013% relative). Below the
  0.3% bar: stall counter 1/3.
- learned: falsified — the learned factor is ≈1, i.e. this network ships
  nearly normally on the bridge Friday (b2c warehouses, not offices). The
  May 05-08/05-15 bias (+0.16, +0.13) therefore comes from level dynamics
  around the holiday cluster, not a missing closing day. Keeping the
  day-type (harmless by construction). Next: per-series BF-week
  multipliers for the Nov-13/20 composition error.

## 007_bf_per_series @ stage1 — 2026-08-06
- hypothesis: Nov-13/20 stuck at 0.39 with bias ≈ 0 ⇒ composition error;
  per-series BF multipliers (actual vs pooled-expected over past BF weeks,
  k=500 shrinkage toward 1, clip [0.2, 3]) convert it into signal.
- result: wMAPE 0.2345 vs 0.2417 — improved 2.97% relative. Current best.
  Biggest single step since 002.
- learned: exactly as aimed — Nov-13 0.39→0.29, Nov-20 0.39→0.29, Nov-06
  0.24→0.23, bias unchanged ≈0, nothing else moved. Customers differ
  strongly and *persistently* (2021/2022 appetite predicts 2023) in BF
  intensity. This mechanism should generalize: next, the same per-series
  multipliers for the Christmas window (Dec-18 residual 0.49, bias +0.14
  — likely the same composition story). Then: BF days as factor-deflated
  level observations, so a post-BF cutoff (Nov-27, bias −0.26) can see
  the December run-up regime through the BF week.

## 008_xmas_per_series @ stage1 — 2026-08-06
- hypothesis: Dec-18 (0.49, bias +0.14) is the BF composition story again;
  a second per-series multiplier group over the Christmas window fixes it.
- result: wMAPE 0.2342 vs 0.2345 — +0.13% relative, below the 0.3% bar.
  Stall counter 1/3.
- learned: partially falsified — Dec-18 gained some composition (0.49→
  0.47) but its aggregate bias *worsened* (+0.14→+0.20; the multiplier
  distribution skews high around the year boundary) and Dec-11 ticked
  down. Christmas-window appetite is much less series-persistent than BF
  appetite — plausibly because wind-down (deadline-driven) and lull
  (restart-driven) behaviors differ per series and the group multiplier
  averages them. Keeping the change (it is a small net win). Next: BF
  days as factor-deflated level observations for the Nov-27 regime gap.
