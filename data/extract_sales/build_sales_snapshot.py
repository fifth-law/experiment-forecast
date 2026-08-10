#!/usr/bin/env python3
"""Assemble and validate the frozen monthly sales-invoiced snapshot.

Reads the slice captures in data/raw_sales/mcp_results/, reassembles each
window's payload from its offsets, and refuses to write anything unless every
check passes:

  1. transport: reassembled length and MD5 equal the values Snowflake reported
     for the payload in the same run that produced the bytes;
  2. shape: the payload header declares its own line counts and window, and
     the parsed content must match;
  3. coverage: the windows tile the snapshot's month range exactly, with no
     gap and no overlap;
  4. semantics: per-month totals summed over the 105 series must equal the `#M`
     trailer totals, which Snowflake computed *without* the series mapping.
     This is what proves the series partition the network exactly. Amounts are
     integer oere throughout, so the check is exact equality, not a tolerance;
  5. membership: every series id belongs to the frozen 105-series split.

Outputs (committed, the sales eval's only data source):
  data/snapshot_sales/monthly_sales_triangle.parquet
      series_id, posting_month, create_offset, ore  (increments, integer oere)
  data/snapshot_sales/series_meta.json    series catalogue + target definition
  data/snapshot_sales/MANIFEST.json       checksums and validation record
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RAW_DIR = os.path.join(REPO, "data", "raw_sales", "mcp_results")
SNAPSHOT_DIR = os.path.join(REPO, "data", "snapshot_sales")
MEMBERSHIP_CSV = os.path.join(REPO, "data", "extract", "membership.csv")

sys.path.insert(0, HERE)
from gen_sales_sql import (  # noqa: E402
    AMOUNT_COL,
    CATCH_ALL,
    EXTRACT_VERSION,
    FIRST_MONTH,
    LAST_MONTH,
    MAX_OFFSET,
    SOURCE_TABLE,
    WINDOWS,
    series_ids,
)

SNAPSHOT_TAKEN = "2026-08-10"  # the day the payloads were pulled from Snowflake


def load_captures() -> dict[str, dict]:
    """window -> {'chunks': {offset: text}, 'payload_len': int, 'payload_md5': str}"""
    windows: dict[str, dict] = {}
    for name in sorted(os.listdir(RAW_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(RAW_DIR, name), encoding="utf-8") as fh:
            rec = json.load(fh)
        if rec.get("extract_version") != EXTRACT_VERSION:
            continue
        w = windows.setdefault(
            rec["window"],
            {"chunks": {}, "payload_len": rec["payload_len"],
             "payload_md5": rec["payload_md5"], "files": []},
        )
        if w["payload_len"] != rec["payload_len"] or w["payload_md5"] != rec["payload_md5"]:
            raise SystemExit(
                f"{rec['window']}: slices disagree on the payload they came from "
                "(the source table changed between calls) — re-pull this window"
            )
        if rec["offset"] in w["chunks"]:
            raise SystemExit(f"{rec['window']}: duplicate capture at offset {rec['offset']}")
        w["chunks"][rec["offset"]] = rec["chunk"]
        w["files"].append(name)
    return windows


def assemble(label: str, w: dict) -> str:
    slice_chars = max(len(c) for c in w["chunks"].values())
    expected = list(range(1, w["payload_len"] + 1, slice_chars))
    missing = [off for off in expected if off not in w["chunks"]]
    if missing:
        raise SystemExit(f"{label}: missing slices at offsets {missing}")
    extra = sorted(set(w["chunks"]) - set(expected))
    if extra:
        raise SystemExit(f"{label}: unexpected slice offsets {extra}")
    payload = "".join(w["chunks"][off] for off in expected)
    if len(payload) != w["payload_len"]:
        raise SystemExit(f"{label}: assembled {len(payload)} chars, expected {w['payload_len']}")
    md5 = hashlib.md5(payload.encode("ascii")).hexdigest()
    if md5 != w["payload_md5"]:
        raise SystemExit(f"{label}: md5 {md5} != expected {w['payload_md5']} — re-pull this window")
    return payload


def parse_payload(label: str, payload: str) -> tuple[pd.DataFrame, dict, dict]:
    lines = payload.split("\n")
    version, n_lines, n_checks, start, end, max_off = lines[0].split(",")
    if version != f"v{EXTRACT_VERSION}":
        raise SystemExit(f"{label}: unexpected payload version {version}")
    if int(max_off) != MAX_OFFSET:
        raise SystemExit(f"{label}: payload max offset {max_off} != {MAX_OFFSET}")
    body = lines[1:]
    cell_lines = [ln for ln in body if not ln.startswith("#M,")]
    check_lines = [ln for ln in body if ln.startswith("#M,")]
    if len(cell_lines) != int(n_lines):
        raise SystemExit(f"{label}: {len(cell_lines)} series-month lines, header says {n_lines}")
    if len(check_lines) != int(n_checks):
        raise SystemExit(f"{label}: {len(check_lines)} check lines, header says {n_checks}")

    records = []
    for ln in cell_lines:
        series_id, pmonth, cells = ln.split("|")
        for cell in cells.split(";"):
            off, ore = cell.split(":")
            records.append((series_id, pmonth, int(off), int(ore)))
    frame = pd.DataFrame(records, columns=["series_id", "posting_month", "create_offset", "ore"])
    if not ((frame["create_offset"] >= 0) & (frame["create_offset"] <= MAX_OFFSET)).all():
        raise SystemExit(f"{label}: create_offset outside [0, {MAX_OFFSET}]")

    checks = {}
    for ln in check_lines:
        _, pmonth, ore, n_src_lines = ln.split(",")
        checks[pmonth] = {"ore": int(ore), "source_lines": int(n_src_lines)}
    return frame, checks, {"start": start, "end": end}


def months_between(start: str, end_exclusive: str) -> list[str]:
    rng = pd.period_range(start=start, end=pd.Timestamp(end_exclusive) - pd.Timedelta(days=1),
                          freq="M")
    return [str(p) for p in rng]


def main() -> None:
    windows = load_captures()
    expected_labels = {label for label, _, _ in WINDOWS}
    if set(windows) != expected_labels:
        raise SystemExit(f"captured windows {sorted(windows)} != expected {sorted(expected_labels)}")

    frames, all_checks, manifest_windows = [], {}, {}
    for label, exp_start, exp_end in WINDOWS:
        payload = assemble(label, windows[label])
        frame, checks, bounds = parse_payload(label, payload)
        if (bounds["start"], bounds["end"]) != (exp_start, exp_end):
            raise SystemExit(
                f"{label}: payload window {bounds} != configured ({exp_start}, {exp_end})")
        want_months = months_between(exp_start, exp_end)
        if sorted(checks) != want_months:
            raise SystemExit(f"{label}: check months {sorted(checks)} != {want_months}")
        if sorted(frame["posting_month"].unique()) != want_months:
            raise SystemExit(f"{label}: cell months do not cover {want_months}")
        overlap = set(checks) & set(all_checks)
        if overlap:
            raise SystemExit(f"{label}: months {sorted(overlap)} already covered by another window")
        frames.append(frame)
        all_checks.update(checks)
        manifest_windows[label] = {
            "start": exp_start,
            "end_exclusive": exp_end,
            "payload_len": windows[label]["payload_len"],
            "payload_md5": windows[label]["payload_md5"],
            "n_slices": len(windows[label]["chunks"]),
            "series_month_lines": int(len(frame.groupby(["series_id", "posting_month"]))),
            "cells": int(len(frame)),
            "source_invoice_lines": int(sum(c["source_lines"] for c in checks.values())),
        }
        print(f"{label}: OK  payload={windows[label]['payload_len']}  cells={len(frame)}")

    # coverage: the windows must tile the snapshot's month range exactly
    want_all = months_between(f"{FIRST_MONTH}-01",
                              str((pd.Period(LAST_MONTH, freq="M") + 1).start_time.date()))
    if sorted(all_checks) != want_all:
        missing = sorted(set(want_all) - set(all_checks))
        extra = sorted(set(all_checks) - set(want_all))
        raise SystemExit(f"month coverage broken: missing={missing} extra={extra}")

    data = pd.concat(frames, ignore_index=True)

    # semantics: series totals per month must equal the independently grouped totals
    got = data.groupby("posting_month")["ore"].sum()
    bad = {m: (int(got.get(m, 0)), all_checks[m]["ore"])
           for m in want_all if int(got.get(m, 0)) != all_checks[m]["ore"]}
    if bad:
        raise SystemExit(f"month totals disagree with the independent check (got, expected): {bad}")
    print(f"month totals: all {len(want_all)} months match the independent aggregation exactly")

    # membership: no series outside the frozen split
    known = set(series_ids())
    unknown = sorted(set(data["series_id"]) - known)
    if unknown:
        raise SystemExit(f"unknown series ids in payload: {unknown}")

    data = data.sort_values(["series_id", "posting_month", "create_offset"]).reset_index(drop=True)
    data["series_id"] = data["series_id"].astype("category")
    data["create_offset"] = data["create_offset"].astype("int16")
    data["ore"] = data["ore"].astype("int64")

    settled = data.groupby(["series_id", "posting_month"], observed=True)["ore"].sum()
    first_month = {}
    for (series_id, pmonth), ore in settled.items():
        if ore != 0 and series_id not in first_month:
            first_month[series_id] = pmonth

    with open(MEMBERSHIP_CSV, newline="", encoding="utf-8") as fh:
        members = list(csv.DictReader(fh))
    customers = [m for m in members if m["series_id"].startswith("c_")]
    groups: dict[str, list[int]] = defaultdict(list)
    for m in members:
        if not m["series_id"].startswith("c_"):
            groups[m["series_id"]].append(int(m["core_account_id"]))

    series_meta = {
        "snapshot_taken": SNAPSHOT_TAKEN,
        "first_month": FIRST_MONTH,
        "last_month": LAST_MONTH,
        "max_create_offset": MAX_OFFSET,
        "target_definition": (
            f"net sales invoiced excl. VAT in DKK, SUM({AMOUNT_COL}) over {SOURCE_TABLE}, "
            "attributed to the calendar month of POSTING_DATE (the invoice posting date). "
            "Credit notes and corrections net out; deleted invoices and invoice lines are "
            "already excluded upstream by the mart. Amounts are stored as integer oere."
        ),
        "triangle_definition": (
            "create_offset = days from the first of the posting month to "
            "DATE(INVOICE_LINE_CREATED_AT), clipped into [0, max_create_offset]. Summing "
            "increments with create_offset <= (cutoff - month start) reproduces exactly what "
            "a nightly job would have seen on the night of that cutoff; summing all "
            "increments gives the settled month total."
        ),
        "known_limitation": (
            "reconstructed from one point-in-time snapshot: invoice lines that existed on a "
            "past night but were later deleted are absent from the mart entirely, so the "
            "as-of view can slightly understate what was visible at the time."
        ),
        "membership_note": (
            "identical to the shipment snapshot's frozen split (data/extract/membership.csv): "
            "top-100 customers of the reference window 2025-08-06..2026-08-05 by shipments, "
            f"remaining ranked accounts in bands g1..g4, {CATCH_ALL} catching everything else. "
            "The 105 series partition network invoiced sales exactly."
        ),
        "series": [
            {
                "series_id": c["series_id"],
                "kind": "customer",
                "core_account_id": int(c["core_account_id"]),
                "name": c["name"],
                "rank": int(c["rank"]),
                "shipment_first_date": c["first_date"],
                "first_invoiced_month": first_month.get(c["series_id"]),
            }
            for c in sorted(customers, key=lambda r: int(r["rank"]))
        ]
        + [
            {
                "series_id": gid,
                "kind": "tail_group",
                "member_account_ids": sorted(ids),
                "n_members_ranked": len(ids),
                "first_invoiced_month": first_month.get(gid),
            }
            for gid, ids in sorted(groups.items())
        ]
        + [
            {
                "series_id": CATCH_ALL,
                "kind": "tail_group",
                "member_account_ids": "all accounts not otherwise listed",
                "first_invoiced_month": first_month.get(CATCH_ALL),
            }
        ],
    }
    listed = {s["series_id"] for s in series_meta["series"]}
    if listed != known:
        raise SystemExit(f"series_meta lists {len(listed)} series, expected {len(known)}")

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    parquet_path = os.path.join(SNAPSHOT_DIR, "monthly_sales_triangle.parquet")
    data.to_parquet(parquet_path, index=False, compression="zstd")
    with open(os.path.join(SNAPSHOT_DIR, "series_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(series_meta, fh, indent=2, ensure_ascii=False)

    manifest = {
        "extract_version": EXTRACT_VERSION,
        "snapshot_taken": SNAPSHOT_TAKEN,
        "built_from": "data/raw_sales/mcp_results (captured Snowflake MCP results)",
        "source_table": SOURCE_TABLE,
        "amount_column": AMOUNT_COL,
        "windows": manifest_windows,
        "months": len(want_all),
        "rows": int(len(data)),
        "series": int(data["series_id"].nunique()),
        "series_expected": len(known),
        "grand_total_ore": int(data["ore"].sum()),
        "month_totals_ore": {m: all_checks[m]["ore"] for m in want_all},
        "source_invoice_lines": int(sum(c["source_lines"] for c in all_checks.values())),
        "parquet_sha256": hashlib.sha256(open(parquet_path, "rb").read()).hexdigest(),
    }
    with open(os.path.join(SNAPSHOT_DIR, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    total_dkk = data["ore"].sum() / 100
    print(f"\nsnapshot written: {parquet_path}")
    print(f"rows={len(data):,}  series={data['series_id'].nunique()}  months={len(want_all)}"
          f"  total={total_dkk:,.0f} DKK")
    print(f"series never invoiced in the window: "
          f"{sorted(known - set(first_month))}")


if __name__ == "__main__":
    main()
