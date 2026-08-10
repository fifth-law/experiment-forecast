# 013_dec_runup — December run-up weeks as up-factors

## Hypothesis

Nov-27 (0.31, bias −0.26) is the last big directional miss: a post-BF
cutoff's level window holds only pre-BF days, so the December run-up
(Cyber Monday → last-order deadline ~Dec 19, roughly +10–30% over the
pre-BF level) is invisible. 009 failed trying to recover it *through*
the 2–3× BF spike; the run-up itself is a mild calendar-anchored lift,
which the damp machinery handles drift-safely.

## Mechanism

Third damp group `runup`: blocks Nov 28–Dec 5 (w3), Dec 6–12 (w2),
Dec 13–19 (w1, deadline week), anchor = pre-BF Monday, base
[anchor−28, anchor) same-weekday clean values, per-group clip (0.8, 2.0).
Applied like every damp group: on normal-day targets and as level-window
deflation (run-up days deflate to pre-BF terms, so every December cutoff
sits on one convention). Groups gain a per-group clip; asc/sum factors
unchanged. One change vs 011 (012 was rejected).

## Expected behavior

Nov-27 bias −0.26 shrinks strongly; 12-04/12-11 stay consistent (their
levels deflate down, their targets factor back up); Dec-18's special_level
convention is untouched. Cutoffs outside Nov 14–Dec 18 windows/horizons
are byte-identical to 011.

## Out of scope / next candidates

- January intra-month decay (Jan-09 +0.18) — needs a forward-anchored
  base ([Jan 2, Jan 8]) in the damp machinery.
- Dec-18 residual (+0.20): year-over-year drift in wind-down/lull depth;
  hard with 2 observations.
