# 009_level_times_growth

## Family

**Previous months + shipments booked to date only** — same information set as 008,
never the current month's invoice accrual.

## Hypothesis

008 came out worse than the naive baseline on stage3 (0.3961 vs 0.3638) at
near-zero bias, which is a variance verdict, not a bias one: rebuilding a bill as
`price x volume` forces an estimate of every series' DKK-per-shipment *level*, and
that level is unstable in the modern era (a transitional posting month mixes two
shipment months, and credit notes do not scale with volume at all).

Anchoring on previous months' invoiced totals and letting shipments supply only the
*change* cancels the price level entirely — only its movement has to be measured,
which is a far smaller thing to get right.

## Method

    yhat   = anchor * g
    anchor = mean invoiced total of the last 3 settled months
    g      = volume(target window) / mean volume(anchor windows)

The volume window is a *two-month* sum (`ship(M) + ship(M-1)`), which makes the
estimate largely indifferent to whether a posting month bills this month's or last
month's shipments — the question 008 had to answer with a hard lag choice. `g` is
clipped to [0.6, 1.6] and shrunk towards the network growth rate with a 3000-shipment
half-weight. The current month's shipments are month-to-date plus remaining days at
a weekday-shaped rate.

## Expected behaviour

- Beats 008 clearly on stage3 and beats the 000 baseline there, since it can only
  deviate from a known-good level by a bounded, shrunk factor.
- On stage1 it should also beat 008: same cancellation argument, and the two-month
  window covers the arrears billing that era used.
- Should still lose to the accrual models late in the month — no amount of volume
  information beats seeing the invoice lines themselves once they exist.
