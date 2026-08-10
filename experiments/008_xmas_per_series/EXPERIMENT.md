# 008_xmas_per_series — per-series Christmas-window multipliers

## Hypothesis

007 proved event appetite is series-specific and persistent (BF cutoffs
0.39→0.29, bias unchanged). Dec-18 — still the worst cutoff at 0.49 with
only +0.14 bias — should be the same composition story around the year
boundary: gift merchants die after the last-order deadline, replenishment
merchants keep shipping through the lull.

## Mechanism

The identical shrunk actual-vs-expected multiplier from 007, computed as
a second group over the Christmas window (dec20..dec30 day-types, Dec
24–26 holidays, New Year's Eve, Jan 1) and applied on those days. Same
k=500, same clip [0.2, 3.0]. BF keeps its own group multiplier. One
change vs 007.

## Expected behavior

Dec-18 and Dec-11 improve; Jan-02 may improve slightly (Jan 1 in its
horizon). November and everything else byte-identical to 007. Risk: the
group pools deadline-driven wind-down days with restart-driven lull days
into one per-series appetite — if those behaviors diverge per series the
multiplier averages them; splitting the group is the follow-up if the
result underwhelms.

## Out of scope / next candidates

- BF days as factor-deflated level observations (Nov-27 bias −0.26).
- January intra-month decay (Jan-09 bias +0.18).
- May holiday-cluster level dynamics (05-08 +0.16 / 05-29 −0.19).
