# 023_blend3_edges — champion blend with edge-v2 heads

## Hypothesis

022's edge features fix the Easter/Ascension edge cutoffs but re-poison
January via distances to the xmas window. Excluding Dec 20–31 + Jan 1
from the distance set keeps the gain without the damage; inside the
champion blend this should beat 0.2001 by ≥0.3%.

## Mechanism

`lgbm_edges2.py` (in this folder) = 022's head with the xmas window
removed from the distance set. Blend identical to 021 with the v2 heads.
One mechanism change vs the champion.

## Expected behavior

Blend below 0.19950 (the 0.3% bar). Gains at 03-27/04-03/04-10,
05-08/15, Nov-06; January unchanged vs 021. If it lands between 0.1995
and 0.2001 the edge signal is too small at blend scale — journal and
count toward the stall.

## Out of scope / next candidates

- Deeper GBM (rounds/leaves) as a blend variant.
- Promotion once the stall rule triggers (counter 1/3 after 022).
