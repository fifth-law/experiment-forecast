# 001_last_settled

## Hypothesis

000's weakness is that it copies a number that is still arriving. Averaging the
last 3 months whose settlement window has *closed* should beat it, because the
level it copies is complete and less noisy — even though the months it uses are
older.

## Method

A month counts as settled when `month_end + 20 days <= cutoff`. Take the mean
per-series total of the last 3 settled months. Still no month-to-date signal.

## Expected behaviour

- Beats 000 in the modern era (2025+), where month-1 is genuinely incomplete
  early in the month.
- Possibly *loses* to 000 in 2021-2024, where every month was fully created
  before its own month end, so month-1 was already complete and is a fresher
  level than a 3-month average.
- Still flat across the month: no day-of-month structure in the error.
