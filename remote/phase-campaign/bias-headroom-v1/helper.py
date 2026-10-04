#!/usr/bin/env python
"""Finite four-pair native headroom campaign; preserves all older evidence."""
from __future__ import with_statement

import imp
import json
import math
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/bias-headroom-v1"
JOBS = ROOT + "/bias-headroom-v1-jobs"
P = imp.load_source("headroom_pvt_guard", ROOT + "/phase-campaign/ade-pvt-qual-v1/helper.py")
LIMIT = imp.load_source("headroom_budget_guard", ROOT + "/phase-campaign/native-mcp-v2/helper.py")
N, BASE, CAND = P.N, P.BASE, P.CAND
ORIGINAL_REFERENCES, ORIGINAL_ENRICH = P.references, P.enrich
N.VERSION, N.JOBS = VERSION, JOBS
P.VERSION, P.JOBS = VERSION, JOBS
N.OPERATING_POINT = "bias-headroom-four-pairs-v1"
LIMIT.BASE, LIMIT.N = BASE, N
PAIRS = ((300, 702), (320, 650), (300, 650), (310, 676))
PAIR = None
FIELDS = ("id", "gm", "gds", "gmbs", "vgs", "vds", "vbs", "vth", "vdsat", "region")
GRAPH = ROOT + "/ade-pvt-diag-v2/extract/devices.private.json"
GRAPH_SHA = "c23b33abf0dae4f838f14cc013dbc964f9a003dfc590883b935fa82137a04a44"
PRIOR_TREES = {
    "/ade-pvt-qual-v1-jobs/07b9ad80-33ce-4bc1-a04c-c3a1b341619d": "4214a48f46bdf1718af9534b9d47d414185369d9d73e2416eb27a029a66c1557",
    "/ade-pvt-qual-v1-jobs/269aafcf-499e-416d-ab3f-ed608acd319f": "0a5f75c6a6871af4eb804e46c04b918b11c3a87251612dc158589d8b25dd441c",
    "/ade-pvt-qual-v1-jobs/ab21baec-217a-4c2a-ab80-92eaa66bb077": "4341099bf8ecab21e2db6c31d435abc2dedbe1f67617bd13eff9bec383a792f4",
    "/ade-pvt-qual-v1-jobs/4b5a9349-9f0a-4643-b0eb-c2e1cddbb8ff": "abf39be5e0767940d460c1df8a6216b7902ce65d38f2e5734187773ff1d9114b",
    "/ade-pvt-qual-v1-jobs/5e11f2c1-aea9-4600-8d18-a72222234313": "0a3e36118d439ee5214a22ebe9803fa2b7dff1dc3e448c91e033213670d60f75",
    "/ade-pvt-qual-v1-jobs/7adc97e5-4b3d-4e24-a471-1b8edf69a87d": "8b310f3c54c9a29cba1416678b00e552d8299ecd9de8cc68b955582a4c502416",
    "/ade-pvt-qual-v1-jobs/ecd03f04-2606-4626-bb68-a6fb05f72d8c": "20fea95ae1ea27d5258e9fd1e08a6e06d4676963b78b227f2ad3983082069e40",
    "/ade-pvt-qual-v1-jobs/e7a24a73-a135-438f-9f8f-d4596ff4c256": "ac5a9e6fdbd69b4afc8e17fff86a904d11e83be455859e76e7ef9b7cb705c628",
    "/ade-pvt-diag-v1": "9edb7ca17efaf33af94edb76ddafe5d2da612e9892097337ea1b996d293b4cfa",
    "/ade-pvt-diag-v2": "f87a356d412d87cc0733b1ddd27ed93bf6aab078ba27a95dc073aa3630e1cb7f",
}


def graph():
    raw = BASE.read(GRAPH, 16384)
    if BASE.sha(raw) != GRAPH_SHA:
        raise ValueError("preserved MOS inventory drift")
    return json.loads(raw)


