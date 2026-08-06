# 020_lgbm_basefix — GBM base-level zero-hole fix

## Hypothesis

017 predicts zero for the entire Jan-02 horizon because its L14 clean
base is NaN when Dec 20–Jan 1 are all special (min_periods=5 unmet) and
the base>1 guard zeroes every series. A fallback cascade L14→L28→L56
removes the hole; 017's other 50 cutoffs are unaffected, so the
standalone GBM should gain roughly the Jan-02 volume share
(~1.5–2% relative).

## Mechanism

`L14 = rolling(14, min5).fillna(rolling(28, min7)).fillna(rolling(56,
min7))`, used everywhere the base was used. At Jan-02 the 28-day window
still holds Dec 6–19 clean days, so the base exists (December run-up
level — high for January, but the day-type features can correct a level;
they cannot correct a hard zero). One change vs 017.

## Expected behavior

Jan-02 goes from ~1.0 (all-zero forecast) to ~0.3; every other cutoff
byte-identical (their L14 was never NaN). Then 021 re-blends with the
fixed head.

## Out of scope / next candidates

- Re-blend (021) with fixed L1+L2 heads.
