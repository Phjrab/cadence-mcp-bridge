#!/usr/bin/env python
"""Python 2.6 guard for fixed symmetric DC scalar reads."""

from __future__ import with_statement

import imp
import json
import math
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME_ROOT = ROOT + "/wp14-differential-dc-scalars-v1"
PSF_HASHES = {"positive": "49184d7d16301779b547af1e5281dfb45804793782bf599b05bb3a730b5393f6",
              "negative": "387501f30447f3b3fd11da3c19ca2f6dbd8da48284e677ce3105af2b15920b2a"}
INPUTS = {"positive": (0.5000005, 0.4999995),
          "negative": (0.4999995, 0.5000005)}
TARGET = "/home/buet/cds_work/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/schematic"
SOURCE_SHA256 = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
STATE_SHA256 = "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193"
MODEL_SHA256 = "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f"
PROFILE_SHA256 = "dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b"
TARGET_SHA256 = "a02d83653f26f2e34f1f4e402531e66e9d34b5ecc41d29ed6d38a70ed8c6983f"
LINE = re.compile(r"^MCP_DIFFERENTIAL_DC_SCALAR[|](Vop|Vom|VDD|Vp|Vm)[|]([-+0-9.eE]+)$")
SIGNALS = ("Vop", "Vom", "VDD", "Vp", "Vm")

if (len(sys.argv) != 3 or sys.argv[1] not in ("preflight", "complete") or
        sys.argv[2] not in PSF_HASHES):
    sys.exit(64)
mode = sys.argv[2]
RUNTIME = RUNTIME_ROOT + "/" + mode
SCALARS = RUNTIME + "/scalars.txt"

worker = imp.load_source("fixed_wp14_dc_scalar_guard", BASE)


def snapshot():
    base = worker.build_snapshot()
    if (base["source_tree"]["sha256"] != SOURCE_SHA256 or
            base["protected"]["ade_state_tree"] != STATE_SHA256 or
            base["protected"]["pdk_model_file"] != MODEL_SHA256 or
            base["protected"]["fixed_profile_registry"] != PROFILE_SHA256 or
            base["locks"]):
        raise ValueError("protected baseline")
    if os.path.islink(TARGET) or os.path.realpath(TARGET) != TARGET:
        raise ValueError("copy path")
    target = worker._tree_fingerprint(TARGET)
    if target["sha256"] != TARGET_SHA256:
        raise ValueError("copy drift")
    path = ROOT + "/wp14-differential-dc-v1/" + mode + "/psf"
    if os.path.islink(path) or os.path.realpath(path) != path:
        raise ValueError("PSF path")
    psf = worker._tree_fingerprint(path)
    if psf["sha256"] != PSF_HASHES[mode] or psf["total_bytes"] != 3966:
        raise ValueError("PSF drift")
    return {"protected": base["protected"], "locks": base["locks"],
            "target": target, "psf": psf}


def parse_scalars(data):
    lines = data.splitlines()
    if len(lines) != 6 or lines[-1] != "MCP_DIFFERENTIAL_DC_SCALAR_COMPLETE|true":
        raise ValueError("scalar line count")
    values = {}
    for line in lines[:-1]:
        match = LINE.match(line)
        if match is None:
            raise ValueError("scalar line")
        signal, text = match.groups()
        if signal in values:
            raise ValueError("duplicate scalar")
        number = float(text)
        if math.isnan(number) or math.isinf(number) or abs(number) > 10:
            raise ValueError("nonfinite scalar")
        values[signal] = number
    if set(values) != set(SIGNALS):
        raise ValueError("missing scalar")
    vp, vm = INPUTS[mode]
    if (abs(values["VDD"] - 1.0) > 1e-6 or
            abs(values["Vp"] - vp) > 2e-7 or
            abs(values["Vm"] - vm) > 2e-7 or
            abs((values["Vp"] - values["Vm"]) - (vp - vm)) > 2e-7):
        raise ValueError("supply or common-mode mismatch")
    values["output_common_mode_v"] = (values["Vop"] + values["Vom"]) / 2.0
    values["output_diff_v"] = values["Vop"] - values["Vom"]
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
            "plan_id": "WP14_FIXED_DIFFERENTIAL_DC_SCALARS_V1",
            "status": "observed",
            "mode": mode,
            "source_sha256": SOURCE_SHA256,
            "target_sha256": TARGET_SHA256,
            "psf_sha256": PSF_HASHES[mode],
            "values_v": values,
            "protected_and_result_unchanged": True,
            "simulation_run": False,
        })
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed DC scalar extraction failed\n")
    sys.exit(69)