def references():
    ORIGINAL_REFERENCES()
    graph()
    for name, digest in PRIOR_TREES.items():
        if CAND.tree(ROOT + name)["sha256"] != digest:
            raise ValueError("prior corner or diagnostic evidence drift")


def configure(job_id, analysis, corner, pair):
    global PAIR
    if (corner not in ("NN", "FF", "SS", "FS", "SF") or analysis not in ("dc", "ac")
            or pair not in ("0", "1", "2", "3")):
        raise ValueError("finite bias campaign settings")
    PAIR, P.CORNER = int(pair), corner
    CAND.CANDIDATE = dict(zip(("VBIASN", "VBIASP"), [v / 1000.0 for v in PAIRS[PAIR]]))
    P.NATIVE_CONFIGURE(job_id, analysis)
    BASE.verify_protected, BASE.validate_netlist = P.verify_protected, P.validate_netlist
    BASE.emit, CAND.NATIVE.emit = emit, emit
    BASE.reserve = LIMIT.reserve
    CAND.candidate_variables = candidate_variables
    P.corner_model = corner_model
    P.request, P.references, P.enrich = request, references, enrich
    P.preflight = preflight
    N.request, N.references, N.project = request, references, P.project


def request():
    data = json.loads(BASE.read(N.RECORD + "/request.json", 1024))
    if data != {"analysis": N.ANALYSIS, "corner": P.CORNER, "pair_index": PAIR,
                "revision_id": N.REVISION, "operating_point_id": N.OPERATING_POINT}:
        raise ValueError("bias request identity")


def candidate_variables(original):
    text = original.decode("latin-1")
    names = re.findall(r'(?m)^tmp([0-9]+)->name = "([^"\n]+)"$', text)
    expressions = re.findall(r'(?m)^tmp([0-9]+)->expression = "([^"\n]+)"$', text)
    if (len(names) != 2 or len(expressions) != 2 or len(dict(names)) != 2
            or len(dict(expressions)) != 2 or set(dict(names).values()) != set(CAND.SAVED)
            or set(dict(names)) != set(dict(expressions))):
        raise ValueError("exact saved variable inventory")
    names = dict(names)
    for index, expression in expressions:
        if BASE.number(expression) != CAND.SAVED[names[index]]:
            raise ValueError("original saved bias drift")
    values = dict(zip(("VBIASN", "VBIASP"), PAIRS[PAIR]))
    def replacement(match):
        return match.group(1) + '"' + str(values[names[match.group(2)]]) + 'm"'
    changed, count = re.subn(r'(?m)^(tmp([0-9]+)->expression = )"([^"\n]+)"$', replacement, text)
    if count != 2:
        raise ValueError("exact two-expression substitution")
    return changed.encode("latin-1")


def corner_model(original, corner):
    if corner not in ("NN", "FF", "SS", "FS", "SF"):
        raise ValueError("corner allowlist")
    text = original.decode("latin-1")
    match = re.match(r'^\(\("([^"\n]+)" "NN"\)\)\s*$', text)
    if match is None or os.path.realpath(match.group(1)) != BASE.MODEL:
        raise ValueError("original model binding")
    return text.replace('"NN"', '"' + corner + '"', 1).encode("latin-1")


def usage():
    attempts, requests = 0, {}
    for name in os.listdir(JOBS):
        if name in ("control.lock", "active"):
            continue
        if not N.ID.match(name):
            raise ValueError("unexpected bias job")
        path = JOBS + "/" + name
        N.contained(path)
        data = json.loads(BASE.read(path + "/request.json", 1024))
        key = (data.get("pair_index"), data.get("corner"), data.get("analysis"))
        if (set(data) != set(("pair_index", "corner", "analysis", "revision_id", "operating_point_id"))
                or type(key[0]) not in BASE.INTEGER_TYPES or key[0] not in (0, 1, 2, 3)
                or key[1] not in ("NN", "FF", "SS", "FS", "SF") or key[2] not in ("dc", "ac")
                or data["revision_id"] != N.REVISION or data["operating_point_id"] != N.OPERATING_POINT
                or key in requests):
            raise ValueError("duplicate or unqualified bias request")
        requests[key] = path
        attempts += int(os.path.isfile(path + "/work/attempt-reserved"))
    if len(requests) > 16 or attempts > 16:
        raise ValueError("sixteen-attempt phase ceiling")
    return attempts, requests


