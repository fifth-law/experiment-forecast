# Monthly sales-invoiced forecast — journal

Second forecasting track in this repo. Same 105-series split as the shipment
track, different metric: **net sales invoiced (excl. VAT, DKK) for the whole
calendar month, re-forecast every night, per customer.**

The one number: `uv run python -m eval_sales.eval --experiment <name> --stage <stage>`,
pooled wMAPE. Leaderboard: `results_sales/leaderboard.csv`.

---

## 2026-08-10 — track setup: what the metric actually is

Before any model, four facts about `MARTS.ANALYTICS.SALES_INVOICE_DETAILS` that
shaped the whole design. All are reproducible from
`data/extract_sales/sql/probe.sql` and the queries quoted below.

1. **Invoicing is a month-end event.** For posting month 2026-06, 36.9M of the
   month's 41.0M DKK posts on the last day of the month; the rest trickles
   through small daily/weekly runs. So "sales invoiced in month M" by posting
   date is essentially one big run, not a daily flow.

2. **A month's total is not knowable at month end.** By creation date, posting
   month 2026-06 was ~71% created during the month, ~3% within 7 days of month
   end, and **~27% at +8..+15 days after month end**. A nightly job cannot see
   the settled total of the month it is forecasting — nor even last month's.
   This is why the snapshot is a *triangle* (series x posting month x creation
   offset) rather than a monthly series, and why the eval reconstructs "what was
   visible on the night of day c" instead of handing models restated history.

3. **Billing moved from arrears to same-month across 2025.** Share of a posting
   month's DKK whose shipment was booked in the *previous* month: 75% (2021),
   83% (2022-2023), 85% (2024), 47% (2025), **6% (2026)** — same-month share
   goes 21% → 93%. The metric therefore does not mean quite the same thing in
   2023 as it does now.

4. **Settlement behaviour changed with it.** Max creation offset per year is
   <= 30 days for 2021-2024 (nothing was created after its own month ended),
   then 107 (2025) and 60 (2026). Conversely the share created *before* the
   posting month began was 36-56% in 2021-2024, 34% in 2025 and 0.3% in 2026.

Consequences baked into the eval: cutoffs are **every night**; the target is the
**settled** month total; the snapshot stops at **2026-06** because 2026-07 was
still ~1/3 short of its final total when the extract was taken (2026-08-10); and
**stage3 is the production-relevant era** — earlier stages are warm-up whose
ranking is not expected to transfer. Holdout is 2026-05..06, untouched.

Snapshot: 59,108 triangle cells, 66 posting months, 103 of the 105 series
(`c_397088` and `c_405616` had not invoiced anything by 2026-06). All 66 monthly
network totals match an independent aggregation exactly (integer øre, so the
check is equality, not tolerance).

**Known limitation, journaled deliberately:** the as-of view is reconstructed
from a single point-in-time snapshot, so invoice lines that existed on a past
night but were later deleted are absent from the mart entirely. The
reconstruction can therefore slightly *understate* what was visible at the time.
Quantifying that would need a second snapshot taken later, or the corrections
table.

---

## Setup-phase calibration note

This first pass deliberately ran both **stage1 and stage3** rather than
iterating on stage1 alone, because finding #3 above means a stage1-only ladder
would say very little about production behaviour. Every stage3 row on the
leaderboard is labelled a calibration run. Where a stage3 observation motivated
a hypothesis (006, 007) the journal says so explicitly, and in both cases the
mechanism is independently visible in the extract probe. From here the normal
protocol applies: iterate on one stage, promote when it stalls.

---

## Experiment log

### 000_prev_month — baseline, stage1 0.2132
Copy last month's visible total. Flat across the month (dom 1-10 0.2140, dom
21-end 0.2115) exactly as expected, bias -0.3%. Network wMAPE 0.1132 — customer
errors cancel heavily, so the per-customer split is the hard part, not the total.

### 001_last_settled — stage1 0.3104 — FAILED (worse than 000)
Mean of the last 3 *settled* months instead of the unsettled previous month.
Much worse. The predicted reason held: in 2021-2024 every month was fully created
before its own month end, so month-1 was already complete, and a 3-month average
just throws away freshness for no gain. Useful negative result — it says the
level anchor wants to be recent, not safe.

### 002_chain_ladder — stage1 0.1126 — BEST on stage1 at the time (-47% vs 000)
Complete the month-to-date accrual with a development factor: `f(d)` = share of a
settled month's DKK created by day `d`, pooled network-wide over 6 settled months,
`yhat = f(d)*(mtd/f(d)) + (1-f(d))*level`. The error decays exactly as the
mechanism predicts: dom 1-10 0.2502, dom 11-20 0.0766, **dom 21-end 0.0151**, and
0.0000 on the last two nights — in this era the month is fully visible by then.
Diagnostics also showed the residual is not random: bias by target month runs
January -7.1%, March +7.7%, May +8.7%, late-year ~0.

