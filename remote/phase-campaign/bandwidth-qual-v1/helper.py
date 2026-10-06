#!/usr/bin/env python
"""Fixed Python 2.6 AC grid study; preserved native input, separate owned jobs."""
from __future__ import with_statement

import imp
import json
import math
import os
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/bandwidth-qual-v1"
RUNTIME = ROOT + "/bandwidth-qual-v1"
SOURCE_ID = "1afa2677-e264-4e80-a23d-dc722e34bb4a"
INPUT_SHA = "53dd6c3bdee80808bfd67880f7e43be289fb275abf4f5486adf5b13f6aad275a"
PSF_SHA = "5f13ca23a7d49aacaef51a59c0922e570da5dc2639baef5719956499ce5909fc"
OLD_LINE = "ac ac start=10 stop=100M dec=10 annotate=status"
N = imp.load_source("bandwidth_native", ROOT + "/phase-campaign/native-mcp-v3/helper.py")
B = N.BASE
GRID = None
JOB = None


def contained(path):
    if os.path.realpath(path) != path or not path.startswith(ROOT + "/"):
        raise ValueError("bandwidth containment")


def configure(grid):
    global GRID, JOB
    if grid not in ("50", "100"):
        raise ValueError("fixed refinement grid")
    GRID = int(grid)
    JOB = RUNTIME + "/grid" + grid
    contained(JOB)


def authorization():
    policy = json.loads(B.read(VERSION + "/policy.json", 8192))
    activation = json.loads(B.read(VERSION + "/activation.private.json", 4096))
    digest = B.sha(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("ascii"))
    if activation != {"phase": "BANDWIDTH-QUAL-02", "policy_sha256": digest,
                      "user_delegation": "explicit-in-current-task", "user_instruction": "proceed"}:
        raise ValueError("bandwidth delegation")
    if (policy.get("phase") != "BANDWIDTH-QUAL-02" or policy.get("source_job_id") != SOURCE_ID
            or policy.get("grids") != [50, 100] or policy.get("start_hz") != 10
            or policy.get("stop_hz") != 1000000 or policy.get("new_attempt_ceiling") != 2
            or policy.get("reservation_bytes_per_job") != B.RESERVATION
            or policy.get("delete_authority") is not False
            or policy.get("publication_authority") is not False):
        raise ValueError("bandwidth fixed scope")
    N.authorization()
    return digest


def capture(function):
    out = []
    original = N.N.emit
    N.N.emit = out.append
    try:
        function()
    finally:
        N.N.emit = original
    if len(out) != 1:
        raise ValueError("native projection capture")
    return out[0]


def source():
    N.N.configure(SOURCE_ID, "ac")
    result = capture(N.N.result)
    if result["input_sha256"] != INPUT_SHA or result["psf_sha256"] != PSF_SHA:
        raise ValueError("exact admitted source")
    return result


def checkpoint():
    source()
    original = B.snapshot()
    jobs = capture(N.N.postflight)
    return {"protected": original, "native": jobs}


def counter(read_only=False):
    data = json.loads(B.read(B.COUNTER, 1024))
    policy = N.authorization()
    if read_only:
        if (set(data) != set(("campaign_id", "count", "result_reserved_bytes"))
                or data["campaign_id"] != "AUTO-PHASE-01"
                or type(data["count"]) not in B.INTEGER_TYPES or not 62 <= data["count"] <= 500
                or type(data["result_reserved_bytes"]) not in B.INTEGER_TYPES
                or not 7114588160 <= data["result_reserved_bytes"] <= 10 * 1024 ** 3):
            raise ValueError("invalid read counter")
    else:
        N.validate_counter(data, policy)
    N.audit_reservations(data)
    for grid in ("50", "100"):
        marker = RUNTIME + "/grid" + grid + "/attempt-reserved"
        contained(marker)
        if os.path.lexists(marker):
            intent = json.loads(B.read(marker, 1024))
            if (set(intent) != set(data) or intent["campaign_id"] != data["campaign_id"]
                    or type(intent["count"]) not in B.INTEGER_TYPES
                    or type(intent["result_reserved_bytes"]) not in B.INTEGER_TYPES
                    or not 1 <= intent["count"] <= data["count"]
                    or not 0 <= intent["result_reserved_bytes"] <= data["result_reserved_bytes"]):
                raise ValueError("unreconciled refinement reservation")
    return data


