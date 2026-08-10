"""000_prev_month — dumbest baseline: last month's invoiced total, as visible tonight.

yhat(series) = sum of everything visible tonight for posting month (target - 1).

No month-to-date information, no settlement correction. In the modern era the
previous month is itself only partly settled early in the current month, so this
baseline is structurally biased low; that gap is exactly what later experiments
have to earn back.
"""

import pandas as pd

PARAMS = {"lag_months": 1}


class Forecaster:
    def fit_predict(
        self,
        history: pd.DataFrame,
        shipments: pd.DataFrame,
        cutoff: pd.Timestamp,
        target_month: str,
        series_meta: dict,
    ) -> pd.DataFrame:
        prev_month = str(pd.Period(target_month, freq="M") - PARAMS["lag_months"])
        totals = (
            history.loc[history["posting_month"] == prev_month]
            .groupby("series_id")["dkk"]
            .sum()
        )
        series = [s["series_id"] for s in series_meta["series"]]
        return pd.DataFrame(
            {"series_id": series, "yhat": [float(totals.get(s, 0.0)) for s in series]}
        )
