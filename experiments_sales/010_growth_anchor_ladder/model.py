"""010_growth_anchor_ladder — 009's anchor inside 007's completion curve.

The day-of-month split is unambiguous: on stage3, 009 (previous months + shipments
to date) beats 007 over days 1-10 (0.2981 vs 0.3433) and loses badly over days
21-end (0.2929 vs 0.1626). Shipments know the month before the invoices exist; the
invoices know it better once they do.

So: 007 unchanged, except the anchor it falls back to early in the month is 009's
level x shipment-growth estimate instead of a flat mean of recent months.

    yhat = f(d) * (mtd / f(d)) + (1 - f(d)) * anchor_009(series)

This is structurally what 004 tried and failed at. The difference is bias: 004's
anchor (003's price x volume) was +5.2% biased and compounded with the accrual's
positive bias, whereas 009 is near-unbiased (stage1 +0.1%, stage3 -2.4%), so the
blend should behave.

NOTE this model uses the current month's invoice accrual, so it is *not* in the
"previous months + shipments only" family that 008/009 belong to. 009 is the best
model in that family.
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
    "growth_clip": (0.6, 1.6),
    "growth_tau": 3000.0,
    "profile_days": 56,
    "shape_tau": 500.0,
    "min_visible_frac": 0.02,
    "weight_power": 1.0,
}

_MONTH_START: dict[str, pd.Timestamp] = {}


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
        anchors = self._growth_anchor(
            history, shipments, cutoff, target_month, series, settled)

        weight = frac ** PARAMS["weight_power"]
        yhat = []
        for sid in series:
            anchor = float(anchors.get(sid, 0.0))
            if frac >= PARAMS["min_visible_frac"]:
                extrapolated = float(mtd.get(sid, 0.0)) / frac
                yhat.append(weight * extrapolated + (1.0 - weight) * anchor)
            else:
                yhat.append(anchor)
        return pd.DataFrame({"series_id": series, "yhat": yhat})

    def _growth_anchor(self, history, shipments, cutoff, target_month, series, settled):
        """009's estimate: last settled months' level, moved by shipment growth."""
        anchor_months = settled[-PARAMS["level_months"]:]
        anchor = (
            history.loc[history["posting_month"].isin(anchor_months)]
            .groupby("series_id")["dkk"].sum().reindex(series).fillna(0.0)
            / len(anchor_months)
        )
        ship = shipments.copy()
        ship["month"] = ship["date"].dt.to_period("M").astype(str)
        ship_month = ship.groupby(["series_id", "month"])["y"].sum()

        def month_volume(month):
            return pd.Series(
                {sid: float(ship_month.get((sid, month), 0.0)) for sid in series},
                dtype="float64",
            )

        current = self._forecast_current_month(ship, ship_month, cutoff, target_month, series)
        target_volume = current + month_volume(shift_month(target_month, 1))
        anchor_volume = sum(
            month_volume(m) + month_volume(shift_month(m, 1)) for m in anchor_months
        ) / len(anchor_months)

        lo, hi = PARAMS["growth_clip"]
        net_growth = (
            float(target_volume.sum()) / float(anchor_volume.sum())
            if float(anchor_volume.sum()) > 0 else 1.0
        )
        net_growth = min(max(net_growth, lo), hi)
        raw = (target_volume / anchor_volume.where(anchor_volume > 0)).clip(lo, hi)
        weight = anchor_volume / (anchor_volume + PARAMS["growth_tau"])
        growth = weight * raw.fillna(net_growth) + (1.0 - weight) * net_growth
        return anchor * growth
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
