"""Metric definitions for the frozen monthly-sales eval. Pure functions of the scored frame.

The scored frame has one row per (series_id, cutoff) forecast that passed the
activity mask, with columns: series_id, kind, cutoff, target_month, dom (day of
the month the cutoff falls on), days_left (nights remaining in the month after
the cutoff), y (settled month total, DKK), yhat.

Primary metric: pooled wMAPE = sum(|yhat - y|) / sum(|y|) over all scored
forecasts. Lower is better. The denominator uses |y| rather than y because a
series-month can net negative when credit notes outweigh invoices.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def wmape(frame: pd.DataFrame) -> float:
    denom = frame["y"].abs().sum()
    if denom <= 0:
        return float("nan")
    return float((frame["yhat"] - frame["y"]).abs().sum() / denom)


def mae(frame: pd.DataFrame) -> float:
    return float((frame["yhat"] - frame["y"]).abs().mean())


def rmse(frame: pd.DataFrame) -> float:
    return float(np.sqrt(((frame["yhat"] - frame["y"]) ** 2).mean()))


def bias(frame: pd.DataFrame) -> float:
    """Signed relative error: >0 means over-forecasting."""
    denom = frame["y"].abs().sum()
    if denom <= 0:
        return float("nan")
    return float((frame["yhat"].sum() - frame["y"].sum()) / denom)


def network_wmape(frame: pd.DataFrame) -> float:
    """wMAPE of the network month total: series summed per cutoff first.

    This is the "where does the whole month land" number a finance owner reads,
    and it is much easier than the per-customer split because series errors
    partly cancel.
    """
    grouped = frame.groupby("cutoff", observed=True)[["y", "yhat"]].sum()
    return wmape(grouped)


def compute_all(frame: pd.DataFrame) -> dict:
    return {
        "wmape": wmape(frame),
        "mae": mae(frame),
        "rmse": rmse(frame),
        "bias": bias(frame),
        # error by how far into the month the forecast is made: day 1-10 is
        # nearly a cold-start month-ahead forecast, day 21+ is mostly nowcast
        "wmape_dom_1_10": wmape(frame[frame["dom"] <= 10]),
        "wmape_dom_11_20": wmape(frame[(frame["dom"] >= 11) & (frame["dom"] <= 20)]),
        "wmape_dom_21_end": wmape(frame[frame["dom"] >= 21]),
        "wmape_customers": wmape(frame[frame["kind"] == "customer"]),
        "wmape_tail": wmape(frame[frame["kind"] == "tail_group"]),
        "network_wmape": network_wmape(frame),
        "n_forecasts": int(len(frame)),
        "n_series": int(frame["series_id"].nunique()),
        "n_cutoffs": int(frame["cutoff"].nunique()),
        "n_months": int(frame["target_month"].nunique()),
    }


def per_cutoff(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for cutoff, grp in frame.groupby("cutoff", observed=True):
        rows.append(
            {
                "cutoff": str(pd.Timestamp(cutoff).date()),
                "target_month": str(grp["target_month"].iloc[0]),
                "dom": int(grp["dom"].iloc[0]),
                "wmape": wmape(grp),
                "bias": bias(grp),
                "n_series": int(grp["series_id"].nunique()),
            }
        )
    return rows


def per_dom(frame: pd.DataFrame) -> list[dict]:
    """wMAPE as a function of day of month — the error-decay curve."""
    rows = []
    for dom, grp in frame.groupby("dom", observed=True):
        rows.append({"dom": int(dom), "wmape": wmape(grp), "bias": bias(grp),
                     "n_forecasts": int(len(grp))})
    return rows


def worst_series(frame: pd.DataFrame, n: int = 20) -> list[dict]:
    rows = []
    for series_id, grp in frame.groupby("series_id", observed=True):
        rows.append(
            {
                "series_id": str(series_id),
                "wmape": wmape(grp),
                "volume": float(grp["y"].abs().sum()),
                "bias": bias(grp),
            }
        )
    rows = [r for r in rows if r["volume"] > 0]
    rows.sort(key=lambda r: r["wmape"] * r["volume"], reverse=True)
    return rows[:n]
