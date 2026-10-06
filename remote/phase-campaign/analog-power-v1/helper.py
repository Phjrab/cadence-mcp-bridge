#!/usr/bin/env python
"""Python 2.6 fixed preserved-result power extraction; never simulates."""
from __future__ import with_statement
import imp
import json
import math
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/analog-power-v1"
RUNTIME = ROOT + "/analog-power-v1"
JOB_ID = "f154d798-0f7f-47d6-9323-6b046394eef6"
N = imp.load_source("power_native", ROOT + "/phase-campaign/native-mcp-v3/helper.py")
B = N.BASE
SOURCES = (("vdd", "V0", "VDD", 1.0, "supply"),
           ("vss", "V5", "VSS", 0.0, "supply"),
           ("bias-n", "V3", "Vbiasn", 0.32, "bias"),
           ("bias-p", "V4", "Vbiasp", 0.702, "bias"),
           ("input-p", "V1", "Vp", 0.5, "stimulus"),
           ("input-m", "V2", "Vm", 0.5, "stimulus"))
INPUT_SHA = "c9bcf3e3bd8a9329ff0bb1513df2a08f8a4f60e314f04075e15a3422c03e4006"
PSF_SHA = "e5f58c16be9db1c672915d9be455c4ef083ca760908bb20bf4991675e3d77cfc"

def emit(data):
    text = json.dumps(data, sort_keys=True)
    if len(text) > 32768:
        raise ValueError("bounded power result")
    sys.stdout.write(text + "\n")

def snapshot():
    N.N.configure(JOB_ID, "dc")
    B.environment_preflight()
    facts = B.verify_netlist()
    if facts["input_sha256"] != INPUT_SHA:
        raise ValueError("exact preserved power source")
    text = re.sub(r"\\\r?\n\s*", " ", B.read(B.NETDIR + "/netlist").decode("latin-1"))
    found = {}
    for line in text.splitlines():
        if " vsource " not in line:
            continue
        match = re.match(r"^(V[0-9]+) \(([A-Za-z0-9_]+) 0\) vsource (.+)$", line.strip())
        if not match or match.group(1) in found:
            raise ValueError("source inventory")
        found[match.group(1)] = match.group(2)
    if found != dict((source[1], source[2]) for source in SOURCES):
        raise ValueError("complete source inventory required")
    psf = N.N.CAND.tree(B.JOB + "/psf")
    if psf["sha256"] != PSF_SHA:
        raise ValueError("preserved PSF drift")
    source = N.N.CAND.tree(os.path.dirname(B.JOB))
    # New bounded extraction fits the existing admitted job reservation.
    if source["total_bytes"] + 8 * 1024 ** 2 > 128 * 1024 ** 2:
        raise ValueError("existing source result reservation insufficient")
    counter = json.loads(B.read(B.COUNTER, 1024))
    N.validate_counter(counter, N.authorization())
    return {"protected": B.snapshot(), "source": source, "counter": counter,
            "psf_sha256": PSF_SHA, "input_sha256": INPUT_SHA}

def begin():
    if os.path.realpath(RUNTIME) != RUNTIME or os.path.lexists(RUNTIME):
        raise ValueError("power extraction containment or replay")
    before = snapshot()
    os.mkdir(RUNTIME, 0o700)
    B.save(RUNTIME + "/before.json", before)
    template = B.read(VERSION + "/extract.ocn").decode("ascii")
    reads = []
    for alias, instance, node, voltage, role in SOURCES:
        reads.append('  voltage=mcpPowerScalar("' + node + '")')
        reads.append('  current=mcpPowerScalar("' + instance + ':p")')
        reads.append('  fprintf(port "SOURCE|' + alias + '|%L|%L\\n" voltage current)')
    for token in ("@FRAME@", "@PSF@", "@READS@"):
        if template.count(token) != 1:
            raise ValueError("closed power template")
    B.write_new(RUNTIME + "/read.ocn", template.replace("@FRAME@", RUNTIME + "/frame.txt")
                .replace("@PSF@", B.JOB + "/psf").replace("@READS@", "\n".join(reads)))

def finish():
    before = json.loads(B.read(RUNTIME + "/before.json", 32768))
    if before != snapshot():
        raise ValueError("power extraction protection")
    log = B.read(RUNTIME + "/ocean.log", 2 * 1024 ** 2).decode("latin-1")
    frame = B.read(RUNTIME + "/frame.txt", 8192)
    lines = frame.decode("ascii").splitlines()
    if len(lines) != 8 or lines[0] != "BEGIN" or lines[-1] != "END":
        raise ValueError("power frame shape")
    sources = []
    missing = False
    for line, source in zip(lines[1:-1], SOURCES):
        alias, instance, node, expected, role = source
        parts = line.split("|")
        if len(parts) != 4 or parts[:2] != ["SOURCE", alias]:
            raise ValueError("power frame identity")
        voltage = None if parts[2] == "nil" else float(parts[2])
        current = None if parts[3] == "nil" else float(parts[3])
        if voltage is None or current is None:
            missing = True
        if voltage is not None and (math.isnan(voltage) or math.isinf(voltage)
                                   or abs(voltage - expected) > 1e-9):
            raise ValueError("effective source voltage mismatch")
        if current is not None and (math.isnan(current) or math.isinf(current)):
            raise ValueError("invalid signed current")
        sources.append({"source_id": alias, "role": role, "voltage_v": voltage,
                        "current_a": current})
    errors = any("*Error*" in line for line in log.splitlines() if not line.startswith("\\i "))
    data = {"schema_version": 1, "job_id": JOB_ID, "analysis": "dc",
            "input_sha256": INPUT_SHA, "psf_sha256": PSF_SHA,
            "frame_sha256": B.sha(frame), "sources": sources,
            "status": "UNQUALIFIED" if missing or errors else "EXTRACTED",
            "reason": "signed_branch_current_unavailable" if missing else
                      "reader_error" if errors else None,
            "protected_unchanged": True, "counter": before["counter"],
            "new_spectre_attempts": 0, "new_reservation_bytes": 0}
    B.save(RUNTIME + "/result.json", data)
    emit(data)

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("begin", "finish", "result"):
        raise ValueError("fixed power action")
    if sys.argv[1] == "begin":
        begin()
    elif sys.argv[1] == "finish":
        finish()
    else:
        current = snapshot()
        before = json.loads(B.read(RUNTIME + "/before.json", 32768))
        if dict((k, v) for k, v in current.items() if k != "counter") != dict(
                (k, v) for k, v in before.items() if k != "counter"):
            raise ValueError("preserved extraction source changed")
        data = json.loads(B.read(RUNTIME + "/result.json", 32768))
        if (data["input_sha256"] != INPUT_SHA or data["psf_sha256"] != PSF_SHA
                or data["frame_sha256"] != B.sha(B.read(RUNTIME + "/frame.txt", 8192))):
            raise ValueError("power result identity")
        emit(data)
