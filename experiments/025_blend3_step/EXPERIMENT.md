# 025_blend3_step — step-switch level in the hand head (stage2)

## Hypothesis

Stage2's dominant miss is step changes (onboarding ramps, churn,
migrations): Sep–Oct 2024 cutoffs alternate biases ±0.11..±0.27 and
c_387459 runs 0.73. 016 proved continuous trend extrapolation drowns in
noise; a SWITCH that fires only on sustained ~20%+ weekly moves
(|log(L7/Lprev7)| > 0.18 → level := recent week) adapts to steps in
~1 week instead of ~3 without touching quiet series.

## Mechanism

hand_step.py = 015 + the switch in the level block. GBM heads identical
to the 024 champion (they already carry l7_ratio/lag features). One
change vs the stage2 champion (0.2508).

## Expected behavior

Sep–Oct 2024 cutoffs and ramping-customer series improve; quiet periods
untouched (the switch stays off). Bar: ≤ 0.250049. Failure mode: TAU
0.18 fires on post-event rebounds already handled by damp deflation —
watch May/January for collateral.

## Out of scope / next candidates

- GBM-side step features (days-since-detected-break).
- g5_tail churn composition (invisible at series granularity — likely
  irreducible without account-level extraction, which the frozen
  snapshot deliberately does not include).
