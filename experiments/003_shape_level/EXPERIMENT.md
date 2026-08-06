# 003_shape_level — weekday shape × recent level

## Hypothesis

002's remaining January regression (cutoffs Jan-02/09/16 at bias +0.23,
+0.23, +0.16) comes from the trailing profile mixing weekday shape with
the level of the weeks the observations came from: skipping special days
makes a January profile reach back into December-peak weeks. Weekday shape
is stable across regimes; level is not. Splitting them — shape from the
last 4 clean same-weekday observations (normalised), level from the last
14 calendar days (shape-deflated) — should fix January and also shrink the
standing growth-trend under-forecast (001 bias −1.4%, 002 −1.8%), since a
14-day level lags a trend less than a 4–8-week profile does.

## Mechanism

- `shape[s, wd]`: 002's clean profile normalised to mean 1 over weekdays.
- `level[s]`: Σy / Σshape over clean days in the last 14 calendar days —
  deflating by shape keeps the estimate unbiased when holidays punch
  holes in the window.
- Normal day: `yhat = shape × level`. Special days: exactly 002 (learned
  per-type factor × raw 28-day clean level).

One variable changed vs 002: normal-day prediction only.

## Expected behavior

January cutoffs improve materially; overall bias moves toward 0; small
gains during any trending period (including the November ramp-up, though
the Black Friday spike itself remains out of scope). Risk: a 14-day level
is noisier than a 4-week profile, so stable periods may pay a small
variance cost.

## Out of scope / next candidates

- Black Friday / November-peak year-over-year lift (Nov-13/20 bias −0.36).
- Year-boundary day-type factors for Dec 20–23 wind-down and Dec 27–30
  lull (Dec-18 residual bias +0.60 in 002).
