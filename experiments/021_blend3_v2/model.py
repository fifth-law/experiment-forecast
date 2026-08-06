"""Equal-thirds blend with the base-fixed GBM heads.

019 (equal thirds with the broken 017 heads) reached 0.2090; 020 fixed
the GBM's base zero-hole and alone reached 0.2050. Same blend hypothesis
as 018/019 - the hand stack and the two GBM calibrations are differently
wrong - now with the fixed heads:

    1/3 * 015_jan_week1 + 1/3 * 020 (L1) + 1/3 * 020 (L2 objective)
"""

import importlib.util
import os

import pandas as pd

PARAMS = {
    "kind": "blend3_v2",
    "components": ["015_jan_week1", "020_lgbm_basefix (l1)", "020_lgbm_basefix (l2 objective)"],
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
_gbm_l1 = _load("exp020_lgbm_l1", "020_lgbm_basefix")
_gbm_l2 = _load("exp020_lgbm_l2", "020_lgbm_basefix")
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