def op_summary(points):
    margins = [abs(p["fields"]["vds"]) - abs(p["fields"]["vdsat"]) for p in points]
    return {"negative_headroom_devices": sum(m < 0 for m in margins),
            "minimum_headroom_v": min(margins)}


def dc_evidence(path, pair, corner):
    work = path + "/work"
    if BASE.read(work + "/stage", 64) != b"succeeded\n":
        raise ValueError("incomplete DC job")
    data = json.loads(BASE.read(work + "/result.json", 32768))
    op = BASE.read(work + "/op-frame.txt", 16384)
    frame = BASE.read(work + "/scalars.txt", 2 * 1024 ** 2)
    if (data.get("quality") != "valid" or data.get("pair_index") != pair
            or data.get("corner") != corner or data.get("analysis") != "dc"
            or data.get("job_id") != os.path.basename(path)
            or data.get("vdd_v") != 1.0 or data.get("spec_evaluation") != "not_evaluated"
            or BASE.sha(op) != data.get("op_frame_sha256")
            or parse_op(op.decode("ascii")) != data.get("operating_points")
            or BASE.sha(frame) != data.get("measurement_frame_sha256")
            or BASE.guard().dc_result(frame.decode("ascii")) != data.get("scalars")
            or CAND.tree(work + "/psf")["sha256"] != data.get("psf_sha256")):
        raise ValueError("invalid DC evidence")
    return data


def selection(requests):
    scores, summaries = [], {}
    baseline = {"FF": (8, -0.1757839), "FS": (8, -0.3078908)}
    for pair in range(4):
        rows = {}
        for corner in ("FF", "FS"):
            key = (pair, corner, "dc")
            if key not in requests:
                raise ValueError("eight screen jobs required")
            data = dc_evidence(requests[key], pair, corner)
            rows[corner] = op_summary(data["operating_points"])
        summaries[pair] = rows
        eligible = all((row["negative_headroom_devices"], -row["minimum_headroom_v"])
                       < (baseline[c][0], -baseline[c][1]) for c, row in rows.items())
        if eligible:
            scores.append((max(r["negative_headroom_devices"] for r in rows.values()),
                           -min(r["minimum_headroom_v"] for r in rows.values()), pair))
    return {"selected_pair_index": min(scores)[2] if scores else None, "screens": summaries,
            "spec_evaluation": "not_evaluated"}


def preflight():
    BASE.environment_preflight()
    BASE.snapshot()
    references()
    if BASE.state_facts()["variables_v"] != CAND.SAVED:
        raise ValueError("saved state drift")
    attempts, requests = usage()
    if attempts >= 16 or ((PAIR, P.CORNER, N.ANALYSIS) in requests and not os.path.isdir(N.RECORD)):
        raise ValueError("bias phase exhaustion or replay")
    if not (P.CORNER in ("FF", "FS") and N.ANALYSIS == "dc"):
        if selection(requests)["selected_pair_index"] != PAIR:
            raise ValueError("only the measured selected pair may proceed")
    if N.ANALYSIS == "ac":
        for corner in ("NN", "FF", "SS", "FS", "SF"):
            key = (PAIR, corner, "dc")
            if key not in requests or BASE.read(requests[key] + "/work/stage", 64) != b"succeeded\n":
                raise ValueError("five selected DC results required before AC")
            dc_evidence(requests[key], PAIR, corner)
    current = json.loads(BASE.read(BASE.COUNTER, 1024))
    if current != {"campaign_id": "AUTO-PHASE-01", "count": 32 + attempts,
                   "result_reserved_bytes": 3088056320 + attempts * BASE.RESERVATION}:
        raise ValueError("shared ledger changed outside bias phase")
    LIMIT.validate_counter(current, LIMIT.authorization())
    LIMIT.audit_reservations(current)


