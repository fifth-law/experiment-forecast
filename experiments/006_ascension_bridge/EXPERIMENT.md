# 006_ascension_bridge — Friday after Ascension as a special day

## Hypothesis

The May cutoffs in 005 oscillate: 05-08 bias +0.16 (its horizon contains
Ascension Thursday + the following Friday), 05-29 bias −0.19 (its clean
windows sit inside the holiday cluster). The Friday after Kristi
himmelfartsdag is a de-facto Danish closing day ("indeklemt fredag") the
model doesn't know: it gets forecast at full Friday volume and then
pollutes clean windows.

## Mechanism

One new day-type, `ascension_bridge` = Ascension + 1 (always a Friday,
so weekday-stable), with a learned level-relative factor like every other
special day. Three-line change over 005. If warehouses largely work that
day the learned factor comes out ≈1 and this is a no-op — the mechanism
cannot lose much, by construction.

## Expected behavior

05-08 improves (bridge day predicted low instead of full Friday); 05-15
and 05-29 improve slightly via cleaner windows. Everything outside the
Ascension weeks is byte-identical to 005.

## Out of scope / next candidates

- Per-series BF-week multipliers (Nov-13/20 composition, both 0.39).
- December run-up regime at the Nov-27 cutoff (bias −0.26).
- January intra-month decay (Jan-09 bias +0.18).
