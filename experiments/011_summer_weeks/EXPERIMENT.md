# 011_summer_weeks — summer vacation week-damping

## Hypothesis

The summer signature in 010 mirrors the May cluster: 06-12 bias +0.16 and
07-10 +0.17 (forecasting into the vacation dip), 07-24/07-31 −0.17 (level
windows inside the dip missing the August recovery). Danish industriferie
is ISO-week-anchored (trough weeks 28–30), so the dip is as calendar-
predictable as Ascension. Per-week learned factors for ISO weeks 25–32
should shrink all of those biases.

## Mechanism

The 010 damp machinery generalised to ordered groups: `sum_wk25..32` join
`asc_wk0..2`, each summer week factored against same-weekday clean network
values from the 28 days before that year's week-25 Monday. Later groups
deflate earlier-group days in their baselines (the summer base window can
contain Ascension-cluster days); asc factors stay byte-identical to 010.
Factors apply to normal-day targets and as level-window deflation
(near-1 factors, drift-safe per 009's lesson). One mechanism vs 010.

## Expected behavior

June/July/August cutoff biases shrink in both directions; edge weeks
(25–26, 32) learn ≈1 if the fade is narrower than assumed. Cutoffs
outside June–August (and the whole calendar-event stack) are unchanged.

## Out of scope / next candidates

- December run-up weeks with up-factors (Nov-27 bias −0.26).
- January intra-month decay (Jan-09 bias +0.18).
- Dec-18 residual aggregate bias (+0.20).
