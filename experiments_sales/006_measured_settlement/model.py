"""006_measured_settlement — stop assuming when a month is finished; measure it.

The stage3 calibration runs showed 002 and 005 biased 11-12% *low* in the modern
era while being unbiased on stage1. The mechanism: both call a month settled 20
days after month end, but since 2025 invoice lines keep arriving well beyond that
(the extract probe finds 1.6% of 2025 DKK created more than 45 days into the
posting month, with a tail out to +107 days). A month that is still filling in gets
used as a "final total", so the development curve's denominator is too small, f(d)
comes out too high, and mtd / f(d) lands too low — every night, in one direction.

Single change from 002: the settlement window is measured from the data instead of
being a constant. Using only months old enough to be complete beyond doubt
(month start at least MATURE_DAYS ago), accumulate DKK by creation offset and take
the offset at which SETTLE_Q of the eventual total has arrived. A month then counts
as settled once the cutoff is that far past its start. This adapts by itself: in
2021-2024 nothing was created after month end and the window collapses to about a
month, while in the modern era it stretches past it.
"""

import pandas as pd

PARAMS = {
    "mature_days": 150,     # a month this old is certainly complete
    "settle_quantile": 0.99,
    "settle_sample": 12,    # mature months pooled to measure the settlement window
    "settle_floor": 30,     # never call a month settled before it has ended
    "curve_months": 6,
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

        # --- completion factor, on genuinely settled months (otherwise as 002) ---
        curve = settled[-PARAMS["curve_months"]:]
        rows = history.loc[history["posting_month"].isin(curve)]
        offsets = (rows["create_date"] - rows["posting_month"].map(starts)).dt.days
        final_sum = float(rows["dkk"].sum())
        visible_sum = float(rows.loc[offsets <= day - 1, "dkk"].sum())
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
