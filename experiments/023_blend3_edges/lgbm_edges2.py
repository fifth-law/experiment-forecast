"""020_lgbm_basefix plus event-edge distance features.

After 021 the worst non-December cutoffs straddle event-cluster EDGES
(03-27/04-03 around Easter, 05-08/15 around Ascension): the day-type ids
label days inside special windows but carry nothing about the surge
before a closure (last-orders pull-forward) or the rebound after it.

One change over 020: two features of the target date,
    to_special    = days until the next special day (capped 10)
    since_special = days since the last special day (capped 10)
computed from the same special-day set the masking uses. Trees can then
learn pre/post-event ripples as smooth functions of distance instead of
per-date memorization.
"""

import datetime as dt

import numpy as np
import pandas as pd
import holidays as holidays_pkg
import lightgbm as lgb

PARAMS = {
    "kind": "lgbm_edges",
    "edge_features": ["to_special", "since_special"],
    "edge_cap": 10,
    "base_cascade": ["L14", "L28", "L56"],
    "num_boost_round": 300,
    "learning_rate": 0.06,
    "num_leaves": 63,
    "min_data_in_leaf": 60,
    "objective": "l1",
    "target": "y / L14(ref), weight L14(ref)",
    "train_refs": "Mondays in [start+120d, cutoff-14d]",
    "seed": 42,
}

EXTRA_FIXED = {(12, 24): "xmas_eve", (12, 31): "nye", (6, 5): "constitution_day"}
XMAS_WINDOW_DAYS = (20, 21, 22, 23, 27, 28, 29, 30)
BF_OFFSETS = range(-4, 4)
RUNUP_BLOCKS = [((11, 28), (12, 5), "runup_w3"), ((12, 6), (12, 12), "runup_w2"), ((12, 13), (12, 19), "runup_w1")]
SUMMER_WEEKS = range(25, 33)
WINTER_WEEKS = (7, 8)
AUTUMN_WEEKS = (41, 42, 43)
LAG_RATIO_CAP = 12.0
TARGET_RATIO_CAP = 15.0

LGB_PARAMS = {
    "objective": "l1",
    "learning_rate": 0.06,
    "num_leaves": 63,
    "min_data_in_leaf": 60,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": 42,
    "deterministic": True,
    "force_row_wise": True,
    "verbosity": -1,
    "num_threads": 4,
}
NUM_BOOST_ROUND = 300


def black_friday(year: int) -> pd.Timestamp:
    """Day after the 4th Thursday of November."""
    nov1 = pd.Timestamp(year=year, month=11, day=1)
    first_thursday = nov1 + pd.Timedelta(days=(3 - nov1.weekday()) % 7)
    return first_thursday + pd.Timedelta(weeks=3, days=1)


def calendar_types(first_year: int, last_year: int) -> tuple[dict, set]:
    """Timestamp -> type name (specials + damp weeks); also the special-only set."""
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
    specials = set(smap)

    types = dict(smap)
    for year in range(first_year, last_year + 1):
        for offset in range(7):
            day = pd.Timestamp(year=year, month=1, day=2) + pd.Timedelta(days=offset)
            types.setdefault(day, "jan_wk1")
        ascension = next(
            pd.Timestamp(day)
            for day, name in sorted(holidays_pkg.Denmark(years=year).items())
            if name == "Kristi himmelfartsdag"
        )
        monday_w0 = ascension - pd.Timedelta(days=3)
        for week in range(3):
            for offset in range(7):
                types.setdefault(monday_w0 + pd.Timedelta(days=7 * week + offset), f"asc_wk{week}")
        for weeks, prefix in ((WINTER_WEEKS, "win_wk"), (SUMMER_WEEKS, "sum_wk"), (AUTUMN_WEEKS, "aut_wk")):
            for week in weeks:
                monday = pd.Timestamp(dt.date.fromisocalendar(year, week, 1))
                for offset in range(7):
                    types.setdefault(monday + pd.Timedelta(days=offset), f"{prefix}{week}")
        for (m1, d1), (m2, d2), name in RUNUP_BLOCKS:
            day = pd.Timestamp(year=year, month=m1, day=d1)
            end = pd.Timestamp(year=year, month=m2, day=d2)
            while day <= end:
                types.setdefault(day, name)
                day += pd.Timedelta(days=1)
    return types, specials


