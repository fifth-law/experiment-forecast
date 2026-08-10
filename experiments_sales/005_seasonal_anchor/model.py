"""005_seasonal_anchor — give 002's early-month anchor a seasonal shape.

002's residual error is almost entirely in days 1-11, and its per-month bias is
seasonal, not random: on stage1 it under-forecasts January by 7% and over-forecasts
March by 8% and May by 9%. The cause is the anchor — a flat mean of the last 3
settled months, which in a month like March is still carrying the Christmas peak.

Single change from 002: the anchor becomes same-month-last-year carried forward by
recent growth,

    anchor(series) = dkk(series, target_month - 12) * g(series)
    g(series)      = recent 3 settled months / the same 3 months a year earlier,
                     shrunk towards the network growth rate by volume

falling back to 002's flat mean when a series has no usable year-ago month (a
customer that onboarded since). The completion half of the model is untouched.
"""

import pandas as pd

PARAMS = {
    "settle_days": 20,
    "curve_months": 6,
    "level_months": 3,
    "min_visible_frac": 0.02,
    "weight_power": 1.0,
    "shrink_dkk": 500_000.0,   # year-ago volume at which a series growth rate is half-trusted
    "growth_clip": (0.4, 2.5),
}

_MONTH_START: dict[str, pd.Timestamp] = {}


def month_start(month: str) -> pd.Timestamp:
    ts = _MONTH_START.get(month)
    if ts is None:
        ts = pd.Period(month, freq="M").start_time
        _MONTH_START[month] = ts
    return ts


def settled_months(months: list[str], cutoff: pd.Timestamp, settle_days: int) -> list[str]:
    out = []
    for m in months:
        month_end = pd.Period(m, freq="M").end_time.normalize()
        if month_end + pd.Timedelta(days=settle_days) <= cutoff:
            out.append(m)
    return out


def shift_month(month: str, lag: int) -> str:
    return str(pd.Period(month, freq="M") - lag)


class Forecaster:
    def fit_predict(
        self,
        history: pd.DataFrame,
        shipments: pd.DataFrame,
        cutoff: pd.Timestamp,
        target_month: str,
        series_meta: dict,
    ) -> pd.DataFrame:
        series = [s["series_id"] for s in series_meta["series"]]
        day = int(cutoff.day)
        months = sorted(history["posting_month"].unique())
        settled = settled_months(months, cutoff, PARAMS["settle_days"])
        if not settled:
            return pd.DataFrame({"series_id": series, "yhat": [0.0] * len(series)})

        # --- completion factor (unchanged from 002) ---
        curve = settled[-PARAMS["curve_months"]:]
        rows = history.loc[history["posting_month"].isin(curve)]
        offset = (rows["create_date"] - rows["posting_month"].map(month_start)).dt.days
        final_sum = float(rows["dkk"].sum())
        visible_sum = float(rows.loc[offset <= day - 1, "dkk"].sum())
        frac = min(max(visible_sum / final_sum if final_sum > 0 else 0.0, 0.0), 1.0)

        mtd = (
            history.loc[history["posting_month"] == target_month]
            .groupby("series_id")["dkk"]
            .sum()
        )
        revenue = history.groupby(["series_id", "posting_month"])["dkk"].sum()

        # --- seasonal anchor ---
        recent = settled[-PARAMS["level_months"]:]
        year_ago = [shift_month(m, 12) for m in recent]
        available = set(months)
        usable_growth = all(m in available for m in year_ago)

        flat_level = (
            history.loc[history["posting_month"].isin(recent)]
            .groupby("series_id")["dkk"]
            .sum()
            / len(recent)
        )

        recent_by_series = (
            history.loc[history["posting_month"].isin(recent)]
            .groupby("series_id")["dkk"]
            .sum()
        )
        yoy_by_series = (
            history.loc[history["posting_month"].isin(year_ago)]
            .groupby("series_id")["dkk"]
            .sum()
        )
        net_recent = float(recent_by_series.sum())
        net_yoy = float(yoy_by_series.sum())
        lo, hi = PARAMS["growth_clip"]
        net_growth = min(max(net_recent / net_yoy, lo), hi) if net_yoy > 0 else 1.0

        base_month = shift_month(target_month, 12)
        base_available = base_month in available

        yhat = []
        for sid in series:
            base = float(revenue.get((sid, base_month), 0.0))
            if usable_growth and base_available and base != 0.0:
                yoy = float(yoy_by_series.get(sid, 0.0))
                if yoy > 0:
                    raw = float(recent_by_series.get(sid, 0.0)) / yoy
                    growth = min(max(raw, lo), hi)
                    w = yoy / (yoy + PARAMS["shrink_dkk"])
                    growth = w * growth + (1.0 - w) * net_growth
                else:
                    growth = net_growth
                anchor = base * growth
            else:
                anchor = float(flat_level.get(sid, 0.0))

            if frac >= PARAMS["min_visible_frac"]:
                extrapolated = float(mtd.get(sid, 0.0)) / frac
                weight = frac ** PARAMS["weight_power"]
                yhat.append(weight * extrapolated + (1.0 - weight) * anchor)
            else:
                yhat.append(anchor)
        return pd.DataFrame({"series_id": series, "yhat": yhat})
