#!/usr/bin/env python
"""Fixed candidate in owned ADE state copies; original state is fingerprinted."""
from __future__ import with_statement

import imp
import json
import os
import re
import subprocess
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/native-candidate-v1"
NATIVE = imp.load_source("candidate_native_guard", ROOT + "/phase-campaign/native-ac-tran-v4/helper.py")
BASE = NATIVE.BASE
ORIGINAL_VERIFY = BASE.verify_protected
SAVED = {"VBIASN": 0.3, "VBIASP": 0.65}
CANDIDATE = {"VBIASN": 0.32, "VBIASP": 0.702}
PREDECESSORS = {
    "/ade-qual-v6/result.json": "c7b5ce95bf17e93d8a95d1985f294c8b342d708bd6951822a509972daba04045",
    "/native-ac-tran-v3-ac/result.json": "34fd3ccd04c19cfe820c5ca6dbd829651dd600064628699cc3c1d501153ba57d",
    "/native-ac-tran-v3-tran/result.json": "c706574585cb4246e889de306f127a5eb84a83a079c28a03bfc3c37ac1f29d82",
    "/native-ac-tran-v4-tran/result.json": "870a96127feb8a168cbba094808f562017b181f407b1fb8bbbf741d1efb01f6a",
}
ANALYSIS = None


def configure(analysis):
    global ANALYSIS
    if analysis not in ("dc", "ac", "tran"):
        raise ValueError("closed candidate analysis")
    ANALYSIS = analysis
    NATIVE.ANALYSIS = analysis
    BASE.VERSION = VERSION
    BASE.JOB = ROOT + "/native-candidate-v1-" + analysis
    BASE.COPIED_STATE = BASE.JOB + "/state-root/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/spectre/state1"
    BASE.NETDIR = BASE.JOB + "/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
    BASE.validate_netlist = validate_netlist
    BASE.verify_protected = verify_protected
    BASE.emit = emit
    NATIVE.emit = emit


def verify_predecessors():
    for path, expected in PREDECESSORS.items():
        data = BASE.read(ROOT + path, 32768)
        if BASE.sha(data) != expected or json.loads(data).get("quality") != "valid":
            raise ValueError("native predecessor drift")


def candidate_variables(original):
    text = original.decode("latin-1")
    names = re.findall(r'(?m)^tmp([0-9]+)->name = "([^"\n]+)"$', text)
    expressions = re.findall(r'(?m)^tmp([0-9]+)->expression = "([^"\n]+)"$', text)
    if (len(names) != 2 or len(expressions) != 2 or len(dict(names)) != 2
            or len(dict(expressions)) != 2 or set(dict(names).values()) != set(SAVED)
            or set(dict(names)) != set(dict(expressions))):
        raise ValueError("closed candidate variables")
    name_map = dict(names)
    for index, expression in expressions:
        if BASE.number(expression) != SAVED[name_map[index]]:
            raise ValueError("saved source bias drift")
    replacements = {"VBIASN": "320m", "VBIASP": "702m"}
    def replace(match):
        return match.group(1) + '"' + replacements[name_map[match.group(2)]] + '"'
    changed, count = re.subn(r'(?m)^(tmp([0-9]+)->expression = )"([^"\n]+)"$', replace, text)
    if count != 2 or changed == text:
        raise ValueError("candidate substitution count")
    return changed.encode("latin-1")


def verify_protected(before):
    verify_predecessors()
    after = BASE.snapshot()
    if (dict((key, before[key]) for key in after) != after
            or before["state_facts"] != BASE.state_facts()
            or before["state_facts"]["variables_v"] != SAVED):
        raise ValueError("protected original drift")
    if BASE.sha(BASE.read(BASE.COPIED_STATE + "/ADE_state.info")) != before["state_copy_info_sha256"]:
        raise ValueError("owned state routing drift")
    original = BASE.read(BASE.STATE + "/variables")
    candidate = candidate_variables(original)
    if BASE.read(BASE.COPIED_STATE + "/variables") != candidate:
        raise ValueError("owned candidate variables drift")
    expected = []
    for record in BASE.state_records(BASE.STATE):
        if record[:2] == ("file", os.path.join(".", "variables")):
            record = (record[0], record[1], BASE.sha(candidate))
        expected.append(record)
    if sorted(expected) != BASE.state_records(BASE.COPIED_STATE):
        raise ValueError("owned state non-variable drift")
    mutation = json.loads(BASE.read(BASE.JOB + "/candidate-state.json", 4096))
    if mutation != {"source_variables_sha256": BASE.sha(original),
                    "owned_variables_sha256": BASE.sha(candidate),
                    "requested_variables_v": CANDIDATE, "source_variables_v": SAVED}:
        raise ValueError("candidate state proof drift")


