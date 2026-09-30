#!/usr/bin/env python
"""Closed native AC/TRAN qualification, using the immutable qualified DC guard."""
from __future__ import with_statement

import imp
import json
import math
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/native-ac-tran-v3"
BASE = imp.load_source("native_dc_guard", ROOT + "/phase-campaign/ade-qual-v6/helper.py")
DC_VALIDATE = BASE.validate_netlist
DC_RESULT = ROOT + "/ade-qual-v6/result.json"
DC_RESULT_SHA = "c7b5ce95bf17e93d8a95d1985f294c8b342d708bd6951822a509972daba04045"
ANALYSIS = None


def configure(analysis):
    global ANALYSIS
    if analysis not in ("ac", "tran"):
        raise ValueError("closed analysis")
    ANALYSIS = analysis
    BASE.VERSION = VERSION
    BASE.JOB = ROOT + "/native-ac-tran-v3-" + analysis
    BASE.COPIED_STATE = BASE.JOB + "/state-root/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/spectre/state1"
    BASE.NETDIR = BASE.JOB + "/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
    BASE.validate_netlist = validate_netlist


def validate_netlist(text, circuit, previous, facts):
    if not circuit or text.count(circuit) != 1:
        raise ValueError("native circuit binding")
    prefix, suffix = text.split(circuit)
    logical = re.sub(r"\\\r?\n\s*", " ", suffix)
    lines = [line.strip() for line in logical.splitlines() if line.strip()]
    analyses = [line for line in lines if re.match(r"^\w+ (dc|ac|tran|noise|stb)\b", line)]
    if len(analyses) != 1:
        raise ValueError("native analysis count")
    parts = analyses[0].split()
    if parts[:2] != [ANALYSIS, ANALYSIS]:
        raise ValueError("native analysis identity")
    pairs = [item.split("=", 1) for item in parts[2:]]
    if any(len(pair) != 2 for pair in pairs) or len(dict(pairs)) != len(pairs):
        raise ValueError("native analysis parameters")
    expected = ({"start": "10", "stop": "100M", "dec": "10", "annotate": "status"}
                if ANALYSIS == "ac" else
                {"stop": "4m", "maxstep": "10u", "write": '"spectre.ic"',
                 "writefinal": '"spectre.fc"', "annotate": "status", "maxiters": "5"})
    if dict(pairs) != expected:
        raise ValueError("native analysis controls")
    lines.remove(analyses[0])
    if ANALYSIS == "tran":
        final_op = "finalTimeOP info what=oppoint where=rawfile"
        if lines.count(final_op) != 1:
            raise ValueError("native final operating point")
        lines.remove(final_op)
    dc_controls = BASE.NATIVE_CONTROL.splitlines()
    dc_controls = [line for line in dc_controls if not line.startswith(("dcOp dc ", "dcOpInfo info "))]
    if " ".join(lines).split() != " ".join(dc_controls).split():
        raise ValueError("native ancillary control boundary")
    # The reused validator covers source equivalence, supply, parameters, include,
    # temperature and exact native header after our separate closed control check.
    DC_VALIDATE(prefix + circuit + BASE.NATIVE_CONTROL, circuit, previous, facts)
    sources = {}
    for line in re.sub(r"\\\r?\n\s*", " ", circuit).splitlines():
        match = re.match(r"^(V[12]) \((Vp|Vm) 0\) vsource (.+)$", line.strip())
        if match:
            key, node, fields = match.groups()
            tokens = fields.split()
            pairs = [token.split("=", 1) for token in tokens]
            if any(len(pair) != 2 for pair in pairs) or len(dict(pairs)) != len(pairs) or key in sources:
                raise ValueError("stimulus syntax")
            sources[key] = (node, dict(pairs))
    expected_sources = {
        "V1": ("Vp", {"dc": "500m", "mag": "500m", "type": "sine", "ampl": "50m", "freq": "1K"}),
        "V2": ("Vm", {"dc": "500m", "mag": "-500m", "type": "sine", "ampl": "50m", "sinephase": "180", "freq": "1K"})}
    if sources != expected_sources:
        raise ValueError("input stimulus binding")
    return ANALYSIS


def netlist():
    log=BASE.read(BASE.JOB + "/netlist.log").decode("latin-1")
    if [line[3:].strip() for line in log.splitlines() if line.startswith("\\o ")].count(
            "MCP_NATIVE_ANALYSIS|" + ANALYSIS) != 1:
        raise ValueError("native analysis configuration proof")
    if [line[3:].strip() for line in log.splitlines() if line.startswith("\\o ")].count(
            "MCP_NATIVE_SESSION_RESTORED|true") != 1:
        raise ValueError("session restoration proof")
    BASE.netlist()


def emit(data):
    # Native netlist metadata retains saved DC enablement separately from applied
    # job-only analysis controls. No observed setting is overwritten in the state.
    data["analysis"] = ANALYSIS
    data["job_analysis_override"] = ( {"start_hz": 10, "stop_hz": 1e8, "points_per_decade": 10}
                                     if ANALYSIS == "ac" else {"stop_s": 0.004, "maxstep_s": 1e-5})
    data["candidate_preserved_v"] = [0.32, 0.702]
    text = json.dumps(data, sort_keys=True)
    if len(text) > 32768:
        raise ValueError("bounded result")
    sys.stdout.write(text + "\n")


def prepare():
    data=BASE.read(DC_RESULT, 32768)
    if BASE.sha(data) != DC_RESULT_SHA:
        raise ValueError("DC predecessor drift")
    predecessor = json.loads(data)
    if (predecessor.get("quality") != "valid" or predecessor.get("simulation") != "succeeded"
            or predecessor.get("analysis") != "dc"):
        raise ValueError("qualified DC predecessor")
    BASE.prepare()


