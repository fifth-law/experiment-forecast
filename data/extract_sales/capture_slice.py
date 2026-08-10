#!/usr/bin/env python3
"""Move a persisted MCP query result into data/raw_sales/mcp_results/ verbatim.

Slice results are too large to render inline, so the harness writes them to a
file under the session's tool-results directory. This script copies the CHUNK
column out of that file into the repo's raw-capture directory, keyed by the
slice's (window, offset) — no payload bytes ever pass through a model.

    python3 data/extract_sales/capture_slice.py <tool_result_file> <window> <offset>
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RAW_DIR = os.path.join(REPO, "data", "raw_sales", "mcp_results")

sys.path.insert(0, HERE)
from gen_sales_sql import EXTRACT_VERSION, SLICE_CHARS  # noqa: E402


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    src, label, off = sys.argv[1], sys.argv[2], int(sys.argv[3])
    with open(src, encoding="utf-8") as fh:
        doc = json.load(fh)
    rows = doc["result"]
    if len(rows) != 1:
        raise SystemExit(f"expected 1 row, got {len(rows)}")
    chunk = rows[0]["CHUNK"]
    if len(chunk) > SLICE_CHARS:
        raise SystemExit(f"chunk is {len(chunk)} chars, slice size is {SLICE_CHARS}")

    os.makedirs(RAW_DIR, exist_ok=True)
    record = {
        "extract_version": EXTRACT_VERSION,
        "window": label,
        "offset": off,
        "slice_chars": SLICE_CHARS,
        "chunk_len": len(chunk),
        "chunk_md5": hashlib.md5(chunk.encode("ascii")).hexdigest(),
        # the whole payload's length and MD5 as reported by the same run that
        # produced these bytes — the assembly check in build_sales_snapshot.py
        "payload_len": int(rows[0]["PLEN"]),
        "payload_md5": rows[0]["PMD5"],
        "source_tool_result": os.path.basename(src),
        "chunk": chunk,
    }
    out = os.path.join(RAW_DIR, f"slice_{label}_{off:08d}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    print(f"{os.path.relpath(out, REPO)}: chunk={len(chunk)} of payload_len="
          f"{record['payload_len']} md5={record['payload_md5']}")
    remaining = record["payload_len"] - (off - 1 + len(chunk))
    print(f"remaining after this slice: {remaining} chars"
          + (f" -> next offset {off + SLICE_CHARS}" if remaining > 0 else " -> complete"))


if __name__ == "__main__":
    main()
