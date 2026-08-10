# 034_blend3_shape6 — weekday shape from 6 clean observations

## Hypothesis

The hand head's weekday shape has used the last 4 clean same-weekday
observations since 001. With the level split out (003) and events
excluded, the shape is the head's noisiest component; 6 observations cut
its variance ~18% at the cost of slower shape drift — a good trade for
the mature, volume-dominant series that dominate pooled wMAPE.

## Mechanism

`SHAPE_OBS 4→6` in the hand head; all else byte-identical to the 033
champion (0.233340). One change.

## Expected behavior

Small broad gain on smooth series; young/step series unaffected (the
step-switch level dominates them). Bar: ≤ 0.232640. Sub-bar → counter
2/3.

## Out of scope

- Further shape-window tuning either way.
