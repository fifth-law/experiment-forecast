#!/usr/bin/env python3
"""Generate the Snowflake extraction artifacts for the monthly sales-invoiced snapshot.

The metric: **net sales invoiced (excl. VAT, DKK) attributed to a calendar
month by invoice POSTING_DATE**, per series, on the *frozen* 105-series split
of the shipment snapshot (data/extract/membership.csv — unchanged, so the two
forecasting tracks are directly comparable).

Why a triangle and not a plain monthly series: ~90% of a month's invoice lines
post on the last day of that month, and in the modern era a large part of them
only *exist in the data* days-to-weeks later (measured on posting month
2026-06: ~71% of the month's DKK was created during the month, ~3% within
+7 days of month end, ~27% at +8..+15 days). A nightly forecaster therefore
cannot see the settled total of the month it is forecasting — nor even last
month's. To keep the backtest point-in-time honest, the snapshot stores
*increments* on two axes:

    (series_id, posting_month, create_offset) -> oere (integer)

where create_offset = days from the first of the posting month to
DATE(INVOICE_LINE_CREATED_AT), clipped into [0, MAX_OFFSET]. The eval
reconstructs "what was visible on the night of day c" by summing every
increment whose create date is <= c, and scores against the settled total.

Transfer works like the shipment snapshot (see data/extract/README.md): a
deterministic text payload is built inside Snowflake, a meta query takes its
LENGTH+MD5, then SUBSTR slices are pulled through the MCP connector and
reassembled + validated locally by build_sales_snapshot.py. Each payload
carries a `#M` trailer of per-month totals aggregated by a second, independent
path (no series mapping, no offset axis) so the semantic check travels inside
the MD5-protected bytes and nothing is transcribed by hand.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MEMBERSHIP_CSV = os.path.join(REPO, "data", "extract", "membership.csv")
SQL_DIR = os.path.join(HERE, "sql")

EXTRACT_VERSION = 1
SLICE_CHARS = 200_000  # payload chars per slice
PAD_CHARS = 200_000    # filler that pushes each result over the inline-render limit

SOURCE_TABLE = "MARTS.ANALYTICS.SALES_INVOICE_DETAILS"
AMOUNT_COL = "SALES_PRICE_EXCL_VAT_IN_DKK"

# Posting months covered. The last month must be *settled*: this snapshot was
# taken 2026-08-10, when 2026-07 was still ~1/3 short of its final total (the
# +8..+15d creation wave had not landed yet), so 2026-07 is excluded.
FIRST_MONTH = "2021-01"
LAST_MONTH = "2026-06"

# Creation-date axis, in days from the first of the posting month. Earlier than
# the month start clips to 0; later than MAX_OFFSET clips to MAX_OFFSET, i.e.
# "only visible well after the month closed". The probe query confirms the clip
# is harmless: 0.00% of DKK is created beyond +120 days in any year.
MAX_OFFSET = 120

CATCH_ALL = "g5_tail"

# Extraction windows: (label, start, end-exclusive). One payload per window,
# and the windows must tile FIRST_MONTH..LAST_MONTH exactly — build_sales_snapshot.py
# checks that from the payload headers themselves. A year at a time works for
# 2021-2024; 2025 is the heaviest year in the mart (~96M lines) and needs halves
# to stay inside the connector's 60s budget.
WINDOWS = [
    ("2021", "2021-01-01", "2022-01-01"),
    ("2022", "2022-01-01", "2023-01-01"),
    ("2023", "2023-01-01", "2024-01-01"),
    ("2024", "2024-01-01", "2025-01-01"),
    ("2025H1", "2025-01-01", "2025-07-01"),
    ("2025H2", "2025-07-01", "2026-01-01"),
    ("2026", "2026-01-01", "2026-07-01"),
]


def window(label: str) -> tuple[str, str]:
    for lbl, start, end in WINDOWS:
        if lbl == label:
            return start, end
    raise SystemExit(f"unknown window {label!r}; known: {[w[0] for w in WINDOWS]}")


def full_window() -> tuple[str, str]:
    return WINDOWS[0][1], WINDOWS[-1][2]


def _members() -> list[dict]:
    with open(MEMBERSHIP_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if len(rows) != 270:
        raise SystemExit(f"membership.csv has {len(rows)} accounts, expected 270")
    return rows


def series_ids() -> list[str]:
    """The 105 frozen series ids."""
    return sorted({r["series_id"] for r in _members()} | {CATCH_ALL})


def series_case() -> str:
    """SQL CASE mapping CORE_ACCOUNT_ID -> series_id, from the frozen membership.

    Compact on purpose: id lists rather than 270 VALUES tuples, so the whole
    mapping fits comfortably inside every extraction query.
    """
    rows = _members()
    top = [r["core_account_id"] for r in rows if r["series_id"].startswith("c_")]
    groups: dict[str, list[str]] = {}
    for r in rows:
        if not r["series_id"].startswith("c_"):
            groups.setdefault(r["series_id"], []).append(r["core_account_id"])
    parts = [f"CASE WHEN s.CORE_ACCOUNT_ID IN ({','.join(top)})"
             " THEN 'c_' || TO_VARCHAR(s.CORE_ACCOUNT_ID)"]
    for gid in sorted(groups):
        parts.append(f"WHEN s.CORE_ACCOUNT_ID IN ({','.join(sorted(groups[gid]))}) THEN '{gid}'")
    parts.append(f"ELSE '{CATCH_ALL}' END")
    return "\n       ".join(parts)


def payload_ctes(start: str, end_exclusive: str) -> str:
    """CTE pipeline building one deterministic payload for a posting-date window.

    Both aggregation levels come out of a single table scan via GROUPING SETS —
    the source table is ~262M rows and a second scan for the check totals blows
    the connector's 60s budget. The month-level grouping set still ignores the
    series mapping entirely, so it remains a real cross-check that the 105
    series partition the network exactly.
    """
    return f"""WITH base AS ( -- SALES v{EXTRACT_VERSION}
  SELECT {series_case()} AS series_id,
         TO_CHAR(DATE_TRUNC('month', s.POSTING_DATE), 'YYYY-MM') AS pmonth,
         LEAST(GREATEST(DATEDIFF(
             day,
             DATE_TRUNC('month', s.POSTING_DATE),
             COALESCE(DATE(s.INVOICE_LINE_CREATED_AT), s.POSTING_DATE)
         ), 0), {MAX_OFFSET}) AS coff,
         ROUND(s.{AMOUNT_COL} * 100) AS ore
  FROM {SOURCE_TABLE} s
  WHERE s.POSTING_DATE >= DATE '{start}' AND s.POSTING_DATE < DATE '{end_exclusive}'
),
agg AS (
  -- integer oere, not float DKK: float SUM is order-dependent, so a rounded
  -- float total is not reproducible run to run (nor across aggregation paths),
  -- which would make the payload MD5 useless as a transport check. Every line
  -- amount is an exact 2-decimal value, so oere sums are exact in a double
  -- (max |sum| here is ~5e9, well under 2^53) and order no longer matters.
  SELECT pmonth, series_id, coff, SUM(ore) AS ore, COUNT(*) AS n_lines,
         GROUPING(series_id) AS g_series
  FROM base
  GROUP BY GROUPING SETS ((pmonth, series_id, coff), (pmonth))
),
cells AS (
  SELECT pmonth, series_id, coff, ore FROM agg WHERE g_series = 0 AND ore <> 0
),
lines AS (
  SELECT series_id || '|' || pmonth || '|' ||
         LISTAGG(TO_VARCHAR(coff) || ':' || TO_VARCHAR(ore), ';')
           WITHIN GROUP (ORDER BY coff) AS line
  FROM cells GROUP BY series_id, pmonth
),
checklines AS (
  -- independent path: month totals with no series mapping and no offset axis
  SELECT '#M,' || pmonth || ',' || TO_VARCHAR(ore) || ',' || TO_VARCHAR(n_lines) AS line
  FROM agg WHERE g_series = 1
),
payload AS (
  -- LISTAGG needs a constant delimiter; Snowflake rejects CHR(10) there, so
  -- the backslash-n escape literal is used (same trick as the shipment extract).
  SELECT 'v{EXTRACT_VERSION},' || TO_VARCHAR((SELECT COUNT(*) FROM lines)) || ','
         || TO_VARCHAR((SELECT COUNT(*) FROM checklines)) || ','
         || '{start},{end_exclusive},{MAX_OFFSET}\\n'
         || LISTAGG(line, '\\n') WITHIN GROUP (ORDER BY line)
         || '\\n' || (SELECT LISTAGG(line, '\\n') WITHIN GROUP (ORDER BY line) FROM checklines) AS p
  FROM lines
)"""


def emit_probe() -> str:
    """One query sizing the extraction and checking the MAX_OFFSET clip."""
    start, end = full_window()
    return f"""WITH cells AS ( /*SALES kind=probe v={EXTRACT_VERSION}*/
  SELECT {series_case()} AS series_id,
         TO_CHAR(DATE_TRUNC('month', s.POSTING_DATE), 'YYYY-MM') AS pmonth,
         DATEDIFF(day, DATE_TRUNC('month', s.POSTING_DATE),
                  COALESCE(DATE(s.INVOICE_LINE_CREATED_AT), s.POSTING_DATE)) AS coff_raw,
         SUM(s.{AMOUNT_COL}) AS dkk,
         COUNT_IF(s.INVOICE_LINE_CREATED_AT IS NULL) AS n_null_created,
         COUNT(*) AS n_lines
  FROM {SOURCE_TABLE} s
  WHERE s.POSTING_DATE >= DATE '{start}' AND s.POSTING_DATE < DATE '{end}'
  GROUP BY 1, 2, 3
)
SELECT LEFT(pmonth, 4) AS PYEAR,
       COUNT(*) AS N_CELLS_RAW,
       COUNT(DISTINCT pmonth) AS N_MONTHS,
       COUNT(DISTINCT series_id) AS N_SERIES,
       SUM(n_null_created) AS N_NULL_CREATED,
       SUM(n_lines) AS N_LINES,
       ROUND(SUM(dkk)) AS DKK,
       MIN(coff_raw) AS MIN_OFF,
       MAX(coff_raw) AS MAX_OFF,
       ROUND(100.0 * SUM(CASE WHEN coff_raw < 0 THEN dkk ELSE 0 END) / SUM(dkk), 3) AS PCT_BEFORE,
       ROUND(100.0 * SUM(CASE WHEN coff_raw > 45 THEN dkk ELSE 0 END) / SUM(dkk), 3) AS PCT_AFTER_45,
       ROUND(100.0 * SUM(CASE WHEN coff_raw > 60 THEN dkk ELSE 0 END) / SUM(dkk), 3) AS PCT_AFTER_60,
       ROUND(100.0 * SUM(CASE WHEN coff_raw > {MAX_OFFSET} THEN dkk ELSE 0 END)
             / SUM(dkk), 3) AS PCT_AFTER_MAX
