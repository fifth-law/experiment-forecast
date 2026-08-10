"""50/50 blend of the hand stack (015) and the global GBM (017).

The two best models have differently shaped residuals: 015 is a
network-calibrated multiplicative factor stack (bias ~0, strong on
aggregates, composition-blind), 017 is a per-cutoff LightGBM chasing
conditional medians (bias -5.5%, strong on interactions and long leads).
Averaging differently-wrong forecasts is the oldest variance reduction
there is; the blend should also pull 017's under-forecast halfway back.

Implementation: loads the two frozen experiment modules by path (past
experiments are immutable per the loop protocol, so this is
reproducible) and averages their yhat per (series, date). No other
logic.
"""

import importlib.util
import os

import pandas as pd

PARAMS = {"kind": "blend", "components": ["015_jan_week1", "017_lgbm_global"], "weights": [0.5, 0.5]}

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(alias: str, folder: str):
    path = os.path.join(HERE, "..", folder, "model.py")
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_hand = _load("exp015_jan_week1", "015_jan_week1")
_gbm = _load("exp017_lgbm_global", "017_lgbm_global")


class Forecaster:
    def fit_predict(self, history, cutoff, horizon, series_meta):
        a = _hand.Forecaster().fit_predict(history, cutoff, horizon, series_meta)
        b = _gbm.Forecaster().fit_predict(history, cutoff, horizon, series_meta)
        a = a.assign(series_id=a["series_id"].astype(str)).set_index(["series_id", "date"])
        b = b.assign(series_id=b["series_id"].astype(str)).set_index(["series_id", "date"])
        yhat = 0.5 * a["yhat"] + 0.5 * b["yhat"]
        return yhat.rename("yhat").reset_index()
