# 021_blend3_v2 — equal-thirds blend with base-fixed GBM heads

## Hypothesis

The 018/019 blend gains came from genuinely uncorrelated residuals, not
from papering over the GBM's Jan-02 zero-hole. With the fixed heads
(020 standalone = 0.2050) the same equal-thirds blend with 015 should
set a new best below 0.2050.

## Mechanism

1/3 × 015 + 1/3 × 020(L1) + 1/3 × 020(L2 objective, in-memory param
override of the frozen module). Identical to 019 except the GBM folder.
Weights stay untuned on principle.

## Expected behavior

New best below 0.2050; bias between 015's ~0 and 020's −3.7%; network
wMAPE at or below 0.089. If the blend NO LONGER beats the fixed GBM,
the earlier blend gains were partly hole-masking — worth knowing, and
the fixed GBM would then be the promotion candidate.

## Out of scope / next candidates

- Promotion check per protocol once the stall rule triggers.
