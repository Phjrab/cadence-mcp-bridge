#!/usr/bin/env python
"""Python 2.6 guard for read-only candidate AC scalar extraction."""

from __future__ import with_statement

import imp
import json
import math
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-ac-scalars-v2"
SCALARS = RUNTIME + "/scalars.txt"
TARGET = "/home/buet/cds_work/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/schematic"
SOURCE_SHA256 = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
STATE_SHA256 = "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193"
MODEL_SHA256 = "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f"
PROFILE_SHA256 = "dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b"
TARGET_SHA256 = "a02d83653f26f2e34f1f4e402531e66e9d34b5ecc41d29ed6d38a70ed8c6983f"
PSF_SHA256 = "f1ddc9b70069055babebdb12ee3b46265b70396020223abfaff71bfcaad8b3e6"
LINE = re.compile(r"^MCP_AC_POINT[|](Vop|Vom|Vp|Vm)[|]([01])[|]([-+0-9.eE]+)[|]([-+0-9.eE]+)[|]([-+0-9.eE]+)$")
VECTOR_LINE = re.compile(r"^MCP_AC_VECTOR[|](Vop|Vom|Vp|Vm)[|]([0-9]+)[|]([0-9]+)$")
SIGNALS = ("Vop", "Vom", "Vp", "Vm")
FREQUENCIES = (1000.0, 10000.0)
STAGES = ("MCP_AC_STAGE|file_open", "MCP_AC_STAGE|results_open",
          "MCP_AC_STAGE|ac_selected")

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_ac_scalar_guard", BASE)


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
    path = ROOT + "/wp14-candidate-ac-v1/psf"
    if os.path.islink(path) or os.path.realpath(path) != path:
        raise ValueError("PSF path")
    psf = worker._tree_fingerprint(path)
    if psf["sha256"] != PSF_SHA256 or psf["total_bytes"] != 4556:
        raise ValueError("PSF drift")
    statvfs = os.statvfs(ROOT)
    total = statvfs.f_blocks * statvfs.f_frsize
    available = statvfs.f_bavail * statvfs.f_frsize
    if available < max(2 * 1024 ** 3, (total + 9) // 10):
        raise ValueError("free-space floor")
    return {"protected": base["protected"], "locks": base["locks"],
            "target": target, "psf": psf}


def parse_scalars(data):
    lines = data.splitlines()
    if (len(lines) != 16 or tuple(lines[:3]) != STAGES or
            lines[-1] != "MCP_AC_POINT_COMPLETE|true"):
        raise ValueError("AC scalar line count")
    values = {}
    cursor = 3
    for expected_signal in SIGNALS:
        vector = VECTOR_LINE.match(lines[cursor])
        if vector is None or vector.group(1) != expected_signal:
            raise ValueError("AC vector header")
        x_length, y_length = int(vector.group(2)), int(vector.group(3))
        if x_length != y_length or x_length < 2 or x_length > 1024:
            raise ValueError("AC vector length")
        cursor += 1
        for expected_index in (0, 1):
            match = LINE.match(lines[cursor])
            if match is None:
                raise ValueError("AC scalar line")
            signal, index_text, freq_text, real_text, imag_text = match.groups()
            index = int(index_text)
            if signal != expected_signal or index != expected_index:
                raise ValueError("AC scalar order")
            key = (signal, index)
            freq = float(freq_text)
            real_part = float(real_text)
            imag_part = float(imag_text)
            if (any(math.isnan(x) or math.isinf(x) for x in (freq, real_part, imag_part)) or
                    abs(freq - FREQUENCIES[index]) > FREQUENCIES[index] * 1e-6 or
                    max(abs(real_part), abs(imag_part)) > 100):
                raise ValueError("invalid AC scalar")
            values[key] = complex(real_part, imag_part)
            cursor += 1
    if set(values) != set((signal, index) for signal in SIGNALS for index in (0, 1)):
        raise ValueError("missing AC scalar")
    points = []
    for index, freq in enumerate(FREQUENCIES):
        input_diff = values[("Vp", index)] - values[("Vm", index)]
        output_diff = values[("Vop", index)] - values[("Vom", index)]
        if abs(abs(input_diff) - 1.0) > 1e-6:
            raise ValueError("input AC magnitude mismatch")
        gain = output_diff / input_diff
        gain_abs = abs(gain)
        points.append({
            "frequency_hz": freq,
            "input_diff_mag_v": abs(input_diff),
            "output_diff_mag_v": abs(output_diff),
            "gain_v_per_v": gain_abs,
            "gain_db": 20.0 * math.log10(gain_abs) if gain_abs > 0 else None,
            "gain_phase_deg": math.degrees(math.atan2(gain.imag, gain.real)),
        })
    return points


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
        points = parse_scalars(raw)
        worker._dump_bounded({
            "schema_version": 1,
            "plan_id": "WP14_FIXED_CANDIDATE_AC_SCALARS_V2",
            "status": "observed",
            "source_sha256": SOURCE_SHA256,
            "target_sha256": TARGET_SHA256,
            "psf_sha256": PSF_SHA256,
            "points": points,
            "protected_and_result_unchanged": True,
            "simulation_run": False,
        })
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed AC scalar extraction failed\n")
    sys.exit(69)