def enrich(data):
    ORIGINAL_ENRICH(data)
    if data.get("netlist_valid"):
        data["applied_bias_values_v"] = [v / 1000.0 for v in PAIRS[PAIR]]
        data["pair_index"] = PAIR
        data["execution_mode"] = "native_ade_owned_bounded_bias_state"
    return data


def emit(data):
    N.emit(enrich(data))


def parse_op(text):
    lines = text.splitlines()
    if len(lines) != 142 or lines[0] != "BEGIN" or lines[-1] != "END":
        raise ValueError("fixed 140-field OP frame")
    points, cursor = [], 1
    for index in range(14):
        alias, values = "mos%02d" % (index + 1), {}
        for field in FIELDS:
            parts = lines[cursor].split("|")
            cursor += 1
            if len(parts) != 4 or parts[:3] != ["OP", alias, field]:
                raise ValueError("OP identity and order")
            number = float(parts[3])
            if math.isnan(number) or math.isinf(number) or abs(number) > 1e12:
                raise ValueError("nonfinite OP field")
            values[field] = number
        points.append({"alias": alias, "fields": values})
    return points


def extraction():
    request()
    (BASE if N.ANALYSIS == "dc" else CAND.NATIVE).extraction()
    if N.ANALYSIS != "dc":
        return
    members = graph()
    diag = imp.load_source("headroom_inventory", ROOT + "/phase-campaign/ade-pvt-diag-v2/helper.py")
    if diag.devices(BASE.read(BASE.NETDIR + "/netlist").decode("latin-1")) != members:
        raise ValueError("actual MOS binding changed")
    op = ['let((port value) port=outfile("' + BASE.JOB + '/op-frame.txt")',
          'unless(port exit(1))', 'unless(selectResult("dcOpInfo") close(port) exit(1))',
          'fprintf(port "BEGIN\\n")']
    for member in members:
        for field in FIELDS:
            op.append('value=pv("' + member["instance"] + '" "' + field + '" ?result "dcOpInfo")')
            op.append('unless(numberp(value) close(port) exit(1))')
            op.append('fprintf(port "OP|' + member["alias"] + '|' + field + '|%L\\n" value)')
    op += ['fprintf(port "END\\n") close(port))', 'exit(0)']
    script = BASE.read(BASE.JOB + "/extract.ocn").decode("ascii")
    if script.count("exit(0)") != 1:
        raise ValueError("fixed extraction insertion")
    BASE.write_new(BASE.JOB + "/extract-op-new.ocn", script.replace("exit(0)", "\n".join(op)))
    os.rename(BASE.JOB + "/extract-op-new.ocn", BASE.JOB + "/extract.ocn")


def complete():
    request()
    def checked(data):
        enrich(data)
        frame_sha = BASE.sha(BASE.read(BASE.JOB + "/scalars.txt", 2 * 1024 ** 2))
        data["measurement_frame_sha256"] = frame_sha
        P.project(data, os.path.basename(N.RECORD), N.ANALYSIS, frame_sha)
        if N.ANALYSIS == "dc":
            op = BASE.read(BASE.JOB + "/op-frame.txt", 16384)
            data["operating_points"] = parse_op(op.decode("ascii"))
            data["op_frame_sha256"] = BASE.sha(op)
            data["headroom"] = op_summary(data["operating_points"])
        N.emit(data)
    BASE.emit, CAND.NATIVE.emit = checked, checked
    (BASE if N.ANALYSIS == "dc" else CAND.NATIVE).complete()


