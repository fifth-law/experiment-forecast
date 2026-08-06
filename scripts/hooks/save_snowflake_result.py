#!/usr/bin/env python3
"""PostToolUse hook: persist every Snowflake MCP result to disk.

Claude Code pipes the hook event JSON (tool_name, tool_input, tool_response)
on stdin. We dump it verbatim to a content-addressed file so large query
results can be reassembled deterministically without the model ever having
to re-type payload bytes. Used by the one-off snapshot extraction.
"""

import hashlib
import json
import os
import sys
import time

RAW_DIR = os.path.join(
    os.environ.get("CLAUDE_PROJECT_DIR", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data", "raw", "mcp_results",
)


def main() -> None:
    payload = sys.stdin.read()
    if not payload.strip():
        return
    os.makedirs(RAW_DIR, exist_ok=True)
    digest = hashlib.sha1(payload.encode("utf-8", errors="replace")).hexdigest()[:16]
    path = os.path.join(RAW_DIR, f"result_{digest}.json")
    if not os.path.exists(path):
        tmp = f"{path}.tmp.{os.getpid()}.{time.time_ns()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    # Never block the tool result; emit nothing on stdout.


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # a broken hook must never break the session
        print(f"save_snowflake_result hook error: {exc}", file=sys.stderr)
        sys.exit(0)
