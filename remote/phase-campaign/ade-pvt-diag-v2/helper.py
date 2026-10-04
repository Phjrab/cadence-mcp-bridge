#!/usr/bin/env python
"""Fixed read-only MOS operating-point diagnosis, Python 2.6."""
from __future__ import with_statement

import imp
import json
import math
import os
import re
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/ade-pvt-diag-v2"
RUNTIME = ROOT + "/ade-pvt-diag-v2"
P = imp.load_source("diag_pvt_guard", ROOT + "/phase-campaign/ade-pvt-qual-v1/helper.py")
B = P.BASE
COUNTER = {"campaign_id": "AUTO-PHASE-01", "count": 32, "result_reserved_bytes": 3088056320}
JOBS = {
    "NN": (ROOT + "/native-mcp-v1-jobs/f154d798-0f7f-47d6-9323-6b046394eef6/work",
        "f056c3ebcf3e0d83fe0848c2c7a54d5d2f014de2e80ec2f6c1dd362373baa70b"),
    "FF": (P.JOBS + "/07b9ad80-33ce-4bc1-a04c-c3a1b341619d/work",
        "4214a48f46bdf1718af9534b9d47d414185369d9d73e2416eb27a029a66c1557"),
    "SS": (P.JOBS + "/ab21baec-217a-4c2a-ab80-92eaa66bb077/work",
        "4341099bf8ecab21e2db6c31d435abc2dedbe1f67617bd13eff9bec383a792f4"),
    "FS": (P.JOBS + "/5e11f2c1-aea9-4600-8d18-a72222234313/work",
        "0a3e36118d439ee5214a22ebe9803fa2b7dff1dc3e448c91e033213670d60f75"),
    "SF": (P.JOBS + "/ecd03f04-2606-4626-bb68-a6fb05f72d8c/work",
        "20fea95ae1ea27d5258e9fd1e08a6e06d4676963b78b227f2ad3983082069e40"),
}
CORNERS = ("NN", "FF", "SS", "FS", "SF")
FIELDS = ("id", "gm", "gds", "gmbs", "vgs", "vds", "vbs", "vth", "vdsat", "region")
SELECTORS = ("dcOpInfo-info", "dcOpInfo")
NETREL = "/project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist/netlist"


def emit(data):
    text = json.dumps(data, sort_keys=True)
    if len(text) > 65536:
        raise ValueError("diagnostic result size")
    sys.stdout.write(text + "\n")


def snapshot():
    B.environment_preflight()
    P.references()
    if json.loads(B.read(B.COUNTER, 1024)) != COUNTER:
        raise ValueError("diagnostic cumulative budget changed")
    data = B.snapshot()
    prior = P.CAND.tree(ROOT + "/ade-pvt-diag-v1")
    if prior["sha256"] != "9edb7ca17efaf33af94edb76ddafe5d2da612e9892097337ea1b996d293b4cfa":
        raise ValueError("preserved diagnostic failure tree drift")
    data["prior_failure_tree_sha256"] = prior["sha256"]
    for corner in CORNERS:
        job, expected = JOBS[corner]
        if P.CAND.tree(os.path.dirname(job))["sha256"] != expected:
            raise ValueError("preserved corner tree drift")
    data.update({"counter": COUNTER, "model_manifest_sha256": P.models()})
    return data


def devices(text):
    logical = re.sub(r"\\\r?\n\s*", " ", text)
    pattern = re.compile(r"^(NM[0-9]+|PM[0-9]+) \(([A-Za-z0-9_ ]+)\) ([A-Za-z0-9_]+) (.+)$")
    found = {}
    for line in logical.splitlines():
        match = pattern.match(line.strip())
        if match:
            name, nodes, model, unused = match.groups()
            nodes = nodes.split()
            if name in found or len(nodes) != 4:
                raise ValueError("MOS terminal identity")
            found[name] = {"kind": "nmos" if name.startswith("NM") else "pmos",
                "nodes": nodes, "model_sha256": B.sha(model.encode("ascii"))}
    if (sum(item["kind"] == "nmos" for item in found.values()) != 8
            or sum(item["kind"] == "pmos" for item in found.values()) != 6):
        raise ValueError("exact preserved MOS inventory")
    result = []
    for index, name in enumerate(sorted(found)):
        item = dict(found[name])
        item.update({"alias": "mos%02d" % (index + 1), "instance": name})
        result.append(item)
    return result


def inventory():
    original = devices(B.read(JOBS["NN"][0] + NETREL).decode("latin-1"))
    for corner in CORNERS[1:]:
        if devices(B.read(JOBS[corner][0] + NETREL).decode("latin-1")) != original:
            raise ValueError("cross-corner MOS topology drift")
    return original