### 003_shipment_price — stage1 0.1930
Pure price x volume, with the billing lag L learned from the stability of the
network revenue-per-shipment ratio. Best early-month number of any model
(dom 1-10 **0.2109**, beating 002's 0.2502) and much worse late (dom 21-end
0.1632) — a fully accrued month beats any driver-based estimate, as expected.
Bias +5.2%.

### 004_blend_ladder_shipments — stage1 0.1153 — FAILED (+2.4% vs 002)
002 with 003's shipment anchor replacing the level anchor. Should have inherited
003's early-month edge; instead dom 1-10 got *worse* (0.2578 vs 002's 0.2502).
The lesson is about bias, not signal: the accrual extrapolation is biased high
(+1.1%) and so is price x volume (+5.2%), so blending them compounds the error,
whereas the flat level anchor is biased slightly low and partially cancels it.
Blending only pays when the components' errors disagree in sign.

### 005_seasonal_anchor — stage1 **0.1066** — BEST on stage1 (-5.3% vs 002)
Anchor becomes same-month-last-year carried forward by shrunk recent growth. Fixed
what the 002 diagnostics pointed at: dom 1-10 0.2502 → 0.2330. Confirms the
early-month problem is a *level and seasonality* problem, not a completion one.
On stage3, though, it is **worse** than 002 (0.2861 vs 0.2648) — see below.

### 006_measured_settlement — stage1 0.1102, stage3 0.2565
Measure the settlement window instead of assuming 20 days: on months at least 150
days old, take the creation offset at which 99% of the eventual total has arrived.
Motivated by the stage3 calibration bias (002 and 005 both ~11-12% low there while
unbiased on stage1) and by finding #4. Improved stage3 by 3.1% and moved bias
-12.4% → -11.6%; stage1 essentially unchanged (0.1126 → 0.1102). So the stale
settlement window was real but was *not* the main cause of the bias.

### 007_recent_curve — stage1 0.1105, stage3 **0.2416** — BEST on stage3 (-5.8% vs 006)
006 with the development curve pooled under exponential recency weights (half-life
2 months) instead of six months weighted equally. Rationale: during 2025-2026 the
accrual shape was *moving* (share created before the posting month collapsed 34% →
0.3%), so an evenly pooled curve overstates how much of the month is visible and
drives every night's forecast low. Bias -11.6% → **-8.7%**, and stage1 unchanged
(0.1102 → 0.1105) as predicted, because that era's curve was stable. Mechanism
confirmed; the drift, not the window, was the dominant term.

---

## 2026-08-10 (later) — scope clarified: previous months + shipments booked to date

The owner clarified the intended information set: predict the final end-of-month
bill from **previous months plus shipments booked to date**, each night. That is a
narrower input set than 002-007 use — those lean on the *current month's invoice
accrual* (draft lines already created), which was never asked for. The target
definition is unchanged, so no re-extraction was needed; 003 was the only existing
model in the requested family and it was a crude first pass.

Models are now tagged by family. The eval hands both frames to every model, so the
family boundary is a modelling choice recorded in each `EXPERIMENT.md` rather than
something the eval enforces — deliberately, so both families compete on one
leaderboard without unfreezing the eval.

### 008_volume_ratio — stage1 0.1849, stage3 0.3961 — FAILED on stage3
Family: previous months + shipments only. 003 done properly: price shrunk towards the
network price (empirical-Bayes ratio, 2000-shipment half-weight) over 6 settled
months instead of a hard 50-shipment cutoff over 3, and a weekday-shaped
remaining-days volume forecast instead of a flat rate. Better than 003 on stage1
(0.1930 → 0.1849) but **worse than the 000 baseline on stage3** (0.3961 vs 0.3638)
at +0.4% bias. A variance verdict, not a bias one: rebuilding the bill as
`price x volume` requires estimating each series' DKK-per-shipment *level*, and that
level is unstable in the modern era — a transitional posting month mixes two shipment
months, and credit notes do not scale with volume at all. Also flat across the month
(0.1853 / 0.1849 / 0.1845 on stage1), as expected when the billing lag is 1 and the
driver is complete from the 1st.

*(An earlier run of 008 was superseded before commit by a performance-only
vectorisation of the remaining-days forecast; the refactor reproduced stage1 to
4 decimals, and the pre-refactor run record was removed so every leaderboard row is
reproducible from committed code.)*

### 009_level_times_growth — stage1 **0.1708**, stage3 **0.2957** — BEST in the requested family
Family: previous months + shipments only. Stop rebuilding the bill; anchor on it and
let shipments supply only the *change*:

    yhat = mean(last 3 settled months) * clip(shrunk volume growth)

