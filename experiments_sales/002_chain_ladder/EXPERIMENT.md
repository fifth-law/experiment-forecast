# 002_chain_ladder

## Hypothesis

The month-to-date accrual is the strongest signal available and both baselines
throw it away. If a known fraction `f(d)` of a month's eventual invoiced total
has been created by day `d`, then `mtd / f(d)` estimates the month total, and the
estimate should get sharper every night as `f(d)` grows towards 1.

## Method

Chain-ladder development factor, network-pooled and volume-weighted over the last
6 settled months (settled = month end + 20 days ago or earlier):

    f(d) = sum(DKK created by day d) / sum(settled total)
    yhat = f(d) * (mtd / f(d)) + (1 - f(d)) * level

`level` is 001's anchor (mean of the last 3 settled months). Weighting by `f(d)`
itself is deliberate: on the 1st the ratio is meaningless and the forecast falls
back to the level; by the last night it is essentially the accrual.

## Expected behaviour

- Clear win over 000/001 on the pooled metric, driven almost entirely by the
  second half of the month.
- Steep error decay across the month: `wmape_dom_21_end` should be a fraction of
  `wmape_dom_1_10`, which stays near 001's level because early in the month there
  is little to extrapolate from.
- Not much help in the first 10 days — that part of the problem is a level and
  seasonality problem, not a completion problem.

## Known approximation

`f(d)` is indexed by days from month start, so pooling months of different
lengths mixes in a day or two past month end for the shorter ones. Harmless for
`d <= 28`, slightly optimistic at `d >= 29`.
