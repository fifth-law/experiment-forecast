# 032_blend3_rounds — boosting rounds rebalanced to the 2× data

## Hypothesis

031 doubled the GBM training rows but kept 300 boosting rounds — a
budget chosen for half this data. With 2× rows per leaf statistics the
heads can absorb more rounds before overfitting; 450 rounds recovers
the capacity-to-data ratio.

## Mechanism

`num_boost_round 300→450` in both GBM heads; all else byte-identical to
the 031 champion (0.234628). One change. Runtime ~+50% on the GBM part
(~45 min per stage3 run, background).

## Expected behavior

Small broad gain if 300 was underfit; flat-to-worse if the walk-forward
already sat at the capacity sweet spot. Bar: ≤ 0.233924.

## Out of scope

- Learning-rate joint tuning (one variable at a time).
