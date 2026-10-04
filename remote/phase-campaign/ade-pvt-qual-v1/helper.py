#!/usr/bin/env python
"""Finite native corner qualification, Python 2.6; no caller scripts or paths."""
from __future__ import with_statement

import imp
import json
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/ade-pvt-qual-v1"
JOBS = ROOT + "/ade-pvt-qual-v1-jobs"
N = imp.load_source("pvt_native", ROOT + "/phase-campaign/native-mcp-v1/helper.py")
BASE, CAND = N.BASE, N.CAND
N.VERSION, N.JOBS = VERSION, JOBS
NATIVE_CONFIGURE = N.configure
CORNER = None
MODEL_MANIFEST = ROOT + "/ade-pvt-prep-v4/model-files.private.json"
MODEL_MANIFEST_SHA = "4a1fda45bb3738fc7253429903aee30b9c65f40439aee28f6cf22047178fd0d0"
NN_TREES = {
    "f154d798-0f7f-47d6-9323-6b046394eef6": "f056c3ebcf3e0d83fe0848c2c7a54d5d2f014de2e80ec2f6c1dd362373baa70b",
    "1afa2677-e264-4e80-a23d-dc722e34bb4a": "50708ce5744c84c4e110e3a162d38e7bb23fa33a87e396eecc43b7c5be4dc969",
    "eca78308-8af8-4810-b848-94c0ad936afe": "706cb6ce0f6b3858f61a6aa6e8e4f77bffdeba85ac29f1555bc6d32ec07cc88c",
}
BASELINE_COUNT, BASELINE_BYTES = 24, 2014314496


def configure(job_id, analysis, corner=None):
    global CORNER
    if corner not in ("FF", "SS", "FS", "SF") or analysis not in ("dc", "ac"):
        raise ValueError("closed corner and analysis")
    CORNER = corner
    NATIVE_CONFIGURE(job_id, analysis)
    BASE.verify_protected = verify_protected
    BASE.validate_netlist = validate_netlist
    BASE.emit = emit
    CAND.NATIVE.emit = emit
    N.request = request
    N.references = references
    N.project = project


def request():
    actual = json.loads(BASE.read(N.RECORD + "/request.json", 1024))
    if actual != {"analysis": N.ANALYSIS, "corner": CORNER,
                  "revision_id": N.REVISION, "operating_point_id": N.OPERATING_POINT}:
        raise ValueError("corner request identity")


def models():
    raw = BASE.read(MODEL_MANIFEST, 4096)
    if BASE.sha(raw) != MODEL_MANIFEST_SHA:
        raise ValueError("protected model manifest drift")
    records = json.loads(raw)["files"]
    if len(records) != 9:
        raise ValueError("model inventory count")
    for name, digest, size in records:
        if not re.match(r"^gpdk090[A-Za-z0-9_]*\.scs$", name):
            raise ValueError("model filename")
        path = os.path.dirname(BASE.MODEL) + "/" + name
        if os.path.realpath(path) != path:
            raise ValueError("model containment")
        content = BASE.read(path, 1024 * 1024)
        if len(content) != size or BASE.sha(content) != digest:
            raise ValueError("protected model file drift")
    return MODEL_MANIFEST_SHA


def references():
    CAND.verify_predecessors()
    for path, digest in N.REFERENCE_RESULTS.items():
        raw = BASE.read(ROOT + path, 32768)
        if BASE.sha(raw) != digest or json.loads(raw).get("quality") != "valid":
            raise ValueError("preserved reference drift")
    for name, digest in NN_TREES.items():
        if CAND.tree(ROOT + "/native-mcp-v1-jobs/" + name)["sha256"] != digest:
            raise ValueError("preserved NN tree drift")
    models()


def phase_usage():
    attempts = 0
    pairs = set()
    for name in os.listdir(JOBS):
        if name in ("control.lock", "active"):
            continue
        if not N.ID.match(name):
            raise ValueError("unexpected corner job")
        path = JOBS + "/" + name
        N.contained(path)
        data = json.loads(BASE.read(path + "/request.json", 1024))
        pair = (data.get("corner"), data.get("analysis"))
        if pair[0] not in ("FF", "SS", "FS", "SF") or pair[1] not in ("dc", "ac") or pair in pairs:
            raise ValueError("duplicate or unqualified corner pair")
        pairs.add(pair)
        attempts += int(os.path.isfile(path + "/work/attempt-reserved"))
    if len(pairs) > 8 or attempts > 8:
        raise ValueError("eight-attempt phase ceiling")
    return attempts, pairs


def preflight():
    BASE.environment_preflight()
    BASE.snapshot()
    references()
    if BASE.state_facts()["variables_v"] != CAND.SAVED:
        raise ValueError("saved source bias drift")
    attempts, pairs = phase_usage()
    if attempts >= 8:
        raise ValueError("phase budget exhausted")
    if not os.path.isdir(N.RECORD) and (CORNER, N.ANALYSIS) in pairs:
        raise ValueError("corner pair already claimed")
    counter = json.loads(BASE.read(BASE.COUNTER, 1024))
    if counter != {"campaign_id": "AUTO-PHASE-01", "count": BASELINE_COUNT + attempts,
                   "result_reserved_bytes": BASELINE_BYTES + attempts * BASE.RESERVATION}:
        raise ValueError("cumulative ledger changed outside phase")


