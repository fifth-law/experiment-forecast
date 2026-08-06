"""Seasonal naive baseline: repeat the most recent observed same weekday.

For target date t: yhat(t) = y(t - 7) if t - 7 <= cutoff else y(t - 14).
With a 14-day horizon both cases stay inside observed history. This is the
floor every real model must beat.
"""

import pandas as pd

PARAMS = {"kind": "seasonal_naive", "season": 7}


class Forecaster:
    def fit_predict(self, history, cutoff, horizon, series_meta):
        lookup = history.set_index(["series_id", "date"])["y"]
        series_ids = sorted(history["series_id"].unique())
        targets = pd.date_range(cutoff + pd.Timedelta(days=1), periods=horizon)

        rows = []
        for target in targets:
            source = target - pd.Timedelta(days=7)
            if source > cutoff:
                source = target - pd.Timedelta(days=14)
            for sid in series_ids:
                rows.append((sid, target, float(lookup.get((sid, source), 0.0))))
        return pd.DataFrame(rows, columns=["series_id", "date", "yhat"])
