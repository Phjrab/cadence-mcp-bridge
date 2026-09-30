#!/usr/bin/env python
"""Python 2.6 adapter for qualified native guards and closed MCP projections."""
from __future__ import with_statement

import imp
import json
import os
import re
import subprocess
import sys
import time

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/native-mcp-v1"
JOBS = ROOT + "/native-mcp-v1-jobs"
CAND = imp.load_source("native_mcp_candidate", ROOT + "/phase-campaign/native-candidate-v2/helper.py")
BASE = CAND.BASE
ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
REVISION = "wp14-native-ade-v1"
OPERATING_POINT = "candidate-320-702mv-v1"
REFERENCE_RESULTS = {
    "/native-candidate-v1-dc/result.json": "b401e57eac543e505dadf135753bd62c09a2fceb05b96a00615d3d6403350dd5",
    "/native-candidate-v2-ac/result.json": "ba7bd129f7bdbc5432a159e2db263e27cda8c12a76d5458f97850d004cb02fee",
    "/native-candidate-v2-tran/result.json": "afc6ef28eb9b9e3024afaa658e545609fca976e2d051c0f447f847d9ba7fa6d2",
}
RECORD = None
ANALYSIS = None
SETTINGS = {
    "corner": "NN", "temperature_c": 27, "vdd_v": 1.0, "input_vcm_v": 0.5,
    "saved_bias_values_v": [0.3, 0.65], "applied_bias_values_v": [0.32, 0.702],
    "saved_enabled_analyses": ["dc"], "ac_start_hz": 10, "ac_stop_hz": 100000000,
    "ac_points_per_decade": 10, "tran_stop_s": 0.004, "tran_maxstep_s": 1e-5,
    "tran_method": "trap", "stimulus": "existing_opposed_1khz_50mv_peak_inputs",
    "load": "existing_topology_no_added_external_load",
}


def contained(path):
    if os.path.realpath(path) != path or not path.startswith(JOBS + "/"):
        raise ValueError("native job containment")


def configure(job_id, analysis):
    global RECORD, ANALYSIS
    if not ID.match(job_id) or analysis not in ("dc", "ac", "tran"):
        raise ValueError("closed native job identity")
    if os.path.islink(JOBS) or os.path.realpath(JOBS) != JOBS:
        raise ValueError("native jobs root")
    RECORD = JOBS + "/" + job_id
    ANALYSIS = analysis
    contained(RECORD)
    CAND.configure(analysis)
    CAND.VERSION = VERSION
    CAND.NATIVE.VERSION = VERSION
    BASE.VERSION = VERSION
    BASE.JOB = RECORD + "/work"
    BASE.COPIED_STATE = BASE.JOB + "/state-root/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/spectre/state1"
    BASE.NETDIR = BASE.JOB + "/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
    contained(BASE.JOB)


def request():
    data = json.loads(BASE.read(RECORD + "/request.json", 1024))
    if data != {"analysis": ANALYSIS, "revision_id": REVISION,
                "operating_point_id": OPERATING_POINT}:
        raise ValueError("native request identity mismatch")


def references():
    CAND.verify_predecessors()
    for path, expected in REFERENCE_RESULTS.items():
        data = BASE.read(ROOT + path, 32768)
        if BASE.sha(data) != expected or json.loads(data).get("quality") != "valid":
            raise ValueError("native reference result drift")


def preflight():
    BASE.environment_preflight()
    BASE.snapshot()
    references()
    if BASE.state_facts()["variables_v"] != CAND.SAVED:
        raise ValueError("source saved settings drift")
    counter = json.loads(BASE.read(BASE.COUNTER, 1024))
    if (counter.get("campaign_id") != "AUTO-PHASE-01"
            or type(counter.get("count")) not in BASE.INTEGER_TYPES
            or not 21 <= counter["count"] < 100
            or type(counter.get("result_reserved_bytes")) not in BASE.INTEGER_TYPES
            or not 1611661312 <= counter["result_reserved_bytes"] <= 5 * 1024 ** 3 - BASE.RESERVATION):
        raise ValueError("cumulative native budget")


def prepare():
    request()
    preflight()
    CAND.prepare()
    template = BASE.read(VERSION + "/netlist-" + ANALYSIS + ".ocn").decode("ascii")
    if "@JOB@" not in template:
        raise ValueError("native routing template")
    BASE.write_new(BASE.JOB + "/netlist.ocn", template.replace("@JOB@", BASE.JOB))


