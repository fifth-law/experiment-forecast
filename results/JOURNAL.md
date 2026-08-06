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

## 009_bf_level_info @ stage1 — 2026-08-06
- hypothesis: BF days deflated by factor×mult are valid level observations,
  letting post-BF cutoffs (Nov-27) see the December run-up through the
  spike.
- result: wMAPE 0.2357 vs best 0.2342 — WORSE by 0.64%. Rejected; 008
  stays the base. Stall counter 2/3.
- learned: falsified with a useful mechanism lesson — deflating an event
  by learned factors imports the event's year-over-year intensity drift
  into the level: Nov-27 bias −0.26→−0.28 and 12-04 flipped +0.02→−0.14,
  meaning 2023 BF ran *below* the 2021/2022-learned intensity, so
  y/(factor×mult) under-recovered the underlying level. Deflation-as-
  level-input is only safe when the factor is near 1 (mild events), never
  for 2–3× spikes where a 15% drift is a 15% level error on the biggest
  volume days of the year. Next (last shot before promotion): Ascension/
  Pentecost cluster week-damping — May cutoffs oscillate +0.16/−0.11/
  −0.19, and the factors there are ~0.9, small enough for deflation to
  be safe under this lesson.

## 010_ascension_weeks @ stage1 — 2026-08-06
- hypothesis: the whole Ascension→Pentecost 3-week cluster is damped on
  non-holiday days too; learned week factors applied to targets and (safely,
  since ~0.9) as level-window deflation fix the May bias oscillation.
- result: wMAPE 0.2333 vs 0.2342 — improved 0.40% relative. Current best.
  Stall counter reset.
- learned: worked in both directions as designed — 05-08 bias +0.16→+0.12,
  05-15 +0.13→+0.11, 05-29 −0.19→−0.14, with wMAPE down 0.015–0.02 at each.
  06-12 (+0.155) barely moved: it sits *outside* the cluster — that bias,
  plus 07-10 (+0.17) and 07-24/31 (−0.17/−0.17), is the summer vacation
  fade (industriferie, ISO weeks ~25–32). Same machinery, ISO-week anchor,
  learned per-week factors → next experiment. December run-up weeks
  (Nov-27 −0.26) queued after with the same generalized machinery
  (up-factors this time).

## 011_summer_weeks @ stage1 — 2026-08-06
- hypothesis: the summer dip (industriferie) is ISO-week-anchored and
  calendar-predictable like the May cluster: sum_wk25..32 damp factors,
  estimated against pre-week-25 bases (with ordered-group deflation for
  asc days in those bases), fix both directions of the June–August bias.
- result: wMAPE 0.2285 vs 0.2333 — improved 2.06% relative. Current best.
- learned: the summer block collapsed — 06-12 bias +0.16→+0.04 (wMAPE
  −0.04), 07-10 +0.17→+0.03 (−0.06), 07-24 −0.18→−0.04 (−0.06), 07-31
  −0.17→−0.05 (−0.06). Vacation damping was a bigger rock than any single
  event. Worst cutoffs are now Dec-18 (0.47), Nov-27 (0.31, −0.26),
  Nov-13/20 (0.29), May cluster residuals (0.25–0.29, biases ±0.09–0.14),
  Jan-02/09. The May/summer residual biases suggest composition: vacation
  appetite is series-specific (B2B dies in July, B2C less so) → next:
  per-series damp multipliers, the same generalization that made 007 the
  biggest win. December run-up weeks still queued.

## 012_vac_per_series @ stage1 — 2026-08-06
- hypothesis: the residual May/summer wMAPE is per-series composition;
  007-style multipliers over damp days convert it into signal.
- result: wMAPE 0.2332 vs best 0.2285 — WORSE by 2.06%. Rejected; 011
  stays the base. Stall counter 1/3.
