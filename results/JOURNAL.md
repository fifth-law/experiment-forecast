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
