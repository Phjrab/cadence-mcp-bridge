#!/usr/bin/env python
"""Python 2.6 fixed work-copy guard and bounded DC/AC reader."""
from __future__ import with_statement

import hashlib
import imp
import json
import math
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/sim-mcp-v2"
JOBS = ROOT + "/sim-mcp-v2-jobs"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
PROJECT = ROOT + "/wp14-copied-netlist-v1/project"
NETLIST = PROJECT + "/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist/netlist"
TARGET = "/home/buet/cds_work/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/schematic"
MODEL = "/home/buet/cadence/gpdk090_v4.6/models/spectre/gpdk090.scs"
SOURCE_SHA = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
STATE_SHA = "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193"
MODEL_SHA = "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f"
PROFILE_SHA = "dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b"
TARGET_SHA = "a02d83653f26f2e34f1f4e402531e66e9d34b5ecc41d29ed6d38a70ed8c6983f"
PROJECT_SHA = "dce155df486c1bb70f3cfd4282f6a002031696b92e0754d78e4d8ed10dfc2387"
NETLIST_SHA = "6189aa9d647671c05a9f03d815530697560c00b661cad95c87f7f415d482192a"
ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
SUMMARY = re.compile(r"spectre completes with ([0-9]+) errors?, ([0-9]+) warnings?, and ([0-9]+) notices?")
DC_LINE = re.compile(r"^MCP_DC_SCALAR[|](Vop|Vom|VDD|Vp|Vm)[|]([-+0-9.eE]+)$")
AC_VECTOR = re.compile(r"^MCP_AC_VECTOR[|](Vop|Vom|Vp|Vm)[|]([0-9]+)[|]([0-9]+)$")
AC_POINT = re.compile(r"^MCP_AC_POINT[|](Vop|Vom|Vp|Vm)[|]([0-9]+)[|]([-+0-9.eE]+)[|]([-+0-9.eE]+)[|]([-+0-9.eE]+)$")
SIGNALS = ("Vop", "Vom", "Vp", "Vm")
try:
    INTEGER_TYPES = (int, long)
except NameError:
    INTEGER_TYPES = (int,)


def fail():
    sys.stderr.write("fixed work-copy diagnostic failed\n")
    sys.exit(69)


def read(path, limit):
    if os.path.islink(path) or os.stat(path).st_size > limit:
        raise ValueError("unsafe or oversized file")
    with open(path, "rb") as stream:
        return stream.read(limit + 1)


def digest(data):
    if not isinstance(data, bytes):
        data = data.encode("ascii")
    return hashlib.sha256(data).hexdigest()