def result():
    request()
    if BASE.read(BASE.JOB + "/stage", 64) != b"succeeded\n":
        raise ValueError("bias job incomplete")
    data = json.loads(BASE.read(BASE.JOB + "/result.json", 32768))
    P.verify_protected(json.loads(BASE.read(BASE.JOB + "/before.json")))
    frame = BASE.read(BASE.JOB + "/scalars.txt", 2 * 1024 ** 2)
    P.project(data, os.path.basename(N.RECORD), N.ANALYSIS, BASE.sha(frame))
    parsed = BASE.guard().dc_result(frame.decode("ascii")) if N.ANALYSIS == "dc" else BASE.guard().ac_result(frame.decode("ascii"))
    if parsed != data["scalars" if N.ANALYSIS == "dc" else "spectrum"]:
        raise ValueError("saved scalar/spectrum drift")
    if CAND.tree(BASE.JOB + "/psf")["sha256"] != data["psf_sha256"]:
        raise ValueError("saved PSF drift")
    if N.ANALYSIS == "dc":
        op = BASE.read(BASE.JOB + "/op-frame.txt", 16384)
        if BASE.sha(op) != data["op_frame_sha256"] or parse_op(op.decode("ascii")) != data["operating_points"]:
            raise ValueError("saved OP drift")
    N.emit(data)


def postflight():
    BASE.environment_preflight()
    BASE.snapshot()
    references()
    if os.path.lexists(JOBS + "/active"):
        raise ValueError("unresolved bias active claim")
    attempts, requests = usage()
    current = json.loads(BASE.read(BASE.COUNTER, 1024))
    if current != {"campaign_id": "AUTO-PHASE-01", "count": 32 + attempts,
                   "result_reserved_bytes": 3088056320 + attempts * BASE.RESERVATION}:
        raise ValueError("bias ledger accounting")
    jobs = {}
    for key, path in requests.items():
        configure(os.path.basename(path), key[2], key[1], str(key[0]))
        request()
        if os.path.isfile(BASE.JOB + "/before.json"):
            P.verify_protected(json.loads(BASE.read(BASE.JOB + "/before.json")))
        tree = CAND.tree(path)
        if tree["total_bytes"] > BASE.RESERVATION:
            raise ValueError("bias artifact size")
        jobs[os.path.basename(path)] = {"request": key, "tree": tree,
                                      "stage": BASE.read(BASE.JOB + "/stage", 64).decode("ascii").strip()}
    disk = os.statvfs(ROOT)
    N.emit({"counter": current, "phase_attempts": attempts, "jobs": jobs,
            "protected_unchanged": True, "free_bytes": disk.f_bavail * disk.f_frsize,
            "total_bytes": disk.f_blocks * disk.f_frsize, "spec_evaluation": "not_evaluated"})


def main():
    if len(sys.argv) not in (6, 7):
        raise ValueError("fixed bias arguments")
    action, job_id, analysis, corner, pair = sys.argv[1:6]
    configure(job_id, analysis, corner, pair)
    if action == "stage" and len(sys.argv) == 7:
        BASE.set_stage(sys.argv[6])
    elif len(sys.argv) == 6 and action in ("preflight", "complete", "postflight", "extraction", "result"):
        globals()[action]()
    elif len(sys.argv) == 6 and action == "prepare":
        P.prepare()
    elif len(sys.argv) == 6 and action == "status":
        N.status()
    elif len(sys.argv) == 6 and action == "netlist":
        request()
        CAND.netlist()
    elif len(sys.argv) == 6 and action == "reserve":
        request()
        preflight()
        LIMIT.reserve()
    elif len(sys.argv) == 6 and action == "selection":
        references()
        N.emit(selection(usage()[1]))
    else:
        raise ValueError("closed bias action")


if __name__ == "__main__":
    try:
        main()
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError, IndexError, ZeroDivisionError):
        sys.stderr.write("fixed bias headroom operation failed\n")
        sys.exit(69)
