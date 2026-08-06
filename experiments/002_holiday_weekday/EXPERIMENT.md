# 002_holiday_weekday — holiday-aware weekday profile

## Hypothesis

The four worst stage1 cutoffs in the best run (001, wMAPE 0.2654) are all
calendar events: 2023-12-18 (wMAPE 1.38, bias +1.30) and 2023-12-11 (0.58,
+0.42) forecast full volume across Christmas/New Year dead days; the
Easter/May cutoffs swing bias ±0.13–0.21 because holidays first get
over-forecast, then pollute the trailing weekday window and cause
under-forecast after. Making the weekday profile holiday-aware should
remove most of that error.

## Mechanism

- Trailing profile uses the last 4 **clean** (non-special) same-weekday
  observations, so holidays stop dragging subsequent weeks down.
- Special target dates get `factor[type] × recent 28-day clean level`,
  with the factor estimated per special-day type from the history frame
  (network-pooled). Level-relative rather than weekday-relative so
  fixed-date specials that migrate across weekdays year over year
  (Dec 24/25/26/31, Jan 1, Jun 5) stay consistent.
- Special days: official DK holidays via the `holidays` package (which
  encodes the 2024 abolition of Store Bededag) + Dec 24, Dec 31, Jun 5.
  Factors are learned, so a special day that is actually normal ≈ no-op.

## Expected behavior

Large improvement on the two December cutoffs and the Easter/May bias
swings; unchanged on cutoffs whose window and horizon contain no special
days (profile then reduces to 001 exactly). Black Friday under-forecast
(2023-11-13/20, bias −0.36) is deliberately out of scope — separate
hypothesis.

## Out of scope / next candidates

- November-peak (Black Friday) year-over-year lift.
- Inter-holiday lull Dec 27–30 and the pre-Christmas wind-down week.
- Trend correction on the 4-week window (001 showed bias −1.4%).
