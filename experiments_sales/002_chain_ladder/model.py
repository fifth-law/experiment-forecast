"""002_chain_ladder — complete the month-to-date accrual with a development curve.

The mechanism the baselines ignore: by the night of day d, some known fraction of
a month's eventual invoiced total has already been created. Estimate that
fraction from months that have settled, then divide tonight's accrual by it.

    f(d)  = (DKK created by day d) / (settled total), pooled over the last
            CURVE_MONTHS settled months, volume-weighted (a chain-ladder
            development factor — network-level, because per-series curves are
            far too noisy for small customers)
    yhat  = w(d) * mtd(series) / f(d)  +  (1 - w(d)) * level(series)

with w(d) = f(d) ** WEIGHT_POWER, so on the 1st — when nothing has accrued and
the ratio would explode — the forecast is just the recent level, and by month end
it is almost entirely the accrual. level(series) is 001's anchor: the mean of the
last LEVEL_MONTHS settled months.

This also absorbs the era change for free: in 2021-2024 roughly half of a month's
lines were created before the month even started, so f(1) is already ~0.5 and the
model leans on the accrual immediately; in 2026 f(1) is ~0 and it leans on the
level until the month fills in.
"""

import pandas as pd

PARAMS = {
    "settle_days": 20,      # a month is trusted as final this long after month end
    "curve_months": 6,      # settled months pooled for the development curve
    "level_months": 3,      # settled months averaged for the level anchor
    "min_visible_frac": 0.02,   # below this, the ratio is not usable at all
    "weight_power": 1.0,    # w(d) = f(d) ** power
}

_MONTH_START: dict[str, pd.Timestamp] = {}


def month_start(month: str) -> pd.Timestamp:
    """Cached first-of-month timestamp (a pure function of the label)."""
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
        day = int(cutoff.day)  # offsets 0..day-1 of the target month are visible

        months = sorted(history["posting_month"].unique())
        settled = settled_months(months, cutoff, PARAMS["settle_days"])

        # development factor at this day of month, pooled over recent settled months
        curve = settled[-PARAMS["curve_months"]:]
        visible_sum = final_sum = 0.0
        if curve:
            rows = history.loc[history["posting_month"].isin(curve)]
            offset = (rows["create_date"] - rows["posting_month"].map(month_start)).dt.days
            final_sum = float(rows["dkk"].sum())
            visible_sum = float(rows.loc[offset <= day - 1, "dkk"].sum())
        frac = visible_sum / final_sum if final_sum > 0 else 0.0
        frac = min(max(frac, 0.0), 1.0)

        mtd = (
            history.loc[history["posting_month"] == target_month]
            .groupby("series_id")["dkk"]
            .sum()
        )
        level_months = settled[-PARAMS["level_months"]:]
        if level_months:
            level = (
                history.loc[history["posting_month"].isin(level_months)]
                .groupby("series_id")["dkk"]
                .sum()
                / len(level_months)
            )
        else:
            level = pd.Series(dtype="float64")

        weight = frac ** PARAMS["weight_power"]
        yhat = []
        for sid in series:
            anchor = float(level.get(sid, 0.0))
            accrued = float(mtd.get(sid, 0.0))
            if frac >= PARAMS["min_visible_frac"]:
                extrapolated = accrued / frac
                yhat.append(weight * extrapolated + (1.0 - weight) * anchor)
            else:
                yhat.append(anchor)
        return pd.DataFrame({"series_id": series, "yhat": yhat})