def prepare():
    verify_predecessors()
    if BASE.state_facts()["variables_v"] != SAVED:
        raise ValueError("saved source bias drift")
    # First use the unchanged DC guard to create and verify an exact state copy.
    BASE.verify_protected = ORIGINAL_VERIFY
    try:
        BASE.prepare()
    finally:
        BASE.verify_protected = verify_protected
    original = BASE.read(BASE.COPIED_STATE + "/variables")
    candidate = candidate_variables(original)
    BASE.write_new(BASE.JOB + "/source-variables.bin", original)
    BASE.write_new(BASE.COPIED_STATE + "/variables.candidate-new", candidate)
    os.rename(BASE.COPIED_STATE + "/variables.candidate-new", BASE.COPIED_STATE + "/variables")
    BASE.save(BASE.JOB + "/candidate-state.json", {
        "source_variables_sha256": BASE.sha(original), "owned_variables_sha256": BASE.sha(candidate),
        "requested_variables_v": CANDIDATE, "source_variables_v": SAVED})
    verify_protected(json.loads(BASE.read(BASE.JOB + "/before.json")))


def validate_netlist(text, circuit, previous, facts):
    if facts["variables_v"] != SAVED:
        raise ValueError("saved facts are distinct from candidate")
    effective = dict(facts)
    effective["variables_v"] = CANDIDATE
    if ANALYSIS == "dc":
        return NATIVE.DC_VALIDATE(text, circuit, previous, effective)
    return NATIVE.validate_netlist(text, circuit, previous, effective)


def emit(data):
    if data.get("netlist_valid"):
        saved = data.get("source_saved_state", data["effective"])
        if saved["variables_v"] != SAVED or data["effective"]["variables_v"] not in (SAVED, CANDIDATE):
            raise ValueError("saved source result binding")
        data["source_saved_state"] = saved
        data["effective"] = dict(saved)
        data["effective"]["variables_v"] = CANDIDATE
        data["applied_bias_values_v"] = [0.32, 0.702]
        data["candidate_applied_in"] = "owned_ADE_state_copy_native_netlist_verified"
        data["execution_mode"] = "native_ade_owned_candidate_state"
        data["analysis"] = ANALYSIS
        data["job_analysis_override"] = ({"start_hz": 10, "stop_hz": 1e8, "points_per_decade": 10}
            if ANALYSIS == "ac" else {"stop_s": 0.004, "maxstep_s": 1e-5, "method": "trap"}
            if ANALYSIS == "tran" else {})
        data["owned_variables_sha256"] = BASE.sha(BASE.read(BASE.COPIED_STATE + "/variables"))
    text = json.dumps(data, sort_keys=True)
    if len(text) > 32768:
        raise ValueError("bounded candidate result")
    sys.stdout.write(text + "\n")


def netlist():
    log = BASE.read(BASE.JOB + "/netlist.log").decode("latin-1")
    actual = [line[3:].strip() for line in log.splitlines() if line.startswith("\\o ")]
    for marker in ("MCP_NATIVE_ANALYSIS|" + ANALYSIS, "MCP_NATIVE_SESSION_RESTORED|true"):
        if actual.count(marker) != 1:
            raise ValueError("native candidate analysis proof")
    BASE.netlist()


def postflight():
    verify_predecessors()
    BASE.environment_preflight()
    process = subprocess.Popen(["ps", "-eo", "comm"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors = process.communicate()
    if process.returncode or errors or any(line.strip() in ("spectre", "ocean", "virtuoso") for line in output.splitlines()):
        raise ValueError("active EDA boundary")
    jobs = {}
    role = imp.load_source("candidate_role", ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py")
    for analysis in ("dc", "ac", "tran"):
        configure(analysis)
        if os.path.exists(BASE.JOB):
            before = json.loads(BASE.read(BASE.JOB + "/before.json"))
            verify_protected(before)
            jobs[analysis] = {"stage": BASE.read(BASE.JOB + "/stage", 64).decode("ascii").strip(),
                              "total_bytes": role._tree_fingerprint(BASE.JOB)["total_bytes"]}
    disk = os.statvfs(ROOT)
    emit({"protected_unchanged": True, "native_predecessors_unchanged": True,
          "active_eda": 0, "free_bytes": disk.f_bavail * disk.f_frsize,
          "total_bytes": disk.f_blocks * disk.f_frsize, "jobs": jobs,
          "counter": json.loads(BASE.read(BASE.COUNTER, 1024)), "spec_evaluation": "not_evaluated"})


def main():
    if len(sys.argv) not in (3, 4):
        raise ValueError("fixed candidate arguments")
    configure(sys.argv[2])
    action = sys.argv[1]
    if action == "stage" and len(sys.argv) == 4:
        BASE.set_stage(sys.argv[3])
    elif len(sys.argv) == 3 and action in ("prepare", "netlist", "postflight"):
        globals()[action]()
    elif len(sys.argv) == 3 and action in ("reserve", "status"):
        getattr(BASE, action)()
    elif len(sys.argv) == 3 and action in ("extraction", "complete"):
        getattr(BASE if ANALYSIS == "dc" else NATIVE, action)()
    else:
        raise ValueError("closed candidate action")


if __name__ == "__main__":
    try:
        main()
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError, IndexError, ZeroDivisionError):
        sys.stderr.write("fixed native candidate qualification failed\n")
        sys.exit(69)
