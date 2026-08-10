# 028_blend3_age — series-age features in the GBM (stage2)

## Hypothesis

Stage2's theme is onboarding and churn (c_387459 at 0.73 during its
ramp; g5_tail churn composition; Feb-26 −0.33 likely a ramp landing).
The GBM cannot distinguish a 3-week-old series from a 3-year-old one:
its ratio features look identical while the right behavior differs
(young series: trust the newest lags, expect continued ramp). Two
features fix the blindness: `age_days` (days since first activity,
clipped 730, −1 if never active) and `active_60` (share of active days
in the last 60).

## Mechanism

Features computed from history only (first non-zero date, rolling
activity share), added to the GBM heads; hand head = 027 champion's.
One change vs 027 (0.247777).

## Expected behavior

Ramping/churning series improve; mature series unaffected (constant
features carry no split value there). Bar: ≤ 0.247034. If under-bar,
that is the third consecutive miss → promote to stage3 per protocol.

## Out of scope

- Any further stage2 work if the stall rule fires.