def corner_model(original, corner):
    if corner not in ("FF", "SS", "FS", "SF"):
        raise ValueError("corner allowlist")
    text = original.decode("latin-1")
    match = re.match(r'^\(\("([^"\n]+)" "NN"\)\)\s*$', text)
    if match is None or os.path.realpath(match.group(1)) != BASE.MODEL:
        raise ValueError("saved model binding")
    return text.replace('"NN"', '"' + corner + '"', 1).encode("latin-1")


def prepare():
    request()
    preflight()
    # Exact original copy and candidate substitution are qualified by the archived guard.
    BASE.verify_protected = CAND.verify_protected
    CAND.prepare()
    BASE.verify_protected = verify_protected
    raw = BASE.read(BASE.STATE + "/modelSetup")
    changed = corner_model(raw, CORNER)
    BASE.write_new(BASE.COPIED_STATE + "/modelSetup.corner-new", changed)
    os.rename(BASE.COPIED_STATE + "/modelSetup.corner-new", BASE.COPIED_STATE + "/modelSetup")
    BASE.save(BASE.JOB + "/corner-state.json", {"corner": CORNER,
        "source_model_setup_sha256": BASE.sha(raw), "owned_model_setup_sha256": BASE.sha(changed),
        "model_manifest_sha256": models()})
    verify_protected(json.loads(BASE.read(BASE.JOB + "/before.json")))
    template = BASE.read(VERSION + "/netlist-" + N.ANALYSIS + ".ocn").decode("ascii")
    if "@JOB@" not in template:
        raise ValueError("owned routing template")
    BASE.write_new(BASE.JOB + "/netlist.ocn", template.replace("@JOB@", BASE.JOB))


def verify_protected(before):
    references()
    after = BASE.snapshot()
    if dict((key, before[key]) for key in after) != after or before["state_facts"] != BASE.state_facts():
        raise ValueError("protected original drift")
    if BASE.sha(BASE.read(BASE.COPIED_STATE + "/ADE_state.info")) != before["state_copy_info_sha256"]:
        raise ValueError("owned state routing drift")
    original = BASE.read(BASE.STATE + "/variables")
    candidate = CAND.candidate_variables(original)
    model = BASE.read(BASE.STATE + "/modelSetup")
    changed = corner_model(model, CORNER)
    if BASE.read(BASE.JOB + "/source-variables.bin") != original:
        raise ValueError("source variable proof drift")
    expected = []
    allowed = {os.path.join(".", "variables"): candidate, os.path.join(".", "modelSetup"): changed}
    for record in BASE.state_records(BASE.STATE):
        if record[0] == "file" and record[1] in allowed:
            record = (record[0], record[1], BASE.sha(allowed[record[1]]))
        expected.append(record)
    if sorted(expected) != BASE.state_records(BASE.COPIED_STATE):
        raise ValueError("owned state non-allowed drift")
    if json.loads(BASE.read(BASE.JOB + "/candidate-state.json", 4096)) != {
            "source_variables_sha256": BASE.sha(original), "owned_variables_sha256": BASE.sha(candidate),
            "requested_variables_v": CAND.CANDIDATE, "source_variables_v": CAND.SAVED}:
        raise ValueError("candidate state proof")
    if json.loads(BASE.read(BASE.JOB + "/corner-state.json", 4096)) != {
            "corner": CORNER, "source_model_setup_sha256": BASE.sha(model),
            "owned_model_setup_sha256": BASE.sha(changed), "model_manifest_sha256": MODEL_MANIFEST_SHA}:
        raise ValueError("corner state proof")


def validate_netlist(text, circuit, previous, facts):
    includes = re.findall(r'(?m)^include "([^"\n]+)"(?: section=([A-Za-z0-9_]+))?$', text)
    if len(includes) != 1 or (os.path.realpath(includes[0][0]), includes[0][1]) != (BASE.MODEL, CORNER):
        raise ValueError("actual generated corner include")
    models()
    # Only the separately proved include section is normalized for reuse of NN's validator.
    line = 'include "' + includes[0][0] + '" section=' + CORNER
    normalized = text.replace(line, 'include "' + includes[0][0] + '" section=NN', 1)
    return CAND.validate_netlist(normalized, circuit, previous, facts)


