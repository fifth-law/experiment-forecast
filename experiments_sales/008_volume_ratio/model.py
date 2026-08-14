"""008_volume_ratio — previous months + shipments booked to date. No invoice accrual.

This is the model family the owner asked for: the only inputs are (a) invoiced
totals of *previous* months and (b) shipments booked so far. It deliberately
ignores the current month's invoice-line accrual, which 002/005/006/007 lean on.

    price(series)  = shrunk DKK per shipment over the reference months
                     (sum revenue + tau * network price) / (sum shipments + tau)
                     — an empirical-Bayes ratio, so a small customer borrows the
                     network price instead of trusting three noisy months
    volume(series) = shipments of the month this posting month bills. The billing
                     lag L is learned from the stability of the network
                     revenue-per-shipment ratio: with L >= 1 the driver is already
                     complete on the 1st, with L = 0 it is month-to-date shipments
                     plus the remaining days at a weekday-shaped daily rate
    yhat           = price * volume, falling back to the recent invoiced level for
                     series whose revenue is not shipment-driven at all

Fixes over 003, which was the same idea done crudely: a hard 50-shipment cutoff
instead of shrinkage, a 3-month price window, and a flat daily rate with no
weekday shape for the remaining days.
"""

import pandas as pd

PARAMS = {
    "mature_days": 150,          # a month this old is certainly complete
    "settle_quantile": 0.99,
    "settle_sample": 12,
    "settle_floor": 30,
    "price_months": 6,           # settled months pooled for the price ratio
    "price_tau": 2000.0,         # shipments at which a series price is half-trusted
    "lag_candidates": (0, 1, 2),
    "lag_months": 6,             # settled months used to choose the billing lag
    "profile_days": 56,          # trailing window for level + weekday shape
    "shape_tau": 500.0,          # shipments at which a series weekday shape is half-trusted
    "level_months": 3,           # fallback anchor for non-shipment-driven series
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

        revenue = history.groupby(["series_id", "posting_month"])["dkk"].sum()
        revenue_net = history.groupby("posting_month")["dkk"].sum()

        ship = shipments.copy()
        ship["month"] = ship["date"].dt.to_period("M").astype(str)
        ship_month = ship.groupby(["series_id", "month"])["y"].sum()
        ship_net = ship.groupby("month")["y"].sum()

        # --- which month does a posting month bill? ---
        best_lag, best_cv = PARAMS["lag_candidates"][0], float("inf")
        for candidate in PARAMS["lag_candidates"]:
            ratios = []
            for m in settled[-PARAMS["lag_months"]:]:
                vol = float(ship_net.get(shift_month(m, candidate), 0.0))
                if vol > 0:
                    ratios.append(float(revenue_net.get(m, 0.0)) / vol)
            if len(ratios) < 2:
                continue
            mean = sum(ratios) / len(ratios)
            if mean <= 0:
                continue
            cv = (sum((r - mean) ** 2 for r in ratios) / len(ratios)) ** 0.5 / mean
            if cv < best_cv:
                best_lag, best_cv = candidate, cv
        lag = best_lag

        # --- price: shrunk DKK per shipment over the reference months ---
        price_months = settled[-PARAMS["price_months"]:]
        rev_sum: dict[str, float] = {}
        vol_sum: dict[str, float] = {}
        for m in price_months:
            src = shift_month(m, lag)
            for sid in series:
                rev_sum[sid] = rev_sum.get(sid, 0.0) + float(revenue.get((sid, m), 0.0))
                vol_sum[sid] = vol_sum.get(sid, 0.0) + float(ship_month.get((sid, src), 0.0))
        net_vol = sum(vol_sum.values())
        net_price = sum(rev_sum.values()) / net_vol if net_vol > 0 else 0.0
        tau = PARAMS["price_tau"] * len(price_months)
        price = {
            sid: (rev_sum[sid] + tau * net_price) / (vol_sum[sid] + tau)
            for sid in series
        }

        # --- volume of the billed month ---
        if lag >= 1:
            src_month = shift_month(target_month, lag)
            volume = {sid: float(ship_month.get((sid, src_month), 0.0)) for sid in series}
        else:
            volume = self._forecast_current_month(ship, ship_month, cutoff, target_month, series)

        level = (
            history.loc[history["posting_month"].isin(settled[-PARAMS["level_months"]:])]
            .groupby("series_id")["dkk"]
            .sum()
            / len(settled[-PARAMS["level_months"]:])
        )

        yhat = []
        for sid in series:
            if vol_sum.get(sid, 0.0) > 0 or volume[sid] > 0:
                yhat.append(price[sid] * volume[sid])
            else:
                # revenue with no shipments behind it (fees, pallets, corrections)
                yhat.append(float(level.get(sid, 0.0)))
        return pd.DataFrame({"series_id": series, "yhat": yhat})

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
            return mtd.to_dict()

        dow = recent["date"].dt.dayofweek
        net_by_dow = recent.groupby(dow)["y"].mean()
        if float(net_by_dow.mean()) <= 0:
            return mtd.to_dict()
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

        # own weekday shape, shrunk towards the network shape by series volume
        own_shape = by_dow.div(daily_level.where(daily_level > 0), axis=0).fillna(1.0)
        weight = (total / (total + PARAMS["shape_tau"])).to_numpy()[:, None]
        shape = weight * own_shape.to_numpy() + (1.0 - weight) * net_shape.to_numpy()[None, :]

        # how many of each weekday are left in the month
        remaining = pd.Series(
            [(cutoff + pd.Timedelta(days=k)).dayofweek for k in range(1, days_left + 1)]
        ).value_counts().reindex(net_shape.index).fillna(0.0).to_numpy()

        projected = daily_level.to_numpy() * (shape * remaining[None, :]).sum(axis=1)
        return (mtd + pd.Series(projected, index=series)).to_dict()
