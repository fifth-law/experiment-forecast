# 006_measured_settlement

## Hypothesis

002 and 005 are unbiased on stage1 but 11-12% biased *low* on stage3. Both treat a
month as final 20 days after month end, which was true through 2024 but is not true
in the modern era: the extract probe finds 1.6% of 2025 DKK created more than 45
days into its posting month, with a tail to +107 days. Using a still-filling month
as a "final total" shrinks the development curve's denominator, inflates f(d), and
drives `mtd / f(d)` low every single night. Measuring the settlement window instead
of assuming it should remove that bias without touching anything else.

## Method

Single change from 002. On months whose start is at least 150 days behind the cutoff
(complete beyond doubt), accumulate DKK by creation offset and take the offset at
which 99% of the eventual total has arrived, flooring it at 30 days. A month counts
as settled once the cutoff is that far past its start. Curve months and level months
both use that rule.

## Expected behaviour

- stage3 bias moves sharply towards zero and pooled wMAPE improves.
- stage1 roughly unchanged or marginally worse: that era had no post-month-end
  creation at all, so the measured window collapses to about a month and the only
  effect is slightly staler curve/level months.
- If stage1 degrades materially, the settlement window is doing more than
  bias-correction and the change should be split further.

## Provenance note

The hypothesis came from the stage3 *calibration* runs (bias sign and magnitude),
not from score-chasing on stage3: the mechanism is independently visible in
`data/extract_sales/sql/probe.sql`, which measures the creation-offset tail per year
directly from the source table.