def enrich(data):
    if data.get("netlist_valid"):
        saved = data.get("source_saved_state", data["effective"])
        if saved != BASE.state_facts():
            raise ValueError("saved facts drift")
        data["source_saved_state"] = saved
        data["effective"] = dict(saved)
        data["effective"]["variables_v"] = CAND.CANDIDATE
        data["effective"]["model_section"] = CORNER
        data["analysis"], data["corner"] = N.ANALYSIS, CORNER
        data["applied_bias_values_v"] = [0.32, 0.702]
        data["execution_mode"] = "native_ade_owned_corner_candidate_state"
        data["owned_variables_sha256"] = BASE.sha(BASE.read(BASE.COPIED_STATE + "/variables"))
        data["owned_model_setup_sha256"] = BASE.sha(BASE.read(BASE.COPIED_STATE + "/modelSetup"))
        data["model_manifest_sha256"] = MODEL_MANIFEST_SHA
        data["job_analysis_override"] = ({} if N.ANALYSIS == "dc" else
            {"start_hz": 10, "stop_hz": 1e8, "points_per_decade": 10})
        data["job_id"] = os.path.basename(N.RECORD)
        data["revision_id"], data["operating_point_id"] = N.REVISION, N.OPERATING_POINT
    return data


def project(data, job_id, analysis, frame_sha):
    saved = BASE.state_facts()
    effective = dict(saved)
    effective.update({"variables_v": CAND.CANDIDATE, "model_section": CORNER})
    if (data.get("quality") != "valid" or data.get("simulation") != "succeeded"
            or data.get("extraction") != "succeeded" or data.get("notices") != 0
            or data.get("corner") != CORNER or data.get("analysis") != analysis
            or data.get("job_id") != job_id or data.get("source_saved_state") != saved
            or data.get("effective") != effective or data.get("vdd_v") != 1.0
            or data.get("measurement_frame_sha256") != frame_sha
            or data.get("spec_evaluation") != "not_evaluated"):
        raise ValueError("corner result provenance or quality")
    for key in ("protected_unchanged", "source_copy_signature_equal", "state_loaded", "netlist_valid"):
        if data.get(key) is not True:
            raise ValueError("corner verification flag")
    return data


def emit(data):
    N.emit(enrich(data))


def complete():
    request()
    def checked(data):
        enrich(data)
        frame_sha = BASE.sha(BASE.read(BASE.JOB + "/scalars.txt", 2 * 1024 ** 2))
        data["measurement_frame_sha256"] = frame_sha
        N.emit(project(data, os.path.basename(N.RECORD), N.ANALYSIS, frame_sha))
    BASE.emit, CAND.NATIVE.emit = checked, checked
    (BASE if N.ANALYSIS == "dc" else CAND.NATIVE).complete()


def postflight():
    BASE.environment_preflight()
    BASE.snapshot()
    references()
    if os.path.lexists(JOBS + "/active"):
        raise ValueError("unresolved active corner claim")
    jobs = {}
    attempts, pairs = phase_usage()
    for name in os.listdir(JOBS):
        if name == "control.lock":
            continue
        data = json.loads(BASE.read(JOBS + "/" + name + "/request.json", 1024))
        configure(name, data["analysis"], data["corner"])
        request()
        if os.path.isfile(BASE.JOB + "/before.json"):
            verify_protected(json.loads(BASE.read(BASE.JOB + "/before.json")))
        tree = CAND.tree(N.RECORD)
        if tree["total_bytes"] > BASE.RESERVATION:
            raise ValueError("corner result storage")
        jobs[name] = {"corner": CORNER, "analysis": N.ANALYSIS,
            "stage": BASE.read(BASE.JOB + "/stage", 64).decode("ascii").strip(),
            "total_bytes": tree["total_bytes"], "tree_sha256": tree["sha256"]}
    counter = json.loads(BASE.read(BASE.COUNTER, 1024))
    if counter != {"campaign_id": "AUTO-PHASE-01", "count": BASELINE_COUNT + attempts,
                   "result_reserved_bytes": BASELINE_BYTES + attempts * BASE.RESERVATION}:
        raise ValueError("corner ledger accounting")
    disk = os.statvfs(ROOT)
    N.emit({"protected_unchanged": True, "reference_results_unchanged": True,
        "model_manifest_sha256": models(), "counter": counter, "phase_attempts": attempts,
        "jobs": jobs, "free_bytes": disk.f_bavail * disk.f_frsize,
        "total_bytes": disk.f_blocks * disk.f_frsize, "spec_evaluation": "not_evaluated"})


def main():
    if len(sys.argv) not in (5, 6):
        raise ValueError("fixed corner arguments")
    action, job_id, analysis, corner = sys.argv[1:5]
    configure(job_id, analysis, corner)
    if action == "stage" and len(sys.argv) == 6:
        BASE.set_stage(sys.argv[5])
    elif len(sys.argv) == 5 and action in ("prepare", "preflight", "complete", "postflight"):
        globals()[action]()
    elif len(sys.argv) == 5 and action in ("status", "result"):
        getattr(N, action)()
    elif len(sys.argv) == 5 and action == "netlist":
        request()
        CAND.netlist()
    elif len(sys.argv) == 5 and action == "reserve":
        request()
        preflight()
        BASE.reserve()
    elif len(sys.argv) == 5 and action == "extraction":
        request()
        (BASE if analysis == "dc" else CAND.NATIVE).extraction()
    else:
        raise ValueError("closed corner action")


if __name__ == "__main__":
    try:
        main()
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError, IndexError, ZeroDivisionError):
        sys.stderr.write("fixed native corner qualification failed\n")
        sys.exit(69)
