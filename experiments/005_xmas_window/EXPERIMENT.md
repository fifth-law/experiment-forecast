# 005_xmas_window — Christmas-window day-types

## Hypothesis

004's worst cutoff by far is Dec-18 (wMAPE 0.67, bias +0.41), with Dec-11
second-worst among calendar cutoffs (0.35, +0.17): the non-holiday days
Dec 20–23 (wind-down after last-order deadlines) and Dec 27–30
(inter-holiday lull) are forecast at full December run-up volume. Giving
each of those eight fixed dates its own learned level-relative factor —
the identical machinery already used for holidays and BF week — should
remove most of that bias.

## Mechanism

`dec20..dec23, dec27..dec30` join the special-day map. Factors learned
per date from the 2021/2022 year boundaries (network-pooled, vs the raw
28-day clean level before each date, clip (0, 1.5)). Dates migrate
weekdays year over year; the level-relative convention already handles
that. One change vs 004.

## Expected behavior

Dec-18 improves strongly (9 of its 14 horizon days are now factor-
predicted), Dec-11 moderately (4 of 14). All cutoffs whose windows and
horizons avoid Dec 20–Jan 1 are byte-identical to 004.

Accepted risk, deliberately not patched: at the Jan-02 cutoff the 14-day
level window keeps only Jan 2 itself as a clean day, so its level estimate
becomes a single-day sample. If Jan-02 regresses, that isolates the next
experiment's target (robust level windows near dense special clusters).

## Out of scope / next candidates

- Per-series BF factors shrunk toward pooled (Nov-13/20 composition error,
  both still ~0.39 with near-zero bias).
- December run-up regime unreachable from pre-BF windows (Nov-27 cutoff,
  bias −0.26).
- Robust level window near dense special-day clusters (Jan-02).