class Forecaster:
    def fit_predict(self, history, cutoff, horizon, series_meta):
        cutoff = pd.Timestamp(cutoff)
        targets = pd.date_range(cutoff + pd.Timedelta(days=1), periods=horizon)
        first_year = history["date"].min().year
        types, specials = calendar_types(first_year, targets[-1].year)

        W = (
            history.pivot_table(index="date", columns="series_id", values="y", aggfunc="sum", observed=True)
            .sort_index()
        )
        series_cats = list(W.columns)
        type_vocab = sorted(set(types.values()) | {"normal"})

        Wc = W.copy()
        Wc[Wc.index.isin(specials)] = np.nan
        L7 = Wc.rolling(7, min_periods=3).mean()
        L28 = Wc.rolling(28, min_periods=7).mean()
        L56 = Wc.rolling(56, min_periods=7).mean()
        # base cascade: prefer the 14-day clean level, fall back to wider
        # windows when a dense special cluster empties the short one
        L14 = Wc.rolling(14, min_periods=5).mean().fillna(L28).fillna(L56)

        def type_of(day: pd.Timestamp) -> str:
            return types.get(day, "normal")

        # distances exclude the xmas window: those days are already densely
        # day-typed, and distance-to-boundary handles let trees overfit the
        # n=2 year boundary (022's January regression)
        special_days = pd.DatetimeIndex(
            sorted(
                d
                for d in specials
                if not ((d.month == 12 and d.day >= 20) or (d.month == 1 and d.day == 1))
            )
        )
        edge_cap = 10

        def edge_dists(dates) -> tuple[np.ndarray, np.ndarray]:
            arr = pd.DatetimeIndex(dates)
            pos_next = special_days.searchsorted(arr, side="left")
            pos_prev = special_days.searchsorted(arr, side="right") - 1
            to_next = np.where(
                pos_next < len(special_days),
                (special_days.values[np.minimum(pos_next, len(special_days) - 1)] - arr.values)
                / np.timedelta64(1, "D"),
                edge_cap,
            )
            since_prev = np.where(
                pos_prev >= 0,
                (arr.values - special_days.values[np.maximum(pos_prev, 0)]) / np.timedelta64(1, "D"),
                edge_cap,
            )
            return np.minimum(to_next, edge_cap), np.minimum(since_prev, edge_cap)

        def build_rows(refs: pd.DatetimeIndex, with_target: bool):
            parts = []
            for lead in range(1, 15):
                T = refs + pd.Timedelta(days=lead)
                k0 = 1 if lead <= 7 else 2
                base = L14.loc[refs].set_axis(T)
                feats = {
                    "l14_log": np.log1p(base),
                    "l28_ratio": (L28.loc[refs].set_axis(T) / base).clip(0, LAG_RATIO_CAP),
                    "l7_ratio": (L7.loc[refs].set_axis(T) / base).clip(0, LAG_RATIO_CAP),
                }
                for j, k in enumerate((k0, k0 + 1, k0 + 2, k0 + 3)):
                    lag_dates = T - pd.Timedelta(days=7 * k)
                    lag = pd.DataFrame(
                        W.reindex(lag_dates).to_numpy(), index=T, columns=W.columns
                    )
                    feats[f"lag{j}_ratio"] = (lag / base).clip(0, LAG_RATIO_CAP)
                X = pd.concat({name: frame.stack() for name, frame in feats.items()}, axis=1)
                dates = X.index.get_level_values(0)
                X["lead"] = lead
                X["weekday"] = dates.weekday
                X["month"] = dates.month
                X["day_type"] = pd.Categorical([type_of(d) for d in dates], categories=type_vocab)
                to_next, since_prev = edge_dists(dates)
                X["to_special"] = to_next
                X["since_special"] = since_prev
                X["series"] = pd.Categorical(X.index.get_level_values(1), categories=series_cats)
                X["_base"] = base.stack()
                if with_target:
                    X["_y"] = W.reindex(T).set_axis(T).stack()
                parts.append(X)
            return pd.concat(parts, ignore_index=True)

        mondays = W.index[
            (W.index.weekday == 0)
            & (W.index >= W.index.min() + pd.Timedelta(days=120))
            & (W.index <= cutoff - pd.Timedelta(days=14))
        ]
        train = build_rows(mondays, with_target=True)
        train = train[(train["_base"] > 1.0) & train["_y"].notna()]
        label = (train["_y"] / train["_base"]).clip(0, TARGET_RATIO_CAP)
        weight = train["_base"]

        feature_cols = [c for c in train.columns if not c.startswith("_") and c != "_y"]
        dataset = lgb.Dataset(
            train[feature_cols], label=label, weight=weight,
            categorical_feature=["day_type", "series"], free_raw_data=True,
        )
        booster = lgb.train(LGB_PARAMS, dataset, num_boost_round=NUM_BOOST_ROUND)

        pred = build_rows(pd.DatetimeIndex([cutoff]), with_target=False)
        ratio = np.clip(booster.predict(pred[feature_cols]), 0.0, None)
        base = pred["_base"].to_numpy()
        yhat = np.where(np.nan_to_num(base, nan=0.0) > 1.0, ratio * np.nan_to_num(base, nan=0.0), 0.0)

        out = pd.DataFrame(
            {
                "series_id": pred["series"].astype(str),
                "date": pd.DatetimeIndex(
                    [cutoff + pd.Timedelta(days=int(l)) for l in pred["lead"]]
                ),
                "yhat": yhat,
            }
        )
        return out