def begin(action):
    if action not in ("probe", "extract") or os.path.realpath(RUNTIME) != RUNTIME:
        raise ValueError("fixed diagnostic action or containment")
    if action == "probe":
        if os.path.lexists(RUNTIME):
            raise ValueError("diagnostic replay")
        os.mkdir(RUNTIME, 0o700)
    before = snapshot()
    record = RUNTIME + "/" + action
    if os.path.lexists(record):
        raise ValueError("diagnostic action replay")
    os.mkdir(record, 0o700)
    B.save(record + "/before.json", before)
    members = inventory()
    B.save(record + "/devices.private.json", members)
    selected = None
    if action == "extract":
        probe = json.loads(B.read(RUNTIME + "/probe/result.json", 65536))
        if probe.get("state") != "succeeded" or not probe.get("pv_callable"):
            raise ValueError("qualified operating-point probe required")
        selected = {}
        for corner in CORNERS:
            usable = [selector for selector in SELECTORS if probe["selectors"][corner][selector]]
            if len(usable) != 1:
                raise ValueError("ambiguous or absent operating-point selector")
            selected[corner] = usable[0]
    template = B.read(VERSION + "/" + action + ".ocn").decode("ascii")
    reads = []
    for corner in CORNERS:
        reads.append('  unless(openResults("' + JOBS[corner][0] + '/psf") close(port) exit(1))')
        if action == "probe":
            for selector in SELECTORS:
                reads.append('  fprintf(port "R|' + corner + '|' + selector + '|%L\\n" mcpHasResult("' + selector + '"))')
        else:
            selector = selected[corner]
            reads.append('  unless(selectResult("' + selector + '") close(port) exit(1))')
            for member in members:
                for field in FIELDS:
                    reads.append('  mcpReadOp(port "' + corner + '" "' + member["alias"] + '" "' + member["instance"] + '" "' + field + '" "' + selector + '")')
    if template.count("@READS@") != 1 or template.count("@FRAME@") != 1:
        raise ValueError("fixed template binding")
    script = template.replace("@READS@", "\n".join(reads)).replace("@FRAME@", record + "/frame.txt")
    B.write_new(record + "/read.ocn", script)


def finish(action):
    record = RUNTIME + "/" + action
    before = json.loads(B.read(record + "/before.json", 32768))
    if before != snapshot() or inventory() != json.loads(B.read(record + "/devices.private.json", 16384)):
        raise ValueError("read-only diagnostic protection")
    log = B.read(record + "/ocean.log").decode("latin-1")
    if any("*Error*" in line for line in log.splitlines() if not line.startswith("\\i ")):
        raise ValueError("operating-point reader error")
    frame = B.read(record + "/frame.txt", 65536)
    if action == "probe":
        result = parse_probe(frame.decode("ascii"))
    else:
        result = parse_frame(frame.decode("ascii"))
    result.update({"state": "succeeded", "phase": "ADE-PVT-DIAG-01", "new_spectre_attempts": 0,
        "protected_unchanged": True, "counter": COUNTER, "spec_evaluation": "not_evaluated",
        "measurement_frame_sha256": B.sha(frame), "model_manifest_sha256": P.MODEL_MANIFEST_SHA})
    B.save(record + "/result.json", result)
    emit(result)


def parse_probe(text):
    lines = text.splitlines()
    if len(lines) != 13 or lines[0] != "BEGIN" or lines[-1] != "END" or lines[1] not in ("PV|t", "PV|nil"):
        raise ValueError("operating-point capability frame")
    selectors = {}
    expected = [(corner, selector) for corner in CORNERS for selector in SELECTORS]
    for line, (corner, selector) in zip(lines[2:-1], expected):
        parts = line.split("|")
        if len(parts) != 4 or parts[:3] != ["R", corner, selector] or parts[3] not in ("t", "nil"):
            raise ValueError("operating-point selector proof")
        selectors.setdefault(corner, {})[selector] = parts[3] == "t"
    return {"pv_callable": lines[1] == "PV|t", "selectors": selectors}


def parse_frame(text):
    lines = text.splitlines()
    if len(lines) != 702 or lines[0] != "BEGIN" or lines[-1] != "END":
        raise ValueError("bounded MOS operating-point frame")
    result = {}
    cursor = 1
    for corner in CORNERS:
        result[corner] = []
        for index in range(14):
            alias = "mos%02d" % (index + 1)
            fields = {}
            for field in FIELDS:
                parts = lines[cursor].split("|")
                cursor += 1
                if len(parts) != 6 or parts[:4] != ["OP", corner, alias, field]:
                    raise ValueError("OP identity, order or field")
                if parts[4] == "missing" and parts[5] == "nil":
                    fields[field] = None
                elif parts[4] == "value":
                    value = float(parts[5])
                    if math.isnan(value) or math.isinf(value) or abs(value) > 1e12:
                        raise ValueError("nonfinite OP field")
                    fields[field] = value
                else:
                    raise ValueError("OP result kind")
            result[corner].append({"alias": alias, "fields": fields})
    return {"operating_points": result, "field_names": list(FIELDS)}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("begin", "finish", "result") or sys.argv[2] not in ("probe", "extract"):
        raise ValueError("fixed diagnostic helper arguments")
    if sys.argv[1] == "begin":
        begin(sys.argv[2])
    elif sys.argv[1] == "finish":
        finish(sys.argv[2])
    else:
        snapshot()
        data = json.loads(B.read(RUNTIME + "/" + sys.argv[2] + "/result.json", 65536))
        if data.get("state") != "succeeded":
            raise ValueError("diagnostic incomplete")
        frame = B.read(RUNTIME + "/" + sys.argv[2] + "/frame.txt", 65536)
        parsed = parse_probe(frame.decode("ascii")) if sys.argv[2] == "probe" else parse_frame(frame.decode("ascii"))
        if data.get("measurement_frame_sha256") != B.sha(frame) or any(data.get(key) != value for key, value in parsed.items()):
            raise ValueError("preserved operating-point result drift")
        emit(data)


if __name__ == "__main__":
    try:
        main()
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError, IndexError):
        sys.stderr.write("fixed MOS diagnostic failed\n")
        sys.exit(69)
