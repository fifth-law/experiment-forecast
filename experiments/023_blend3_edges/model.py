"""Champion blend with edge-v2 GBM heads.

022 showed edge-distance features genuinely fix the Easter/Ascension
edge cutoffs but re-poison January when the xmas-window specials are in
the distance set. The v2 head (lgbm_edges2.py in this folder) keeps the
features and excludes Dec 20-31 + Jan 1 from the distance set.

Blend identical to 021:
    1/3 * 015_jan_week1 + 1/3 * edges2 (L1) + 1/3 * edges2 (L2)
"""

import importlib.util
import os

import pandas as pd

PARAMS = {
    "kind": "blend3_edges",
    "components": ["015_jan_week1", "lgbm_edges2 (l1)", "lgbm_edges2 (l2 objective)"],
    "weights": [1 / 3, 1 / 3, 1 / 3],
    "edge_distance_set": "specials minus xmas window",
}

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(alias: str, path: str):
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_hand = _load("exp015_jan_week1", os.path.join(HERE, "..", "015_jan_week1", "model.py"))
_gbm_l1 = _load("edges2_l1", os.path.join(HERE, "lgbm_edges2.py"))
_gbm_l2 = _load("edges2_l2", os.path.join(HERE, "lgbm_edges2.py"))
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
