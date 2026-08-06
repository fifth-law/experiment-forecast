"""Weekday-profile baseline: mean of the last 4 observations per weekday.

For each series and each target weekday, average the 4 most recent
observations of that weekday at or before the cutoff. Smooths single-week
noise that trips seasonal naive, still blind to trend and holidays.
"""

import pandas as pd

PARAMS = {"kind": "weekday_profile", "window_weeks": 4}


class Forecaster:
    def fit_predict(self, history, cutoff, horizon, series_meta):
        recent = history[history["date"] > cutoff - pd.Timedelta(days=7 * 6)].copy()
        recent["weekday"] = recent["date"].dt.weekday
        profile = (
            recent.sort_values("date")
            .groupby(["series_id", "weekday"], observed=True)["y"]
            .apply(lambda s: s.tail(4).mean())
        )

        series_ids = sorted(history["series_id"].unique())
        targets = pd.date_range(cutoff + pd.Timedelta(days=1), periods=horizon)
        rows = []
        for target in targets:
            wd = target.weekday()
            for sid in series_ids:
                rows.append((sid, target, float(profile.get((sid, wd), 0.0))))
        return pd.DataFrame(rows, columns=["series_id", "date", "yhat"])
