# 019_blend3 — equal-thirds blend: hand stack + L1 GBM + L2 GBM

## Hypothesis

018 proved the families' residuals are substantially uncorrelated. The
cheapest new diversity is a mean-calibrated GBM: identical features and
training rows to 017 but L2 objective → conditional means instead of
medians, opposite bias direction, network-friendly. Equal thirds beats
the 50/50 two-model blend (0.2108).

## Mechanism

Load frozen 015 and 017 twice; override the second 017 copy's objective
to "regression" in memory (frozen file untouched). Average the three
yhats. Blend weights stay untuned on principle. One change vs 018.

## Expected behavior

Pooled wMAPE below 0.2108, network wMAPE toward 0.09 or below, blend
bias closer to −2%. Runtime roughly doubles the GBM cost (~7–8 min,
inside the budget). If flat-to-worse: the L2 head's errors correlate
with the L1 head's (same features) and mean-calibration adds nothing
the hand stack didn't already contribute — informative before
promotion.

## Out of scope / next candidates

- Distinct feature sets per GBM head (decorrelate further).
- Promotion check: stall counter currently 0.
