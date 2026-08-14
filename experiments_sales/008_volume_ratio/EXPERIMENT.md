# 008_volume_ratio

## Family

**Previous months + shipments booked to date only.** This is the information set
the owner specified. Unlike 002/005/006/007 it never reads the current month's
invoice-line accrual — only settled *previous* months' invoiced totals and the
shipment counts visible tonight.

## Hypothesis

003 tested this idea crudely and scored 0.1930 on stage1 with the driver volume
*fully known* (that era bills the previous month's shipments), which says the
binding constraint is the noise in DKK-per-shipment, not the volume. Estimating
that ratio properly — shrunk towards the network price, pooled over 6 months
instead of 3 — plus a weekday-shaped remaining-days volume forecast should close
much of the gap to the accrual-based models.

## Method

    price(series)  = (sum revenue + tau * network price) / (sum shipments + tau)
                     over the last 6 settled months, tau = 2000 shipments/month
    volume(series) = shipments of month (target - L), L learned from the stability
                     of the network revenue-per-shipment ratio; for L = 0,
                     month-to-date shipments + remaining days at a weekday-shaped
                     daily rate (series shape shrunk towards the network shape)
    yhat           = price * volume, with the recent invoiced level as the fallback
                     for series that have revenue but no shipments behind it

Settled months are identified with 006's measured settlement window, so the price
denominator is never a still-filling month.

## Expected behaviour

- Clear improvement on 003 in both stages; the question is how much of the gap to
  007 (0.2416 on stage3) it closes without the accrual.
- Flatter error across the month than the accrual models: with L = 1 the forecast
  barely changes as the month passes, and with L = 0 it improves only as shipments
  accumulate — not as invoices are created.
- If it lands close to 007, the accrual is mostly a restatement of shipments and
  the simpler input set is the better production choice.
