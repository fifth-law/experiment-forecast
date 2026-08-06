"""Ascension/Pentecost cluster week-damping, on top of 008_xmas_per_series.

The May cutoffs oscillate (05-08 bias +0.16, 05-22 -0.11, 05-29 -0.19,
06-12 +0.16): the whole three-week holiday cluster runs below normal
volume (vacations depress demand on the non-holiday days too), so
forecasts INTO the cluster over-shoot, and forecasts FROM level windows
inside the cluster under-shoot the June recovery.

One mechanism over 008, applied in two places:
  - the weeks W0 (Ascension week), W1 (between), W2 (Pentecost week) get
    learned pooled damp factors on their non-special days:
        yhat = shape * level * damp[week]
    estimated per year against same-weekday clean-network values from the
    28 days before the cluster starts;
  - damp-week days inside the 14-day level window count as observations
    at y / damp[week] (weight shape[wd], since they are ordinary weekdays,
    just damped). Per 009's lesson deflation is only safe for near-1
    factors - these are ~0.9, so the imported drift is a few percent at
    most, unlike the 2-3x BF spike.
"""

import numpy as np
import pandas as pd
import holidays as holidays_pkg

PARAMS = {
    "kind": "ascension_weeks",
    "damp_weeks": ["asc_wk0", "asc_wk1", "asc_wk2"],
    "damp_clip": [0.5, 1.3],
    "series_mult_groups": ["bf", "xmas"],
    "series_mult_shrinkage_k": 500,
    "series_mult_clip": [0.2, 3.0],
    "bridge_days": ["ascension+1"],
    "shape_obs": 4,
    "recent_level_days": 14,
    "special_level_window_days": 28,
    "factor_clip": [0.0, 1.5],
    "bf_factor_clip": [0.0, 5.0],
    "bf_offsets": [-4, 3],
    "extra_special_days": ["12-24", "12-31", "06-05"],
    "xmas_window_days": [20, 21, 22, 23, 27, 28, 29, 30],
}

EXTRA_FIXED = {(12, 24): "xmas_eve", (12, 31): "nye", (6, 5): "constitution_day"}
XMAS_WINDOW_DAYS = (20, 21, 22, 23, 27, 28, 29, 30)
FACTOR_CLIP = (0.0, 1.5)
BF_FACTOR_CLIP = (0.0, 5.0)
BF_OFFSETS = range(-4, 4)  # Mon..Thu before BF, BF Friday, Sat, Sun, Cyber Monday
BF_SERIES_K = 500.0
BF_SERIES_CLIP = (0.2, 3.0)
DAMP_CLIP = (0.5, 1.3)
SPECIAL_LEVEL_WINDOW_DAYS = 28
RECENT_LEVEL_DAYS = 14
SHAPE_OBS = 4


def black_friday(year: int) -> pd.Timestamp:
    """Day after the 4th Thursday of November."""
    nov1 = pd.Timestamp(year=year, month=11, day=1)
    first_thursday = nov1 + pd.Timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thursday + pd.Timedelta(weeks=3, days=1)


def special_day_map(first_year: int, last_year: int) -> dict:
    """Timestamp -> special-day type name, covering [first_year, last_year]."""
    smap = {}
    for year in range(first_year, last_year + 1):
        for day, name in holidays_pkg.Denmark(years=year).items():
            smap[pd.Timestamp(day)] = name
            if name == "Kristi himmelfartsdag":
                smap.setdefault(pd.Timestamp(day) + pd.Timedelta(days=1), "ascension_bridge")
        for (month, day), name in EXTRA_FIXED.items():
            smap.setdefault(pd.Timestamp(year=year, month=month, day=day), name)
        bf = black_friday(year)
        for offset in BF_OFFSETS:
            smap.setdefault(bf + pd.Timedelta(days=offset), f"bf{offset:+d}")
        for day in XMAS_WINDOW_DAYS:
            smap.setdefault(pd.Timestamp(year=year, month=12, day=day), f"dec{day:02d}")
    return smap


def damp_week_map(first_year: int, last_year: int, smap: dict) -> dict:
    """Timestamp -> asc_wkN for non-special days of the 3-week cluster."""
    damp = {}
    for year in range(first_year, last_year + 1):
        ascension = next(
            pd.Timestamp(day)
            for day, name in sorted(holidays_pkg.Denmark(years=year).items())
            if name == "Kristi himmelfartsdag"
        )
        monday_w0 = ascension - pd.Timedelta(days=3)
        for week in range(3):
            for offset in range(7):
                day = monday_w0 + pd.Timedelta(days=7 * week + offset)
                if day not in smap:
                    damp[day] = f"asc_wk{week}"
    return damp


def _clip_for(name: str) -> tuple:
    return BF_FACTOR_CLIP if name.startswith("bf") else FACTOR_CLIP


