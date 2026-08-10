"""Equal-thirds blend: hand stack + L1 GBM + L2 GBM.

018 proved the families' residuals are substantially uncorrelated. The
cheapest additional diversity is a mean-calibrated GBM: same features and
training rows as 017 but objective L2, so it predicts conditional means
instead of medians (network-friendly, opposite bias direction to the L1
head). Three components, equal weights - blend weights are deliberately
never tuned on the eval.

The L2 variant is created by loading a fresh copy of the frozen 017
module and overriding its LGB_PARAMS objective in memory; the frozen
file itself is untouched.
"""

import importlib.util
import os

import pandas as pd

PARAMS = {
    "kind": "blend3",
    "components": ["015_jan_week1", "017_lgbm_global (l1)", "017_lgbm_global (l2 objective)"],
    "weights": [1 / 3, 1 / 3, 1 / 3],
}

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(alias: str, folder: str):
    path = os.path.join(HERE, "..", folder, "model.py")
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_hand = _load("exp015_jan_week1", "015_jan_week1")
_gbm_l1 = _load("exp017_lgbm_l1", "017_lgbm_global")
_gbm_l2 = _load("exp017_lgbm_l2", "017_lgbm_global")
_gbm_l2.LGB_PARAMS = {**_gbm_l2.LGB_PARAMS, "objective": "regression"}


def _indexed(frame: pd.DataFrame) -> pd.Series:
    frame = frame.assign(series_id=frame["series_id"].astype(str))
    return frame.set_index(["series_id", "date"])["yhat"]


class Forecaster:
    def fit_predict(self, history, cutoff, horizon, series_meta):
        parts = [
            _indexed(_hand.Forecaster().fit_predict(history, cutoff, horizon, series_meta)),
            _indexed(_gbm_l1.Forecaster().fit_predict(history, cutoff, horizon, series_meta)),
            _indexed(_gbm_l2.Forecaster().fit_predict(history, cutoff, horizon, series_meta)),
        ]
        yhat = sum(parts) / len(parts)
        return yhat.rename("yhat").reset_index()
