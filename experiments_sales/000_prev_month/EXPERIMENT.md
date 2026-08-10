# 000_prev_month

## Hypothesis

The floor. A month's invoiced sales look mostly like the previous month's, so
"repeat what you can see for last month" is the reference every real model must
beat.

## Method

`yhat(series) = ` everything visible on the night of the cutoff for posting
month `target_month - 1`. No month-to-date signal, no settlement correction, no
seasonality.

## Expected behaviour

- Flat error across the month: the forecast never updates as the month fills in,
  so `wmape_dom_1_10` ≈ `wmape_dom_21_end`.
- Biased low, and worse in the modern era: early in month M, month M-1 has not
  finished settling (the +8..+15 day creation wave has not landed), so the number
  being copied is itself incomplete.
- Network wMAPE much better than per-series wMAPE — customer-level errors cancel.
