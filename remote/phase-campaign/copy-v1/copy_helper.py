#!/usr/bin/env python
"""Fixed one-shot copy gate and protected-tree verification for WP-14."""

from __future__ import with_statement

import imp
import os
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-copy-current-oa-v1"
WORKLIB = "/home/buet/cds_work/MCP_WorkLib"
TARGET_CELL = WORKLIB + "/WP14_AUTO_PHASE_01_TB2"
TARGET_VIEW = TARGET_CELL + "/schematic"
MARKER = "MCP_WP14_COPY|true|35|14|8|true|true|true"
SOURCE_SHA256 = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
STATE_SHA256 = "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193"
MODEL_SHA256 = "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f"
PROFILE_SHA256 = "dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b"

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_copy_guard", BASE)
worker.RUNTIME = RUNTIME
worker.BEFORE_PATH = RUNTIME + "/before.json"

try:
    if sys.argv[1] in ("preflight", "gate"):
        if os.path.islink(WORKLIB) or os.path.realpath(WORKLIB) != WORKLIB:
            raise ValueError("work library path")
        if os.stat(WORKLIB).st_uid != os.getuid() or os.path.lexists(TARGET_CELL):
            raise ValueError("work target absent")
        sys.exit(worker.main())
    before = worker._load_before()
    if (before["protected"]["ade_state_tree"] != STATE_SHA256 or
            before["protected"]["pdk_model_file"] != MODEL_SHA256 or
            before["protected"]["fixed_profile_registry"] != PROFILE_SHA256 or
            before["locks"]):
        raise ValueError("protected baseline")
    stream = sys.stdin.read(worker.MAX_STREAM_BYTES + 1)
    after = worker.build_snapshot()
    if len(stream) > worker.MAX_STREAM_BYTES:
        raise ValueError("stream bound")
    if before["source_tree"]["sha256"] != SOURCE_SHA256:
        raise ValueError("source fingerprint")
    if before["protected"] != after["protected"] or before["locks"] != after["locks"]:
        raise ValueError("protected drift")
    markers = [line.strip() for line in stream.splitlines() if line.startswith("MCP_WP14_COPY|")]
    if markers != [MARKER]:
        raise ValueError("copy contract")
    if os.path.islink(TARGET_CELL) or os.path.realpath(TARGET_VIEW) != TARGET_VIEW:
        raise ValueError("target path")
    target = worker._tree_fingerprint(TARGET_VIEW)
    if target["entry_count"] < 2 or target["total_bytes"] <= 0:
        raise ValueError("empty copy")
    payload = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_CURRENT_OA_COPY_V1",
        "status": "copied",
        "source_sha256": SOURCE_SHA256,
        "state_tree_sha256": before["protected"]["ade_state_tree"],
        "target_tree_sha256": target["sha256"],
        "target_entries": target["entry_count"],
        "target_bytes": target["total_bytes"],
        "source_and_protected_unchanged": True,
        "locks_unchanged": True,
        "target_topology_equal": True,
        "target_instance_and_net_signatures_equal": True,
        "simulation_run": False,
    }
    worker._dump_bounded(payload)
    sys.exit(0)
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed WP-14 copy guard failed\n")
    sys.exit(69)
