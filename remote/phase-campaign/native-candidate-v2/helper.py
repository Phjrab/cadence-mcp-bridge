#!/usr/bin/env python
"""Fixed candidate in owned ADE state copies; original state is fingerprinted."""
from __future__ import with_statement

import imp
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/native-candidate-v2"
NATIVE = imp.load_source("candidate_native_guard", ROOT + "/phase-campaign/native-ac-tran-v4/helper.py")
BASE = NATIVE.BASE
ORIGINAL_VERIFY = BASE.verify_protected
SAVED = {"VBIASN": 0.3, "VBIASP": 0.65}
CANDIDATE = {"VBIASN": 0.32, "VBIASP": 0.702}
PREDECESSORS = {
    "/native-candidate-v1-dc/result.json": "b401e57eac543e505dadf135753bd62c09a2fceb05b96a00615d3d6403350dd5",
    "/ade-qual-v6/result.json": "c7b5ce95bf17e93d8a95d1985f294c8b342d708bd6951822a509972daba04045",
    "/native-ac-tran-v3-ac/result.json": "34fd3ccd04c19cfe820c5ca6dbd829651dd600064628699cc3c1d501153ba57d",
    "/native-ac-tran-v3-tran/result.json": "c706574585cb4246e889de306f127a5eb84a83a079c28a03bfc3c37ac1f29d82",
    "/native-ac-tran-v4-tran/result.json": "870a96127feb8a168cbba094808f562017b181f407b1fb8bbbf741d1efb01f6a",
}
ANALYSIS = None
FAILED_AC = ROOT + "/native-candidate-v1-ac"
AC_NETLIST_SHA = "76ebe3b768a4a684cd932e1a26fa3a82a636d2a9b29925b168e603fe2196d172"


def configure(analysis):
    global ANALYSIS
    if analysis not in ("dc", "ac", "tran"):
        raise ValueError("closed candidate analysis")
    ANALYSIS = analysis
    NATIVE.ANALYSIS = analysis
    NATIVE.VERSION = VERSION
    BASE.VERSION = VERSION
    BASE.JOB = ROOT + "/native-candidate-v2-" + analysis
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
    if BASE.read(BASE.JOB + "/source-variables.bin") != original:
        raise ValueError("preserved source variable bytes drift")
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
        if ANALYSIS == "ac" and os.path.exists(BASE.JOB + "/recovery-source.json"):
            data["recovery_provenance"] = verify_recovery()
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


