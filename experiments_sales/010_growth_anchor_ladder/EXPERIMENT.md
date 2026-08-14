# 010_growth_anchor_ladder

## Family

Uses the current month's invoice accrual **and** previous months + shipments, so it
is *not* in the "previous months + shipments only" family. 009 is the best model in
that family; this one measures what the accrual is worth on top of it.

## Hypothesis

The day-of-month split between the two families is clean. On stage3, 009 beats 007
over days 1-10 (0.2981 vs 0.3433) and loses over days 21-end (0.2929 vs 0.1626):
shipments know the month before the invoices exist, the invoices know it better once
they do. Handing 007's completion curve a 009 anchor instead of a flat recent mean
should therefore win in both halves.

## Method

007 unchanged (measured settlement window, recency-weighted development curve), with

    yhat = f(d) * (mtd / f(d)) + (1 - f(d)) * anchor_009(series)

## Why this is not 004 again

004 tried the same structure with 003's price x volume anchor and lost, because that
anchor was +5.2% biased and compounded with the accrual extrapolation's positive
bias. 009 is near-unbiased (stage1 +0.1%, stage3 -2.4%), which is the property 004's
post-mortem said the anchor needed.

## Expected behaviour

- Best overall model on both stages; `wmape_dom_1_10` near 009's and
  `wmape_dom_21_end` near 007's.
- If it fails despite the bias fix, the conclusion is that early-month accrual
  extrapolation is actively harmful and the weight curve — not the anchor — is what
  needs work.
