# 016_damped_trend — damped per-series local trend

## Hypothesis

With the calendar stack in place the remaining scattered biases look
like level lag: autumn-ramp and post-dip-recovery cutoffs run
−0.10..−0.16 (06-19/26, 08-28, 09-25, 10-23/30), a few spring cutoffs
+0.08..+0.12. The 14-day level's center sits ~7 days behind the cutoff
and targets sit 1–14 days ahead; a damped extrapolation of the last
week's growth should close part of that gap. (003 showed a naive
responsive level amplifies event noise — but events are now excluded
from the windows, which is what makes this retry plausible.)

## Mechanism

`g = level_last7 / level_prev7` per series (both halves shape- and
damp-deflated), clipped [0.85, 1.15], then hard-shrunk:
`g_eff = 1 + 0.5 · w · (g−1)`, `w = vol7/(vol7+500)`. Normal-day
predictions get `× g_eff^(lead/7)`; special days untouched. Max effect
at lead 14 is g_eff² — a few percent for typical values. One change vs
015.

## Expected behavior

Ramp/recovery cutoff biases shrink; wmape_lead_8_14 improves more than
lead_1_7; stable periods nearly unchanged (g_eff ≈ 1). Failure mode:
if the trend signal is mostly noise at 7-day granularity, everything
gets slightly worse — a clean falsification of "level lag matters".

## Out of scope / next candidates

- Dec-18 residual (+0.20, factor drift with n=2).
- May cluster residual (possible asc drift).
- November event-week composition noise.