def extraction():
    facts = BASE.verify_netlist()
    if facts["result_name"] != ANALYSIS:
        raise ValueError("native selector mismatch")
    template = BASE.read(VERSION + "/extract-" + ANALYSIS + ".ocn").decode("ascii")
    BASE.write_new(BASE.JOB + "/extract.ocn", template.replace("@JOB@", BASE.JOB))


def tran_result(text):
    finite = BASE.guard().finite
    lines = text.splitlines()
    if not lines or lines[0] != "MCP_TRAN_BEGIN" or lines[-1] != "MCP_TRAN_COMPLETE":
        raise ValueError("TRAN frame")
    cursor = 1
    vectors = {}
    times = None
    for signal in ("Vop", "Vom", "Vp", "Vm", "VDD"):
        head = lines[cursor].split("|")
        cursor += 1
        if len(head) != 4 or head[:2] != ["MCP_TRAN_VECTOR", signal] or head[2] != head[3]:
            raise ValueError("TRAN vector")
        count = int(head[2])
        if not 401 <= count <= 3000:
            raise ValueError("TRAN count")
        values = []
        axis = []
        for index in range(count):
            point = lines[cursor].split("|")
            cursor += 1
            if len(point) != 5 or point[:3] != ["MCP_TRAN_POINT", signal, str(index)]:
                raise ValueError("TRAN point")
            axis.append(finite(point[3]))
            values.append(finite(point[4]))
        if times is None:
            times = axis
        elif axis != times:
            raise ValueError("TRAN time binding")
        vectors[signal] = values
    if cursor != len(lines) - 1 or times[0] != 0 or abs(times[-1] - 0.004) > 1e-12:
        raise ValueError("TRAN endpoints or trailing data")
    for index, time in enumerate(times):
        if index and not 0 < time - times[index - 1] <= 1.00001e-5:
            raise ValueError("TRAN monotonic step")
        excitation = 0.05 * math.sin(2 * math.pi * 1000 * time)
        if (abs(vectors["Vp"][index] - (0.5 + excitation)) > 1e-5 or
                abs(vectors["Vm"][index] - (0.5 - excitation)) > 1e-5 or
                abs(vectors["VDD"][index] - 1.0) > 1e-9):
            raise ValueError("TRAN applied stimulus or supply")
    output = [p - m for p, m in zip(vectors["Vop"], vectors["Vom"])]
    common = [(p + m) / 2.0 for p, m in zip(vectors["Vop"], vectors["Vom"])]
    return {"point_count": len(times), "start_s": times[0], "stop_s": times[-1],
            "max_observed_step_s": max(b - a for a, b in zip(times, times[1:])),
            "output_differential_min_v": min(output), "output_differential_max_v": max(output),
            "output_common_mode_min_v": min(common), "output_common_mode_max_v": max(common),
            "input_vcm_v": 0.5, "input_differential_peak_v": 0.1,
            "input_tone_hz": 1000, "vdd_v": 1.0,
            "sampling": "adaptive_native_no_fft", "stimulus_verified": True}


def complete():
    facts = BASE.verify_netlist()
    diag = BASE.guard()
    log = BASE.read(BASE.JOB + "/spectre.log").decode("latin-1")
    summary = diag.SUMMARY.findall(log)
    if len(summary) != 1 or int(summary[0][0]):
        raise ValueError("simulator completion")
    warnings = [line for line in log.splitlines() if "WARNING" in line]
    if (len(warnings) != int(summary[0][1]) or len(warnings) > 2 or
            any("WARNING (CMI-2477):" not in line for line in warnings)):
        raise ValueError("simulator warning quality")
    extract_log = BASE.read(BASE.JOB + "/extract.log").decode("latin-1")
    if any("*Error*" in line for line in extract_log.splitlines() if not line.startswith("\\i ")):
        raise ValueError("native extraction error")
    if BASE.read(BASE.JOB + "/selector.txt", 64).decode("ascii") != "MCP_NATIVE_SELECTOR|" + ANALYSIS + "\n":
        raise ValueError("selector proof")
    data = BASE.read(BASE.JOB + "/scalars.txt", 2 * 1024 ** 2).decode("ascii")
    if ANALYSIS == "ac":
        facts["spectrum"] = diag.ac_result(data)
    else:
        facts["transient"] = tran_result(data)
    role = imp.load_source("native_role", ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py")
    psf = role._tree_fingerprint(BASE.JOB + "/psf")
    if psf["entry_count"] == 0 or not 0 < psf["total_bytes"] <= BASE.RESERVATION:
        raise ValueError("PSF bounds")
    facts.update({"simulation": "succeeded", "extraction": "succeeded", "quality": "valid",
                  "psf_sha256": psf["sha256"], "warnings": len(warnings), "notices": int(summary[0][2]),
                  "result_selector": ANALYSIS, "measurement_frame_sha256": BASE.sha(data.encode("ascii")),
                  "counter": json.loads(BASE.read(BASE.COUNTER, 1024))})
    emit(facts)


def main():
    if len(sys.argv) not in (3, 4):
        raise ValueError("fixed helper arguments")
    configure(sys.argv[2])
    BASE.emit = emit
    action = sys.argv[1]
    if action == "stage" and len(sys.argv) == 4:
        BASE.set_stage(sys.argv[3])
    elif len(sys.argv) == 3 and action in ("prepare", "netlist", "extraction", "complete"):
        globals()[action]()
    elif len(sys.argv) == 3 and action in ("reserve", "status"):
        getattr(BASE, action)()
    else:
        raise ValueError("closed helper action")


if __name__ == "__main__":
    try:
        main()
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError, IndexError, ZeroDivisionError):
        sys.stderr.write("fixed native AC/TRAN qualification failed\n")
        sys.exit(69)
