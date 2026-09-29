#!/usr/bin/env python
"""Classify fixed role marker shapes without retaining private OA output."""

from __future__ import with_statement

import imp
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-marker-diagnostic-v5"
KNOWN_ERRORS = (
    "OA lifecycle",
    "duplicate topology",
    "candidate enum",
    "private marker",
    "blocker marker",
    "unsafe private token",
    "unsafe terminal pair",
    "stream bound",
    "terminal pairs",
    "terminal count",
)

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_marker_diagnostic", BASE)
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
    topology_prefix_count = 0
    topology_regex_count = 0
    topology_min_length = None
    topology_max_length = 0
    complete_prefix_count = 0
    complete_regex_count = 0
    complete_min_length = None
    complete_max_length = 0
    for raw_line in stream.splitlines():
        line = raw_line.strip()
        if line.startswith("MCP_WP14_TOPOLOGY|"):
            topology_prefix_count += 1
            topology_min_length = min(topology_min_length, len(line)) if topology_min_length else len(line)
            topology_max_length = max(topology_max_length, len(line))
            if worker.TOPOLOGY_PATTERN.match(line) is not None:
                topology_regex_count += 1
        if line.startswith("MCP_WP14_COMPLETE|"):
            complete_prefix_count += 1
            complete_min_length = min(complete_min_length, len(line)) if complete_min_length else len(line)
            complete_max_length = max(complete_max_length, len(line))
            if worker.COMPLETE_PATTERN.match(line) is not None:
                complete_regex_count += 1
    parse_error = "none"
    parsed_role_counts = None
    try:
        roles, unsupported = worker.parse_private_stream(stream)
        parsed_role_counts = dict((role, len(roles[role])) for role in worker.ROLES)
    except ValueError as error:
        parse_error = str(error) if str(error) in KNOWN_ERRORS else "other_value_error"
    except (OverflowError, ArithmeticError):
        parse_error = "bounded_or_topology_error"
    payload = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_MARKER_DIAGNOSTIC_V5",
        "parse_error": parse_error,
        "role_counts_if_parsed": parsed_role_counts,
        "topology_prefix_count": topology_prefix_count,
        "topology_regex_count": topology_regex_count,
        "topology_min_length": topology_min_length,
        "topology_max_length": topology_max_length,
        "complete_prefix_count": complete_prefix_count,
        "complete_regex_count": complete_regex_count,
        "complete_min_length": complete_min_length,
        "complete_max_length": complete_max_length,
        "protected_fingerprints_unchanged": before["protected"] == after["protected"],
        "locks_unchanged": before["locks"] == after["locks"],
        "names_included": False,
        "raw_content_included": False,
        "values_included": False,
        "simulation_run": False,
    }
    worker._dump_bounded(payload)
    sys.exit(0)
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed WP-14 marker diagnostic failed\n")
    sys.exit(69)
