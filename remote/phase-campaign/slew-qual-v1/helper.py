#!/usr/bin/env python
"""Fixed owned step copies; no original netlist, result or ADE mutation."""
from __future__ import with_statement

import imp
import json
import os
import subprocess
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/slew-qual-v1"
RUNTIME = ROOT + "/slew-qual-v1"
W = imp.load_source("slew_preserved_bandwidth", ROOT + "/phase-campaign/bandwidth-qual-v1/helper.py")
B, N = W.B, W.N
A = imp.load_source("slew_fixed_analysis", VERSION + "/analysis.py")
SOURCE_ID = "eca78308-8af8-4810-b848-94c0ad936afe"
INPUT_SHA = "3efc38f937a7fb8e662eb71a82464ea8fff45e50d5d5fcd11d9a453b1c1ce975"
PSF_SHA = "6b3bde9514941767b2fd573649621322ba5b53333dbe9ce77978e0119c0a679a"
CASES = ("coarse", "medium", "fine", "fast")
CONTROLS = {"coarse": ("10n", "1n", "3999n"), "medium": ("5n", "1n", "3999n"),
            "fine": ("2.5n", "1n", "3999n"), "fast": ("2.5n", "0.5n", "3999.5n")}
CASE, JOB = None, None


def contained(path):
    if os.path.realpath(path) != path or not path.startswith(ROOT + "/"):
        raise ValueError("step containment")


def configure(case):
    global CASE, JOB
    if case not in CASES:
        raise ValueError("fixed step case")
    CASE, JOB = case, RUNTIME + "/" + case
    contained(JOB)


def changes():
    step, edge, width = CONTROLS[CASE]
    return (("V1 (Vp 0) vsource dc=500m mag=500m type=sine ampl=50m freq=1K",
             "V1 (Vp 0) vsource dc=450m mag=500m type=pulse val0=450m val1=550m delay=2u rise="+edge+" fall="+edge+" width="+width+" period=20u"),
            ("V2 (Vm 0) vsource dc=500m mag=-500m type=sine ampl=50m sinephase=180 \\\n        freq=1K",
             "V2 (Vm 0) vsource dc=550m mag=-500m type=pulse val0=550m val1=450m delay=2u rise="+edge+" fall="+edge+" width="+width+" period=20u"),
            ('tran tran stop=4m maxstep=10u write="spectre.ic" writefinal="spectre.fc" \\\n    method=trap annotate=status maxiters=5 ',
             'tran tran stop=10u maxstep='+step+' write="spectre.ic" writefinal="spectre.fc" \\\n    method=trap annotate=status maxiters=5 '))


def authorization():
    p = json.loads(B.read(VERSION + "/policy.json", 8192))
    digest = B.sha(json.dumps(p, sort_keys=True, separators=(",", ":")).encode("ascii"))
    if json.loads(B.read(VERSION + "/activation.private.json", 4096)) != {
            "phase": "ANALOG-SLEW-01", "policy_sha256": digest,
            "user_delegation": "explicit-in-current-task", "user_instruction": "proceed"}:
        raise ValueError("step delegation")
    if (p.get("phase") != "ANALOG-SLEW-01" or p.get("source_job_id") != SOURCE_ID
            or p.get("cases") != list(CASES) or p.get("new_attempt_ceiling") != 4
            or p.get("reservation_bytes_per_job") != B.RESERVATION
            or p.get("baseline_counter") != {"campaign_id":"AUTO-PHASE-01","count":64,"result_reserved_bytes":7383023616}
            or p.get("delete_authority") is not False or p.get("publication_authority") is not False):
        raise ValueError("step scope")
    W.authorization()
    return digest


def source():
    N.N.configure(SOURCE_ID, "tran")
    r = W.capture(N.N.result)
    if r["input_sha256"] != INPUT_SHA or r["psf_sha256"] != PSF_SHA:
        raise ValueError("admitted TRAN identity")
    return r


