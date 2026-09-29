#!/usr/bin/env python
"""Python 2.6 boundary for a fixed copied-cell netlist capability probe."""

from __future__ import with_statement

import imp
import json
import os
import stat
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-copied-netlist-v1"
PROJECT = RUNTIME + "/project"
TARGET = "/home/buet/cds_work/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/schematic"
DEFAULT_OUTPUT = "/home/buet/simulation/WP14_AUTO_PHASE_01_TB2"
SOURCE_SHA256 = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
STATE_SHA256 = "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193"
MODEL_SHA256 = "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f"
PROFILE_SHA256 = "dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b"
TARGET_SHA256 = "a02d83653f26f2e34f1f4e402531e66e9d34b5ecc41d29ed6d38a70ed8c6983f"
MARKER = "MCP_WP14_COPIED_NETLIST|true"

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_copied_netlist_guard", BASE)
worker.RUNTIME = RUNTIME
worker.BEFORE_PATH = RUNTIME + "/before.json"


def snapshot():
    base = worker.build_snapshot()
    if (base["source_tree"]["sha256"] != SOURCE_SHA256 or
            base["protected"]["ade_state_tree"] != STATE_SHA256 or
            base["protected"]["pdk_model_file"] != MODEL_SHA256 or
            base["protected"]["fixed_profile_registry"] != PROFILE_SHA256 or
            base["locks"]):
        raise ValueError("protected baseline")
    if os.path.islink(TARGET) or os.path.realpath(TARGET) != TARGET:
        raise ValueError("target path")
    target = worker._tree_fingerprint(TARGET)
    if target["sha256"] != TARGET_SHA256:
        raise ValueError("target copy drift")
    if os.path.lexists(DEFAULT_OUTPUT):
        raise ValueError("default output collision")
    return {"protected": base["protected"], "locks": base["locks"], "target": target}


def output_facts():
    if os.path.islink(PROJECT) or os.path.realpath(PROJECT) != PROJECT:
        raise ValueError("project path")
    tree = worker._tree_fingerprint(PROJECT)
    if tree["entry_count"] < 3 or tree["total_bytes"] <= 0:
        raise ValueError("empty netlist project")
    netlists = []
    inputs = []
    for current, _dirs, files in os.walk(PROJECT):
        for name in files:
            path = os.path.join(current, name)
            if name == "netlist":
                netlists.append(path)
            elif name == "input.scs":
                inputs.append(path)
    if len(netlists) != 1 or len(inputs) != 1:
        raise ValueError("netlist artifact count")
    artifacts = []
    for path in (netlists[0], inputs[0]):
        info = os.stat(path)
        if (os.path.islink(path) or not stat.S_ISREG(info.st_mode) or
                info.st_size <= 0 or info.st_size > 10 * 1024 * 1024):
            raise ValueError("netlist artifact bound")
        artifacts.append(worker._sha256(worker._read_bounded(path, 10 * 1024 * 1024)))
    return tree, artifacts


try:
    mode = sys.argv[1]
    if mode == "preflight":
        worker._dump_bounded(snapshot())
    elif mode == "gate":
        before = worker._load_before()
        if before != snapshot():
            raise ValueError("gate drift")
    else:
        before = worker._load_before()
        stream = sys.stdin.read(worker.MAX_STREAM_BYTES + 1)
        after = snapshot()
        if (len(stream) > worker.MAX_STREAM_BYTES or before != after or
                [line.strip() for line in stream.splitlines()
                 if line.startswith("MCP_WP14_COPIED_NETLIST|")] != [MARKER]):
            raise ValueError("netlist contract")
        tree, artifacts = output_facts()
        worker._dump_bounded({
            "schema_version": 1,
            "plan_id": "WP14_FIXED_COPIED_NETLIST_V1",
            "status": "netlisted",
            "source_sha256": SOURCE_SHA256,
            "target_sha256": TARGET_SHA256,
            "state_tree_sha256": STATE_SHA256,
            "netlist_tree_sha256": tree["sha256"],
            "netlist_entries": tree["entry_count"],
            "netlist_bytes": tree["total_bytes"],
            "circuit_netlist_sha256": artifacts[0],
            "input_scs_sha256": artifacts[1],
            "protected_and_copy_unchanged": True,
            "simulation_run": False,
        })
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed copied-netlist guard failed\n")
    sys.exit(69)
