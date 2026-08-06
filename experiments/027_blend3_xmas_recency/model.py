"""Champion blend with a step-switch hand head (stage2 opener).

Stage2's dominant miss is non-calendar: onboarding ramps, churn and
migrations produce step changes (Sep-Oct 2024 cutoffs alternate biases
±0.11..±0.27; c_387459 at 0.73). 016 showed CONTINUOUS trend
extrapolation drowns in noise; a step SWITCH only fires on sustained
~20%+ weekly moves, where averaging across the break is guaranteed
wrong by half the step.

hand_step.py = 015 with one change: the 14-day level snaps to the
recent-week level when |log(L7/Lprev7)| > 0.18. GBM heads identical to
the 024 champion.

    1/3 * hand_step + 1/3 * lgbm_edges2 (L1) + 1/3 * lgbm_edges2 (L2)
"""

import importlib.util
import os

import pandas as pd

PARAMS = {
    "kind": "blend3_xmas_recency",
    "recency_scope": "year-boundary responses only, hand head only",
    "components": ["hand_step (015 + step-switch)", "lgbm_edges2 (l1)", "lgbm_edges2 (l2 objective)"],
    "weights": [1 / 3, 1 / 3, 1 / 3],
    "step_tau": 0.18,
}

HERE = os.path.dirname(os.path.abspath(__file__))


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
        parts = [
            _indexed(_hand.Forecaster().fit_predict(history, cutoff, horizon, series_meta)),
            _indexed(_gbm_l1.Forecaster().fit_predict(history, cutoff, horizon, series_meta)),
            _indexed(_gbm_l2.Forecaster().fit_predict(history, cutoff, horizon, series_meta)),
        ]
        yhat = sum(parts) / len(parts)
        return yhat.rename("yhat").reset_index()
