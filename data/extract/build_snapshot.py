#!/usr/bin/env python3
"""Assemble and validate the frozen snapshot from hook-captured MCP results.

Reads every JSON dump in data/raw/mcp_results/, reassembles each year's
payload from its SUBSTR slices, and enforces three independent checks before
anything is written:

  1. transport: reassembled payload length and MD5 must equal the values the
     meta_<year>.sql query reported from inside Snowflake;
  2. shape: payload declares its own series and day counts in the header;
  3. semantics: per-series yearly totals in the parsed dataframe must equal
     the independently queried totals_<year>.sql results.

Outputs (committed, the eval's only data source):
  data/snapshot/daily_shipments.parquet   long format: date, series_id, y
  data/snapshot/series_meta.json          series catalogue + provenance
  data/snapshot/MANIFEST.json             checksums and validation record
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MCP_RESULTS_DIR = os.path.join(REPO, "data", "raw", "mcp_results")
MEMBERSHIP_CSV = os.path.join(HERE, "membership.csv")
SNAPSHOT_DIR = os.path.join(REPO, "data", "snapshot")

sys.path.insert(0, HERE)
from gen_extract_sql import (  # noqa: E402
    CATCH_ALL,
    EXTRACT_VERSION,
    REF_WINDOW,
    SLICE_CHARS,
    SNAPSHOT_END,
    SNAPSHOT_START,
    TAIL_BOUNDS,
    YEARS,
)

MARKER_RE = re.compile(r"/\*SNAP kind=(\w+) y=(\d{4})(?: off=(\d+))? v=(\d+)\*/")


def load_captures():
    metas, slices, totals = {}, defaultdict(dict), {}
    for name in sorted(os.listdir(MCP_RESULTS_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(MCP_RESULTS_DIR, name), encoding="utf-8") as fh:
            doc = json.load(fh)
        sql = doc.get("tool_input", {}).get("sql", "")
        m = MARKER_RE.search(sql)
        if not m:
            continue
        kind, year, off, version = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
        if version != EXTRACT_VERSION:
            continue
        data = json.loads(doc["tool_response"][0]["text"])["result_set"]["data"]
        if kind == "meta":
            metas[year] = {"plen": int(data[0][0]), "pmd5": data[0][1], "file": name}
        elif kind == "slice":
            slices[year][int(off)] = data[0][0]
        elif kind == "totals":
            totals[year] = {row[0]: int(row[1]) for row in data}
    return metas, slices, totals


def assemble_year(year: int, meta: dict, year_slices: dict[int, str]) -> str:
    expected_offsets = list(range(1, meta["plen"] + 1, SLICE_CHARS))
    missing = [off for off in expected_offsets if off not in year_slices]
    if missing:
        raise SystemExit(f"{year}: missing slices at offsets {missing}")
    payload = "".join(year_slices[off] for off in expected_offsets)
    if len(payload) != meta["plen"]:
        raise SystemExit(f"{year}: length {len(payload)} != expected {meta['plen']}")
    md5 = hashlib.md5(payload.encode("ascii")).hexdigest()
    if md5 != meta["pmd5"]:
        raise SystemExit(f"{year}: md5 {md5} != expected {meta['pmd5']} (re-extract this year)")
    return payload


def parse_year(year: int, payload: str) -> pd.DataFrame:
    lines = payload.split("\n")
    header = lines[0].split(",")
    version, n_series, n_days, start, end = (
        header[0], int(header[1]), int(header[2]), header[3], header[4],
    )
    if version != f"v{EXTRACT_VERSION}":
        raise SystemExit(f"{year}: unexpected payload version {version}")
    if len(lines) - 1 != n_series:
        raise SystemExit(f"{year}: {len(lines) - 1} series lines, header says {n_series}")
    dates = pd.date_range(start, end, freq="D")
    if len(dates) != n_days:
        raise SystemExit(f"{year}: date spine {len(dates)} != header {n_days}")
    frames = []
    for line in lines[1:]:
        series_id, *values = line.split(",")
        if len(values) != n_days:
            raise SystemExit(f"{year}/{series_id}: {len(values)} values != {n_days} days")
        frames.append(
            pd.DataFrame({"date": dates, "series_id": series_id, "y": [int(v) for v in values]})
        )
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    metas, slices, totals = load_captures()
    missing_years = [y for y, _, _ in YEARS if y not in metas or y not in totals]
    if missing_years:
        raise SystemExit(f"missing meta/totals captures for years {missing_years}")

    year_frames, manifest_years = [], {}
    for year, start, end in YEARS:
        payload = assemble_year(year, metas[year], slices[year])
        df = parse_year(year, payload)
        got_totals = df.groupby("series_id")["y"].sum().to_dict()
        expected = totals[year]
        if set(got_totals) != set(expected):
            raise SystemExit(f"{year}: series set mismatch vs totals query")
        bad = {s: (got_totals[s], expected[s]) for s in expected if got_totals[s] != expected[s]}
        if bad:
            raise SystemExit(f"{year}: totals mismatch (parsed, expected): {bad}")
        year_frames.append(df)
        manifest_years[year] = {
            "start": start,
            "end": end,
            "payload_len": metas[year]["plen"],
            "payload_md5": metas[year]["pmd5"],
            "n_slices": len(range(1, metas[year]["plen"] + 1, SLICE_CHARS)),
            "total_shipments": int(sum(expected.values())),
        }
        print(f"{year}: OK  len={metas[year]['plen']}  total={sum(expected.values()):,}")

    data = pd.concat(year_frames, ignore_index=True).sort_values(["date", "series_id"])
    data = data.reset_index(drop=True)
    data["series_id"] = data["series_id"].astype("category")
    data["y"] = data["y"].astype("int32")

    with open(MEMBERSHIP_CSV, newline="", encoding="utf-8") as fh:
        members = list(csv.DictReader(fh))
    customers = [m for m in members if m["series_id"].startswith("c_")]
    groups = defaultdict(list)
    for m in members:
        if not m["series_id"].startswith("c_"):
            groups[m["series_id"]].append(int(m["core_account_id"]))

    series_meta = {
        "snapshot_start": SNAPSHOT_START,
        "snapshot_end": SNAPSHOT_END,
        "reference_window": {"start": REF_WINDOW[0], "end": REF_WINDOW[1]},
        "target_definition": (
            "daily count of shipments by CREATED_AT_DATE from MARTS.ANALYTICS.SHIPMENTS "
            "with IS_BOOKED_RETURN=FALSE AND RETURN_AT IS NULL AND CANCEL_AT IS NULL"
        ),
        "membership_note": (
            "top-100 customers by shipments in the reference window; remaining ranked "
            "accounts grouped into cumulative-volume quintile bands g1..g4 by rank "
            f"bounds {TAIL_BOUNDS}; {CATCH_ALL} catches rank>270 and accounts not "
            "active in the reference window. Membership is frozen; series partition "
            "total network volume exactly."
        ),
        "series": [
            {
                "series_id": c["series_id"],
                "kind": "customer",
                "core_account_id": int(c["core_account_id"]),
                "name": c["name"],
                "rank": int(c["rank"]),
                "n_ref": int(c["n_ref"]),
                "first_date": c["first_date"],
            }
            for c in sorted(customers, key=lambda r: int(r["rank"]))
        ]
        + [
            {
                "series_id": gid,
                "kind": "tail_group",
                "member_account_ids": sorted(ids),
                "n_members_ranked": len(ids),
                "first_date": SNAPSHOT_START,
            }
            for gid, ids in sorted(groups.items())
        ]
        + [
            {
                "series_id": CATCH_ALL,
                "kind": "tail_group",
                "member_account_ids": "all accounts not otherwise listed",
                "first_date": SNAPSHOT_START,
            }
        ],
    }

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    parquet_path = os.path.join(SNAPSHOT_DIR, "daily_shipments.parquet")
    data.to_parquet(parquet_path, index=False, compression="zstd")

    with open(os.path.join(SNAPSHOT_DIR, "series_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(series_meta, fh, indent=2, ensure_ascii=False)

    manifest = {
        "extract_version": EXTRACT_VERSION,
        "built_from": "data/raw/mcp_results (hook-captured Snowflake MCP results)",
        "years": manifest_years,
        "rows": int(len(data)),
        "series": int(data["series_id"].nunique()),
        "grand_total_shipments": int(data["y"].sum()),
        "parquet_sha256": hashlib.sha256(open(parquet_path, "rb").read()).hexdigest(),
    }
    with open(os.path.join(SNAPSHOT_DIR, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"\nsnapshot written: {parquet_path}")
    print(f"rows={len(data):,}  series={data['series_id'].nunique()}  total={data['y'].sum():,}")


if __name__ == "__main__":
    main()
