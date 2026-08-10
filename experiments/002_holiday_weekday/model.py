"""Holiday-aware weekday profile.

Two changes over 001_weekday_profile, both driven by the Danish calendar
(timeless knowledge, allowed):

1. The trailing per-weekday profile is built from the last 4 *clean*
   same-weekday observations — special days are skipped instead of being
   averaged in, so a holiday no longer drags the following weeks down.
2. Special target dates are predicted as `factor[type] * recent_level`,
   where the factor is estimated from the history frame at each cutoff:
   network volume on past occurrences of that special-day type divided by
   the clean-day network level just before them. Level-relative (not
   weekday-relative) so fixed-date specials that migrate across weekdays
   (Christmas, New Year) stay consistent year over year.

Special days = official DK public holidays (`holidays` package, which also
knows Store Bededag was abolished from 2024) + Dec 24, Dec 31 and Jun 5
(Constitution Day) — warehouses close on those even though they are not
official. Their factors are learned, so a special day that turns out to be
normal costs nothing.
"""

import numpy as np
import pandas as pd
import holidays as holidays_pkg

PARAMS = {
    "kind": "holiday_weekday",
    "window_weeks": 4,
    "level_window_days": 28,
    "factor_clip": [0.0, 1.5],
    "extra_special_days": ["12-24", "12-31", "06-05"],
}

EXTRA_FIXED = {(12, 24): "xmas_eve", (12, 31): "nye", (6, 5): "constitution_day"}
FACTOR_CLIP = (0.0, 1.5)
LEVEL_WINDOW_DAYS = 28
PROFILE_OBS = 4


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

        # 1) per-weekday profile: mean of last PROFILE_OBS clean observations
        profile = {}
        for wd in range(7):
            block = clean[clean_weekday == wd].tail(PROFILE_OBS)
            profile[wd] = block.mean().fillna(0.0) if len(block) else pd.Series(0.0, index=wide.columns)

        # 2) pooled factor per special-day type: actual network volume on past
        #    occurrences vs the clean-day network level in the 28 days before
        net = wide.sum(axis=1)
        clean_net = net[~special_mask]
        actual, expected = {}, {}
        for day, name in sorted(smap.items()):
            if day not in net.index:
                continue
            base = clean_net[(clean_net.index < day) & (clean_net.index >= day - pd.Timedelta(days=LEVEL_WINDOW_DAYS))]
            if len(base) < 10 or base.mean() <= 0:
                continue
            actual[name] = actual.get(name, 0.0) + float(net[day])
            expected[name] = expected.get(name, 0.0) + float(base.mean())
        pooled_all = sum(actual.values()) / sum(expected.values()) if expected else 0.5
        pooled_all = float(np.clip(pooled_all, *FACTOR_CLIP))
        factors = {
            name: float(np.clip(actual[name] / expected[name], *FACTOR_CLIP)) for name in actual
        }

        # per-series clean-day level over the last 28 days before the cutoff
        recent = clean[clean.index >= cutoff - pd.Timedelta(days=LEVEL_WINDOW_DAYS)]
        level = recent.mean().fillna(0.0) if len(recent) else pd.Series(0.0, index=wide.columns)

        rows = []
        for target in targets:
            if target in smap:
                factor = factors.get(smap[target], pooled_all)
                yhat = level * factor
            else:
                yhat = profile[target.weekday()]
            for sid in wide.columns:
                rows.append((sid, target, float(yhat[sid])))
        return pd.DataFrame(rows, columns=["series_id", "date", "yhat"])
