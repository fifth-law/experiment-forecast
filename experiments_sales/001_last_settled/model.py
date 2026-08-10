"""001_last_settled — repeat the most recent month that has actually settled.

000 copies month-1 even when month-1 is still filling in. This one only trusts a
month once its settlement window has passed (month end + SETTLE_DAYS <= cutoff)
and averages the last LOOKBACK such months, which also damps single-month noise.

Still uses no month-to-date information: it is the "how much does ignoring the
accrual cost?" reference point.
"""

import pandas as pd

PARAMS = {"settle_days": 20, "lookback": 3}


def settled_months(history: pd.DataFrame, cutoff: pd.Timestamp, settle_days: int) -> list[str]:
    """Months whose settlement window closed on or before the cutoff, oldest first."""
    months = sorted(history["posting_month"].unique())
    out = []
    for m in months:
        month_end = pd.Period(m, freq="M").end_time.normalize()
        if month_end + pd.Timedelta(days=settle_days) <= cutoff:
            out.append(m)
    return out


class Forecaster:
    def fit_predict(
        self,
        history: pd.DataFrame,
        shipments: pd.DataFrame,
        cutoff: pd.Timestamp,
        target_month: str,
        series_meta: dict,
    ) -> pd.DataFrame:
        months = settled_months(history, cutoff, PARAMS["settle_days"])
        recent = months[-PARAMS["lookback"]:]
        series = [s["series_id"] for s in series_meta["series"]]
        if not recent:
            return pd.DataFrame({"series_id": series, "yhat": [0.0] * len(series)})

        window = history.loc[history["posting_month"].isin(recent)]
        level = window.groupby("series_id")["dkk"].sum() / len(recent)
        return pd.DataFrame(
            {"series_id": series, "yhat": [float(level.get(s, 0.0)) for s in series]}
        )
