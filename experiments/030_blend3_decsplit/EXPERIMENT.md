# 030_blend3_decsplit — split December multipliers: wind-down vs lull

## Hypothesis

008 journaled why the single xmas multiplier underperformed: it averages
a deadline-driven behavior (Dec 20–24: gift merchants die at last-order
deadline) with a restart-driven one (Dec 27–Jan 1: replenishment
merchants keep shipping). The December residual (12-22 at 0.387, 12-29
at 0.340, bias ≈ 0) is composition-shaped. With four observed
year-boundaries and recency weighting, two separate per-series
multipliers are now estimable.

## Mechanism

`_mult_group` splits: dec_wind = {dec20..23, xmas_eve}, dec_lull =
{dec27..30, nye, Nytårsdag, Juledag, Anden juledag}; both keep k=500
shrinkage and year-boundary recency weighting. Components otherwise
byte-identical to the 029 champion (0.236039). One change.

## Expected behavior

December cutoffs (12-15/12-22/12-29) improve via better composition;
everything else unchanged. Bar: ≤ 0.235331. Sub-bar → counter 1/3.

## Out of scope / next candidates

- Erratic-series spike timing (journaled as irreducible without
  exogenous data).
- Final summary once the stall rule fires.
