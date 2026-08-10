# 018_blend — 50/50 blend of 015 and 017

## Hypothesis

015 (hand stack: bias ≈ 0, network-calibrated, composition-blind) and
017 (GBM: bias −5.5%, median-chasing, interaction-aware) are differently
wrong. Averaging differently-wrong forecasts reduces variance, and the
blend pulls the GBM's under-forecast halfway back — it should beat both
components (0.2232 / 0.2189).

## Mechanism

Load the two frozen experiment modules by path (immutable per protocol
rule 4, so reproducible), average yhat per (series, date) at 0.5/0.5.
Nothing else.

## Expected behavior

Pooled wMAPE below 0.2189; bias ≈ −2.8% (midpoint); network wMAPE
recovers toward 015's 0.0900. If the blend does NOT beat 017, their
errors are more correlated than the bias split suggests — worth knowing
before promotion. Weight tuning is deliberately left out (one variable).

## Out of scope / next candidates

- Tuned blend weight w (if 0.5 helps, w≈0.6–0.7 toward the GBM may be
  better; risk of overfitting the stage).
- GBM variants: more rounds, L2/tweedie head for network calibration.
