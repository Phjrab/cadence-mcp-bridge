#!/usr/bin/env python
"""Turn an anonymous OA stream into role commitments and fixed diagnostics."""

from __future__ import with_statement

import imp
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-role-parse-v4"

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_role_parse_v4", BASE)
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
    role_result = worker.build_complete_result(before, after, stream)
    payload = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_ROLE_PARSE_V4",
        "role_result": role_result,
        "stage_started": "MCP_WP14_STAGE|restore_start" in stream,
        "stage_closed": "MCP_WP14_STAGE|close_returned" in stream,
        "topology_marker_seen": "MCP_WP14_TOPOLOGY|" in stream,
        "completion_marker_seen": "MCP_WP14_COMPLETE|true|true" in stream,
        "raw_content_included": False,
        "names_included": False,
        "values_included": False,
        "simulation_run": False,
    }
    worker._dump_bounded(payload)
    sys.exit(0)
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed WP-14 role parse failed\n")
    sys.exit(69)
