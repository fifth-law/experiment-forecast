"""Per-series Black Friday multipliers, on top of 006_ascension_bridge.

004 fixed the aggregate BF bias (Nov-13/20 bias collapsed to ~0) but the
wMAPE there stayed at 0.39: a network-pooled factor forecasts every series
with the same relative spike, and customers differ wildly in BF appetite
(pure-play e-commerce triples; B2B-ish accounts barely move).

One change over 006: each series gets a BF multiplier — its own actual
volume over past BF weeks divided by its pooled-factor expectation, shrunk
toward 1 with k=500 shipments so thin series stay pooled while large
series go individual. Applied on bf-type days only:

    yhat = special_level * factor[offset] * mult[series]
"""

import numpy as np
import pandas as pd
import holidays as holidays_pkg

PARAMS = {
    "kind": "bf_per_series",
    "bf_series_shrinkage_k": 500,
    "bf_series_clip": [0.2, 3.0],
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
BF_SERIES_K = 500.0
BF_SERIES_CLIP = (0.2, 3.0)
BF_OFFSETS = range(-4, 4)  # Mon..Thu before BF, BF Friday, Sat, Sun, Cyber Monday
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


def _clip_for(name: str) -> tuple:
    return BF_FACTOR_CLIP if name.startswith("bf") else FACTOR_CLIP


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

        special_recent = clean[clean.index >= cutoff - pd.Timedelta(days=SPECIAL_LEVEL_WINDOW_DAYS)]
        special_level = (
            special_recent.mean().fillna(0.0) if len(special_recent) else pd.Series(0.0, index=wide.columns)
        )

        # per-series BF-week multiplier: the series' own volume over past BF
        # weeks vs its pooled-factor expectation, shrunk toward 1
        bf_actual = pd.Series(0.0, index=wide.columns)
        bf_expected = pd.Series(0.0, index=wide.columns)
        for day, name in sorted(smap.items()):
            if not name.startswith("bf") or day not in wide.index or name not in factors:
                continue
            base_rows = clean[
                (clean.index < day)
                & (clean.index >= day - pd.Timedelta(days=SPECIAL_LEVEL_WINDOW_DAYS))
            ]
            if len(base_rows) < 10:
                continue
            bf_actual += wide.loc[day]
            bf_expected += base_rows.mean() * factors[name]
        bf_mult = ((bf_actual + BF_SERIES_K) / (bf_expected + BF_SERIES_K)).clip(*BF_SERIES_CLIP)

        rows = []
        for target in targets:
            if target in smap:
                name = smap[target]
                fallback = 1.0 if name.startswith("bf") else float(np.clip(pooled_all, *FACTOR_CLIP))
                factor = factors.get(name, fallback)
                yhat = special_level * factor
                if name.startswith("bf"):
                    yhat = yhat * bf_mult
            else:
                yhat = shape[target.weekday()] * level
            for sid in wide.columns:
                rows.append((sid, target, float(yhat[sid])))
        return pd.DataFrame(rows, columns=["series_id", "date", "yhat"])
