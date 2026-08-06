"""Metric definitions for the frozen eval. Pure functions of the scored frame.

The scored frame has one row per (series_id, cutoff, date) cell that passed
the activity mask, with columns: series_id, kind, cutoff, date, lead, y, yhat.

Primary metric: pooled wMAPE = sum(|yhat - y|) / sum(y) over all scored cells.
Lower is better. It is scale-free and weighs customers by their volume, which
matches business impact (top-100 customers carry ~94% of network volume).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def wmape(frame: pd.DataFrame) -> float:
    denom = frame["y"].sum()
    if denom <= 0:
        return float("nan")
    return float((frame["yhat"] - frame["y"]).abs().sum() / denom)


def mae(frame: pd.DataFrame) -> float:
    return float((frame["yhat"] - frame["y"]).abs().mean())


def rmse(frame: pd.DataFrame) -> float:
    return float(np.sqrt(((frame["yhat"] - frame["y"]) ** 2).mean()))


def bias(frame: pd.DataFrame) -> float:
    """Signed relative error: >0 means over-forecasting."""
    denom = frame["y"].sum()
    if denom <= 0:
        return float("nan")
    return float((frame["yhat"].sum() - denom) / denom)


def network_wmape(frame: pd.DataFrame) -> float:
    """wMAPE of the network total: series summed per (cutoff, date) first."""
    grouped = frame.groupby(["cutoff", "date"], observed=True)[["y", "yhat"]].sum()
    return wmape(grouped)


def compute_all(frame: pd.DataFrame) -> dict:
    customers = frame[frame["kind"] == "customer"]
    tail = frame[frame["kind"] == "tail_group"]
    lead_1_7 = frame[frame["lead"] <= 7]
    lead_8_14 = frame[frame["lead"] >= 8]
    return {
        "wmape": wmape(frame),
        "mae": mae(frame),
        "rmse": rmse(frame),
        "bias": bias(frame),
        "wmape_lead_1_7": wmape(lead_1_7),
        "wmape_lead_8_14": wmape(lead_8_14),
        "wmape_customers": wmape(customers),
        "wmape_tail": wmape(tail),
        "network_wmape": network_wmape(frame),
        "n_cells": int(len(frame)),
        "n_series": int(frame["series_id"].nunique()),
        "n_cutoffs": int(frame["cutoff"].nunique()),
    }


def per_cutoff(frame: pd.DataFrame) -> list[dict]:
    rows = []
    for cutoff, grp in frame.groupby("cutoff", observed=True):
        rows.append(
            {
                "cutoff": str(pd.Timestamp(cutoff).date()),
                "wmape": wmape(grp),
                "bias": bias(grp),
                "n_series": int(grp["series_id"].nunique()),
            }
        )
    return rows


def worst_series(frame: pd.DataFrame, n: int = 20) -> list[dict]:
    rows = []
    for series_id, grp in frame.groupby("series_id", observed=True):
        rows.append(
            {
                "series_id": str(series_id),
                "wmape": wmape(grp),
                "volume": float(grp["y"].sum()),
                "bias": bias(grp),
            }
        )
    rows = [r for r in rows if r["volume"] > 0]
    rows.sort(key=lambda r: r["wmape"] * r["volume"], reverse=True)
    return rows[:n]
