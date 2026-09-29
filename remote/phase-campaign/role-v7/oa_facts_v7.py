#!/usr/bin/env python
"""Bounded private parser for current read-only WP-14 OA facts."""

from __future__ import with_statement

import imp
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-oa-facts-v7"
EXPECTED_SOURCE_SHA256 = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
TOKEN = re.compile(r"^[\x21-\x7e]{1,128}$")
TOPOLOGY = re.compile(r"^MCP_WP14_TOPOLOGY[|]([0-9]+)[|]([0-9]+)[|]([0-9]+)[|]([0-9]+)$")
PROPERTIES = ("dc", "vdc", "idc", "r", "c", "l", "acmag", "ampl", "freq", "v1", "v2", "type", "val")
PREFIXES = ("MCP_WP14_FACT_BEGIN|", "MCP_WP14_INST|", "MCP_WP14_TERM|",
            "MCP_WP14_PROP|", "MCP_WP14_TOPOLOGY|", "MCP_WP14_FACT_COMPLETE|")

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_private_oa_facts", BASE)
worker.RUNTIME = RUNTIME
worker.BEFORE_PATH = RUNTIME + "/before.json"
worker.MAX_OUTPUT_BYTES = 32768

if sys.argv[1] != "complete":
    sys.exit(worker.main())

try:
    before = worker._load_before()
    stream = sys.stdin.read(worker.MAX_STREAM_BYTES + 1)
    after = worker.build_snapshot()
    if len(stream) > worker.MAX_STREAM_BYTES:
        raise ValueError("stream bound")
    if before["source_tree"]["sha256"] != EXPECTED_SOURCE_SHA256:
        raise ValueError("source revision")
    if before["protected"] != after["protected"] or before["locks"] != after["locks"]:
        raise ValueError("protected drift")
    instances = {}
    begin = 0
    complete = 0
    topology = None
    property_lines = 0
    for raw_line in stream.splitlines():
        line = raw_line.strip()
        if not line.startswith(PREFIXES):
            continue
        if len(line) > 512 or any(ord(character) > 127 for character in line):
            raise ValueError("unsafe marker")
        if line == "MCP_WP14_FACT_BEGIN|true":
            begin += 1
            continue
        if line == "MCP_WP14_FACT_COMPLETE|true|true":
            complete += 1
            continue
        if line.startswith("MCP_WP14_TOPOLOGY|"):
            if topology is not None:
                raise ValueError("duplicate topology")
            match = TOPOLOGY.match(line)
            if match is None:
                raise ValueError("topology marker")
            topology = tuple(int(value) for value in match.groups())
            continue
        if line.startswith("MCP_WP14_INST|"):
            parts = line.split("|")
            if len(parts) != 5 or not all(TOKEN.match(value) for value in parts[1:4]):
                raise ValueError("instance marker")
            name = parts[1]
            count = int(parts[4])
            if name in instances or count > 16 or len(instances) >= 64:
                raise ValueError("instance bound")
            instances[name] = {"master_lib": parts[2], "master_cell": parts[3],
                               "terminal_count": count, "terminals": [], "properties": []}
            continue
        if line.startswith("MCP_WP14_TERM|"):
            parts = line.split("|")
            if len(parts) != 4 or not all(TOKEN.match(value) for value in parts[1:]):
                raise ValueError("terminal marker")
            if parts[1] not in instances:
                raise ValueError("terminal order")
            instances[parts[1]]["terminals"].append({"terminal": parts[2], "net": parts[3]})
            continue
        if line.startswith("MCP_WP14_PROP|"):
            parts = line.split("|", 4)
            if len(parts) != 5 or not all(TOKEN.match(value) for value in parts[1:4]):
                raise ValueError("property marker")
            if parts[1] not in instances or parts[2] not in PROPERTIES:
                raise ValueError("property scope")
            if parts[3] not in ("string", "float", "int"):
                raise ValueError("property type")
            if len(parts[4]) > 256 or any(ord(character) < 32 or ord(character) > 126 for character in parts[4]):
                raise ValueError("property value bound")
            property_lines += 1
            if property_lines > 256:
                raise ValueError("property count bound")
            instances[parts[1]]["properties"].append({"name": parts[2],
                "type": parts[3], "value_repr": parts[4]})
            continue
        raise ValueError("marker variant")
    if begin != 1 or complete != 1 or topology is None or topology[:3] != (35, 14, 8):
        raise ValueError("OA lifecycle or topology")
    if len(instances) != topology[0] or topology[3] > 1024:
        raise ValueError("instance topology")
    for instance in instances.values():
        if len(instance["terminals"]) != instance["terminal_count"]:
            raise ValueError("terminal count")
    payload = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_PRIVATE_OA_FACTS_V7",
        "status": "observed",
        "source_sha256": EXPECTED_SOURCE_SHA256,
        "state_tree_sha256": before["protected"]["ade_state_tree"],
        "topology": topology,
        "instances": instances,
        "protected_fingerprints_unchanged": True,
        "locks_unchanged": True,
        "simulation_run": False,
    }
    worker._dump_bounded(payload)
    sys.exit(0)
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed WP-14 OA facts failed\n")
    sys.exit(69)
