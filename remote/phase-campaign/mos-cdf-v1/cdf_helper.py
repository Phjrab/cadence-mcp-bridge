#!/usr/bin/env python
"""Python 2.6 parser for a fixed read-only MOS instance CDF inventory."""

from __future__ import with_statement

import imp
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-mos-cdf-v1"
SOURCE_SHA256 = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
TOKEN = re.compile(r"^[A-Za-z0-9_.$+-]{1,128}$")
VALUE = re.compile(r"^[\x21-\x7e]{1,96}$")
NAMES = ("w", "l", "m", "nf", "fw", "width", "length", "fingers", "totalWidth")
PREFIXES = ("MCP_MOS_CDF_BEGIN|", "MCP_MOS_CDF_INST|", "MCP_MOS_CDF_PARAM|",
            "MCP_MOS_CDF_COUNTS|", "MCP_MOS_CDF_COMPLETE|")

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_mos_cdf_guard", BASE)
worker.RUNTIME = RUNTIME
worker.BEFORE_PATH = RUNTIME + "/before.json"
worker.MAX_OUTPUT_BYTES = 32768

if sys.argv[1] != "complete":
    sys.exit(worker.main())


def parse_private(stream):
    instances = {}
    begin = 0
    done = 0
    counts = None
    parameter_count = 0
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith(PREFIXES):
            continue
        if len(line) > 512 or any(ord(character) > 127 for character in line):
            raise ValueError("marker bound")
        if line == "MCP_MOS_CDF_BEGIN|true":
            begin += 1
            continue
        if line == "MCP_MOS_CDF_COMPLETE|true|true":
            done += 1
            continue
        if line.startswith("MCP_MOS_CDF_INST|"):
            parts = line.split("|")
            if (len(parts) != 4 or not TOKEN.match(parts[1]) or
                    parts[2] not in ("nmos1v", "pmos1v") or
                    parts[3] not in ("true", "false") or
                    parts[1] in instances or len(instances) >= 14):
                raise ValueError("instance marker")
            instances[parts[1]] = {"master_cell": parts[2],
                                   "cdf_present": parts[3] == "true", "parameters": {}}
            continue
        if line.startswith("MCP_MOS_CDF_PARAM|"):
            parts = line.split("|", 4)
            if (len(parts) != 5 or parts[1] not in instances or
                    not instances[parts[1]]["cdf_present"] or parts[2] not in NAMES or
                    not VALUE.match(parts[3]) or not VALUE.match(parts[4]) or
                    parts[2] in instances[parts[1]]["parameters"]):
                raise ValueError("parameter marker")
            instances[parts[1]]["parameters"][parts[2]] = {
                "value_repr": parts[3], "default_repr": parts[4]}
            parameter_count += 1
            if parameter_count > 126:
                raise ValueError("parameter bound")
            continue
        if line.startswith("MCP_MOS_CDF_COUNTS|"):
            parts = line.split("|")
            if len(parts) != 5 or counts is not None:
                raise ValueError("count marker")
            counts = tuple(int(value) for value in parts[1:])
            continue
        raise ValueError("marker variant")
    if (begin != 1 or done != 1 or counts is None or
            counts[0] != 35 or counts[1] != 14 or counts[2] != 14 or
            counts[3] != sum(1 for item in instances.values() if item["cdf_present"]) or
            len(instances) != 14):
        raise ValueError("OA lifecycle or topology")
    masters = [item["master_cell"] for item in instances.values()]
    if masters.count("nmos1v") != 8 or masters.count("pmos1v") != 6:
        raise ValueError("MOS master count")
    return {"instances": instances, "topology_counts": list(counts),
            "parameter_count": parameter_count}


try:
    before = worker._load_before()
    stream = sys.stdin.read(worker.MAX_STREAM_BYTES + 1)
    after = worker.build_snapshot()
    if (len(stream) > worker.MAX_STREAM_BYTES or
            before["source_tree"]["sha256"] != SOURCE_SHA256 or
            before["source_tree"] != after["source_tree"] or
            before["protected"] != after["protected"] or
            before["locks"] != after["locks"] or
            before["blockers"] or after["blockers"]):
        raise ValueError("protected or stream drift")
    parsed = parse_private(stream)
    worker._dump_bounded({
        "schema_version": 1,
        "plan_id": "WP14_FIXED_MOS_CDF_INVENTORY_V1",
        "status": "observed",
        "source_sha256": SOURCE_SHA256,
        "state_tree_sha256": before["protected"]["ade_state_tree"],
        "instances": parsed["instances"],
        "topology_counts": parsed["topology_counts"],
        "parameter_count": parsed["parameter_count"],
        "protected_fingerprints_unchanged": True,
        "locks_unchanged": True,
        "simulation_run": False,
    })
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed MOS CDF inventory failed\n")
    sys.exit(69)
