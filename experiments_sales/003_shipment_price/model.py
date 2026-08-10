"""003_shipment_price — price x volume, using shipments as the leading indicator.

002 leaves nearly all of its error in the first third of the month, where there
is no accrual to complete yet. But shipments are visible the day they happen,
with no invoicing lag at all, so the volume behind a month's invoice can be known
long before the invoice exists.

Which volume a posting month bills is itself learned rather than assumed, because
it changed: through 2024 a month's invoices were mostly for the *previous*
month's shipments, by 2026 mostly for the same month's. The model picks the lag
L in {0, 1, 2} whose network revenue-per-shipment ratio is most stable across
recent settled months, then

    price(series)  = settled DKK / shipments, summed over the last PRICE_MONTHS
                     settled months (lagged by L), network price as fallback
    volume(series) = shipments of month (target - L); for L = 0 the month is still
                     running, so month-to-date plus remaining days at the trailing
                     daily rate
    yhat           = price * volume

No accrual information is used at all — this is the pure "does volume predict
the invoice?" test, to be blended with 002 rather than to stand alone.
"""

import pandas as pd

PARAMS = {
    "settle_days": 20,
    "price_months": 3,        # settled months pooled for the price estimate
    "lag_candidates": (0, 1, 2),
    "rate_days": 28,          # trailing window for the within-month shipment rate
    "min_shipments": 50,      # below this a series-level price is not trusted
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
        months = sorted(history["posting_month"].unique())
        settled = settled_months(months, cutoff, PARAMS["settle_days"])
        price_months = settled[-PARAMS["price_months"]:]

        if not price_months:
            return pd.DataFrame({"series_id": series, "yhat": [0.0] * len(series)})

        # monthly shipments per series. The target month is partial by construction
        # (shipments only run to the cutoff), which is handled below for lag 0.
        ship = shipments.copy()
        ship["month"] = ship["date"].dt.to_period("M").astype(str)
        ship_month = ship.groupby(["series_id", "month"])["y"].sum()
        ship_net = ship.groupby("month")["y"].sum()

        revenue = history.groupby(["series_id", "posting_month"])["dkk"].sum()
        revenue_net = history.groupby("posting_month")["dkk"].sum()

        # pick the billing lag: the one whose network price is most stable
        best_lag, best_cv = PARAMS["lag_candidates"][0], float("inf")
        for lag in PARAMS["lag_candidates"]:
            ratios = []
            for m in price_months:
                vol = float(ship_net.get(shift_month(m, lag), 0.0))
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
                best_lag, best_cv = lag, cv
        lag = best_lag

        # price: pooled over the price window, per series and network-wide
        rev_sum: dict[str, float] = {}
        vol_sum: dict[str, float] = {}
        for m in price_months:
            src = shift_month(m, lag)
            for sid in series:
                rev_sum[sid] = rev_sum.get(sid, 0.0) + float(revenue.get((sid, m), 0.0))
                vol_sum[sid] = vol_sum.get(sid, 0.0) + float(ship_month.get((sid, src), 0.0))
        net_rev = sum(rev_sum.values())
        net_vol = sum(vol_sum.values())
        net_price = net_rev / net_vol if net_vol > 0 else 0.0

        # level fallback for series whose revenue is not shipment-driven
        level = (
            history.loc[history["posting_month"].isin(price_months)]
            .groupby("series_id")["dkk"]
            .sum()
            / len(price_months)
        )

        # target-month volume
        if lag >= 1:
            src_month = shift_month(target_month, lag)
            volume = {sid: float(ship_month.get((sid, src_month), 0.0)) for sid in series}
        else:
            day = int(cutoff.day)
            days_left = int(cutoff.days_in_month) - day
            window_start = cutoff - pd.Timedelta(days=PARAMS["rate_days"] - 1)
            recent = ship.loc[ship["date"] >= window_start]
            rate = recent.groupby("series_id")["y"].sum() / PARAMS["rate_days"]
            volume = {
                sid: float(ship_month.get((sid, target_month), 0.0))
                + float(rate.get(sid, 0.0)) * days_left
                for sid in series
            }

        yhat = []
        for sid in series:
            if vol_sum.get(sid, 0.0) >= PARAMS["min_shipments"] and rev_sum.get(sid, 0.0) != 0:
                price = rev_sum[sid] / vol_sum[sid]
            elif volume[sid] > 0:
                price = net_price
            else:
                yhat.append(float(level.get(sid, 0.0)))
                continue
            yhat.append(price * volume[sid])
        return pd.DataFrame({"series_id": series, "yhat": yhat})