- learned: rejected for a mechanistic reason worth keeping: every summer
  cutoff swung positive (07-17 bias −0.01→+0.04, 07-24 −0.04→+0.02 with
  wMAPE +0.04..+0.05) — the multiplier distribution skews >1 because the
  estimator's base sits at the cluster *anchor* while the damp days run
  up to 6 weeks later, so any series-level trend over that gap is
  misread as vacation appetite. 007 worked because its base ends 4 days
  before the event. Per-series event multipliers need tight bases; with
  long anchor→day gaps use pooled factors only. (Whether vacation
  appetite is truly persistent per series remains unknown — the estimator
  couldn't measure it.)

## 013_dec_runup @ stage1 — 2026-08-06
- hypothesis: the December run-up (Cyber Monday → ~Dec 19) is a mild
  calendar-anchored lift; runup_w1–3 up-factors (clip 0.8–2.0, pre-BF
  anchor) fix the Nov-27 regime blindness that 009 failed on.
- result: wMAPE 0.2264 vs 0.2285 — improved 0.92% relative. Current best.
  Global bias now −0.001 (was −1.4% at 001); network wMAPE 0.0954.
- learned: Nov-27 0.31→0.27 with bias −0.26→+0.03, Nov-20 also improved
  (runup days in its horizon), zero regressions. The mild-factor damp
  machinery is now the workhorse: 5 of the last 7 accepted changes use
  it. Remaining rocks: Dec-18 0.47 (+0.20, YoY drift in wind-down depth
  with only 2 observations — may be irreducible by hand), Nov-13/20/27
  ~0.27–0.29 (bias ~0, event-week noise), May cluster 0.25–0.29 (±0.09–
  0.14), Jan-09 0.27 (+0.18). Next: January intra-month decay via a
  forward-anchored base ([Jan 2, Jan 8]) in the damp machinery.

## 014_school_vacations @ stage1 — 2026-08-06
- hypothesis: the remaining February (+0.11/+0.15→−0.08/−0.13) and October
  (+0.07→−0.12/−0.16) bias swings are vinterferie (ISO wk 7–8) and
  efterårsferie (wk 41–43) — the summer signature twice more.
- result: wMAPE 0.2248 vs 0.2264 — improved 0.71% relative. Current best.
- learned: February collapsed as designed (02-06 0.23→0.20, 02-13
  0.24→0.20, 02-20/27 better, biases halved); October only partial —
  Oct-09 improved but Oct-23/30 barely moved and Oct-16 ticked down, so
  the wk-42 dip is weaker/less year-stable than vinterferie. Mar-06
  ticked down (wk-8 deflation slightly over-lifts its level window).
  Global bias now −0.0006. Next: January week 1 as an *up*-anomaly
  (post-NY surge decaying to the true level) — a forward-anchored base
  ([anchor+7, anchor+21)) rather than "weeks 2–4 low", which would break
  the level chain at the February boundary.

## 015_jan_week1 @ stage1 — 2026-08-06
- hypothesis: January's anomaly is week 1 being HIGH (post-NY backlog +
  returns surge), not weeks 2–4 low; jan_wk1 as an up-anomaly with a
  forward base ([anchor+7, anchor+21)) fixes Jan-09/16 without breaking
  the February boundary.
- result: wMAPE 0.2232 vs 0.2248 — improved 0.71% relative. Current best.
- learned: all three January cutoffs improved (Jan-02 0.27→0.25, Jan-09
  0.27→0.22 with bias +0.18→+0.09, Jan-16 0.25→0.22, +0.15→+0.10) and
  nothing else moved. The forward-base option makes the damp machinery
  handle anomalies adjacent to regime breaks. Remaining: Dec-18 0.47
  (+0.20, factor drift), May cluster (±0.09–0.14, possibly asc-factor
  drift), November event weeks (bias ≈0 — composition/noise), scattered
  −0.10..−0.16 biases on autumn-ramp and post-dip-recovery cutoffs that
  look like 14-day-level lag → next: damped per-series local trend
  applied by lead.

## 016_damped_trend @ stage1 — 2026-08-06
- hypothesis: remaining ±0.10–0.16 ramp/recovery biases are 14-day-level
  lag; a hard-shrunk weekly growth ratio applied as g^(lead/7) on normal
  days closes part of the gap now that events are out of the windows.
- result: wMAPE 0.2256 vs best 0.2232 — WORSE by 1.1%. Rejected; 015
  stays the base. Stall counter 1/3.
- learned: cleanly falsified, with the failure exactly where the
  mechanism applies most — lead 1–7 unchanged (0.2112→0.2110), lead 8–14
  degraded (0.2354→0.2403). Even shrunk to half-weight and clipped, a
  7d/7d ratio imports more variance than the lag bias it removes. Level
  lag is real but not extrapolatable at weekly granularity with these
  series. The cheap single-mechanism well is thinning: remaining rocks
  are factor drift (Dec-18, May) and event-week composition, all
  n=2-observation problems. Next: the long-flagged LightGBM global
  model over the same calendar/level feature knowledge — interactions
  (series × day-type × lead) are where a learned model can still beat
  the multiplicative stack.

## 017_lgbm_global @ stage1 — 2026-08-06
- hypothesis: a per-cutoff LightGBM over the same calendar/level
  knowledge (day-type ids, lead, weekday, series, clean rolling levels,
  same-weekday lag ratios; target y/L14, weight L14, L1) learns the
  interactions the multiplicative stack cannot.
- result: wMAPE 0.2189 vs 0.2232 — improved 1.93% relative. Current
  best. Determinism verified (0.218880 twice); runtime 210 s.
