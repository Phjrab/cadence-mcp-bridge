#!/usr/bin/env python
"""Python 2.6 guard for bounded read-only WP-14 DC scalar extraction."""

from __future__ import with_statement

import imp
import json
import math
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-dc-scalars-v1"
SCALARS = RUNTIME + "/scalars.txt"
TARGET = "/home/buet/cds_work/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/schematic"
SOURCE_SHA256 = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
STATE_SHA256 = "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193"
MODEL_SHA256 = "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f"
PROFILE_SHA256 = "dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b"
TARGET_SHA256 = "a02d83653f26f2e34f1f4e402531e66e9d34b5ecc41d29ed6d38a70ed8c6983f"
PSF_HASHES = {
    "baseline": "3718f6ab9c09da4e0d34a7995c46704b42e7d3dc1b1c827b3d355de2d0a903c0",
    "candidate": "4e6e85cce1836659a629599aec7b8e15a339aa8886c364f7c3443ba8d26d5873",
}
LINE = re.compile(r"^MCP_DC_SCALAR[|](baseline|candidate)[|](Vop|Vom|VDD|Vp|Vm)[|]([-+0-9.eE]+)$")
SIGNALS = ("Vop", "Vom", "VDD", "Vp", "Vm")

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_dc_scalar_guard", BASE)


def snapshot():
    base = worker.build_snapshot()
    if (base["source_tree"]["sha256"] != SOURCE_SHA256 or
            base["protected"]["ade_state_tree"] != STATE_SHA256 or
            base["protected"]["pdk_model_file"] != MODEL_SHA256 or
            base["protected"]["fixed_profile_registry"] != PROFILE_SHA256 or
            base["locks"]):
        raise ValueError("protected baseline")
    target = worker._tree_fingerprint(TARGET)
    if target["sha256"] != TARGET_SHA256:
        raise ValueError("copy drift")
    psf = {}
    for mode in ("baseline", "candidate"):
        path = ROOT + "/wp14-copied-dc-v1/" + mode + "/psf"
        if os.path.islink(path) or os.path.realpath(path) != path:
            raise ValueError("PSF path")
        tree = worker._tree_fingerprint(path)
        if tree["sha256"] != PSF_HASHES[mode] or tree["total_bytes"] != 3966:
            raise ValueError("PSF drift")
        psf[mode] = tree
    return {"protected": base["protected"], "locks": base["locks"],
            "target": target, "psf": psf}


def parse_scalars(data):
    lines = data.splitlines()
    if len(lines) != 11 or lines[-1] != "MCP_DC_SCALAR_COMPLETE|true":
        raise ValueError("scalar line count")
    values = {"baseline": {}, "candidate": {}}
    for line in lines[:-1]:
        match = LINE.match(line)
        if match is None:
            raise ValueError("scalar line")
        mode, signal, text = match.groups()
        if signal in values[mode]:
            raise ValueError("duplicate scalar")
        number = float(text)
        if math.isnan(number) or math.isinf(number) or abs(number) > 10:
            raise ValueError("nonfinite scalar")
        values[mode][signal] = number
    for mode in ("baseline", "candidate"):
        if set(values[mode]) != set(SIGNALS):
            raise ValueError("missing scalar")
        if (abs(values[mode]["VDD"] - 1.0) > 1e-6 or
                abs(values[mode]["Vp"] - 0.5) > 1e-6 or
                abs(values[mode]["Vm"] - 0.5) > 1e-6):
            raise ValueError("supply or common-mode mismatch")
        values[mode]["output_common_mode_v"] = (
            values[mode]["Vop"] + values[mode]["Vom"]) / 2.0
        values[mode]["output_diff_v"] = values[mode]["Vop"] - values[mode]["Vom"]
    return values


try:
    if sys.argv[1] == "preflight":
        if os.path.lexists(SCALARS):
            raise ValueError("scalar output exists")
        worker._dump_bounded(snapshot())
    else:
        before = json.loads(worker._read_bounded(RUNTIME + "/before.json", worker.MAX_JSON_BYTES))
        after = snapshot()
        if before != after:
            raise ValueError("protected or PSF drift")
        raw = worker._read_bounded(SCALARS, 4096)
        values = parse_scalars(raw)
        worker._dump_bounded({
            "schema_version": 1,
            "plan_id": "WP14_FIXED_COPIED_DC_SCALARS_V1",
            "status": "observed",
            "source_sha256": SOURCE_SHA256,
            "target_sha256": TARGET_SHA256,
            "psf_sha256": PSF_HASHES,
            "values_v": values,
            "protected_and_results_unchanged": True,
            "simulation_run": False,
        })
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed DC scalar extraction failed\n")
    sys.exit(69)
