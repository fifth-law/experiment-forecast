# 004_blend_ladder_shipments

## Hypothesis

002 and 003 fail in opposite halves of the month. Replacing 002's level anchor
with 003's shipment-driven price x volume anchor should keep 002's late-month
accuracy and pick up 003's early-month advantage, with the crossover set by the
measured development curve instead of a tuned date.

## Method

Exactly 002, one change:

    yhat = f(d) * (mtd / f(d)) + (1 - f(d)) * price(series) * volume(series)

where `price` and `volume` are 003's (billing lag learned from the stability of
the network revenue-per-shipment ratio).

## Expected behaviour

- `wmape_dom_1_10` close to 003's, `wmape_dom_21_end` close to 002's, so pooled
  wMAPE below both.
- If it does *not* beat 002, the anchor is not adding information the accrual
  lacks, and the next move is a better early-month level (seasonality, growth)
  rather than a better driver.
