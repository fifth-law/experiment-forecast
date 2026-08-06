#!/usr/bin/env python3
"""Generate the one-off Snowflake extraction artifacts for the frozen snapshot.

The snapshot freeze works in phases (see data/extract/README.md):

  1. Membership was captured from three marked queries (/*SNAPMETA .../)
     whose raw results sit in data/raw/mcp_results/.  `--emit-membership`
     turns them into data/extract/membership.csv — the canonical, hardcoded
     account -> series mapping used by every later query, immune to live
     drift in the mart.

  2. `--emit-year-sql` writes meta_<year>.sql (payload length + md5) and
     totals_<year>.sql (independent per-series totals for validation).

  3. After the meta results are in, `--emit-slices <year> <payload_len>`
     writes slice_<offset>.sql files that SUBSTR the deterministic payload
     into <= SLICE_CHARS chunks. Subagents execute them; a PostToolUse hook
     saves every result to data/raw/mcp_results/ verbatim.

  4. data/extract/build_snapshot.py reassembles, validates and writes the
     frozen parquet under data/snapshot/.

Series design (decided 2026-08-06, see README.md):
  - c_<core_account_id>: the 100 largest customers by outbound non-cancelled
    shipments in the reference window 2025-08-06..2026-08-05.
  - g1_tail..g4_tail: cumulative-volume quintile bands of the remaining
    ranked accounts (ranks 101-116, 117-137, 138-170, 171-270).
  - g5_tail: every other account (rank > 270 or not active in the reference
    window). Together the 105 series partition total network volume exactly.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MCP_RESULTS_DIR = os.path.join(REPO, "data", "raw", "mcp_results")
MEMBERSHIP_CSV = os.path.join(HERE, "membership.csv")
SQL_DIR = os.path.join(HERE, "sql")

EXTRACT_VERSION = 2  # v2: dropped RETURN_AT IS NULL from the filters (owner decision
# 2026-08-06): an outbound shipment that later comes back as a passive return still
# shipped, so it counts. Booked returns and cancellations stay excluded.
SLICE_CHARS = 40_000
SNAPSHOT_START = "2021-01-01"
SNAPSHOT_END = "2026-08-05"
REF_WINDOW = ("2025-08-06", "2026-08-05")
# Tail group rank boundaries (inclusive upper rank), derived from the
# cumulative-volume quintile query captured as /*SNAPMETA name=tail_groups v=2*/
TAIL_BOUNDS = [(116, "g1_tail"), (138, "g2_tail"), (170, "g3_tail"), (270, "g4_tail")]
CATCH_ALL = "g5_tail"

SHIPMENT_FILTERS = "s.IS_BOOKED_RETURN = FALSE AND s.CANCEL_AT IS NULL"

YEARS = [
    (2021, "2021-01-01", "2021-12-31"),
    (2022, "2022-01-01", "2022-12-31"),
    (2023, "2023-01-01", "2023-12-31"),
    (2024, "2024-01-01", "2024-12-31"),
    (2025, "2025-01-01", "2025-12-31"),
    (2026, "2026-01-01", SNAPSHOT_END),
]


def _load_marked_result(marker: str) -> list[list[str]]:
    """Find the hook-captured MCP result whose SQL contains `marker`."""
    matches = []
    for name in sorted(os.listdir(MCP_RESULTS_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(MCP_RESULTS_DIR, name)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if marker in doc.get("tool_input", {}).get("sql", ""):
            payload = json.loads(doc["tool_response"][0]["text"])
            matches.append((name, payload["result_set"]["data"]))
    if not matches:
        raise SystemExit(f"no captured result found for marker {marker!r}")
    if len(matches) > 1:
        names = ", ".join(n for n, _ in matches)
        raise SystemExit(f"marker {marker!r} matched multiple captures: {names}")
    return matches[0][1]


def emit_membership() -> None:
    top100 = _load_marked_result(f"SNAPMETA name=top100 v={EXTRACT_VERSION}")
    tail = _load_marked_result(f"SNAPMETA name=member_map_tail v={EXTRACT_VERSION}")
    first = dict(_load_marked_result(f"SNAPMETA name=first_dates v={EXTRACT_VERSION}"))

    rows = []
    for acct, name, n_ref, rk in top100:
        rows.append(
            {
                "core_account_id": int(acct),
                "series_id": f"c_{acct}",
                "rank": int(rk),
                "n_ref": int(n_ref),
                "name": name,
                "first_date": first.get(acct, ""),
            }
        )
    for acct, rk in tail:
        rank = int(rk)
        series = CATCH_ALL
        for bound, gid in TAIL_BOUNDS:
            if rank <= bound:
                series = gid
                break
        rows.append(
            {
                "core_account_id": int(acct),
                "series_id": series,
                "rank": rank,
                "n_ref": "",
                "name": "",
                "first_date": "",
            }
        )

    with open(MEMBERSHIP_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["core_account_id", "series_id", "rank", "n_ref", "name", "first_date"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {MEMBERSHIP_CSV} ({len(rows)} accounts)")


def _member_values() -> str:
    with open(MEMBERSHIP_CSV, newline="", encoding="utf-8") as fh:
        pairs = [(r["core_account_id"], r["series_id"]) for r in csv.DictReader(fh)]
    if len(pairs) != 270:
        raise SystemExit(f"membership.csv has {len(pairs)} accounts, expected 270")
    return ",".join(f"({acct},'{series}')" for acct, series in pairs)


def _payload_ctes(year: int, start: str, end: str) -> str:
    return f"""WITH member(core_account_id, series_id) AS (
  SELECT * FROM VALUES {_member_values()}
),
spine AS (
  SELECT d FROM (
    SELECT DATEADD(day, ROW_NUMBER() OVER (ORDER BY NULL) - 1, DATE '{start}') AS d
    FROM TABLE(GENERATOR(ROWCOUNT => 370))
  ) WHERE d <= DATE '{end}'
),
serieslist AS (
  SELECT DISTINCT series_id FROM member UNION SELECT '{CATCH_ALL}'
),
daily AS (
  SELECT s.CREATED_AT_DATE AS d, COALESCE(m.series_id, '{CATCH_ALL}') AS series_id, COUNT(*) AS cnt
  FROM MARTS.ANALYTICS.SHIPMENTS s
  LEFT JOIN member m ON s.CORE_ACCOUNT_ID = m.core_account_id
  WHERE s.CREATED_AT_DATE BETWEEN '{start}' AND '{end}'
    AND {SHIPMENT_FILTERS}
  GROUP BY 1, 2
),
dense AS (
  SELECT sp.d, sl.series_id, COALESCE(dl.cnt, 0) AS cnt
  FROM spine sp
  CROSS JOIN serieslist sl
  LEFT JOIN daily dl ON dl.d = sp.d AND dl.series_id = sl.series_id
),
lines AS (
  SELECT series_id || ',' || LISTAGG(TO_VARCHAR(cnt), ',') WITHIN GROUP (ORDER BY d) AS line
  FROM dense GROUP BY series_id
),
payload AS (
  -- NB: LISTAGG's delimiter must be a compile-time constant in Snowflake;
  -- CHR(10) is rejected there, so use the backslash-n escape literal instead.
  SELECT 'v{EXTRACT_VERSION},' || TO_VARCHAR((SELECT COUNT(*) FROM serieslist)) || ','
         || TO_VARCHAR((SELECT COUNT(*) FROM spine)) || ',{start},{end}\\n'
         || LISTAGG(line, '\\n') WITHIN GROUP (ORDER BY line) AS p
  FROM lines
)"""


def emit_year_sql() -> None:
    os.makedirs(SQL_DIR, exist_ok=True)
    for year, start, end in YEARS:
        ctes = _payload_ctes(year, start, end)
        meta = (
            f"/*SNAP kind=meta y={year} v={EXTRACT_VERSION}*/\n"
            f"{ctes}\nSELECT LENGTH(p) AS PLEN, MD5(p) AS PMD5 FROM payload"
        )
        totals = (
            f"/*SNAP kind=totals y={year} v={EXTRACT_VERSION}*/\n"
            f"{ctes}\nSELECT series_id AS SERIES_ID, TO_VARCHAR(SUM(cnt)) AS TOTAL,"
            f" TO_VARCHAR(COUNT(*)) AS NDAYS FROM dense GROUP BY 1 ORDER BY 1"
        )
        with open(os.path.join(SQL_DIR, f"meta_{year}.sql"), "w", encoding="utf-8") as fh:
            fh.write(meta)
        with open(os.path.join(SQL_DIR, f"totals_{year}.sql"), "w", encoding="utf-8") as fh:
            fh.write(totals)
    print(f"wrote meta/totals SQL for {len(YEARS)} years under {SQL_DIR}")


def emit_slices(year: int, payload_len: int) -> None:
    match = [(y, s, e) for y, s, e in YEARS if y == year]
    if not match:
        raise SystemExit(f"unknown year {year}")
    _, start, end = match[0]
    year_dir = os.path.join(SQL_DIR, str(year))
    os.makedirs(year_dir, exist_ok=True)
    ctes = _payload_ctes(year, start, end)
    offsets = list(range(1, payload_len + 1, SLICE_CHARS))
    for off in offsets:
        sql = (
            f"/*SNAP kind=slice y={year} off={off} v={EXTRACT_VERSION}*/\n"
            f"{ctes}\nSELECT SUBSTR(p, {off}, {SLICE_CHARS}) AS CHUNK FROM payload"
        )
        with open(os.path.join(year_dir, f"slice_{off:07d}.sql"), "w", encoding="utf-8") as fh:
            fh.write(sql)
    print(f"wrote {len(offsets)} slice files for {year} under {year_dir}")


def emit_slices_from_captures() -> None:
    """Read hook-captured meta results and emit slice SQL for every year."""
    import re

    marker = re.compile(rf"/\*SNAP kind=meta y=(\d{{4}}) v={EXTRACT_VERSION}\*/")
    found = {}
    for name in sorted(os.listdir(os.path.join(REPO, "data", "raw", "mcp_results"))):
        if not name.endswith(".json"):
            continue
        path = os.path.join(REPO, "data", "raw", "mcp_results", name)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        m = marker.search(doc.get("tool_input", {}).get("sql", ""))
        if m:
            data = json.loads(doc["tool_response"][0]["text"])["result_set"]["data"]
            found[int(m.group(1))] = int(data[0][0])
    for year, _, _ in YEARS:
        if year not in found:
            print(f"{year}: no meta capture yet — skipped")
            continue
        emit_slices(year, found[year])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-membership", action="store_true")
    parser.add_argument("--emit-year-sql", action="store_true")
    parser.add_argument("--emit-slices", nargs=2, metavar=("YEAR", "PAYLOAD_LEN"), type=int)
    parser.add_argument("--emit-slices-from-captures", action="store_true")
    args = parser.parse_args()
    if args.emit_membership:
        emit_membership()
    if args.emit_year_sql:
        emit_year_sql()
    if args.emit_slices:
        emit_slices(args.emit_slices[0], args.emit_slices[1])
    if args.emit_slices_from_captures:
        emit_slices_from_captures()
    if not (
        args.emit_membership
        or args.emit_year_sql
        or args.emit_slices
        or args.emit_slices_from_captures
    ):
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
