# 003_shipment_price

## Hypothesis

002's remaining error is concentrated in days 1-10, where there is no accrual to
complete. Shipments are visible the day they happen with no invoicing lag, so the
volume behind this month's invoices can be known before the invoices exist —
especially in an era where a posting month bills the *previous* month's shipments,
in which case the driver is fully known from the 1st.

## Method

`yhat = price(series) * volume(series)`, with the billing lag L learned rather
than assumed: for L in {0, 1, 2}, compute the network revenue-per-shipment ratio
across the last 3 settled months and keep the L with the lowest coefficient of
variation. `price` is pooled DKK/shipment over those months (network price when a
series has under 50 shipments); `volume` is the shipments of month `target - L`,
or for L = 0 month-to-date plus remaining days at the trailing 28-day rate.
Series with no shipment history fall back to a level anchor.

## Expected behaviour

- Should beat 002 in the first 10 days by a wide margin on stage1/stage2, where
  the learned lag should come out as 1 and the driver is therefore complete.
- Should *lose* to 002 late in the month: a fully accrued month beats any
  price x volume estimate.
- Weaker in the modern era, where the lag collapses to 0 and the current month's
  volume has to be forecast rather than read off.
- Diagnostic value: if the chosen lag flips to 0 around 2025, that confirms the
  billing-process change independently of the posting-vs-booking analysis.

## Known simplification

The lag-0 volume forecast uses a flat trailing daily rate with no weekday or
holiday shape, so it is weakest with only a few days left in the month. 004
blends this anchor with the accrual, where that weakness matters least.
