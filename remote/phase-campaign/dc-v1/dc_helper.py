#!/usr/bin/env python
"""Python 2.6 guard for two fixed DC jobs from the copied current OA netlist."""

from __future__ import with_statement

import imp
import json
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
NETLIST = ROOT + "/wp14-copied-netlist-v1/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist/netlist"
PROJECT = ROOT + "/wp14-copied-netlist-v1/project"
RUNTIME = ROOT + "/wp14-copied-dc-v1"
TARGET = "/home/buet/cds_work/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/schematic"
MODEL = "/home/buet/cadence/gpdk090_v4.6/models/spectre/gpdk090.scs"
SOURCE_SHA256 = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
STATE_SHA256 = "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193"
MODEL_SHA256 = "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f"
PROFILE_SHA256 = "dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b"
TARGET_SHA256 = "a02d83653f26f2e34f1f4e402531e66e9d34b5ecc41d29ed6d38a70ed8c6983f"
PROJECT_SHA256 = "dce155df486c1bb70f3cfd4282f6a002031696b92e0754d78e4d8ed10dfc2387"
NETLIST_SHA256 = "6189aa9d647671c05a9f03d815530697560c00b661cad95c87f7f415d482192a"
MODES = {"baseline": ("300m", "650m"), "candidate": ("320m", "702m")}
SUMMARY = re.compile(r"spectre completes with ([0-9]+) errors?, ([0-9]+) warnings?, and ([0-9]+) notices?")

if len(sys.argv) != 3 or sys.argv[1] not in ("check", "prepare", "complete") or sys.argv[2] not in MODES:
    sys.exit(64)

worker = imp.load_source("fixed_wp14_copied_dc_guard", BASE)
mode = sys.argv[2]
job = RUNTIME + "/" + mode


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
    project = worker._tree_fingerprint(PROJECT)
    if target["sha256"] != TARGET_SHA256 or project["sha256"] != PROJECT_SHA256:
        raise ValueError("copy or netlist drift")
    circuit = worker._read_bounded(NETLIST, 10 * 1024 * 1024)
    if worker._sha256(circuit) != NETLIST_SHA256:
        raise ValueError("circuit netlist drift")
    for line in ("V0 (VDD 0) vsource dc=1 type=dc",
                 "V1 (Vp 0) vsource dc=500m",
                 "V2 (Vm 0) vsource dc=500m",
                 "V3 (Vbiasn 0) vsource dc=VBIASN type=dc",
                 "V4 (Vbiasp 0) vsource dc=VBIASP type=dc"):
        if line not in circuit:
            raise ValueError("fixed binding mismatch")
    statvfs = os.statvfs(ROOT)
    total = statvfs.f_blocks * statvfs.f_frsize
    available = statvfs.f_bavail * statvfs.f_frsize
    if available < max(2 * 1024 ** 3, (total + 9) // 10):
        raise ValueError("free-space floor")
    return {"protected": base["protected"], "target_sha256": target["sha256"],
            "project_sha256": project["sha256"], "netlist_sha256": NETLIST_SHA256,
            "locks": base["locks"]}


def check():
    current = snapshot()
    if os.path.lexists(job):
        raise ValueError("job already exists")
    if mode == "baseline" and os.path.lexists(RUNTIME):
        raise ValueError("runtime already exists")
    if mode == "candidate" and (not os.path.isdir(RUNTIME) or
                                 os.path.islink(RUNTIME)):
        raise ValueError("runtime missing")
    worker._dump_bounded({"status": "ready", "mode": mode,
                          "target_sha256": current["target_sha256"],
                          "netlist_sha256": current["netlist_sha256"]})


def write_file(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def prepare():
    before = snapshot()
    if os.path.islink(job) or os.listdir(job):
        raise ValueError("job not empty")
    circuit = worker._read_bounded(NETLIST, 10 * 1024 * 1024)
    write_file(job + "/design-netlist.scs", circuit)
    vbiasn, vbiasp = MODES[mode]
    wrapper = (
        "simulator lang=spectre\n\n"
        "global 0\n"
        "include \"%s\" section=NN\n"
        "parameters VBIASN=%s VBIASP=%s\n"
        "include \"design-netlist.scs\"\n\n"
        "simulatorOptions options temp=27 tnom=27\n"
        "save Vop Vom VDD Vp Vm\n"
        "dc1 dc\n"
    ) % (MODEL, vbiasn, vbiasp)
    write_file(job + "/profile.scs", wrapper)
    before["mode"] = mode
    before["wrapper_sha256"] = worker._sha256(wrapper)
    worker._dump_bounded(before)


def complete():
    before = json.loads(worker._read_bounded(job + "/before.json", worker.MAX_JSON_BYTES))
    after = snapshot()
    if (before["mode"] != mode or
            dict((key, before[key]) for key in after) != after or
            worker._sha256(worker._read_bounded(job + "/design-netlist.scs", 10 * 1024 * 1024)) != NETLIST_SHA256 or
            worker._sha256(worker._read_bounded(job + "/profile.scs", 10 * 1024 * 1024)) != before["wrapper_sha256"]):
        raise ValueError("DC pre/post drift")
    log = worker._read_bounded(job + "/spectre.log", 10 * 1024 * 1024)
    found = SUMMARY.findall(log)
    if len(found) != 1:
        raise ValueError("Spectre summary missing")
    errors, warnings, notices = tuple(int(value) for value in found[0])
    warning_lines = [line for line in log.splitlines() if "WARNING" in line]
    allowed = warnings <= 2 and len(warning_lines) == warnings and all(
        "WARNING (CMI-2477):" in line for line in warning_lines)
    psf = job + "/psf"
    if not os.path.isdir(psf) or os.path.islink(psf):
        raise ValueError("PSF absent")
    result_tree = worker._tree_fingerprint(psf)
    if result_tree["entry_count"] == 0 or result_tree["total_bytes"] == 0:
        raise ValueError("PSF empty")
    status = "dc_completed" if errors == 0 and allowed else "simulator_failed"
    worker._dump_bounded({
        "schema_version": 1,
        "plan_id": "WP14_FIXED_COPIED_DC_V1",
        "status": status,
        "mode": mode,
        "source_sha256": SOURCE_SHA256,
        "target_sha256": TARGET_SHA256,
        "netlist_sha256": NETLIST_SHA256,
        "wrapper_sha256": before["wrapper_sha256"],
        "model_sha256": MODEL_SHA256,
        "model_section": "NN",
        "temperature_c": 27,
        "vdd_v": 1.0,
        "input_vcm_v": 0.5,
        "bias_values_v": [0.300, 0.650] if mode == "baseline" else [0.320, 0.702],
        "spectre_errors": errors,
        "spectre_warnings": warnings,
        "spectre_notices": notices,
        "psf_tree_sha256": result_tree["sha256"],
        "psf_entries": result_tree["entry_count"],
        "psf_bytes": result_tree["total_bytes"],
        "protected_and_copy_unchanged": True,
        "simulation_run": True,
    })


try:
    if sys.argv[1] == "check":
        check()
    elif sys.argv[1] == "prepare":
        prepare()
    else:
        complete()
except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError):
    sys.stderr.write("fixed copied DC guard failed\n")
    sys.exit(69)