def checkpoint():
    c = W.checkpoint()
    source()
    f = imp.load_source("slew_preserved_sizing", ROOT + "/phase-campaign/fs-sizing-screen-02-v2/helper.py")
    f.configure("00000000-0000-4000-8000-000000000000", "dc", "FS")
    f.authority()
    f.protection()
    if os.path.lexists(f.JOBS+"/active"):
        raise ValueError("active sizing")
    c["sizing"] = f.C.tree(f.JOBS)
    c["bandwidth"] = N.N.CAND.tree(W.RUNTIME)
    return c


def counter(read_only=False):
    data = W.counter(True)
    if not read_only:
        N.validate_counter(data, N.authorization())
    count = 0
    for case in CASES:
        marker = RUNTIME + "/" + case + "/attempt-reserved"
        contained(marker)
        if os.path.lexists(marker):
            count += 1
            r = json.loads(B.read(marker, 1024))
            if r != {"campaign_id":"AUTO-PHASE-01", "count":64+count,
                     "result_reserved_bytes":7383023616+count*B.RESERVATION}:
                raise ValueError("step reservation sequence")
        elif any(os.path.lexists(RUNTIME+"/"+later+"/attempt-reserved") for later in CASES[CASES.index(case)+1:]):
            raise ValueError("out of order reservation")
    if data != {"campaign_id":"AUTO-PHASE-01", "count":64+count,
                "result_reserved_bytes":7383023616+count*B.RESERVATION}:
        raise ValueError("whole campaign conservation")
    return data


def verify():
    before = json.loads(B.read(JOB + "/before.json", 65536))
    if before != checkpoint():
        raise ValueError("protected original jobs ADE PDK drift")
    text = B.read(JOB+"/netlist/input.scs")
    for old, new in changes():
        if text.count(new.encode("ascii")) != 1:
            raise ValueError("effective step identity")
        text = text.replace(new.encode("ascii"), old.encode("ascii"))
    if B.sha(text) != INPUT_SHA:
        raise ValueError("reverse pinned input identity")


def begin():
    digest = authorization()
    B.environment_preflight()
    data = counter()
    if data["count"] != 64+CASES.index(CASE) or os.path.lexists(JOB):
        raise ValueError("step replay or order")
    before = checkpoint()
    source()
    text = B.read(B.NETDIR+"/input.scs")
    if B.sha(text) != INPUT_SHA:
        raise ValueError("source byte identity")
    for old, new in changes():
        if text.count(old.encode("ascii")) != 1:
            raise ValueError("reviewed replacement boundary")
        text = text.replace(old.encode("ascii"), new.encode("ascii"))
    contained(RUNTIME)
    if not os.path.exists(RUNTIME):
        os.mkdir(RUNTIME, 0o700)
    os.mkdir(JOB, 0o700)
    os.mkdir(JOB+"/netlist", 0o700)
    os.mkdir(JOB+"/psf", 0o700)
    B.save(JOB+"/before.json", before)
    B.save(JOB+"/admission.json", {"policy_sha256":digest, "case":CASE, "source_job_id":SOURCE_ID})
    B.write_new(JOB+"/netlist/input.scs", text)
    B.write_new(JOB+"/extract.ocn", B.read(VERSION+"/extract.ocn").decode("ascii").replace("@JOB@",JOB))
    verify()


def reserve():
    authorization()
    B.environment_preflight()
    verify()
    if os.path.lexists(JOB+"/attempt-reserved"):
        raise ValueError("step replay")
    data = counter()
    if data["count"] != 64+CASES.index(CASE):
        raise ValueError("step reservation order")
    data["count"] += 1
    data["result_reserved_bytes"] += B.RESERVATION
    B.save(JOB+"/attempt-reserved", data)
    B.save(B.COUNTER+".ade-tmp", data)
    os.rename(B.COUNTER+".ade-tmp", B.COUNTER)


def receipt():
    N.N.CAND.tree(JOB)
    rows = []
    for current, dirs, files in os.walk(JOB):
        for name in dirs:
            rows.append(["d",os.path.relpath(os.path.join(current,name),JOB)])
        for name in files:
            path = os.path.join(current,name)
            if path != JOB+"/complete.json":
                rows.append(["f",os.path.relpath(path,JOB),B.sha(B.read(path,B.RESERVATION))])
    return sorted(rows)


