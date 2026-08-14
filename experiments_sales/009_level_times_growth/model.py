"""009_level_times_growth — previous months' bill, moved by shipment growth.

Same family as 008 (previous months + shipments booked to date, never the current
month's invoice accrual), but it stops trying to rebuild the bill from a price.

008 reconstructs revenue as price x volume, which forces it to estimate the DKK per
shipment *level* for every series. On stage3 that came out worse than copying last
month (0.3961 vs 0.3638) at near-zero bias — pure variance, because a series' DKK
per shipment is unstable in the modern era: during the arrears-to-same-month
transition a posting month mixes two shipment months, and credit notes do not scale
with volume at all.

This model only ever uses the price *implicitly*, and only its change:

    yhat(series) = anchor(series) * g(series)
    anchor       = mean invoiced total of the last LEVEL_MONTHS settled months
    g            = volume(target window) / mean volume(anchor windows)

so whatever a customer's price level is, it cancels — only the movement in
shipments has to be measured. Two further robustness choices: the volume window is
a *two-month* sum (`ship(M) + ship(M-1)`), which makes the estimate largely
indifferent to whether a posting month bills this month's or last month's
shipments, and `g` is shrunk towards the network growth rate and clipped.
"""

import pandas as pd

PARAMS = {
    "mature_days": 150,
    "settle_quantile": 0.99,
    "settle_sample": 12,
    "settle_floor": 30,
    "level_months": 3,          # settled months averaged for the anchor
    "growth_clip": (0.6, 1.6),
    "growth_tau": 3000.0,       # shipments at which a series growth rate is half-trusted
    "profile_days": 56,         # trailing window for level + weekday shape
    "shape_tau": 500.0,
}

_MONTH_START: dict[str, pd.Timestamp] = {}


def month_start(month: str) -> pd.Timestamp:
    ts = _MONTH_START.get(month)
    if ts is None:
        ts = pd.Period(month, freq="M").start_time
        _MONTH_START[month] = ts
    return ts


def shift_month(month: str, lag: int) -> str:
    return str(pd.Period(month, freq="M") - lag)


def measure_settlement(history: pd.DataFrame, months: list[str], starts: dict,
                       age: dict) -> int:
    """Creation offset by which SETTLE_QUANTILE of a month has arrived (see 006)."""
    mature = [m for m in months if age[m] >= PARAMS["mature_days"]][-PARAMS["settle_sample"]:]
    if not mature:
        return PARAMS["settle_floor"]
    rows = history.loc[history["posting_month"].isin(mature)]
    offsets = (rows["create_date"] - rows["posting_month"].map(starts)).dt.days
    by_offset = rows.groupby(offsets)["dkk"].sum().sort_index()
    total = float(by_offset.sum())
    if total <= 0:
        return PARAMS["settle_floor"]
    cumulative = by_offset.cumsum() / total
    reached = cumulative[cumulative >= PARAMS["settle_quantile"]]
    if not len(reached):
        return PARAMS["settle_floor"]
    return max(int(reached.index[0]), PARAMS["settle_floor"])


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
        months = sorted(history["posting_month"].unique())
        starts = {m: month_start(m) for m in months}
        age = {m: (cutoff - starts[m]).days for m in months}

        settle_offset = measure_settlement(history, months, starts, age)
        settled = [m for m in months if age[m] >= settle_offset and m != target_month]
        if not settled:
            return pd.DataFrame({"series_id": series, "yhat": [0.0] * len(series)})
        anchor_months = settled[-PARAMS["level_months"]:]

        anchor = (
            history.loc[history["posting_month"].isin(anchor_months)]
            .groupby("series_id")["dkk"]
            .sum()
            .reindex(series)
            .fillna(0.0)
            / len(anchor_months)
        )

        ship = shipments.copy()
        ship["month"] = ship["date"].dt.to_period("M").astype(str)
        ship_month = ship.groupby(["series_id", "month"])["y"].sum()

        def month_volume(month: str) -> pd.Series:
            return pd.Series(
                {sid: float(ship_month.get((sid, month), 0.0)) for sid in series},
                dtype="float64",
            )

        # two-month volume window: largely indifferent to which month is billed
        current = self._forecast_current_month(ship, ship_month, cutoff, target_month, series)
        target_volume = current + month_volume(shift_month(target_month, 1))
        anchor_volume = sum(
            month_volume(m) + month_volume(shift_month(m, 1)) for m in anchor_months
        ) / len(anchor_months)

        net_growth = (
            float(target_volume.sum()) / float(anchor_volume.sum())
            if float(anchor_volume.sum()) > 0 else 1.0
        )
        lo, hi = PARAMS["growth_clip"]
        net_growth = min(max(net_growth, lo), hi)

        raw = (target_volume / anchor_volume.where(anchor_volume > 0)).clip(lo, hi)
        weight = anchor_volume / (anchor_volume + PARAMS["growth_tau"])
        growth = (weight * raw.fillna(net_growth) + (1.0 - weight) * net_growth)

        return pd.DataFrame({"series_id": series, "yhat": (anchor * growth).to_numpy()})

    def _forecast_current_month(self, ship, ship_month, cutoff, target_month, series):
        """Month-to-date shipments plus remaining days at a weekday-shaped rate."""
        days_left = int(cutoff.days_in_month) - int(cutoff.day)
        mtd = pd.Series(
            {sid: float(ship_month.get((sid, target_month), 0.0)) for sid in series},
            dtype="float64",
        )
        window_start = cutoff - pd.Timedelta(days=PARAMS["profile_days"] - 1)
        recent = ship.loc[ship["date"] >= window_start]
        if recent.empty or days_left == 0:
            return mtd

        dow = recent["date"].dt.dayofweek
        net_by_dow = recent.groupby(dow)["y"].mean()
        if float(net_by_dow.mean()) <= 0:
            return mtd
        net_shape = net_by_dow / net_by_dow.mean()

        n_days = int(recent["date"].nunique())
        total = recent.groupby("series_id")["y"].sum().reindex(series).fillna(0.0)
        daily_level = total / n_days
        by_dow = (
            recent.groupby(["series_id", dow])["y"].mean()
            .unstack(fill_value=0.0)
            .reindex(index=series, columns=net_shape.index)
            .fillna(0.0)
        )
        own_shape = by_dow.div(daily_level.where(daily_level > 0), axis=0).fillna(1.0)
        weight = (total / (total + PARAMS["shape_tau"])).to_numpy()[:, None]
        shape = weight * own_shape.to_numpy() + (1.0 - weight) * net_shape.to_numpy()[None, :]
        remaining = pd.Series(
            [(cutoff + pd.Timedelta(days=k)).dayofweek for k in range(1, days_left + 1)]
        ).value_counts().reindex(net_shape.index).fillna(0.0).to_numpy()
        projected = daily_level.to_numpy() * (shape * remaining[None, :]).sum(axis=1)
        return mtd + pd.Series(projected, index=series)
