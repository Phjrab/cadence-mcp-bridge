#!/usr/bin/env python
"""Consume private Virtuoso output and retain only fixed diagnostic stages."""

from __future__ import with_statement

import imp
import json
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-role-diagnostic-v3"
STAGES = (
    "restore_start",
    "oa_open_returned",
    "oa_opened",
    "loop_start",
    "master_class_done",
    "slots_done",
    "terminals_done",
    "instance_done",
    "loop_done",
    "close_returned",
)

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_role_diagnostic", BASE)
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
    stages_seen = []
    error_seen = False
    private_marker_count = 0
    topology_seen = False
    complete_seen = False
    for line in stream.splitlines():
        if line.startswith("MCP_WP14_STAGE|"):
            stage = line[len("MCP_WP14_STAGE|") :].strip()
            if stage not in STAGES:
                raise ValueError("unknown stage")
            stages_seen.append(stage)
        elif line.startswith("MCP_WP14_PRIVATE|"):
            private_marker_count += 1
        elif line.startswith("MCP_WP14_TOPOLOGY|"):
            topology_seen = True
        elif line.startswith("MCP_WP14_COMPLETE|"):
            complete_seen = True
        elif "*Error*" in line or "*ERROR*" in line:
            error_seen = True
    unchanged = before["protected"] == after["protected"]
    locks_unchanged = before["locks"] == after["locks"]
    payload = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_OA_STAGE_DIAGNOSTIC_V3",
        "status": "observed" if unchanged and locks_unchanged else "blocked",
        "last_stage": stages_seen[-1] if stages_seen else "none",
        "stage_count": len(stages_seen),
        "error_marker_seen": error_seen,
        "private_marker_count": private_marker_count,
        "topology_marker_seen": topology_seen,
        "completion_marker_seen": complete_seen,
        "protected_fingerprints_unchanged": unchanged,
        "locks_unchanged": locks_unchanged,
        "raw_content_included": False,
        "names_included": False,
        "values_included": False,
        "simulation_run": False,
    }
    worker._dump_bounded(payload)
    sys.exit(0)
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed WP-14 diagnostic failed\n")
    sys.exit(69)
