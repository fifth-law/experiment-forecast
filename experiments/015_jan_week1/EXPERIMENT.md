# 015_jan_week1 — January week 1 as an up-anomaly

## Hypothesis

Jan-09/16 over-forecast (+0.18/+0.15) because the first January week
(post-New-Year backlog release + returns surge) runs high and then volume
decays to its true level. The anomaly is week 1 being HIGH, not weeks 2–4
being low: damping weeks 2–4 would deflate week-4 days in late-January
level windows and over-lift February forecasts (exit-boundary break).
Week 1 as a transient up-anomaly keeps the chain intact everywhere.

## Mechanism

Damp group `jan` = Jan 2–8 (jan_wk1, clip (0.9, 1.6)) with a FORWARD
base: groups gain a per-group `base_span`, jan uses [anchor+7, anchor+21)
— the backward window would cross the year-boundary regime break —
with min 1 same-weekday base observation (the forward window holds 2
weeks). Applied generically: week-1 targets × factor; week-1 days in
level windows deflate down to the true January level, which is exactly
what the Jan-02/09/16 cutoffs need. One change vs 014.

## Expected behavior

Jan-09 (+0.18) and Jan-16 (+0.15) biases shrink strongly; Jan-02
improves via both channels (targets Jan 3–8 lifted × factor, later
targets forecast at deflated true level). At-cutoff estimation uses
prior years plus whatever forward-base days are already observed.
Everything outside January windows byte-identical.

## Out of scope / next candidates

- Dec-18 residual (+0.20). Nov event-week noise (bias ≈0).
- May cluster residual (05-08 +0.12 / 05-29 −0.14): possible asc factor
  YoY drift; hard with 2 observations.
