"""January week 1 as an up-anomaly, on top of 014_school_vacations.

Jan-09/16 over-forecast (+0.18/+0.15): the first January week (post-New-
Year backlog release and returns surge) runs HIGH, then volume decays to
its true level. Modelling weeks 2-4 as "low" would break the level chain
at the February boundary (deflating week-4 days would over-lift February
forecasts); the correct shape is week 1 as a transient up-anomaly.

One change over 014: damp group `jan` = Jan 2-8 (type jan_wk1, up-clip
(0.9, 1.6)) with a FORWARD base: the damp machinery gains a per-group
base_span, and jan uses [anchor+7, anchor+21) - the two weeks after -
because the backward window crosses the year-boundary regime break.
Applied generically: week-1 targets x factor, week-1 days in level
windows deflate down to the true January level (which is exactly what
the Jan-02/09/16 cutoffs need).
"""

import datetime as dt

import numpy as np
import pandas as pd
import holidays as holidays_pkg

PARAMS = {
    "kind": "hand_step_recency",
    "recency_half_life_days": 365.25,
    "step_tau": 0.18,
    "damp_groups": ["jan_wk1", "win_wk7-8", "asc_wk0-2", "sum_wk25-32", "aut_wk41-43", "runup_w1-3"],
    "jan_clip": [0.9, 1.6],
    "jan_base_span": [7, 21],
    "damp_clip": [0.5, 1.3],
    "runup_clip": [0.8, 2.0],
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
RUNUP_CLIP = (0.8, 2.0)
JAN_CLIP = (0.9, 1.6)
STEP_TAU = 0.18  # |log weekly ratio| beyond this = step, snap level to recent week
RECENCY_HALF_LIFE_DAYS = 365.25  # learned responses decay: last year counts double
BACK_BASE = (-28, 0)  # default: the 28 days before the anchor
JAN_BASE = (7, 21)  # forward: the two weeks after week 1
RUNUP_BLOCKS = [((11, 28), (12, 5), "runup_w3"), ((12, 6), (12, 12), "runup_w2"), ((12, 13), (12, 19), "runup_w1")]
SUMMER_WEEKS = range(25, 33)
WINTER_WEEKS = (7, 8)
AUTUMN_WEEKS = (41, 42, 43)
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


def _iso_week_days(year: int, week: int):
    monday = pd.Timestamp(dt.date.fromisocalendar(year, week, 1))
    return [monday + pd.Timedelta(days=offset) for offset in range(7)], monday


def damp_groups(first_year: int, last_year: int, smap: dict) -> list:
    """Ordered [(group, {Timestamp: (type_name, anchor)}, clip, base_span, min_obs)]."""
    january, winter, asc, summer, autumn, runup = {}, {}, {}, {}, {}, {}
    for year in range(first_year, last_year + 1):
        jan_anchor = pd.Timestamp(year=year, month=1, day=2)
        for offset in range(7):
            day = jan_anchor + pd.Timedelta(days=offset)
            if day not in smap:
                january[day] = ("jan_wk1", jan_anchor)
        win_anchor = pd.Timestamp(dt.date.fromisocalendar(year, WINTER_WEEKS[0], 1))
        for week in WINTER_WEEKS:
            days, _ = _iso_week_days(year, week)
            for day in days:
                if day not in smap:
                    winter[day] = (f"win_wk{week}", win_anchor)
        aut_anchor = pd.Timestamp(dt.date.fromisocalendar(year, AUTUMN_WEEKS[0], 1))
        for week in AUTUMN_WEEKS:
            days, _ = _iso_week_days(year, week)
            for day in days:
                if day not in smap:
                    autumn[day] = (f"aut_wk{week}", aut_anchor)
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
                    asc[day] = (f"asc_wk{week}", monday_w0)
        wk25_monday = pd.Timestamp(dt.date.fromisocalendar(year, 25, 1))
        for week in SUMMER_WEEKS:
            monday = pd.Timestamp(dt.date.fromisocalendar(year, week, 1))
            for offset in range(7):
                day = monday + pd.Timedelta(days=offset)
                if day not in smap and day not in asc:
                    summer[day] = (f"sum_wk{week}", wk25_monday)
        pre_bf_monday = black_friday(year) - pd.Timedelta(days=4)
        for (m1, d1), (m2, d2), name in RUNUP_BLOCKS:
            day = pd.Timestamp(year=year, month=m1, day=d1)
            end = pd.Timestamp(year=year, month=m2, day=d2)
            while day <= end:
                if day not in smap:
                    runup[day] = (name, pre_bf_monday)
                day += pd.Timedelta(days=1)
    return [
        ("jan", january, JAN_CLIP, JAN_BASE, 1),  # forward base: 1 obs per weekday per year
        ("win", winter, DAMP_CLIP, BACK_BASE, 2),
        ("asc", asc, DAMP_CLIP, BACK_BASE, 2),
        ("sum", summer, DAMP_CLIP, BACK_BASE, 2),
        ("aut", autumn, DAMP_CLIP, BACK_BASE, 2),
        # runup last: its pre-BF base deflates week-43 days
        ("runup", runup, RUNUP_CLIP, BACK_BASE, 2),
    ]


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
        groups = damp_groups(first_year, targets[-1].year, smap)

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
            w = 0.5 ** ((cutoff - day).days / RECENCY_HALF_LIFE_DAYS)
            actual[name] = actual.get(name, 0.0) + w * float(net[day])
            expected[name] = expected.get(name, 0.0) + w * float(base.mean())
        pooled_all = sum(actual.values()) / sum(expected.values()) if expected else 0.5
        factors = {
            name: float(np.clip(actual[name] / expected[name], *_clip_for(name)))
            for name in actual
        }

        # damp-week factors, group by group; later groups deflate earlier-group
        # days appearing in their baselines
        clean_net_weekday = clean_net.index.weekday
        damp_factors = {}
        day_damp = {}
        for _, gmap, clip, base_span, min_obs in groups:
            g_actual, g_expected = {}, {}
            for day, (name, anchor) in sorted(gmap.items()):
                if day not in net.index:
                    continue
                base = clean_net[
                    (clean_net.index >= anchor + pd.Timedelta(days=base_span[0]))
                    & (clean_net.index < anchor + pd.Timedelta(days=base_span[1]))
                    & (clean_net_weekday == day.weekday())
                ]
                if len(base) < min_obs:
                    continue
                base_vals = [
                    value / damp_factors.get(day_damp.get(base_day), 1.0)
                    for base_day, value in base.items()
                ]
                base_mean = sum(base_vals) / len(base_vals)
                if base_mean <= 0:
                    continue
                w = 0.5 ** ((cutoff - day).days / RECENCY_HALF_LIFE_DAYS)
                g_actual[name] = g_actual.get(name, 0.0) + w * float(net[day])
                g_expected[name] = g_expected.get(name, 0.0) + w * base_mean
            for name in g_actual:
                damp_factors[name] = float(np.clip(g_actual[name] / g_expected[name], *clip))
            day_damp.update({day: name for day, (name, _) in gmap.items()})

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
            w = 0.5 ** ((cutoff - day).days / RECENCY_HALF_LIFE_DAYS)
            group_actual[group] += w * wide.loc[day]
            group_expected[group] += w * base_rows.mean() * factors[name]
        mult = {
            g: ((group_actual[g] + BF_SERIES_K) / (group_expected[g] + BF_SERIES_K)).clip(*BF_SERIES_CLIP)
            for g in group_actual
        }

        # shape-deflated recent level over the last 14 calendar days; damp-week
        # days count at y / damp[type] (ordinary weekdays, just damped).
        # Accumulated per 7-day half: on a sustained step (|log weekly ratio|
        # > STEP_TAU) the level snaps to the post-break week instead of
        # averaging across the break.
        num = {h: pd.Series(0.0, index=wide.columns) for h in ("recent", "prev")}
        den = {h: pd.Series(0.0, index=wide.columns) for h in ("recent", "prev")}
        window = wide[wide.index > cutoff - pd.Timedelta(days=RECENT_LEVEL_DAYS)]
        split = cutoff - pd.Timedelta(days=7)
        for day in window.index:
            if day in smap:
                continue
            damp_f = damp_factors.get(day_damp.get(day), 1.0)
            half = "recent" if day > split else "prev"
            num[half] += window.loc[day] / damp_f
            den[half] += shape[day.weekday()]
        num_all = num["recent"] + num["prev"]
        den_all = den["recent"] + den["prev"]
        level = (num_all / den_all).where(den_all > 0, 0.0).fillna(0.0)
        l_recent = (num["recent"] / den["recent"]).where(den["recent"] > 0, 0.0).fillna(0.0)
        l_prev = (num["prev"] / den["prev"]).where(den["prev"] > 0, 0.0).fillna(0.0)
        valid = (l_recent > 0) & (l_prev > 0)
        log_ratio = pd.Series(0.0, index=wide.columns)
        log_ratio[valid] = np.log(l_recent[valid] / l_prev[valid])
        step = valid & (log_ratio.abs() > STEP_TAU)
        level = level.where(~step, l_recent)

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
                damp_f = damp_factors.get(day_damp.get(target), 1.0)
                yhat = yhat * damp_f
            for sid in wide.columns:
                rows.append((sid, target, float(yhat[sid])))
        return pd.DataFrame(rows, columns=["series_id", "date", "yhat"])
