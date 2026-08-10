#!/usr/bin/env python3
"""THE FIXED EVAL for the monthly sales-invoiced forecast.

    uv run python -m eval_sales.eval --experiment <name> --stage <stage>

The question it scores: on the night of day c, for each of the 105 series, what
will this calendar month's total *sales invoiced* (excl. VAT, DKK, net of credit
notes, by invoice posting date) come to when the month has settled? Every night
of the stage window is a cutoff, so a month is forecast ~30 times — cold on the
1st, near-nowcast on the last night.

Rules (enforced, not advisory):
  - eval_sales/eval.py, eval_sales/metrics.py, eval_sales/stages.yaml and the
    snapshot manifests are FROZEN. Their joint sha256 must match
    eval_sales/EVAL_LOCK or the run aborts. Changing the eval means the human
    owner rewrites the lock deliberately (EVAL_UNLOCK=1 ... --write-lock) and
    all leaderboard history restarts.
  - The 'holdout' stage refuses to run without HOLDOUT_OK=1. It is reserved for
    the final report of the chosen model, not for iteration.
  - Models only ever receive data that existed on the night of the cutoff. The
    invoice frame is reconstructed from the creation-date axis of the snapshot
    triangle, so month-to-date accruals are as incomplete as they really were,
    and recent months are as unsettled as they really were. Experiments
    importing from data/ are forbidden (checked crudely below).

Experiment contract (experiments_sales/<name>/model.py):
    PARAMS: dict            # optional, echoed into the run record
    class Forecaster:
        def fit_predict(self, history, shipments, cutoff, target_month, series_meta):
            '''history: DataFrame(series_id, posting_month, create_date, dkk) —
            invoiced increments visible on the night of `cutoff`; a row means
            "dkk was booked against posting_month, and became visible on
            create_date". Sum a series-month's rows to get what was visible so
            far; months that have settled are complete.
            shipments: DataFrame(date, series_id, y) — daily shipment counts,
            dense, date <= cutoff (the same frozen snapshot the shipment eval
            uses). Volume leads revenue and has no reporting lag.
            cutoff: Timestamp (the night in question).
            target_month: str 'YYYY-MM' — the month cutoff falls in.
            Return DataFrame(series_id, yhat) with exactly one row per series,
            yhat in DKK for the whole target month. Deterministic.'''

A fresh Forecaster is created for every cutoff. Cutoffs run in chronological
order, so module-level caching of work derived from the frames already handed
in is allowed; caching anything else is leakage. Negative predictions are kept
(a month can net negative when credit notes dominate) and counted.
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
    os.path.join(REPO, "data", "snapshot_sales", "MANIFEST.json"),
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
        raise SystemExit("eval_sales/EVAL_LOCK missing — run --write-lock once at setup")
    expected = open(LOCK_PATH).read().strip()
    if sha != expected:
        raise SystemExit(
            "EVAL DEFINITION CHANGED — refusing to run.\n"
            f"  expected {expected}\n  computed {sha}\n"
            "The eval files and snapshots are frozen. Revert your changes to "
            "eval_sales/ and data/snapshot*/, or (human owner only) rewrite the lock."
        )
    return sha


def load_stages() -> dict:
    with open(os.path.join(EVAL_DIR, "stages.yaml")) as fh:
        return yaml.safe_load(fh)


def load_experiment(name: str):
    exp_dir = os.path.join(REPO, "experiments_sales", name)
    model_path = os.path.join(exp_dir, "model.py")
    if not os.path.exists(model_path):
        raise SystemExit(f"no such experiment: {model_path}")
    source = open(model_path, encoding="utf-8").read()
    if "data/snapshot" in source or "data_snapshot" in source:
        raise SystemExit("experiment source references a snapshot directly — forbidden")
    spec = importlib.util.spec_from_file_location(f"experiments_sales.{name}.model", model_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Forecaster"):
        raise SystemExit("experiment must define a Forecaster class")
    return module


def load_data(config: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    triangle = pd.read_parquet(os.path.join(REPO, config["triangle"]))
    triangle["series_id"] = triangle["series_id"].astype(str)
    month_start = pd.PeriodIndex(triangle["posting_month"], freq="M").start_time
    triangle["create_date"] = month_start + pd.to_timedelta(triangle["create_offset"], unit="D")
    triangle["dkk"] = triangle["ore"] / 100.0

    shipments = pd.read_parquet(os.path.join(REPO, config["shipments"]))
    shipments["date"] = pd.to_datetime(shipments["date"])
    shipments["series_id"] = shipments["series_id"].astype(str)

    with open(os.path.join(REPO, config["series_meta"])) as fh:
        series_meta = json.load(fh)
    return triangle, shipments, series_meta


def run_backtest(module, config: dict, stage_name: str) -> tuple[pd.DataFrame, int]:
    stage = config["stages"][stage_name]
    triangle, shipments, series_meta = load_data(config)

    kind = {s["series_id"]: s["kind"] for s in series_meta["series"]}
    all_series = sorted(kind)
    train_start = str(config["train_start_month"])
    cutoffs = pd.date_range(stage["first_cutoff"], stage["last_cutoff"], freq="D")

    in_range = triangle[triangle["posting_month"] >= train_start]
    settled = in_range.groupby(["series_id", "posting_month"])["dkk"].sum()
    last_month = str(pd.PeriodIndex(triangle["posting_month"], freq="M").max())
    for cutoff in (cutoffs[0], cutoffs[-1]):
        if str(cutoff.to_period("M")) > last_month:
            raise SystemExit(f"stage reaches {cutoff.date()}, past the settled month {last_month}")

    scored_frames = []
    negative_preds = 0

    for cutoff in cutoffs:
        target_month = str(cutoff.to_period("M"))
        visible = in_range[in_range["create_date"] <= cutoff]
        history = visible[["series_id", "posting_month", "create_date", "dkk"]]
        ship = shipments[shipments["date"] <= cutoff]

        forecaster = module.Forecaster()
        preds = forecaster.fit_predict(
            history=history.copy(),
            shipments=ship.copy(),
            cutoff=cutoff,
            target_month=target_month,
            series_meta=series_meta,
        )

        preds = preds[["series_id", "yhat"]].copy()
        preds["series_id"] = preds["series_id"].astype(str)
        if len(preds) != len(all_series):
            raise SystemExit(
                f"{cutoff.date()}: got {len(preds)} predictions, expected {len(all_series)}")
        if set(preds["series_id"]) != set(all_series):
            raise SystemExit(f"{cutoff.date()}: series set mismatch")
        if preds["yhat"].isna().any():
            raise SystemExit(f"{cutoff.date()}: NaN predictions")
        negative_preds += int((preds["yhat"] < 0).sum())

        # activity mask: only score series that were already visible in the
        # invoice data on the night of the cutoff. Depends on as-of data only,
        # so it cannot leak; churn-to-zero stays scored.
        active = set(visible["series_id"].unique())
        preds = preds[preds["series_id"].isin(active)]
        idx = pd.MultiIndex.from_arrays(
            [preds["series_id"], [target_month] * len(preds)])
        preds["y"] = settled.reindex(idx).fillna(0.0).to_numpy()
        preds["cutoff"] = cutoff
        preds["target_month"] = target_month
        preds["dom"] = cutoff.day
        preds["days_left"] = cutoff.days_in_month - cutoff.day
        preds["kind"] = preds["series_id"].map(kind)
        scored_frames.append(preds)

    scored = pd.concat(scored_frames, ignore_index=True)
    if scored["y"].isna().any():
        raise SystemExit("internal error: scored rows missing actuals")
    return scored, negative_preds


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed monthly-sales forecast eval")
    parser.add_argument("--experiment", help="folder name under experiments_sales/")
    parser.add_argument("--stage", help="stage name from eval_sales/stages.yaml")
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
    scored, negative_preds = run_backtest(module, config, args.stage)
    runtime = time.time() - t0

    summary = metrics.compute_all(scored)
    summary.update(
        {
            "negative_preds": negative_preds,
            "runtime_s": round(runtime, 1),
            "eval_sha": sha[:16],
        }
    )

    with open(os.path.join(REPO, "data", "snapshot_sales", "MANIFEST.json")) as fh:
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
        "per_dom": metrics.per_dom(scored),
        "per_cutoff": metrics.per_cutoff(scored),
        "worst_series": metrics.worst_series(scored),
    }
    runs_dir = os.path.join(REPO, "results_sales", "runs")
    os.makedirs(runs_dir, exist_ok=True)
    run_path = os.path.join(runs_dir, f"{run_id}_{args.experiment}_{args.stage}.json")
    with open(run_path, "w") as fh:
        json.dump(record, fh, indent=2)

    leaderboard = os.path.join(REPO, "results_sales", "leaderboard.csv")
    columns = [
        "run_id", "experiment", "stage", "wmape", "mae", "rmse", "bias",
        "wmape_dom_1_10", "wmape_dom_11_20", "wmape_dom_21_end",
        "wmape_customers", "wmape_tail", "network_wmape",
        "n_forecasts", "n_series", "n_cutoffs", "n_months", "negative_preds",
        "runtime_s", "eval_sha", "notes",
    ]
    row = {c: record.get(c, summary.get(c, "")) for c in columns}
    header = not os.path.exists(leaderboard)
    pd.DataFrame([row])[columns].to_csv(
        leaderboard, mode="a", header=header, index=False, float_format="%.6f"
    )

    print(f"\n=== {args.experiment} on {args.stage} ===")
    for key in ["wmape", "wmape_dom_1_10", "wmape_dom_11_20", "wmape_dom_21_end",
                "wmape_customers", "wmape_tail", "network_wmape", "bias", "mae", "rmse"]:
        print(f"{key:>18}: {summary[key]:.4f}")
    print(f"{'forecasts':>18}: {summary['n_forecasts']} across {summary['n_cutoffs']} nights"
          f" ({summary['n_series']} series, {summary['n_months']} months,"
          f" {negative_preds} negative preds)")
    print(f"run record: {os.path.relpath(run_path, REPO)}")


if __name__ == "__main__":
    main()