- learned: the gain concentrates exactly where hypothesized — lead 8–14
  0.2354→0.2274, customers 0.2514→0.2442. Two structural properties:
  (1) bias −5.5% — the L1 objective predicts conditional medians of a
  right-skewed target, which is optimal for pooled wMAPE but costs
  network-level accuracy (network wMAPE 0.0900→0.1064); if the business
  ever scores network totals, an L2/tweedie variant or quantile blend
  trades back. (2) The GBM and the hand stack (015) have differently
  shaped residuals (median-chasing vs network-calibrated factors) →
  next: 50/50 blend of 015 and 017, classic variance reduction across
  model families. Justified lightgbm (installed extra) per the
  modeling-guardrails note.

## 018_blend @ stage1 — 2026-08-06
- hypothesis: 015 and 017 are differently wrong (bias ≈0 network-
  calibrated factors vs −5.5% median-chasing interactions); a 50/50
  blend beats both.
- result: wMAPE 0.2108 vs 0.2189 — improved 3.70% relative. Current
  best, and the largest single step of the loop.
- learned: everything improved at once — lead 1–7 0.2104→0.2007, lead
  8–14 0.2274→0.2209, customers 0.2442→0.2363, tail 0.1622→0.1535,
  network 0.1064→0.0908, bias −5.5%→−3.0% — confirming the residuals
  are substantially uncorrelated. Model families, not more factors, are
  now the axis of progress. Next: add a third differently-calibrated
  component — an L2-objective variant of the GBM (mean-predictor,
  network-friendly) at equal thirds. Deliberately NOT tuning the blend
  weight on the eval (one scalar fitted to 51 cutoffs is cheap stage
  overfitting; equal weights or nothing).

## 019_blend3 @ stage1 — 2026-08-06
- hypothesis: a mean-calibrated (L2) GBM head adds diversity the 50/50
  blend lacks; equal thirds beats 0.2108.
- result: wMAPE 0.2090 vs 0.2108 — improved 0.86% relative. Current
  best. Runtime 364 s (budget-relevant: each GBM head costs ~3.5 min).
- learned: accepted, but the real finding is in worst_series mining:
  Jan-02 sits at 0.68 with bias −0.67 because the GBM heads predict
  ZERO for that entire horizon — 017's L14 base is rolling(14,
  min_periods=5) over clean days and Dec 20–Jan 1 are all special, so
  the base is NaN and the base>1 guard zeroes every series. 017 has
  been silently eating a ~1.0-wMAPE cutoff (its other 50 cutoffs are
  better than its 0.2189 suggests), and the blend diluted the hole to
  −0.67. Next: base fallback cascade L14→L28→L56 in a fixed GBM (020),
  then re-blend (021). The Jan-02 zero-hole is the only one of its kind
  in stage1 (no other 14-day window is >9/14 special).

## 020_lgbm_basefix @ stage1 — 2026-08-06
- hypothesis: the L14→L28→L56 base cascade removes the Jan-02 zero-hole;
  standalone GBM gains roughly Jan-02's volume share (~1.5–2%).
- result: wMAPE 0.2050 vs blend best 0.2090 — improved 1.91% relative
  over the BLEND, 6.3% over broken 017. The standalone GBM now beats the
  three-way blend. Current best.
- learned: the estimate was far too conservative because the prediction
  hole was only half the bug — TRAINING refs near the 2021/2022 year
  boundaries also had NaN bases, so their rows were silently dropped by
  the base>1 filter and the GBM had never learned the Christmas window
  properly. With those rows restored: tail 0.1622→0.1439, lead 8–14
  0.2274→0.2150, network 0.1064→0.0890. Lesson for the record: a
  data-prep guard (min_periods + filter) can silently starve a model of
  exactly the regime it most needs; worst-cutoff mining caught it only
  because the blend diluted the zero into a visible −0.67 bias. Next:
  re-blend 015 + fixed L1/L2 heads (021).

## 021_blend3_v2 @ stage1 — 2026-08-06
- hypothesis: the blend gains were genuine residual diversity, not
  hole-masking; equal thirds with the fixed heads beats 0.2050.
- result: wMAPE 0.2001 vs 0.2050 — improved 2.39% relative. Current
  best. Network wMAPE 0.0789 (best yet), bias −1.2%.
- learned: confirmed — the three families remain complementary after the
  fix. Cumulative: 0.2938 (naive floor) → 0.2001, −32% relative; the
  split is roughly: calendar structure (002–015) −15%, GBM + fix
  (017/020) −8%, blending (018–021) −9% of what remained. Runtime ~8 min
  per stage run (budget edge — no room for a fourth GBM head; further
  gains must come from inside the heads or the hand stack).

## 022_lgbm_edges @ stage1 — 2026-08-06
- hypothesis: to_special/since_special distance features let trees learn
  pre-closure pull-forward and post-closure rebound at event edges
  (worst non-Dec cutoffs straddle Easter/Ascension edges).