XMAS_GROUP_NAMES = {"xmas_eve", "nye", "Juledag", "Anden juledag", "Nytårsdag"}


def _mult_group(name: str) -> str | None:
    """Series-multiplier group a special-day type belongs to, if any."""
    if name.startswith("bf"):
        return "bf"
    if name.startswith("dec") or name in XMAS_GROUP_NAMES:
        return "xmas"
    return None


class Forecaster:
    def fit_predict(self, history, cutoff, horizon, series_meta):
        cutoff = pd.Timestamp(cutoff)
        targets = pd.date_range(cutoff + pd.Timedelta(days=1), periods=horizon)
        first_year = history["date"].min().year
        smap = special_day_map(first_year, targets[-1].year)
        damp_map = damp_week_map(first_year, targets[-1].year, smap)

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

        # special-day factors: network volume on past occurrences vs the raw
        # clean-day level in the 28 days before
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
        factors = {
            name: float(np.clip(actual[name] / expected[name], *_clip_for(name)))
            for name in actual
        }

        # damp-week factors: cluster-week network volume vs same-weekday
        # clean values from the 28 days before that year's cluster start
        clean_net_weekday = clean_net.index.weekday
        damp_actual, damp_expected = {}, {}
        for day, wk_name in sorted(damp_map.items()):
            if day not in net.index:
                continue
            ascension_monday = day - pd.Timedelta(days=int((day.weekday()))) - pd.Timedelta(
                days=7 * int(wk_name[-1])
            )
            base = clean_net[
                (clean_net.index >= ascension_monday - pd.Timedelta(days=SPECIAL_LEVEL_WINDOW_DAYS))
                & (clean_net.index < ascension_monday)
                & (clean_net_weekday == day.weekday())
            ]
            if len(base) < 2 or base.mean() <= 0:
                continue
            damp_actual[wk_name] = damp_actual.get(wk_name, 0.0) + float(net[day])
            damp_expected[wk_name] = damp_expected.get(wk_name, 0.0) + float(base.mean())
        damp = {
            name: float(np.clip(damp_actual[name] / damp_expected[name], *DAMP_CLIP))
            for name in damp_actual
        }

        special_recent = clean[clean.index >= cutoff - pd.Timedelta(days=SPECIAL_LEVEL_WINDOW_DAYS)]
        special_level = (
            special_recent.mean().fillna(0.0) if len(special_recent) else pd.Series(0.0, index=wide.columns)
        )

        # per-series event multiplier per group: the series' own volume over
        # past group days vs its pooled-factor expectation, shrunk toward 1
        group_actual = {"bf": pd.Series(0.0, index=wide.columns), "xmas": pd.Series(0.0, index=wide.columns)}
        group_expected = {"bf": pd.Series(0.0, index=wide.columns), "xmas": pd.Series(0.0, index=wide.columns)}
        for day, name in sorted(smap.items()):
            group = _mult_group(name)
            if group is None or day not in wide.index or name not in factors:
                continue
            base_rows = clean[
                (clean.index < day)
                & (clean.index >= day - pd.Timedelta(days=SPECIAL_LEVEL_WINDOW_DAYS))
            ]
            if len(base_rows) < 10:
                continue
            group_actual[group] += wide.loc[day]
            group_expected[group] += base_rows.mean() * factors[name]
        mult = {
            g: ((group_actual[g] + BF_SERIES_K) / (group_expected[g] + BF_SERIES_K)).clip(*BF_SERIES_CLIP)
            for g in group_actual
        }

        # shape-deflated recent level over the last 14 calendar days; damp-week
        # days count at y / damp[week] (they are ordinary weekdays, just damped)
        num = pd.Series(0.0, index=wide.columns)
        den = pd.Series(0.0, index=wide.columns)
        window = wide[wide.index > cutoff - pd.Timedelta(days=RECENT_LEVEL_DAYS)]
        for day in window.index:
            if day in smap:
                continue
            wk_name = damp_map.get(day)
            damp_f = damp.get(wk_name, 1.0) if wk_name else 1.0
            num += window.loc[day] / damp_f
            den += shape[day.weekday()]
        level = (num / den).where(den > 0, 0.0).fillna(0.0)

        rows = []
        for target in targets:
            if target in smap:
                name = smap[target]
                fallback = 1.0 if name.startswith("bf") else float(np.clip(pooled_all, *FACTOR_CLIP))
                factor = factors.get(name, fallback)
                yhat = special_level * factor
                group = _mult_group(name)
                if group is not None:
                    yhat = yhat * mult[group]
            else:
                yhat = shape[target.weekday()] * level
                wk_name = damp_map.get(target)
                if wk_name is not None:
                    yhat = yhat * damp.get(wk_name, 1.0)
            for sid in wide.columns:
                rows.append((sid, target, float(yhat[sid])))
        return pd.DataFrame(rows, columns=["series_id", "date", "yhat"])