FROM cells GROUP BY 1 ORDER BY 1"""


def slice_sql(label: str, off: int) -> str:
    """One slice query: payload bytes [off, off+SLICE_CHARS) plus self-validation.

    Every slice also returns the *whole* payload's LENGTH and MD5, computed in
    the same run that produced the bytes, so assembly can be verified without a
    separate meta query and without any value being transcribed by hand. PAD is
    filler that pushes the result past the inline-render limit, which is what
    makes the harness persist it to a file verbatim.
    """
    start, end = window(label)
    return (f"{payload_ctes(start, end)}"
            f" /*SALES kind=slice w={label} off={off} v={EXTRACT_VERSION}*/\n"
            f"SELECT SUBSTR(p, {off}, {SLICE_CHARS}) AS CHUNK, LENGTH(p) AS PLEN,"
            f" MD5(p) AS PMD5, REPEAT('.', {PAD_CHARS}) AS PAD FROM payload")


def emit_first_slices() -> None:
    """Slice 1 of every window — also reports each payload's length for slicing."""
    for label, _, _ in WINDOWS:
        out_dir = os.path.join(SQL_DIR, label)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "slice_00000001.sql"), "w", encoding="utf-8") as fh:
            fh.write(slice_sql(label, 1) + "\n")
    print(f"wrote slice 1 for {len(WINDOWS)} windows under {SQL_DIR}")