- result: head 0.2045 vs head-baseline 0.2050 (+0.26%); does not touch
  the stage best 0.2001. Stall counter 1/3.
- learned: the mechanism is real but self-sabotaging as built — Easter
  edges improved exactly as aimed (04-10 −0.023, 04-03 −0.013, May and
  BF shoulders too) while January REGRESSED (Jan-02 +0.020): distances
  to the xmas-window specials hand the trees a year-boundary handle to
  overfit at n=2, partially re-poisoning what 020 fixed. Also noted:
  head-only experiments can never reset the stall counter (the rule
  measures against the stage best, i.e. the blend champion) → test head
  refinements inside the blend from now on. Next: edge distances
  excluding the xmas window (it is already densely day-typed), as a
  blend variant.

## 023_blend3_edges @ stage1 — 2026-08-06
- hypothesis: edge distances minus the xmas window keep 022's edge gains
  without the January damage; in-blend this clears the 0.3% bar.
- result: wMAPE 0.199565 vs 0.200103 — improved 0.269%, a NEW BEST but
  0.03pp under the bar. Stall counter 2/3 (per the pre-registered
  criterion). Network wMAPE 0.0776.
- learned: the January regression is gone (exclusion worked) and the
  edge gains survive blending, but at blend scale the mechanism is worth
  ~0.27%, not 0.5%+. One more sub-bar experiment promotes to stage2.
  Last shot: GBM capacity bump (num_leaves 63→127, min_data_in_leaf
  60→20) inside the champion blend — 200k interaction-rich rows may be
  underfit at 63 leaves, and the walk-forward eval punishes overfit
  honestly if not.

## 024_blend3_capacity @ stage1 — 2026-08-06
- hypothesis: the GBM heads are underfit at 63 leaves / min 60; doubling
  capacity clears the bar inside the champion blend.
- result: wMAPE 0.199104 vs 0.199565 — improved 0.231%, under the bar.
  New best, but the THIRD consecutive sub-0.3% experiment.
- learned: capacity was worth a fraction of a percent, not a step —
  the stage1 error floor for this data/feature space is ≈0.199.

## STAGE PROMOTION: stage1 → stage2 — 2026-08-06

Stall rule fired (022 +0.26% head-only, 023 +0.269%, 024 +0.231% — all
below 0.3% relative). Stage1 final state: best 0.199104
(024_blend3_capacity), from a 0.293827 seasonal-naive floor — −32.2%
relative. Per protocol: re-running the stage1 top 3 (024, 023, 021) on
stage2 (2024 cutoffs, train from 2021), then continuing the loop on
stage2 only.

Promotion results (stage2): 024 = 0.2508, 023 = 0.2521, 021 = 0.2539 —
**rank order identical to stage1**, no era-overfitting signal; the
stage1 improvements generalize. Stage2 is harder (0.2508 vs 0.1991) and
the decomposition says why: customers held (0.2244→0.2430) while the
tail nearly doubled (0.1425→0.2699), dominated by g5_tail (wMAPE 0.28
at 9.9M volume, bias ≈0). Worst cutoffs are non-calendar: 02-26 bias
−0.33, a Sep–Oct cluster alternating ±0.11..±0.27, plus the usual
Dec-16 wind-down (+0.20). Signature of STEP CHANGES — onboarding ramps
(c_387459 at 0.73), churn (2024-big accounts that fell out of the
2025–26 reference window sit inside g5_tail), migrations. Stage2's
axis is adaptivity, not more calendar.

## 025_blend3_step @ stage2 — 2026-08-06
- hypothesis: a step SWITCH (level := recent week when |log(L7/Lprev7)|
  > 0.18) adapts to onboarding/churn/migration steps in ~1 week without
  016's noise-amplification (it stays off on quiet series).
- result: wMAPE 0.2480 vs 0.2508 — improved 1.12% relative. Current
  stage2 best. Stall counter 0/3.
- learned: gains broadly where steps live (Mar-04 −0.040, Sep-16 −0.027,
  Oct-21/28, May-13) with only small collateral (Oct-07 +0.012) — the
  high threshold is what 016 lacked. Remaining rocks: Dec-16 (0.40,
  +0.20) — wind-down factors STILL over-predict with 3 years of
  history, i.e. the dip deepens monotonically and a flat average lags
  it; Feb-26 (0.39, −0.33) and the Sep-09/Sep-30/Oct-14 alternation —
  step residuals at long leads (GBM lags start 14 days back for leads
  8–14). Next: exponential recency weighting (half-life 1 year) of ALL
  learned calendar responses — hand-head factor ratios and GBM training
  rows alike — one mechanism, both heads.