def tree(path):
    return imp.load_source("candidate_tree", ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py")._tree_fingerprint(path)


def content_digest(path):
    # The tree guard rejects links, special objects and excessive entries/bytes.
    tree(path)
    records = []
    for current, dirs, files in os.walk(path):
        for name in dirs:
            records.append(("d", os.path.relpath(os.path.join(current, name), path)))
        for name in files:
            file_path = os.path.join(current, name)
            records.append(("f", os.path.relpath(file_path, path), BASE.sha(BASE.read(file_path, BASE.RESERVATION))))
    return BASE.sha(json.dumps(sorted(records)).encode("ascii"))


def validate_failed_ac():
    if (BASE.read(FAILED_AC + "/stage", 64) != b"extraction_failed\n"
            or not os.path.isfile(FAILED_AC + "/attempt-reserved")
            or BASE.sha(BASE.read(FAILED_AC + "/netlist-result.json", 32768)) != AC_NETLIST_SHA):
        raise ValueError("fixed AC recovery source")
    for name in ("extract.ocn", "scalars.txt", "selector.txt", "result.json", "recovery-source.json"):
        if os.path.lexists(FAILED_AC + "/" + name):
            raise ValueError("unexpected prior extraction artifact")
    destination = BASE.JOB
    BASE.JOB = FAILED_AC
    BASE.COPIED_STATE = FAILED_AC + "/state-root/MCP_WorkLib/WP14_AUTO_PHASE_01_TB2/spectre/state1"
    BASE.NETDIR = FAILED_AC + "/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
    try:
        facts = BASE.verify_netlist()
        before = json.loads(BASE.read(FAILED_AC + "/before.json"))
        text = BASE.read(BASE.NETDIR + "/input.scs").decode("latin-1")
        circuit = BASE.read(BASE.NETDIR + "/netlist").decode("latin-1")
        validate_netlist(text, circuit, BASE.read(BASE.guard().NETLIST).decode("latin-1"), before["state_facts"])
        if facts.get("applied_bias_values_v") != [0.32, 0.702] or facts.get("result_name") != "ac":
            raise ValueError("recovery candidate input")
        log = BASE.read(FAILED_AC + "/spectre.log").decode("latin-1")
        summaries = BASE.guard().SUMMARY.findall(log)
        warnings = [line for line in log.splitlines() if "WARNING" in line]
        if (len(summaries) != 1 or int(summaries[0][0]) or len(warnings) != int(summaries[0][1])
                or len(warnings) > 2 or any("WARNING (CMI-2477):" not in line for line in warnings)):
            raise ValueError("recovery simulator quality")
        psf = tree(FAILED_AC + "/psf")
        job = tree(FAILED_AC)
        if not 0 < psf["total_bytes"] <= job["total_bytes"] < BASE.RESERVATION // 2:
            raise ValueError("recovery duplicate result budget")
        return {"source_stage": "extraction_failed", "source_job_tree": job,
                "source_psf_tree": psf, "source_content_sha256": content_digest(FAILED_AC),
                "reused_dc_tree": tree(ROOT + "/native-candidate-v1-dc"),
                "psf_content_sha256": content_digest(FAILED_AC + "/psf"),
                "netlist_result_sha256": AC_NETLIST_SHA, "input_sha256": facts["input_sha256"],
                "simulation": "reused_succeeded", "extraction": "new_only"}
    finally:
        configure("ac")
        if BASE.JOB != destination:
            raise ValueError("recovery destination binding")


def recover():
    if ANALYSIS != "ac" or os.path.lexists(BASE.JOB):
        raise ValueError("closed recovery or replay")
    BASE.environment_preflight()
    proof = validate_failed_ac()
    shutil.copytree(FAILED_AC, BASE.JOB)
    if (content_digest(BASE.JOB) != proof["source_content_sha256"]
            or tree(FAILED_AC) != proof["source_job_tree"]):
        raise ValueError("recovery copy or preserved failure drift")
    BASE.save(BASE.JOB + "/recovery-source.json", proof)
    BASE.set_stage("extracting")
    verify_recovery()


def verify_recovery():
    proof = json.loads(BASE.read(ROOT + "/native-candidate-v2-ac/recovery-source.json", 4096))
    if (proof != validate_failed_ac()
            or content_digest(ROOT + "/native-candidate-v2-ac/psf") != proof["psf_content_sha256"]
            or BASE.sha(BASE.read(ROOT + "/native-candidate-v2-ac/netlist-result.json")) != AC_NETLIST_SHA
            or BASE.sha(BASE.read(ROOT + "/native-candidate-v2-ac/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist/input.scs")) != proof["input_sha256"]
            or tree(FAILED_AC)["total_bytes"] + tree(ROOT + "/native-candidate-v2-ac")["total_bytes"] > BASE.RESERVATION):
        raise ValueError("recovery provenance or combined size drift")
    return proof


def postflight():
    verify_predecessors()
    BASE.environment_preflight()
    process = subprocess.Popen(["ps", "-eo", "comm"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors = process.communicate()
    if process.returncode or errors or any(line.strip() in ("spectre", "ocean", "virtuoso") for line in output.splitlines()):
        raise ValueError("active EDA boundary")
    jobs = {}
    role = imp.load_source("candidate_role", ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py")
    configure("ac")
    recovery = verify_recovery() if os.path.exists(BASE.JOB) else None
    for analysis in ("ac", "tran"):
        configure(analysis)
        if os.path.exists(BASE.JOB):
            before = json.loads(BASE.read(BASE.JOB + "/before.json"))
            verify_protected(before)
            jobs[analysis] = {"stage": BASE.read(BASE.JOB + "/stage", 64).decode("ascii").strip(),
                              "total_bytes": role._tree_fingerprint(BASE.JOB)["total_bytes"]}
    disk = os.statvfs(ROOT)
    emit({"protected_unchanged": True, "native_predecessors_unchanged": True,
          "preserved_failed_ac": recovery, "candidate_dc_reused": True,
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
    elif len(sys.argv) == 3 and action in ("prepare", "netlist", "postflight", "recover"):
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
