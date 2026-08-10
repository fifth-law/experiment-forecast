# 033_blend3_slowlr — slower learning, larger round budget

## Hypothesis

The capacity axis is still paying (031 +0.61%, 032 +0.44%, each ~2/3 of
the last). The conventional next step trades learning rate for rounds
(0.06→0.045, 450→650): finer steps usually squeeze the last of a
capacity axis before it flattens.

## Mechanism

Coupled lr/rounds change in both GBM heads (a single axis by
convention); all else byte-identical to the 032 champion (0.233639).
Runtime ~60 min per stage3 run.

## Expected behavior

If the geometric decay holds, ~+0.3% — right at the bar. Sub-bar means
the axis is spent and the loop is likely at its stage3 asymptote
(counter would go 1/3, with only low-EV levers left).

## Out of scope

- Further same-axis steps regardless of outcome (diminishing returns
  documented).
