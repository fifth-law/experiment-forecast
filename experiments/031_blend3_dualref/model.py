"""Burstiness-aware per-series blend weights (stage3).

Stage3's error mass concentrates in a few erratic high-volume customers
(c_387459: wMAPE 0.65, bias -0.07, ~10% of all stage3 error alone).
Near-zero bias with huge daily error means spike-timing volatility, and
for an absolute-error metric the optimal point forecast of a bursty
distribution is its conditional MEDIAN - which only the L1 GBM head
provides. The equal-thirds blend dilutes it with two mean-calibrated
heads on exactly the series where that costs most.

One change over 027: blend weights become per-series functions of a
history-measured burstiness statistic

    rho = median(y) / mean(y)   over clean days in the last 84 days

    rho >= 0.75 (smooth)  -> equal thirds (unchanged)
    rho <= 0.25 (bursty)  -> (0.15, 0.70, 0.15) toward the L1 head
    linear in between.

Constants are mechanism-derived, not fitted to the eval: a fully bursty
series wants the median forecaster, a smooth one keeps the diversity
gain. Components byte-identical to 027.
"""

import importlib.util
import os

import pandas as pd

PARAMS = {
    "kind": "blend3_dualref",
    "gbm_train_refs": "Mondays + Thursdays",
    "components": ["hand_step (027)", "lgbm_edges2 (l1)", "lgbm_edges2 (l2 objective)"],
    "weights": "per-series: equal thirds -> (0.15, 0.70, 0.15) as rho falls 0.75 -> 0.25",
    "burstiness_window_days": 84,
}

HERE = os.path.dirname(os.path.abspath(__file__))

RHO_HIGH = 0.75
RHO_LOW = 0.25
L1_MAX_WEIGHT = 0.70
BURSTINESS_WINDOW_DAYS = 84


def _load(alias: str, path: str):
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_hand = _load("hand_step", os.path.join(HERE, "hand_step.py"))
_gbm_l1 = _load("edges2cap_l1", os.path.join(HERE, "lgbm_edges2.py"))
_gbm_l2 = _load("edges2cap_l2", os.path.join(HERE, "lgbm_edges2.py"))
_gbm_l2.LGB_PARAMS = {**_gbm_l2.LGB_PARAMS, "objective": "regression"}


def _indexed(frame: pd.DataFrame) -> pd.Series:
    frame = frame.assign(series_id=frame["series_id"].astype(str))
    return frame.set_index(["series_id", "date"])["yhat"]


class Forecaster:
    def fit_predict(self, history, cutoff, horizon, series_meta):
        cutoff = pd.Timestamp(cutoff)
        hand = _indexed(_hand.Forecaster().fit_predict(history, cutoff, horizon, series_meta))
        l1 = _indexed(_gbm_l1.Forecaster().fit_predict(history, cutoff, horizon, series_meta))
        l2 = _indexed(_gbm_l2.Forecaster().fit_predict(history, cutoff, horizon, series_meta))

        targets = pd.date_range(cutoff + pd.Timedelta(days=1), periods=horizon)
        smap = _hand.special_day_map(history["date"].min().year, targets[-1].year)
        recent = history[
            (history["date"] > cutoff - pd.Timedelta(days=BURSTINESS_WINDOW_DAYS))
            & (history["date"] <= cutoff)
            & (~history["date"].isin(smap.keys()))
        ]
        stats = recent.groupby("series_id", observed=True)["y"].agg(["median", "mean"])
        rho = (stats["median"] / stats["mean"]).where(stats["mean"] > 0, 1.0).fillna(1.0)
        rho.index = rho.index.astype(str)

        s = ((RHO_HIGH - rho) / (RHO_HIGH - RHO_LOW)).clip(0.0, 1.0)
        w_l1 = 1.0 / 3.0 + s * (L1_MAX_WEIGHT - 1.0 / 3.0)
        w_other = (1.0 - w_l1) / 2.0

        series_level = hand.index.get_level_values(0)
        wl1 = w_l1.reindex(series_level).fillna(1.0 / 3.0).to_numpy()
        wot = w_other.reindex(series_level).fillna(1.0 / 3.0).to_numpy()
        yhat = hand * wot + l1 * wl1 + l2 * wot
        return yhat.rename("yhat").reset_index()
