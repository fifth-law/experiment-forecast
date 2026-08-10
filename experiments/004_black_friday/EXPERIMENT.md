# 004_black_friday — BF week as learned special days

## Hypothesis

The two remaining error families in 003 share one cause. Nov-13/20 cutoffs
under-forecast the Black Friday spike (bias −0.30/−0.36); 11-27/12-04
cutoffs over-forecast because BF week sits inside the 14-day level window
(bias +0.08/+0.20). Making bf−4 (Monday) .. bf+3 (Cyber Monday) special-day
types — the BF date is a calendar rule, timeless knowledge — fixes both at
once: the spike gets predicted via learned per-offset up-factors, and BF
week stops contaminating every clean window.

## Mechanism

Identical machinery to the holiday factors in 002/003, with two
type-specific tweaks: clip (0, 5) instead of (0, 1.5) because these are
up-factors (BF-day volume ÷ pre-BF 28-day level ≈ 2–4×), and a neutral
fallback of 1.0 if a bf type has no history (cannot happen on stage1,
which sees the 2021 and 2022 BFs). One change vs 003.

## Expected behavior

Nov-13/20 improve strongly (the horizon's BF days get 2–4× factors learned
from 2021/2022); 11-27/12-04 recover to ~002 levels or better (clean level
windows); all non-November cutoffs byte-identical to 003. Risk: BF
intensity drifts year-over-year (DK BF was still growing through the
2020s), so a 2-year pooled factor may under- or over-shoot 2023 — but the
direction should still beat a no-event model by a wide margin.

## Out of scope / next candidates

- Year-boundary day-types: Dec 20–23 wind-down, Dec 27–30 lull (Dec-18
  residual bias +0.47 in 003).
- Robust (median-based) level estimation if unexplained spike sensitivity
  remains outside calendar events.