def finish():
    authorization()
    verify()
    data = counter(True)
    if not os.path.isfile(JOB+"/attempt-reserved"):
        raise ValueError("missing reservation")
    log = B.read(JOB+"/spectre.log").decode("latin-1")
    summaries = B.guard().SUMMARY.findall(log)
    warnings = [l for l in log.splitlines() if "WARNING" in l]
    if (len(summaries)!=1 or int(summaries[0][0]) or len(warnings)!=int(summaries[0][1])
            or len(warnings)>2 or any("WARNING (CMI-2477):" not in w for w in warnings)):
        raise ValueError("step simulation quality")
    ocean = B.read(JOB+"/ocean.log",2*1024**2).decode("latin-1")
    if any("*Error*" in l for l in ocean.splitlines() if not l.startswith("\\i ")):
        raise ValueError("step extraction error")
    frame = B.read(JOB+"/frame.txt",8*1024**2)
    summary = A.parse(frame, CASE)
    psf = N.N.CAND.tree(JOB+"/psf")
    if not 0 < psf["total_bytes"] < N.N.CAND.tree(JOB)["total_bytes"] < B.RESERVATION-65536:
        raise ValueError("step result byte bound")
    result = {"schema_version":1,"source_job_id":SOURCE_ID,"source_input_sha256":INPUT_SHA,
              "source_psf_sha256":PSF_SHA,"input_sha256":B.sha(B.read(JOB+"/netlist/input.scs")),
              "psf_sha256":psf["sha256"],"frame_sha256":B.sha(frame),"summary":summary,
              "counter":data,"warnings":len(warnings),"notices":int(summaries[0][2]),
              "protected_unchanged":True}
    B.save(JOB+"/result.json",result)
    B.save(JOB+"/complete.json",receipt())


def result():
    authorization()
    counter(True)
    rows = []
    for case in CASES:
        configure(case)
        verify()
        if json.loads(B.read(JOB+"/complete.json",65536)) != receipt():
            raise ValueError("durable step result drift")
        r = json.loads(B.read(JOB+"/result.json",16384))
        if r["summary"] != A.parse(B.read(JOB+"/frame.txt",8*1024**2),case):
            raise ValueError("step parsed summary drift")
        rows.append(r)
    print(json.dumps({"schema_version":1,"cases":rows},sort_keys=True))


def postflight():
    authorization()
    data = counter(True)
    jobs = {}
    for case in CASES:
        configure(case)
        if os.path.lexists(JOB):
            verify()
            if not os.path.isfile(JOB+"/complete.json") or json.loads(B.read(JOB+"/complete.json",65536)) != receipt():
                raise ValueError("incomplete or changed step evidence")
            tree = N.N.CAND.tree(JOB)
            p = subprocess.Popen(["du","-sk",JOB],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            out,err = p.communicate()
            if p.returncode or err or len(out)>1024:
                raise ValueError("bounded allocation")
            jobs[case] = {"tree":tree,"allocated_bytes":int(out.split()[0])*1024}
    disk = os.statvfs(ROOT)
    print(json.dumps({"protected":checkpoint(),"counter":data,"jobs":jobs,
                     "free_bytes":disk.f_bavail*disk.f_frsize,
                     "total_bytes":disk.f_blocks*disk.f_frsize},sort_keys=True))


if __name__ == "__main__":
    try:
        if sys.argv[1:] in (["result"],["postflight"]):
            globals()[sys.argv[1]]()
        elif len(sys.argv)==3 and sys.argv[1] in ("begin","reserve","finish"):
            configure(sys.argv[2])
            globals()[sys.argv[1]]()
        else:
            raise ValueError("fixed step action")
    except (IOError,OSError,ValueError,KeyError,TypeError,IndexError,ZeroDivisionError):
        sys.stderr.write("fixed step qualification failed\n")
        sys.exit(69)
