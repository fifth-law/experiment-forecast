"""007_recent_curve — weight the development curve towards recent months.

006 measured the settlement window correctly and still came out 11.6% low on
stage3. What is left is drift in the curve itself, not in the settlement window.
The share of a month created *before* its posting month collapsed from 34% in 2025
to 0.3% in 2026 as billing moved from arrears to same-month, so the accrual now
happens later in the month than it used to. A development curve pooled evenly over
six months therefore claims more of the month is visible than really is, and
mtd / f(d) lands low every night.

Single change from 006: the curve pools months with exponential recency weights
(half-life CURVE_HALFLIFE months) instead of weighting six months equally, so it
tracks a moving process instead of averaging over the move.
"""

import pandas as pd

PARAMS = {
    "mature_days": 150,     # a month this old is certainly complete
    "settle_quantile": 0.99,
    "settle_sample": 12,    # mature months pooled to measure the settlement window
    "settle_floor": 30,     # never call a month settled before it has ended
    "curve_months": 6,        # months considered for the curve
    "curve_halflife": 2.0,    # exponential recency weight over those months
    "level_months": 3,
    "min_visible_frac": 0.02,
    "weight_power": 1.0,
}

_MONTH_START: dict[str, pd.Timestamp] = {}


def month_start(month: str) -> pd.Timestamp:
    ts = _MONTH_START.get(month)
    if ts is None:
        ts = pd.Period(month, freq="M").start_time
        _MONTH_START[month] = ts
    return ts


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
        starts = {m: month_start(m) for m in months}
        age = {m: (cutoff - starts[m]).days for m in months}

        # --- measure the settlement window on months old enough to be complete ---
        mature = [m for m in months if age[m] >= PARAMS["mature_days"]]
        mature = mature[-PARAMS["settle_sample"]:]
        settle_offset = PARAMS["settle_floor"]
        if mature:
            rows = history.loc[history["posting_month"].isin(mature)]
            offsets = (rows["create_date"] - rows["posting_month"].map(starts)).dt.days
            by_offset = rows.groupby(offsets)["dkk"].sum().sort_index()
            total = float(by_offset.sum())
            if total > 0:
                cumulative = by_offset.cumsum() / total
                reached = cumulative[cumulative >= PARAMS["settle_quantile"]]
                if len(reached):
                    settle_offset = max(int(reached.index[0]), PARAMS["settle_floor"])

        settled = [m for m in months if age[m] >= settle_offset and m != target_month]
        if not settled:
            return pd.DataFrame({"series_id": series, "yhat": [0.0] * len(series)})

        # --- completion factor, recency-weighted over settled months ---
        curve = settled[-PARAMS["curve_months"]:]
        visible_sum = final_sum = 0.0
        for position, month in enumerate(reversed(curve)):
            weight_m = 0.5 ** (position / PARAMS["curve_halflife"])
            rows = history.loc[history["posting_month"] == month]
            offsets = (rows["create_date"] - starts[month]).dt.days
            final_sum += weight_m * float(rows["dkk"].sum())
            visible_sum += weight_m * float(rows.loc[offsets <= day - 1, "dkk"].sum())
        frac = min(max(visible_sum / final_sum if final_sum > 0 else 0.0, 0.0), 1.0)

        mtd = (
            history.loc[history["posting_month"] == target_month]
            .groupby("series_id")["dkk"]
            .sum()
        )
        level = (
            history.loc[history["posting_month"].isin(settled[-PARAMS["level_months"]:])]
            .groupby("series_id")["dkk"]
            .sum()
            / len(settled[-PARAMS["level_months"]:])
        )

        weight = frac ** PARAMS["weight_power"]
        yhat = []
        for sid in series:
            anchor = float(level.get(sid, 0.0))
            if frac >= PARAMS["min_visible_frac"]:
                extrapolated = float(mtd.get(sid, 0.0)) / frac
                yhat.append(weight * extrapolated + (1.0 - weight) * anchor)
            else:
                yhat.append(anchor)
        return pd.DataFrame({"series_id": series, "yhat": yhat})