def verify():
    before = json.loads(B.read(JOB + "/before.json", 65536))
    now = checkpoint()
    if before["protected"] != now["protected"]:
        raise ValueError("source ADE PDK drift")
    for key in ("jobs", "protected_unchanged", "reference_results_unchanged", "active_eda"):
        if before["native"][key] != now["native"][key]:
            raise ValueError("prior job evidence drift")
    text = B.read(JOB + "/netlist/input.scs")
    # Reconstruct the exact pinned native input; only the one AC line may differ.
    line = "ac ac start=10 stop=1M dec=" + str(GRID) + " annotate=status"
    if text.count(line.encode("ascii")) != 1 or B.sha(text.replace(line.encode("ascii"),
            OLD_LINE.encode("ascii"))) != INPUT_SHA:
        raise ValueError("effective input drift")
    return before


def begin():
    digest = authorization()
    B.environment_preflight()
    counter()
    if os.path.lexists(JOB):
        raise ValueError("refinement replay or uncertain prior attempt")
    before = checkpoint()
    # source() leaves B configured to the original admitted job.
    source()
    original = B.read(B.NETDIR + "/input.scs")
    if B.sha(original) != INPUT_SHA or original.count(OLD_LINE.encode("ascii")) != 1:
        raise ValueError("source input identity")
    contained(RUNTIME)
    if not os.path.exists(RUNTIME):
        os.mkdir(RUNTIME, 0o700)
    os.mkdir(JOB, 0o700)
    os.mkdir(JOB + "/netlist", 0o700)
    os.mkdir(JOB + "/psf", 0o700)
    B.save(JOB + "/before.json", before)
    B.save(JOB + "/admission.json", {"policy_sha256": digest, "grid": GRID,
                                    "source_job_id": SOURCE_ID})
    line = "ac ac start=10 stop=1M dec=" + str(GRID) + " annotate=status"
    B.write_new(JOB + "/netlist/input.scs", original.replace(OLD_LINE.encode("ascii"),
                                                            line.encode("ascii")))
    template = B.read(VERSION + "/extract.ocn").decode("ascii")
    if template.count("@COUNT@") != 2 or template.count("@JOB@") != 2:
        raise ValueError("fixed extraction template")
    B.write_new(JOB + "/extract.ocn", template.replace("@JOB@", JOB).replace(
        "@COUNT@", str(5 * GRID + 1)))
    verify()


def reserve():
    authorization()
    B.environment_preflight()
    verify()
    if os.path.lexists(JOB + "/attempt-reserved"):
        raise ValueError("refinement simulation replay")
    data = counter()
    data["count"] += 1
    data["result_reserved_bytes"] += B.RESERVATION
    B.save(JOB + "/attempt-reserved", data)
    B.save(B.COUNTER + ".ade-tmp", data)
    os.rename(B.COUNTER + ".ade-tmp", B.COUNTER)


def parse_frame(frame):
    lines = frame.decode("ascii").splitlines()
    if not lines or lines[0] != "BEGIN" or lines[-1] != "END":
        raise ValueError("refinement frame")
    cursor = 1
    axis = None
    vectors = {}
    count = 5 * GRID + 1
    for signal in ("Vop", "Vom", "Vp", "Vm"):
        if lines[cursor] != "VECTOR|" + signal + "|" + str(count):
            raise ValueError("refinement vector length")
        cursor += 1
        freqs, values = [], []
        for index in range(count):
            parts = lines[cursor].split("|")
            cursor += 1
            if len(parts) != 5 or parts[:2] != ["POINT", str(index)]:
                raise ValueError("refinement point identity")
            f, real, imag = [float(v) for v in parts[2:]]
            if any(math.isnan(v) or math.isinf(v) for v in (f, real, imag)):
                raise ValueError("refinement finite sample")
            expected = 10 ** (1.0 + float(index) / GRID)
            if abs(f - expected) > expected * 1e-6:
                raise ValueError("refinement frequency grid")
            freqs.append(f)
            values.append(complex(real, imag))
        if axis is None:
            axis = freqs
        elif freqs != axis:
            raise ValueError("refinement shared axis")
        vectors[signal] = values
    if cursor != len(lines) - 1:
        raise ValueError("trailing refinement data")
    points = []
    for index, f in enumerate(axis):
        vp, vm = vectors["Vp"][index], vectors["Vm"][index]
        if abs(vp - 0.5) > 1e-9 or abs(vm + 0.5) > 1e-9:
            raise ValueError("effective differential AC stimulus")
        gain = abs((vectors["Vop"][index] - vectors["Vom"][index]) / (vp - vm))
        if gain <= 0 or math.isnan(gain) or math.isinf(gain):
            raise ValueError("refinement nonzero finite gain")
        points.append({"frequency_hz": f, "gain_db": 20 * math.log10(gain)})
    return points


