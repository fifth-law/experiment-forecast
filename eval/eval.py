#!/usr/bin/env python3
"""THE FIXED EVAL. This file is the optimization target of the agentic loop.

    uv run python -m eval.eval --experiment <name> --stage <stage>

Rules (enforced, not advisory):
  - eval/eval.py, eval/metrics.py, eval/stages.yaml and the data snapshot are
    FROZEN. Their joint sha256 must match eval/EVAL_LOCK or the run aborts.
    Changing the eval means the human owner re-writes the lock deliberately
    (EVAL_UNLOCK=1 ... --write-lock) and all leaderboard history restarts.
  - The 'holdout' stage refuses to run without HOLDOUT_OK=1. It is reserved
    for the final report of the chosen model, not for iteration.
  - Models only ever receive data with date <= cutoff. Leakage by
    construction is impossible unless an experiment smuggles in the snapshot
    itself; experiments importing from data/ are therefore forbidden
    (checked crudely below).

Experiment contract (experiments/<name>/model.py):
    PARAMS: dict            # optional, echoed into the run record
    class Forecaster:
        def fit_predict(self, history, cutoff, horizon, series_meta):
            '''history: DataFrame(date, series_id, y), dense daily grid for
            all 105 series, train_start <= date <= cutoff.
            Return DataFrame(series_id, date, yhat) covering every series for
            every date in (cutoff, cutoff + horizon days]. Deterministic.'''

A fresh Forecaster instance is created for every cutoff, so no state can
leak across cutoffs. Negative predictions are clipped to 0 (count reported).
NaNs or a wrong shape abort the run.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time

import pandas as pd
import yaml

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(EVAL_DIR)
sys.path.insert(0, EVAL_DIR)

import metrics  # noqa: E402

LOCK_PATH = os.path.join(EVAL_DIR, "EVAL_LOCK")
LOCKED_FILES = [
    os.path.join(EVAL_DIR, "eval.py"),
    os.path.join(EVAL_DIR, "metrics.py"),
    os.path.join(EVAL_DIR, "stages.yaml"),
    os.path.join(REPO, "data", "snapshot", "MANIFEST.json"),
]


def eval_sha() -> str:
    digest = hashlib.sha256()
    for path in LOCKED_FILES:
        digest.update(open(path, "rb").read())
    return digest.hexdigest()


def check_lock(write: bool) -> str:
    sha = eval_sha()
    if write:
        if os.environ.get("EVAL_UNLOCK") != "1":
            raise SystemExit("refusing --write-lock without EVAL_UNLOCK=1")
        with open(LOCK_PATH, "w") as fh:
            fh.write(sha + "\n")
        print(f"EVAL_LOCK written: {sha}")
        return sha
    if not os.path.exists(LOCK_PATH):
        raise SystemExit("eval/EVAL_LOCK missing — run --write-lock once at setup")
    expected = open(LOCK_PATH).read().strip()
    if sha != expected:
        raise SystemExit(
            "EVAL DEFINITION CHANGED — refusing to run.\n"
            f"  expected {expected}\n  computed {sha}\n"
            "The eval files and snapshot are frozen. Revert your changes to "
            "eval/ and data/snapshot/, or (human owner only) rewrite the lock."
        )
    return sha


def load_stages() -> dict:
    with open(os.path.join(EVAL_DIR, "stages.yaml")) as fh:
        return yaml.safe_load(fh)


def mondays(first: str, last: str) -> list[pd.Timestamp]:
    days = pd.date_range(first, last, freq="D")
    result = [d for d in days if d.weekday() == 0]
    if not result or result[0] != pd.Timestamp(first) or result[-1] != pd.Timestamp(last):
        raise SystemExit(f"stage cutoffs {first}..{last} must start and end on Mondays")
    return result


def load_experiment(name: str):
    exp_dir = os.path.join(REPO, "experiments", name)
    model_path = os.path.join(exp_dir, "model.py")
    if not os.path.exists(model_path):
        raise SystemExit(f"no such experiment: {model_path}")
    source = open(model_path, encoding="utf-8").read()
    if "data/snapshot" in source or "data_snapshot" in source:
        raise SystemExit("experiment source references the snapshot directly — forbidden")
    spec = importlib.util.spec_from_file_location(f"experiments.{name}.model", model_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Forecaster"):
        raise SystemExit("experiment must define a Forecaster class")
    return module


def run_backtest(module, config: dict, stage_name: str) -> tuple[pd.DataFrame, int]:
    stage = config["stages"][stage_name]
    horizon = int(config["horizon_days"])
    snapshot_path = os.path.join(REPO, config["snapshot"])
    meta_path = os.path.join(REPO, config["series_meta"])

    data = pd.read_parquet(snapshot_path)
    data["date"] = pd.to_datetime(data["date"])
    data["series_id"] = data["series_id"].astype(str)
    with open(meta_path) as fh:
        series_meta = json.load(fh)

    kind = {s["series_id"]: s["kind"] for s in series_meta["series"]}
    first_date = {
        s["series_id"]: pd.Timestamp(s["first_date"]) for s in series_meta["series"]
    }
    all_series = sorted(kind)
    train_start = pd.Timestamp(stage["train_start"])
    cutoffs = mondays(stage["first_cutoff"], stage["last_cutoff"])

    snapshot_end = data["date"].max()
    if cutoffs[-1] + pd.Timedelta(days=horizon) > snapshot_end:
        raise SystemExit("last cutoff + horizon exceeds snapshot end")

    actual = data.set_index(["series_id", "date"])["y"]
    scored_frames = []
    clipped = 0

    for cutoff in cutoffs:
        history = data[(data["date"] >= train_start) & (data["date"] <= cutoff)]
        forecaster = module.Forecaster()
        preds = forecaster.fit_predict(
            history=history.copy(), cutoff=cutoff, horizon=horizon, series_meta=series_meta
        )

        expected_dates = pd.date_range(cutoff + pd.Timedelta(days=1), periods=horizon)
        preds = preds[["series_id", "date", "yhat"]].copy()
        preds["date"] = pd.to_datetime(preds["date"])
        preds["series_id"] = preds["series_id"].astype(str)
        expected_cells = len(all_series) * horizon
        if len(preds) != expected_cells:
            raise SystemExit(
                f"{cutoff.date()}: got {len(preds)} prediction rows, expected {expected_cells}"
            )
        if preds["yhat"].isna().any():
            raise SystemExit(f"{cutoff.date()}: NaN predictions")
        if set(preds["series_id"]) != set(all_series):
            raise SystemExit(f"{cutoff.date()}: series set mismatch")
        if sorted(preds["date"].unique()) != list(expected_dates):
            raise SystemExit(f"{cutoff.date()}: forecast dates mismatch")

        negatives = preds["yhat"] < 0
        clipped += int(negatives.sum())
        preds.loc[negatives, "yhat"] = 0.0

        # activity mask: only score series already active at the cutoff
        preds = preds[preds["series_id"].map(first_date) <= cutoff]
        idx = pd.MultiIndex.from_frame(preds[["series_id", "date"]])
        preds["y"] = actual.reindex(idx).to_numpy()
        preds["cutoff"] = cutoff
        preds["lead"] = (preds["date"] - cutoff).dt.days
        preds["kind"] = preds["series_id"].map(kind)
        scored_frames.append(preds)

    scored = pd.concat(scored_frames, ignore_index=True)
    if scored["y"].isna().any():
        raise SystemExit("internal error: scored cells missing actuals")
    return scored, clipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed forecast eval")
    parser.add_argument("--experiment", help="experiment folder name under experiments/")
    parser.add_argument("--stage", help="stage name from eval/stages.yaml")
    parser.add_argument("--notes", default="", help="free-text note for the leaderboard row")
    parser.add_argument("--write-lock", action="store_true", help="(setup only) write EVAL_LOCK")
    args = parser.parse_args()

    if args.write_lock:
        check_lock(write=True)
        return
    if not args.experiment or not args.stage:
        parser.error("--experiment and --stage are required")

    sha = check_lock(write=False)
    config = load_stages()
    if args.stage not in config["stages"]:
        raise SystemExit(f"unknown stage {args.stage}; known: {list(config['stages'])}")
    stage = config["stages"][args.stage]
    if stage.get("locked") and os.environ.get("HOLDOUT_OK") != "1":
        raise SystemExit(
            "stage 'holdout' is LOCKED. It is for the final report of the chosen "
            "model only — never for iteration. Set HOLDOUT_OK=1 to acknowledge."
        )

    module = load_experiment(args.experiment)
    t0 = time.time()
    scored, clipped = run_backtest(module, config, args.stage)
    runtime = time.time() - t0

    summary = metrics.compute_all(scored)
    summary.update(
        {
            "clipped_cells": clipped,
            "runtime_s": round(runtime, 1),
            "eval_sha": sha[:16],
        }
    )

    with open(os.path.join(REPO, "data", "snapshot", "MANIFEST.json")) as fh:
        snapshot_sha = json.load(fh)["parquet_sha256"][:16]

    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    record = {
        "run_id": run_id,
        "experiment": args.experiment,
        "stage": args.stage,
        "params": getattr(module, "PARAMS", {}),
        "notes": args.notes,
        "snapshot_sha": snapshot_sha,
        **summary,
        "per_cutoff": metrics.per_cutoff(scored),
        "worst_series": metrics.worst_series(scored),
    }
    runs_dir = os.path.join(REPO, "results", "runs")
    os.makedirs(runs_dir, exist_ok=True)
    run_path = os.path.join(runs_dir, f"{run_id}_{args.experiment}_{args.stage}.json")
    with open(run_path, "w") as fh:
        json.dump(record, fh, indent=2)

    leaderboard = os.path.join(REPO, "results", "leaderboard.csv")
    columns = [
        "run_id", "experiment", "stage", "wmape", "mae", "rmse", "bias",
        "wmape_lead_1_7", "wmape_lead_8_14", "wmape_customers", "wmape_tail",
        "network_wmape", "n_cells", "n_series", "n_cutoffs", "clipped_cells",
        "runtime_s", "eval_sha", "notes",
    ]
    row = {c: record.get(c, summary.get(c, "")) for c in columns}
    header = not os.path.exists(leaderboard)
    pd.DataFrame([row])[columns].to_csv(
        leaderboard, mode="a", header=header, index=False, float_format="%.6f"
    )

    print(f"\n=== {args.experiment} on {args.stage} ===")
    for key in ["wmape", "wmape_lead_1_7", "wmape_lead_8_14", "wmape_customers",
                "wmape_tail", "network_wmape", "bias", "mae", "rmse"]:
        print(f"{key:>18}: {summary[key]:.4f}")
    print(f"{'cells':>18}: {summary['n_cells']} across {summary['n_cutoffs']} cutoffs"
          f" ({summary['n_series']} series, {clipped} clipped)")
    print(f"run record: {os.path.relpath(run_path, REPO)}")


if __name__ == "__main__":
    main()