def write_new(path, data):
    if not isinstance(data, bytes):
        data = data.encode("ascii")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def emit(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if len(data) > 32768:
        raise ValueError("response too large")
    sys.stdout.write(data + "\n")


def validate_args():
    if len(sys.argv) != 4 or sys.argv[1] not in ("preflight", "prepare", "complete", "status", "result", "reserve"):
        sys.exit(64)
    job_id, analysis = sys.argv[2:4]
    if not ID.match(job_id) or analysis not in ("dc", "ac"):
        sys.exit(64)
    return job_id, analysis


def snapshot():
    worker = imp.load_source("sim_mcp_v1_role_guard", BASE)
    base = worker.build_snapshot()
    if (base["source_tree"]["sha256"] != SOURCE_SHA or
            base["protected"]["ade_state_tree"] != STATE_SHA or
            base["protected"]["pdk_model_file"] != MODEL_SHA or
            base["protected"]["fixed_profile_registry"] != PROFILE_SHA or base["locks"]):
        raise ValueError("protected baseline drift")
    if os.path.islink(TARGET) or os.path.realpath(TARGET) != TARGET:
        raise ValueError("copy path")
    target = worker._tree_fingerprint(TARGET)
    project = worker._tree_fingerprint(PROJECT)
    if target["sha256"] != TARGET_SHA or project["sha256"] != PROJECT_SHA:
        raise ValueError("copy drift")
    circuit = read(NETLIST, 10 * 1024 * 1024)
    if digest(circuit) != NETLIST_SHA:
        raise ValueError("netlist drift")
    for line in ("V0 (VDD 0) vsource dc=1 type=dc",
                 "V1 (Vp 0) vsource dc=500m",
                 "V2 (Vm 0) vsource dc=500m",
                 "V3 (Vbiasn 0) vsource dc=VBIASN type=dc",
                 "V4 (Vbiasp 0) vsource dc=VBIASP type=dc"):
        if circuit.count(line) != 1:
            raise ValueError("netlist binding drift")
    fs = os.statvfs(ROOT)
    total = fs.f_blocks * fs.f_frsize
    available = fs.f_bavail * fs.f_frsize
    if available - 128 * 1024 * 1024 < max(2 * 1024 ** 3, (total + 9) // 10):
        raise ValueError("free-space floor")
    return {"source_sha256": SOURCE_SHA, "copy_sha256": TARGET_SHA,
            "project_sha256": PROJECT_SHA, "netlist_sha256": NETLIST_SHA,
            "model_sha256": MODEL_SHA, "protected": base["protected"]}


def wrapper(analysis):
    tail = "dc1 dc\n" if analysis == "dc" else "ac1 ac start=10 stop=100Meg dec=10\n"
    return ("simulator lang=spectre\n\nglobal 0\ninclude \"%s\" section=NN\n"
            "parameters VBIASN=320m VBIASP=702m\ninclude \"design-netlist.scs\"\n\n"
            "simulatorOptions options temp=27 tnom=27\nsave Vop Vom VDD Vp Vm\n%s") % (MODEL, tail)


def prepare(job, analysis):
    before = snapshot()
    if os.path.islink(job) or set(os.listdir(job)) != set(("request.json", "stage", "worker.stdout", "worker.stderr")):
        raise ValueError("job path changed")
    request = json.loads(read(job + "/request.json", 1024))
    if request != {"analysis": analysis, "revision_id": "wp14-copied-netlist-v1",
                   "operating_point_id": "candidate-320-702mv-v1"}:
        raise ValueError("request changed")
    circuit = read(NETLIST, 10 * 1024 * 1024)
    profile = wrapper(analysis)
    write_new(job + "/design-netlist.scs", circuit)
    write_new(job + "/profile.scs", profile)
    before["wrapper_sha256"] = digest(profile)
    before["analysis"] = analysis
    write_new(job + "/before.json", json.dumps(before, sort_keys=True))


def finite(text):
    value = float(text)
    if math.isnan(value) or math.isinf(value) or abs(value) > 1e12:
        raise ValueError("nonfinite measurement")
    return value


def dc_result(data):
    lines = data.splitlines()
    if len(lines) != 6 or lines[-1] != "MCP_DC_SCALAR_COMPLETE|true":
        raise ValueError("DC frame")
    values = {}
    for line in lines[:-1]:
        match = DC_LINE.match(line)
        if match is None or match.group(1) in values:
            raise ValueError("DC scalar")
        values[match.group(1)] = finite(match.group(2))
    if set(values) != set(("Vop", "Vom", "VDD", "Vp", "Vm")):
        raise ValueError("DC outputs")
    if abs(values["VDD"] - 1.0) > 1e-6 or abs(values["Vp"] - 0.5) > 2e-7 or abs(values["Vm"] - 0.5) > 2e-7:
        raise ValueError("DC applied inputs")
    names = (("vop", values["Vop"]), ("vom", values["Vom"]),
             ("vdd", values["VDD"]), ("vp", values["Vp"]), ("vm", values["Vm"]),
             ("output_common_mode", (values["Vop"] + values["Vom"]) / 2.0),
             ("output_differential", values["Vop"] - values["Vom"]))
    return [{"logical_id": name, "unit": "V", "value": value} for name, value in names]


def ac_result(data):
    lines = data.splitlines()
    if tuple(lines[:3]) != ("MCP_AC_STAGE|file_open", "MCP_AC_STAGE|results_open", "MCP_AC_STAGE|ac_selected") or lines[-1] != "MCP_AC_POINT_COMPLETE|true":
        raise ValueError("AC frame")
    cursor = 3
    vectors = {}
    frequencies = None
    for signal in SIGNALS:
        head = AC_VECTOR.match(lines[cursor])
        if head is None or head.group(1) != signal or head.group(2) != head.group(3):
            raise ValueError("AC vector")
        count = int(head.group(2))
        if count < 70 or count > 72:
            raise ValueError("AC count")
        cursor += 1
        points = []
        for index in range(count):
            point = AC_POINT.match(lines[cursor])
            if point is None or point.group(1) != signal or int(point.group(2)) != index:
                raise ValueError("AC point")
            frequency = finite(point.group(3))
            points.append((frequency, complex(finite(point.group(4)), finite(point.group(5)))))
            cursor += 1
        if frequencies is None:
            frequencies = [point[0] for point in points]
        elif any(abs(point[0] - frequencies[index]) > frequencies[index] * 1e-6 for index, point in enumerate(points)):
            raise ValueError("AC frequencies")
        vectors[signal] = points
    if cursor != len(lines) - 1 or len(set(map(len, vectors.values()))) != 1:
        raise ValueError("AC trailing data")
    if abs(frequencies[0] - 10) > 1e-4 or abs(frequencies[-1] - 1e8) > 100:
        raise ValueError("AC endpoints")
    result = []
    for index, frequency in enumerate(frequencies):
        if index and (frequency <= frequencies[index - 1] or frequency / frequencies[index - 1] > 1.4):
            raise ValueError("AC progression")
        input_diff = vectors["Vp"][index][1] - vectors["Vm"][index][1]
        if abs(abs(input_diff) - 1.0) > 1e-6:
            raise ValueError("AC applied input")
        gain = (vectors["Vop"][index][1] - vectors["Vom"][index][1]) / input_diff
        magnitude = abs(gain)
        if math.isnan(magnitude) or math.isinf(magnitude) or magnitude > 1e12:
            raise ValueError("AC gain")
        result.append({"frequency_hz": frequency, "gain_v_per_v": magnitude,
                       "gain_db": 20.0 * math.log10(magnitude) if magnitude else None,
                       "phase_deg": math.degrees(math.atan2(gain.imag, gain.real))})
    return result


def complete(job, analysis):
    before = json.loads(read(job + "/before.json", 16384))
    after = snapshot()
    if any(before.get(key) != value for key, value in after.items()) or before.get("analysis") != analysis:
        raise ValueError("protected pre/post drift")
    if digest(read(job + "/design-netlist.scs", 10 * 1024 * 1024)) != NETLIST_SHA or digest(read(job + "/profile.scs", 8192)) != before["wrapper_sha256"]:
        raise ValueError("job-local binding drift")
    log = read(job + "/spectre.log", 10 * 1024 * 1024)
    found = SUMMARY.findall(log)
    if len(found) != 1:
        raise ValueError("Spectre summary")
    errors, warnings, notices = map(int, found[0])
    warning_lines = [line for line in log.splitlines() if "WARNING" in line]
    if errors or warnings > 2 or len(warning_lines) != warnings or any("WARNING (CMI-2477):" not in line for line in warning_lines):
        raise ValueError("Spectre result quality")
    worker = imp.load_source("sim_mcp_v1_result_guard", BASE)
    psf = job + "/psf"
    if os.path.islink(psf) or not os.path.isdir(psf):
        raise ValueError("PSF missing")
    tree = worker._tree_fingerprint(psf)
    if tree["entry_count"] == 0 or tree["total_bytes"] == 0 or tree["total_bytes"] > 128 * 1024 * 1024:
        raise ValueError("PSF size")
    data = read(job + "/scalars.txt", 32768)
    scalars = dc_result(data) if analysis == "dc" else []
    spectrum = ac_result(data) if analysis == "ac" else []
    emit({"job_id": os.path.basename(job), "state": "succeeded",
          "profile_id": "actual-wp14-" + analysis + "-v1",
          "revision_id": "wp14-copied-netlist-v1",
          "operating_point_id": "candidate-320-702mv-v1",
          "simulator": "succeeded", "extraction": "succeeded", "quality": "valid",
          "spec_evaluation": "not_evaluated", "source_sha256": SOURCE_SHA,
          "copy_sha256": TARGET_SHA, "netlist_sha256": NETLIST_SHA,
          "wrapper_sha256": before["wrapper_sha256"], "psf_sha256": tree["sha256"],
          "vdd_v": 1.0, "input_vcm_v": 0.5,
          "applied_bias_values_v": [0.32, 0.702],
          "scalars": scalars, "spectrum": spectrum,
          "artifact_names": ["profile.scs", "spectre.log", "psf", "scalars.txt"]})


def status(job, analysis):
    request = json.loads(read(job + "/request.json", 1024))
    if request.get("analysis") != analysis:
        raise ValueError("job analysis mismatch")
    stage = read(job + "/stage", 64).strip()
    if stage not in ("queued", "running", "extracting", "succeeded", "failed", "simulator_failed", "extraction_failed"):
        raise ValueError("job stage")
    state = {"queued": "queued", "running": "running", "extracting": "running",
             "succeeded": "succeeded", "failed": "failed",
             "simulator_failed": "failed", "extraction_failed": "failed"}[stage]
    simulator = ("succeeded" if stage in ("extracting", "succeeded", "extraction_failed")
                 else "failed" if stage == "simulator_failed"
                 else "running" if stage == "running" else "not_started")
    extraction = ("succeeded" if stage == "succeeded" else "failed" if stage == "extraction_failed"
                  else "running" if stage == "extracting" else "not_started")
    emit({"job_id": os.path.basename(job), "state": state,
          "profile_id": "actual-wp14-" + analysis + "-v1",
          "revision_id": "wp14-copied-netlist-v1", "operating_point_id": "candidate-320-702mv-v1",
          "updated_at": __import__("datetime").datetime.utcfromtimestamp(os.stat(job + "/stage").st_mtime).isoformat() + "Z",
          "simulator": simulator, "extraction": extraction})


def reserve(job):
    counter_path = JOBS + "/counter.json"
    counter = json.loads(read(counter_path, 1024))
    if counter.get("campaign_id") != "AUTO-PHASE-01" or type(counter.get("count")) is not int or not 9 <= counter["count"] < 100:
        raise ValueError("Spectre budget")
    if type(counter.get("result_reserved_bytes")) not in INTEGER_TYPES:
        raise ValueError("result budget")
    if (counter["result_reserved_bytes"] < 1048576 or
            counter["result_reserved_bytes"] + 128 * 1024 * 1024 > 5 * 1024 ** 3):
        raise ValueError("result budget")
    marker = job + "/attempt-reserved"
    if os.path.lexists(marker):
        raise ValueError("attempt replay")
    write_new(marker, str(counter["count"] + 1) + "\n")
    temporary = counter_path + ".tmp"
    write_new(temporary, json.dumps({"campaign_id": "AUTO-PHASE-01",
                                     "count": counter["count"] + 1,
                                     "result_reserved_bytes": counter["result_reserved_bytes"] + 128 * 1024 * 1024}))
    os.rename(temporary, counter_path)


def main():
    job_id, analysis = validate_args()
    job = JOBS + "/" + job_id
    command = sys.argv[1]
    if command == "preflight":
        emit(snapshot())
    elif command == "prepare":
        prepare(job, analysis)
    elif command == "complete":
        complete(job, analysis)
    elif command == "status":
        status(job, analysis)
    elif command == "reserve":
        reserve(job)
    else:
        if read(job + "/stage", 64).strip() != "succeeded":
            raise ValueError("result not complete")
        sys.stdout.write(read(job + "/result.json", 32768))


if __name__ == "__main__":
    try:
        main()
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError, IndexError, ZeroDivisionError):
        fail()