with a **two-month** volume window (`ship(M) + ship(M-1)`), which sidesteps the lag
question that sank 008 — whichever month is billed, it is inside the window. The
price level cancels; only its movement has to be measured. Beats 008 by 8% on stage1
and 25% on stage3, beats the baseline in both eras (-20% / -19%), and is nearly
unbiased (+0.1% / -2.4%).

**The finding that matters most:** this family is *better than the accrual models
early in the month* and much worse later.

| stage3 | days 1-10 | days 11-20 | days 21-end | pooled |
|---|---|---|---|---|
| 007_recent_curve (accrual) | 0.3433 | 0.2218 | **0.1626** | 0.2416 |
| 009_level_times_growth (prev months + shipments) | **0.2981** | 0.2962 | 0.2929 | 0.2957 |

Shipments know the month before the invoices exist; the invoices know it better once
they do. The same crossover holds on stage1 (009 0.1693 vs 005 0.2330 over days 1-10).

### 010_growth_anchor_ladder — stage1 0.1088, stage3 **0.2237** — BEST overall
Uses both (so *outside* the requested family). 007 with its flat level anchor replaced
by 009's level x growth estimate. Best stage3 result so far, -7.4% against 007, with
the best late-month number of any model (dom 21-end 0.1585) and a much better
early-month number than 007 (0.3091 vs 0.3433).

This is structurally what 004 tried and failed. The post-mortem was right about why:
004's anchor was +5.2% biased and compounded with the accrual's positive bias, while
009 is near-unbiased. Same structure, unbiased anchor, and it works.

Note it is still *worse* early in the month than 009 alone (0.3091 vs 0.2981), so the
weight curve `w = f(d)` over-trusts the accrual in the first days. That is now the
cheapest remaining win.

---

## Standings

**Family A — previous months + shipments booked to date only** (the requested inputs)

| | stage1 | stage3 (production era) |
|---|---|---|
| **009_level_times_growth** | **0.1708** | **0.2957** |
| 008_volume_ratio | 0.1849 | 0.3961 |
| 003_shipment_price | 0.1930 | — |
| 000_prev_month (baseline) | 0.2132 | 0.3638 |
| 001_last_settled | 0.3104 | — |

**Family B — also uses the current month's invoice accrual**

| | stage1 | stage3 (production era) |
|---|---|---|
| **010_growth_anchor_ladder** | 0.1088 | **0.2237** |
| 005_seasonal_anchor | **0.1066** | 0.2861 |
| 006_measured_settlement | 0.1102 | 0.2565 |
| 007_recent_curve | 0.1105 | 0.2416 |
| 002_chain_ladder | 0.1126 | 0.2648 |
| 004_blend_ladder_shipments | 0.1153 | — |

**What the accrual is worth:** 0.2957 → 0.2237 on stage3, i.e. the draft invoice
lines cut the error by ~24% beyond what previous months and shipments give. All of
that gain lands after roughly day 10; before then the accrual is a liability.

**Ranks still reshuffle across eras**, which per the protocol is the finding: 005 wins
stage1 and is 4th on stage3. The two eras are different problems — on stage1 the month
is fully visible by month end (late-month wMAPE 0.015, and exactly 0.0000 on the last
two nights) so the task is level and seasonality; on stage3 a quarter of the month has
not been created yet on the last night (late-month wMAPE 0.159) so the task is
completing what cannot be seen. The modern era is much harder: 0.224 vs 0.107.

## Next hypotheses, in priority order

1. **Fix the early-month weight curve** (cheapest win). 010 is worse than 009 alone
   over days 1-10, so `w = f(d)` over-trusts the accrual in the first days. Try
   `w = f(d) ** p` with p > 1, or pick `w` per day-of-month by minimising error on
   settled months — a measured weight rather than an assumed one.
2. **The -8.9% stage3 bias.** 006 (settlement window) and 007 (curve drift) each took
   a bite; what remains is likely per-series curve heterogeneity — month-end-billed
   customers and continuously-billed tail groups genuinely have different `f(d)`, and
   one network curve cannot fit both. Try a per-series curve shrunk to the network one.
3. **Seasonality in 009's anchor.** 005 showed a same-month-last-year anchor beats a
   flat mean on stage1; 009 still uses a flat 3-month mean. That change is orthogonal
   to everything in 010.
4. **Explicit late-arrival model.** Rather than dividing by `f(d)`, forecast the
   post-month-end creation wave as its own quantity — it is ~27% of a modern month and
   arrives on a fairly regular +8..+15 day schedule.
5. **Promotion discipline.** stage2 has not been run at all. Before any further
   tuning, run the top models on stage2 to check the stage1/stage3 story holds in the
   transition year.
