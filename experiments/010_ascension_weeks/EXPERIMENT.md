# 010_ascension_weeks — holiday-cluster week damping

## Hypothesis

The May cutoffs oscillate (05-08 +0.16, 05-22 −0.11, 05-29 −0.19, 06-12
+0.16): the whole Ascension→Pentecost cluster runs below normal volume on
its *non-holiday* days too (vacation weeks depress demand), so forecasts
into the cluster over-shoot and level windows inside the cluster
under-shoot the June recovery. Learned week factors fix both directions.

## Mechanism

Weeks W0 (Ascension), W1 (between), W2 (Pentecost), anchored on the
calendar rule: non-special days get `yhat = shape × level × damp[week]`,
with damp learned per week per year against same-weekday clean network
values from the 28 days before the cluster start (clip [0.5, 1.3]); and
damp-week days inside the level window count as `y / damp[week]`.
Deflation-as-level-input is safe here per 009's lesson: these factors are
~0.9, so imported year-over-year drift is a few percent (unlike BF's
2–3×). One mechanism, two application sites, vs 008.

## Expected behavior

All four May/June cutoff biases shrink toward 0. Cutoffs outside
April–June are byte-identical to 008. If damp factors learn ≈1, the
whole change is a no-op — falsifying the vacation-damping theory.

## Out of scope / next candidates

- January intra-month decay (Jan-09 bias +0.18).
- Dec-18 residual aggregate bias (+0.20).
- Summer vacation (weeks 28–31) damping — same mechanism, July anchor —
  if this works.