def finish():
    authorization()
    verify()
    data = counter(True)
    if not os.path.isfile(JOB + "/attempt-reserved"):
        raise ValueError("missing simulation reservation")
    summary = B.guard().SUMMARY.findall(B.read(JOB + "/spectre.log").decode("latin-1"))
    log = B.read(JOB + "/spectre.log").decode("latin-1")
    warnings = [line for line in log.splitlines() if "WARNING" in line]
    if (len(summary) != 1 or int(summary[0][0]) or len(warnings) != int(summary[0][1])
            or len(warnings) > 2 or any("WARNING (CMI-2477):" not in w for w in warnings)):
        raise ValueError("refinement simulator quality")
    ocean = B.read(JOB + "/ocean.log", 2 * 1024 ** 2).decode("latin-1")
    if any("*Error*" in line for line in ocean.splitlines() if not line.startswith("\\i ")):
        raise ValueError("refinement extraction error")
    frame = B.read(JOB + "/frame.txt", 262144)
    spectrum = parse_frame(frame)
    psf = N.N.CAND.tree(JOB + "/psf")
    size = N.N.CAND.tree(JOB)["total_bytes"]
    if not 0 < psf["total_bytes"] <= size < B.RESERVATION - 65536:
        raise ValueError("refinement result reservation")
    result = {"schema_version": 1, "grid": GRID, "source_job_id": SOURCE_ID,
              "source_input_sha256": INPUT_SHA, "source_psf_sha256": PSF_SHA,
              "input_sha256": B.sha(B.read(JOB + "/netlist/input.scs")),
              "frame_sha256": B.sha(frame), "psf_sha256": psf["sha256"],
              "spectrum": spectrum, "counter": data, "warnings": len(warnings),
              "notices": int(summary[0][2]), "protected_unchanged": True}
    B.save(JOB + "/result.json", result)
    B.save(JOB + "/complete.json", receipt())


def receipt():
    N.N.CAND.tree(JOB)  # Existing link/special-object/entry/byte bound guard.
    entries = []
    for current, dirs, files in os.walk(JOB):
        for name in dirs:
            entries.append(["d", os.path.relpath(os.path.join(current, name), JOB)])
        for name in files:
            path = os.path.join(current, name)
            if path == JOB + "/complete.json":
                continue
            entries.append(["f", os.path.relpath(path, JOB), B.sha(B.read(path, B.RESERVATION))])
    return sorted(entries)


def result():
    authorization()
    counter(True)
    results = []
    for grid in ("50", "100"):
        configure(grid)
        verify()
        complete = json.loads(B.read(JOB + "/complete.json", 65536))
        if complete != receipt():
            raise ValueError("refinement durable result drift")
        data = json.loads(B.read(JOB + "/result.json", 65536))
        if data["spectrum"] != parse_frame(B.read(JOB + "/frame.txt", 262144)):
            raise ValueError("refinement parsed result drift")
        results.append(data)
    text = json.dumps({"schema_version": 1, "grids": results}, sort_keys=True)
    if len(text) > 65536:
        raise ValueError("bounded refinement read")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "result":
            result()
        elif len(sys.argv) == 3 and sys.argv[1] in ("begin", "reserve", "finish"):
            configure(sys.argv[2])
            globals()[sys.argv[1]]()
        else:
            raise ValueError("fixed bandwidth action")
    except (IOError, OSError, ValueError, KeyError, TypeError, IndexError, ZeroDivisionError):
        sys.stderr.write("fixed bandwidth qualification failed\n")
        sys.exit(69)
