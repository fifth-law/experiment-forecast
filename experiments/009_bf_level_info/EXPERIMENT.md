# 009_bf_level_info — BF days as deflated level observations

## Hypothesis

Nov-27 (0.31, bias −0.26) under-forecasts because excluding BF week from
the level window leaves only pre-BF days, hiding the December run-up that
is already underway underneath the spike. Deflating BF-day actuals by
their own model (factor × per-series multiplier) recovers the underlying
level, so a post-BF cutoff can see the run-up through the event.

## Mechanism

In the 14-day level window, bf-type days contribute
`y / (factor[offset] × mult[series])` with weight 1.0 in the
shape-deflated denominator (the special-day model is level-relative, so
the implied value is shape-neutral). Other specials stay excluded — the
year boundary is a regime break, BF is a pulse riding on the current
regime. One change vs 008; requires reordering so factors/multipliers
are estimated before the level.

## Expected behavior

Nov-27 bias −0.26 shrinks toward 0 and its wMAPE drops; 12-04 may tick
either way (its window gains deflated BF days); cutoffs whose windows
contain no BF days are byte-identical. Risk: factor/multiplier
misestimation leaks noise into the level exactly where volumes are
largest — bounded by the window still being mostly clean days.

## Out of scope / next candidates

- January intra-month decay (Jan-09 bias +0.18).
- May holiday-cluster level dynamics (05-08 +0.16 / 05-29 −0.19).
- Dec-18 residual aggregate bias (+0.20 after 008).
