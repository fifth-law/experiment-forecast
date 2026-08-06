"""Experiment template — copy this folder to experiments/NNN_short_name/.

Contract (enforced by eval/eval.py):
  - history: DataFrame(date, series_id, y). Dense daily grid, all 105 series,
    train_start <= date <= cutoff. Counts are int, zero-filled.
  - Return DataFrame(series_id, date, yhat) with exactly one row for every
    series for every date in (cutoff, cutoff + horizon days].
  - A fresh Forecaster is constructed per cutoff; keep no cross-cutoff state.
  - Must be deterministic: fix all seeds.
  - Never read data/snapshot directly; history is your only data source.
    (Exogenous knowledge that would have been known at the cutoff — weekday,
    month, public holidays via the `holidays` package — is allowed.)
"""

import pandas as pd

PARAMS = {}  # echoed into the run record on the leaderboard


class Forecaster:
    def fit_predict(
        self,
        history: pd.DataFrame,
        cutoff: pd.Timestamp,
        horizon: int,
        series_meta: dict,
    ) -> pd.DataFrame:
        raise NotImplementedError
