# 022_lgbm_edges — event-edge distance features

## Hypothesis

After 021 the worst non-December cutoffs straddle event-cluster edges
(03-27/04-03 around Easter, 05-08/15 around Ascension). Day-type ids
say nothing about the last-orders pull-forward before a closure or the
rebound after; `to_special` / `since_special` (days, capped 10) let the
trees learn those ripples as smooth distance functions. Tested on the
standalone L1 head against 020 (0.2050) for clean attribution before
re-blending.

## Mechanism

Two numeric features of the target date from the same special-day set
the masking uses, via searchsorted. One change vs 020.

## Expected behavior

Standalone GBM below 0.2050 with gains at the Easter/Ascension-edge
cutoffs; if flat, the edges carry no learnable signal at n=2 years and
the feature is dropped rather than blended.

## Out of scope / next candidates

- Re-blend with edge heads if standalone wins (023).
