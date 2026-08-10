"""Weekday shape x recent level.

One change over 002_holiday_weekday, which predicted normal days directly
from the last-4-clean-observations weekday profile: that profile mixes
weekday SHAPE with the volume LEVEL of whatever weeks the observations came
from. Around the year boundary the two diverge badly — at a January cutoff
the clean profile reaches back into December peak weeks and over-forecasts
the whole month (002's January cutoffs ran bias +0.16 to +0.23).

Here the profile is split:
  shape[s, wd]  = last-4-clean-obs weekday profile, normalised to mean 1
                  across the 7 weekdays (weekday shape is stable across
                  volume regimes);
  level[s]      = shape-deflated mean of the last 14 calendar days' clean
                  observations (sum y / sum shape over those days, so a
                  window with punched-out holidays stays unbiased);
  yhat(normal)  = shape * level.

Special-day handling is byte-for-byte the semantics of 002: skip specials
from all clean windows, predict them as learned per-type factors x the
raw 28-day clean level (factors are estimated against that same raw level
in past years, so the convention is self-consistent).
"""

import numpy as np
import pandas as pd
import holidays as holidays_pkg

PARAMS = {
    "kind": "shape_level",
    "shape_obs": 4,
    "recent_level_days": 14,
    "special_level_window_days": 28,
    "factor_clip": [0.0, 1.5],
    "extra_special_days": ["12-24", "12-31", "06-05"],
}

EXTRA_FIXED = {(12, 24): "xmas_eve", (12, 31): "nye", (6, 5): "constitution_day"}
FACTOR_CLIP = (0.0, 1.5)
SPECIAL_LEVEL_WINDOW_DAYS = 28
RECENT_LEVEL_DAYS = 14
SHAPE_OBS = 4


def special_day_map(first_year: int, last_year: int) -> dict:
    """Timestamp -> special-day type name, covering [first_year, last_year]."""
    smap = {}
    for year in range(first_year, last_year + 1):
        for day, name in holidays_pkg.Denmark(years=year).items():
            smap[pd.Timestamp(day)] = name
        for (month, day), name in EXTRA_FIXED.items():
            smap.setdefault(pd.Timestamp(year=year, month=month, day=day), name)
    return smap


class Forecaster:
    def fit_predict(self, history, cutoff, horizon, series_meta):
        cutoff = pd.Timestamp(cutoff)
        targets = pd.date_range(cutoff + pd.Timedelta(days=1), periods=horizon)
        smap = special_day_map(history["date"].min().year, targets[-1].year)

        wide = (
            history.pivot_table(index="date", columns="series_id", values="y", aggfunc="sum", observed=True)
            .sort_index()
        )
        special_mask = wide.index.isin(smap.keys())
        clean = wide[~special_mask]
        clean_weekday = clean.index.weekday

        # weekday shape: last-4-clean-obs profile, normalised to mean 1 per series
        profile = pd.DataFrame(
            {wd: clean[clean_weekday == wd].tail(SHAPE_OBS).mean() for wd in range(7)}
        ).fillna(0.0)
        shape = profile.div(profile.mean(axis=1), axis=0).fillna(0.0)

        # shape-deflated recent level over the last 14 calendar days
        recent = clean[clean.index > cutoff - pd.Timedelta(days=RECENT_LEVEL_DAYS)]
        if len(recent):
            num = recent.sum(axis=0)
            den = shape[list(recent.index.weekday)].sum(axis=1)
            level = (num / den).where(den > 0, 0.0).fillna(0.0)
        else:
            level = pd.Series(0.0, index=wide.columns)

        # special-day factors, identical semantics to 002: network volume on
        # past occurrences vs the raw clean-day level in the 28 days before
        net = wide.sum(axis=1)
        clean_net = net[~special_mask]
        actual, expected = {}, {}
        for day, name in sorted(smap.items()):
            if day not in net.index:
                continue
            base = clean_net[
                (clean_net.index < day)
                & (clean_net.index >= day - pd.Timedelta(days=SPECIAL_LEVEL_WINDOW_DAYS))
            ]
            if len(base) < 10 or base.mean() <= 0:
                continue
            actual[name] = actual.get(name, 0.0) + float(net[day])
            expected[name] = expected.get(name, 0.0) + float(base.mean())
        pooled_all = sum(actual.values()) / sum(expected.values()) if expected else 0.5
        pooled_all = float(np.clip(pooled_all, *FACTOR_CLIP))
        factors = {
            name: float(np.clip(actual[name] / expected[name], *FACTOR_CLIP)) for name in actual
        }

        special_recent = clean[clean.index >= cutoff - pd.Timedelta(days=SPECIAL_LEVEL_WINDOW_DAYS)]
        special_level = (
            special_recent.mean().fillna(0.0) if len(special_recent) else pd.Series(0.0, index=wide.columns)
        )

        rows = []
        for target in targets:
            if target in smap:
                factor = factors.get(smap[target], pooled_all)
                yhat = special_level * factor
            else:
                yhat = shape[target.weekday()] * level
            for sid in wide.columns:
                rows.append((sid, target, float(yhat[sid])))
        return pd.DataFrame(rows, columns=["series_id", "date", "yhat"])
