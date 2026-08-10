"""Experiment template — copy this folder to experiments_sales/NNN_short_name/.

Contract (enforced by eval_sales/eval.py):
  - history: DataFrame(series_id, posting_month, create_date, dkk). Invoiced
    increments *visible on the night of the cutoff*: a row means "dkk was booked
    against posting_month, and became visible on create_date". Summing a
    series-month's rows gives what was visible so far — for the target month
    that is the month-to-date accrual, for a month that has settled it is the
    final total. Nothing with create_date > cutoff is present, so recent months
    are as incomplete here as they were in reality.
  - shipments: DataFrame(date, series_id, y). Dense daily shipment counts for
    all 105 series, date <= cutoff. Volume leads invoiced revenue and carries no
    reporting lag, so it is the natural driver for the not-yet-invoiced part of
    the month.
  - cutoff: Timestamp — the night the forecast is made on.
  - target_month: str 'YYYY-MM' — the month cutoff falls in. Predict its
    *settled* total, not the remainder.
  - Return DataFrame(series_id, yhat) with exactly one row per series in
    series_meta, yhat in DKK. Negative predictions are allowed (a month can net
    negative when credit notes dominate) and are not clipped.
  - A fresh Forecaster is constructed per cutoff. Cutoffs run chronologically,
    so module-level caching of work derived from frames already handed in is
    allowed; caching anything else is leakage.
  - Must be deterministic: fix all seeds.
  - Never read data/ directly; history and shipments are your only data sources.
    (Exogenous knowledge that would have been known at the cutoff — weekday,
    month, public holidays via the `holidays` package — is allowed.)

Useful derived quantities:
    month_start = pd.Period(target_month, "M").start_time
    days_in_month = cutoff.days_in_month
    create_offset = (history["create_date"] - month_start_of_that_row).dt.days
"""

import pandas as pd

PARAMS = {}  # echoed into the run record on the leaderboard


class Forecaster:
    def fit_predict(
        self,
        history: pd.DataFrame,
        shipments: pd.DataFrame,
        cutoff: pd.Timestamp,
        target_month: str,
        series_meta: dict,
    ) -> pd.DataFrame:
        raise NotImplementedError