def emit_slices(label: str, payload_len: int) -> None:
    """Every slice query needed to cover one window's payload."""
    out_dir = os.path.join(SQL_DIR, label)
    os.makedirs(out_dir, exist_ok=True)
    offsets = list(range(1, payload_len + 1, SLICE_CHARS))
    for off in offsets:
        with open(os.path.join(out_dir, f"slice_{off:08d}.sql"), "w", encoding="utf-8") as fh:
            fh.write(slice_sql(label, off) + "\n")
    print(f"{label}: wrote {len(offsets)} slice file(s) under {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-probe", action="store_true")
    parser.add_argument("--emit-first-slices", action="store_true")
    parser.add_argument("--emit-slices", nargs=2, metavar=("WINDOW", "PAYLOAD_LEN"),
                        help="all slice queries for a window, given its payload length")
    args = parser.parse_args()
    if args.emit_probe:
        os.makedirs(SQL_DIR, exist_ok=True)
        path = os.path.join(SQL_DIR, "probe.sql")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(emit_probe() + "\n")
        print(f"wrote {path}")
    if args.emit_first_slices:
        emit_first_slices()
    if args.emit_slices:
        emit_slices(args.emit_slices[0], int(args.emit_slices[1]))
    if not (args.emit_probe or args.emit_first_slices or args.emit_slices):
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
