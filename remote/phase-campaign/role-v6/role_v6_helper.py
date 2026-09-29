#!/usr/bin/env python
"""Parse only fixed ASCII OA markers; discard Cadence's non-ASCII banner."""

from __future__ import with_statement

import imp
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-ascii-role-parse-v6"
PREFIXES = (
    "MCP_WP14_PRIVATE|",
    "MCP_WP14_BLOCKER|",
    "MCP_WP14_TOPOLOGY|",
    "MCP_WP14_COMPLETE|",
)

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_ascii_role_parse", BASE)
worker.RUNTIME = RUNTIME
worker.BEFORE_PATH = RUNTIME + "/before.json"

if sys.argv[1] != "complete":
    sys.exit(worker.main())

try:
    before = worker._load_before()
    stream = sys.stdin.read(worker.MAX_STREAM_BYTES + 1)
    after = worker.build_snapshot()
    if len(stream) > worker.MAX_STREAM_BYTES:
        raise ValueError("stream bound")
    marker_lines = []
    for raw_line in stream.splitlines():
        line = raw_line.strip()
        if line.startswith(PREFIXES):
            if any(ord(character) > 127 for character in line):
                raise ValueError("non-ASCII marker")
            marker_lines.append(line)
    filtered = "\n".join(marker_lines) + "\n"
    role_result = worker.build_complete_result(before, after, filtered)
    payload = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_ASCII_ROLE_PARSE_V6",
        "role_result": role_result,
        "filtered_marker_count": len(marker_lines),
        "raw_content_included": False,
        "names_included": False,
        "values_included": False,
        "simulation_run": False,
    }
    worker._dump_bounded(payload)
    sys.exit(0)
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed WP-14 ASCII role parse failed\n")
    sys.exit(69)
