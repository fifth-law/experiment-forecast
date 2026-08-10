# 031_blend3_dualref — GBM training refs doubled (Mon + Thu)

## Hypothesis

The GBM heads train on Monday refs only: each calendar event is seen
from one ref-offset alignment per week of history. Adding Thursday refs
doubles the (ref, lead) alignments per event and per step transition —
the most general remaining capacity lever, and unlike 024's leaf bump it
adds *information* (new alignments), not just flexibility.

## Mechanism

Training refs = Mondays + Thursdays in the same date range (prediction
still from the true cutoff). ~2× training rows; runtime roughly doubles
per head (stage3 run ≈ 35 min, background). Components otherwise
byte-identical to 029 (0.236039). One change.

## Expected behavior

Broad small gains, strongest on event weeks and long leads (more
alignments of dec-types/bf-types × lead). Bar: ≤ 0.235331. Sub-bar →
counter 2/3 and the loop is one miss from the final summary.

## Out of scope

- Mixing eval-cadence assumptions into the eval itself (the eval stays
  Monday-cutoff; only GBM training refs change).