def complete():
    request()
    references()
    def checked(data):
        frame_sha = BASE.sha(BASE.read(BASE.JOB + "/scalars.txt", 2 * 1024 ** 2))
        data["measurement_frame_sha256"] = frame_sha
        project(data, os.path.basename(RECORD), ANALYSIS, frame_sha)
        CAND.emit(data)
    BASE.emit = checked
    CAND.NATIVE.emit = checked
    if ANALYSIS == "dc":
        BASE.complete()
    else:
        CAND.NATIVE.complete()


def status():
    request()
    outer = BASE.read(RECORD + "/stage", 64).decode("ascii").strip()
    stage = outer
    if outer not in ("queued", "failed"):
        raise ValueError("native outer stage")
    if outer != "failed" and os.path.isfile(BASE.JOB + "/stage"):
        stage = BASE.read(BASE.JOB + "/stage", 64).decode("ascii").strip()
        if stage not in BASE.STAGES:
            raise ValueError("native work stage")
    state = "succeeded" if stage == "succeeded" else "failed" if stage.endswith("failed") else "queued" if stage == "queued" else "running"
    # A lost worker is unknown and keeps the active/replay evidence intact.
    if state in ("running", "queued"):
        if not os.path.isfile(RECORD + "/worker.pid"):
            state = "unknown"
        else:
            pid = BASE.read(RECORD + "/worker.pid", 64).decode("ascii").strip()
            if not re.match(r"^[1-9][0-9]{0,9}$", pid):
                raise ValueError("native worker PID")
            try:
                args = BASE.read("/proc/" + pid + "/cmdline", 4096)
                if (VERSION + "/run.sh\x00worker\x00" + os.path.basename(RECORD) + "\x00" + ANALYSIS).encode("ascii") not in args:
                    state = "unknown"
            except (IOError, OSError, ValueError):
                state = "unknown"
    simulator = ("succeeded" if stage in ("extracting", "extraction_failed", "verifying", "verification_failed", "succeeded") else "failed" if stage == "simulator_failed" else "running" if stage == "simulating" else "not_started")
    extraction = ("succeeded" if stage in ("verifying", "verification_failed", "succeeded") else "failed" if stage == "extraction_failed" else "running" if stage == "extracting" else "not_started")
    touched = os.path.getmtime(BASE.JOB + "/stage" if stage in BASE.STAGES else RECORD + "/stage")
    emit({"job_id": os.path.basename(RECORD), "revision_id": REVISION,
          "operating_point_id": OPERATING_POINT, "analysis": ANALYSIS,
          "state": state, "stage": stage, "simulator": simulator, "extraction": extraction,
          "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(touched))})


def project(data, job_id, analysis, frame_sha):
    saved = {"variables_v": CAND.SAVED, "enabled_analyses": ["dc"],
             "model_section": "NN", "temperature_c": 27}
    effective = dict(saved)
    effective["variables_v"] = CAND.CANDIDATE
    override = ({} if analysis == "dc" else {"start_hz": 10, "stop_hz": 1e8, "points_per_decade": 10}
                if analysis == "ac" else {"stop_s": 0.004, "maxstep_s": 1e-5, "method": "trap"})
    if (data.get("analysis") != analysis or data.get("quality") != "valid"
            or data.get("simulation") != "succeeded" or data.get("extraction") != "succeeded"
            or data.get("applied_bias_values_v") != [0.32, 0.702]
            or data.get("source_saved_state") != saved or data.get("effective") != effective
            or data.get("job_analysis_override") != override or data.get("vdd_v") != 1.0
            or data.get("spec_evaluation") != "not_evaluated"
            or data.get("execution_mode") != "native_ade_owned_candidate_state"
            or data.get("notices") != 0 or data.get("result_selector") != ("dcOp" if analysis == "dc" else analysis)):
        raise ValueError("native result provenance")
    hashes = ("source_sha256", "copy_sha256", "state_sha256", "model_sha256",
              "circuit_sha256", "input_sha256", "owned_variables_sha256", "psf_sha256")
    result = dict((key, data[key]) for key in hashes)
    result.update({"job_id": job_id, "revision_id": REVISION, "operating_point_id": OPERATING_POINT,
                   "analysis": analysis, "state": "succeeded", "simulator": "succeeded",
                   "extraction": "succeeded", "quality": "valid", "spec_evaluation": "not_evaluated",
                   "execution_mode": data["execution_mode"], "settings": SETTINGS,
                   "measurement_frame_sha256": frame_sha, "result_selector": data["result_selector"],
                   "warnings": data["warnings"], "notices": data["notices"],
                   "scalars": data.get("scalars", []), "spectrum": data.get("spectrum", []),
                   "transient": data.get("transient")})
    for key in ("protected_unchanged", "source_copy_signature_equal", "state_loaded", "netlist_valid"):
        if data.get(key) is not True:
            raise ValueError("native result verification flag")
        result[key] = True
    return result


def result():
    request()
    if BASE.read(BASE.JOB + "/stage", 64) != b"succeeded\n":
        raise ValueError("native result incomplete")
    references()
    facts = BASE.verify_netlist()
    data = json.loads(BASE.read(BASE.JOB + "/result.json", 32768))
    for key in ("input_sha256", "circuit_sha256", "source_sha256", "copy_sha256",
                "state_sha256", "model_sha256", "owned_variables_sha256",
                "source_saved_state", "effective"):
        if facts[key] != data.get(key):
            raise ValueError("native result input provenance drift")
    frame = BASE.read(BASE.JOB + "/scalars.txt", 2 * 1024 ** 2).decode("ascii")
    if data.get("measurement_frame_sha256") != BASE.sha(frame.encode("ascii")):
        raise ValueError("native measurement frame digest drift")
    parsed = (BASE.guard().dc_result(frame) if ANALYSIS == "dc" else BASE.guard().ac_result(frame)
              if ANALYSIS == "ac" else CAND.NATIVE.tran_result(frame))
    key = "scalars" if ANALYSIS == "dc" else "spectrum" if ANALYSIS == "ac" else "transient"
    if parsed != data.get(key):
        raise ValueError("native saved measurement drift")
    psf = CAND.tree(BASE.JOB + "/psf")
    if psf["sha256"] != data["psf_sha256"] or not 0 < psf["total_bytes"] <= BASE.RESERVATION:
        raise ValueError("native PSF drift")
    emit(project(data, os.path.basename(RECORD), ANALYSIS, BASE.sha(frame.encode("ascii"))))


def postflight():
    BASE.environment_preflight()
    BASE.snapshot()
    references()
    process = subprocess.Popen(["ps", "-eo", "comm"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors = process.communicate()
    if process.returncode or errors or any(line.strip() in ("spectre", "ocean", "virtuoso") for line in output.splitlines()):
        raise ValueError("active EDA boundary")
    if os.path.lexists(JOBS + "/active"):
        raise ValueError("unresolved native active claim")
    jobs = {}
    for name in os.listdir(JOBS):
        if name == "control.lock":
            continue
        if not ID.match(name):
            raise ValueError("unexpected native job entry")
        path = JOBS + "/" + name
        contained(path)
        data = json.loads(BASE.read(path + "/request.json", 1024))
        configure(name, data["analysis"])
        request()
        if os.path.isfile(BASE.JOB + "/before.json"):
            CAND.verify_protected(json.loads(BASE.read(BASE.JOB + "/before.json")))
        tree = CAND.tree(path)
        if tree["total_bytes"] > BASE.RESERVATION:
            raise ValueError("native job result budget")
        jobs[name] = {"total_bytes": tree["total_bytes"], "tree_sha256": tree["sha256"]}
    disk = os.statvfs(ROOT)
    emit({"protected_unchanged": True, "reference_results_unchanged": True, "active_eda": 0,
          "free_bytes": disk.f_bavail * disk.f_frsize, "total_bytes": disk.f_blocks * disk.f_frsize,
          "counter": json.loads(BASE.read(BASE.COUNTER, 1024)), "jobs": jobs,
          "spec_evaluation": "not_evaluated"})


def emit(data):
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    if len(text) > 32768:
        raise ValueError("bounded native MCP response")
    sys.stdout.write(text + "\n")


def main():
    if len(sys.argv) not in (4, 5):
        raise ValueError("native arguments")
    action, job_id, analysis = sys.argv[1:4]
    configure(job_id, analysis)
    if action == "stage" and len(sys.argv) == 5:
        BASE.set_stage(sys.argv[4])
    elif len(sys.argv) == 4 and action in ("preflight", "prepare", "complete", "status", "result", "postflight"):
        globals()[action]()
    elif len(sys.argv) == 4 and action == "netlist":
        request()
        CAND.netlist()
    elif len(sys.argv) == 4 and action == "reserve":
        request()
        preflight()
        BASE.reserve()
    elif len(sys.argv) == 4 and action == "extraction":
        request()
        (BASE if ANALYSIS == "dc" else CAND.NATIVE).extraction()
    else:
        raise ValueError("closed native action")


if __name__ == "__main__":
    try:
        main()
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError, IndexError, ZeroDivisionError):
        sys.stderr.write("fixed native MCP operation failed\n")
        sys.exit(69)
