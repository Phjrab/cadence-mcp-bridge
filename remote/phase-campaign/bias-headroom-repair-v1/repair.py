#!/usr/bin/env python
"""One-shot exact reconstruction of the accidentally extended extraction script."""
from __future__ import with_statement
import hashlib
import json
import os

ROOT = "/home/buet/cds_work/.cadence_mcp"
OLD = ROOT + "/ade-qual-v6"
EVIDENCE = ROOT + "/bias-headroom-repair-v1"
TARGET = OLD + "/extract.ocn"
CHANGED_SHA = "13055b9a7e56a040f54c7e1a23f90b2f03f5b82dd170c5bf0cf05f6b36f25cfa"
GRAPH = ROOT + "/ade-pvt-diag-v2/extract/devices.private.json"
GRAPH_SHA = "c23b33abf0dae4f838f14cc013dbc964f9a003dfc590883b935fa82137a04a44"
FIELDS = ("id", "gm", "gds", "gmbs", "vgs", "vds", "vbs", "vth", "vdsat", "region")

def read(path):
    if os.path.realpath(path) != path or not os.path.isfile(path) or os.path.getsize(path) > 65536:
        raise ValueError("fixed recovery file boundary")
    return open(path, "rb").read()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)

def main():
    if os.path.lexists(EVIDENCE) or os.path.realpath(OLD) != OLD:
        raise ValueError("exact reconstruction replay or containment")
    changed = read(TARGET)
    if sha(changed) != CHANGED_SHA:
        raise ValueError("unexpected changed extraction bytes")
    graph = read(GRAPH)
    if sha(graph) != GRAPH_SHA:
        raise ValueError("preserved graph")
    original = read(ROOT + "/phase-campaign/sim-mcp-v2/extract-dc.ocn").replace("@JOB@", OLD)
    original = original.replace("  unless(selectResult('dc) close(port) exit(1))",
        '  unless(member(\'dcOp results()) || member("dcOp" results()) close(port) exit(1))\n'
        "  unless(selectResult('dcOp) close(port) exit(1))\n"
        '  let((proof) proof=outfile("' + OLD + '/selector.txt")\n'
        '    unless(proof close(port) exit(1))\n'
        '    fprintf(proof "MCP_ADE_RESULT_SELECTOR|dcOp\\n") close(proof))')
    op = ['let((port value) port=outfile("' + OLD + '/op-frame.txt")',
          'unless(port exit(1))', 'unless(selectResult("dcOpInfo") close(port) exit(1))',
          'fprintf(port "BEGIN\\n")']
    for member in json.loads(graph):
        for field in FIELDS:
            op += ['value=pv("' + member["instance"] + '" "' + field + '" ?result "dcOpInfo")',
                'unless(numberp(value) close(port) exit(1))',
                'fprintf(port "OP|' + member["alias"] + '|' + field + '|%L\\n" value)']
    op += ['fprintf(port "END\\n") close(port))', 'exit(0)']
    if original.count("exit(0)") != 1 or original.replace("exit(0)", "\n".join(op)) != changed:
        raise ValueError("change is not exactly the known accidental insertion")
    os.mkdir(EVIDENCE, 0o700)
    write(EVIDENCE + "/changed-extract.private.ocn", changed)
    record = {"changed_sha256": sha(changed), "reconstructed_sha256": sha(original),
              "method": "qualified_template_plus_exact_verified_inverse_insertion",
              "metadata_restoration": "not_claimed", "simulation": "not_run"}
    write(EVIDENCE + "/intent.json", json.dumps(record, sort_keys=True))
    write(EVIDENCE + "/reconstructed-extract.private.ocn", original)
    write(EVIDENCE + "/restore.tmp", original)
    if read(TARGET) != changed:
        raise ValueError("changed evidence drift before restore")
    os.rename(EVIDENCE + "/restore.tmp", TARGET)
    if read(TARGET) != original or read(EVIDENCE + "/changed-extract.private.ocn") != changed:
        raise ValueError("reconstruction verification")
    write(EVIDENCE + "/result.json", json.dumps(record, sort_keys=True))
    print(json.dumps(record, sort_keys=True))

if __name__ == "__main__":
    main()
