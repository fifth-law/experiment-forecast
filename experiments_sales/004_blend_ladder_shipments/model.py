"""004_blend_ladder_shipments — 002's completion with 003's anchor.

002 and 003 fail in opposite halves of the month: the chain ladder has nothing to
complete on the 1st, and price x volume cannot compete with a nearly fully accrued
month on the 30th. This is 002 with exactly one change — the fallback anchor is
003's shipment-driven price x volume estimate instead of the mean of recent
settled months:

    yhat = f(d) * (mtd / f(d))  +  (1 - f(d)) * price(series) * volume(series)

so the forecast starts the month as a volume-driven estimate and ends it as a
completed accrual, with the crossover set by the measured development curve
rather than a tuned date.
"""

import pandas as pd

PARAMS = {
    "settle_days": 20,
    "curve_months": 6,        # settled months pooled for the development curve
    "price_months": 3,        # settled months pooled for the price estimate
    "lag_candidates": (0, 1, 2),
    "rate_days": 28,
    "min_shipments": 50,
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

        # --- completion factor at this day of month (002) ---
        curve = settled[-PARAMS["curve_months"]:]
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

        # --- shipment-driven anchor (003) ---
        price_months = settled[-PARAMS["price_months"]:]
        ship = shipments.copy()
        ship["month"] = ship["date"].dt.to_period("M").astype(str)
        ship_month = ship.groupby(["series_id", "month"])["y"].sum()
        ship_net = ship.groupby("month")["y"].sum()
        revenue = history.groupby(["series_id", "posting_month"])["dkk"].sum()
        revenue_net = history.groupby("posting_month")["dkk"].sum()

        best_lag, best_cv = PARAMS["lag_candidates"][0], float("inf")
        for lag_candidate in PARAMS["lag_candidates"]:
            ratios = []
            for m in price_months:
                vol = float(ship_net.get(shift_month(m, lag_candidate), 0.0))
                rev = float(revenue_net.get(m, 0.0))
                if vol > 0:
                    ratios.append(rev / vol)
            if len(ratios) < 2:
                continue
            mean = sum(ratios) / len(ratios)
            if mean <= 0:
                continue
            var = sum((r - mean) ** 2 for r in ratios) / len(ratios)
            cv = var ** 0.5 / mean
            if cv < best_cv:
                best_lag, best_cv = lag_candidate, cv
        lag = best_lag

        rev_sum: dict[str, float] = {}
        vol_sum: dict[str, float] = {}
        for m in price_months:
            src = shift_month(m, lag)
            for sid in series:
                rev_sum[sid] = rev_sum.get(sid, 0.0) + float(revenue.get((sid, m), 0.0))
                vol_sum[sid] = vol_sum.get(sid, 0.0) + float(ship_month.get((sid, src), 0.0))
        net_vol = sum(vol_sum.values())
        net_price = sum(rev_sum.values()) / net_vol if net_vol > 0 else 0.0
        level = (
            history.loc[history["posting_month"].isin(price_months)]
            .groupby("series_id")["dkk"]
            .sum()
            / len(price_months)
        )

        if lag >= 1:
            src_month = shift_month(target_month, lag)
            volume = {sid: float(ship_month.get((sid, src_month), 0.0)) for sid in series}
        else:
            days_left = int(cutoff.days_in_month) - day
            window_start = cutoff - pd.Timedelta(days=PARAMS["rate_days"] - 1)
            recent = ship.loc[ship["date"] >= window_start]
            rate = recent.groupby("series_id")["y"].sum() / PARAMS["rate_days"]
            volume = {
                sid: float(ship_month.get((sid, target_month), 0.0))
                + float(rate.get(sid, 0.0)) * days_left
                for sid in series
            }

        weight = frac ** PARAMS["weight_power"]
        yhat = []
        for sid in series:
            if vol_sum.get(sid, 0.0) >= PARAMS["min_shipments"] and rev_sum.get(sid, 0.0) != 0:
                anchor = rev_sum[sid] / vol_sum[sid] * volume[sid]
            elif volume[sid] > 0:
                anchor = net_price * volume[sid]
            else:
                anchor = float(level.get(sid, 0.0))
            if frac >= PARAMS["min_visible_frac"]:
                extrapolated = float(mtd.get(sid, 0.0)) / frac
                yhat.append(weight * extrapolated + (1.0 - weight) * anchor)
            else:
                yhat.append(anchor)
        return pd.DataFrame({"series_id": series, "yhat": yhat})
