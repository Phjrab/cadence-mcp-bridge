#!/usr/bin/env python
"""Read preserved offset receipts after future phases advance the shared ledger.

Separate timeless reader, no monkeypatch or weakening of the phase verifier.
"""
from __future__ import with_statement

import imp
import json
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/offset-read-v1"
M = imp.load_source("offset_read_preserved", ROOT+"/phase-campaign/offset-qual-v1/helper.py")


def accounting(current, markers):
    if (len(markers) != 5 or set(current) != set(("campaign_id","count","result_reserved_bytes"))
            or current["campaign_id"] != "AUTO-PHASE-01"
            or type(current["count"]) not in M.B.INTEGER_TYPES or not 72 <= current["count"] <= 500
            or type(current["result_reserved_bytes"]) not in M.B.INTEGER_TYPES
            or not 8456765440 <= current["result_reserved_bytes"] <= 10*1024**3):
        raise ValueError("current cumulative read bounds")
    for index, r in enumerate(markers):
        if r != {"campaign_id":"AUTO-PHASE-01","count":68+index,
                 "result_reserved_bytes":7919894528+index*M.B.RESERVATION}:
            raise ValueError("immutable historical admission sequence")



def preserved(before,now):
    # The native postflight has validated added jobs individually. Preserve every
    # pre-existing job exactly, without treating legitimate new IDs as mutation.
    old_jobs = before["native"]["jobs"]
    new_jobs = now["native"]["jobs"]
    if not isinstance(old_jobs,dict) or not isinstance(new_jobs,dict):
        raise ValueError("native fingerprint inventory")
    if any(k not in new_jobs or new_jobs[k] != v for k,v in old_jobs.items()):
        raise ValueError("historical job removed or changed")
    now["native"]["jobs"] = old_jobs
    if before != now:
        raise ValueError("source ADE PDK historical jobs changed")

def authorization():
    p = json.loads(M.B.read(VERSION+"/policy.json",4096))
    digest = M.B.sha(json.dumps(p,sort_keys=True,separators=(",",":")).encode("ascii"))
    if (p.get("phase") != "ANALOG-OFFSET-01" or p.get("operation") != "read_preserved_offset_receipts"
            or p.get("max_new_attempts") != 0 or p.get("max_new_reserved_bytes") != 0
            or p.get("delete_authority") is not False or p.get("publication_authority") is not False
            or json.loads(M.B.read(VERSION+"/activation.private.json",4096)) != {
                "phase":"ANALOG-OFFSET-01","policy_sha256":digest,
                "user_delegation":"explicit-in-current-task","user_instruction":"proceed"}):
        raise ValueError("read-only deployment delegation")
    M.authorization()
    M.source()


def result():
    authorization()
    # W's bounded ledger read does not assume all later reservations are this phase's.
    current = M.W.counter(True)
    markers = []
    rows = []
    for case in M.CASES:
        M.configure(case)
        before = json.loads(M.B.read(M.JOB+"/before.json",65536))
        now = M.protected()
        index = M.CASES.index(case)
        n = max(0,index-1)
        if before["counter"] != {"campaign_id":"AUTO-PHASE-01","count":68+n,
                "result_reserved_bytes":7919894528+n*M.B.RESERVATION}:
            raise ValueError("historical protected checkpoint accounting")
        preserved(before["protected"],now)
        text = M.B.read(M.JOB+"/netlist/input.scs")
        for old, new in (() if case=="zero" else M.changes()):
            if text.count(new.encode("ascii")) != 1:
                raise ValueError("historical effective input")
            text = text.replace(new.encode("ascii"),old.encode("ascii"))
        if M.B.sha(text) != M.INPUT_SHA:
            raise ValueError("historical original input identity")
        if json.loads(M.B.read(M.JOB+"/complete.json",65536)) != M.receipt():
            raise ValueError("historical whole result receipt")
        marker = ({"campaign_id":"AUTO-PHASE-01","count":68,"result_reserved_bytes":7919894528}
                  if case=="zero" else json.loads(M.B.read(M.JOB+"/attempt-reserved",1024)))
        if case=="zero":
            if M.os.path.lexists(M.JOB+"/attempt-reserved"):
                raise ValueError("zero must not reserve a new attempt")
            M.source()
        r = json.loads(M.B.read(M.JOB+"/result.json",16384))
        if (r["counter"] != marker or r["scalars"] != M.parse(M.B.read(M.JOB+"/frame.txt",4096))):
            raise ValueError("historical admission or extraction drift")
        markers.append(marker)
        rows.append(r)
    accounting(current,markers)
    if current != M.W.counter(True):
        raise ValueError("ledger changed during preserved read")
    output = json.dumps({"schema_version":1,"cases":rows},sort_keys=True)
    if len(output)>32768:
        raise ValueError("bounded offset summary")
    print(output)


if __name__ == "__main__":
    try:
        if sys.argv[1:] != ["result"]:
            raise ValueError("read-only offset result action")
        result()
    except (IOError,OSError,ValueError,KeyError,TypeError,IndexError,ZeroDivisionError):
        sys.stderr.write("preserved offset result read failed\n")
        sys.exit(69)
