# 024_blend3_capacity — GBM capacity bump in the champion blend

## Hypothesis

The GBM heads may be underfit: ~200k interaction-rich rows on 63 leaves
with min_data_in_leaf 60. Doubling leaf count (127) and lowering the
leaf minimum (20) lets trees form series × day-type × lead splits they
currently cannot afford. Tested inside the champion blend (023,
0.199565); the walk-forward eval punishes any overfit honestly.

## Mechanism

`num_leaves 63→127`, `min_data_in_leaf 60→20` in the local head module;
everything else identical to 023. One change.

## Expected behavior

If underfit was real: broad small gains, clearing the bar (≤0.198966).
If not: flat-to-worse from variance — and that makes three consecutive
sub-0.3% experiments, triggering promotion to stage2 per the protocol.

## Out of scope

- Any further stage1 tuning if the stall rule fires.
