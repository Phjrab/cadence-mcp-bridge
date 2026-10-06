#!/usr/bin/env python
"""Fixed nominal input-nulling study, preserving all old source and jobs."""
from __future__ import with_statement

import imp
import json
import math
import os
import subprocess
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/offset-qual-v1"
RUNTIME = ROOT + "/offset-qual-v1"
M = imp.load_source("offset_preserved_slew", ROOT + "/phase-campaign/slew-qual-v4/helper.py")
B, N, W = M.B, M.N, M.W
SOURCE_ID = "f154d798-0f7f-47d6-9323-6b046394eef6"
INPUT_SHA = "c9bcf3e3bd8a9329ff0bb1513df2a08f8a4f60e314f04075e15a3422c03e4006"
PSF_SHA = "e5f58c16be9db1c672915d9be455c4ef083ca760908bb20bf4991675e3d77cfc"
CASES = ("zero", "minus1", "plus1", "minus05", "plus05")
VALUES = {"zero":("500m","500m",0.0), "minus1":("499.9995m","500.0005m",-1e-6),
          "plus1":("500.0005m","499.9995m",1e-6),
          "minus05":("499.99975m","500.00025m",-0.5e-6),
          "plus05":("500.00025m","499.99975m",0.5e-6)}
CASE, JOB = None, None


def configure(case):
    global CASE, JOB
    if case not in CASES:
        raise ValueError("fixed offset case")
    CASE, JOB = case, RUNTIME + "/" + case
    M.contained(JOB)


def source():
    N.N.configure(SOURCE_ID, "dc")
    r = W.capture(N.N.result)
    if r["input_sha256"] != INPUT_SHA or r["psf_sha256"] != PSF_SHA or r["quality"] != "valid":
        raise ValueError("pinned valid DC required")
    return r


def protected():
    p = M.checkpoint()
    # Ledger advancement is checked independently with the exact offset sequence.
    del p["native"]["counter"]
    p["slew"] = N.N.CAND.tree(M.RUNTIME)
    return p


def authorization():
    p = json.loads(B.read(VERSION+"/policy.json",8192))
    d = B.sha(json.dumps(p,sort_keys=True,separators=(",",":")).encode("ascii"))
    if json.loads(B.read(VERSION+"/activation.private.json",4096)) != {
            "phase":"ANALOG-OFFSET-01","policy_sha256":d,
            "user_delegation":"explicit-in-current-task","user_instruction":"input_nulling"}:
        raise ValueError("explicit offset selection/delegation")
    if (p.get("phase")!="ANALOG-OFFSET-01" or p.get("source_job_id")!=SOURCE_ID
            or p.get("cases")!=list(CASES) or p.get("new_attempt_ceiling")!=4
            or p.get("definition")!="nominal-open-loop-input-nulling-v1"
            or p.get("reservation_bytes_per_job")!=B.RESERVATION
            or p.get("baseline_counter")!={"campaign_id":"AUTO-PHASE-01","count":68,"result_reserved_bytes":7919894528}
            or p.get("delete_authority") is not False or p.get("publication_authority") is not False):
        raise ValueError("fixed offset scope")
    W.authorization()
    return d


def counter(submit=False):
    data = W.counter(True)
    n = 0
    for case in CASES[1:]:
        path=RUNTIME+"/"+case+"/attempt-reserved"
        if os.path.lexists(path):
            n += 1
            if json.loads(B.read(path,1024)) != {"campaign_id":"AUTO-PHASE-01","count":68+n,
                    "result_reserved_bytes":7919894528+n*B.RESERVATION}:
                raise ValueError("offset admission sequence")
        elif any(os.path.lexists(RUNTIME+"/"+later+"/attempt-reserved") for later in CASES[CASES.index(case)+1:]):
            raise ValueError("out of order offset admission")
    if data != {"campaign_id":"AUTO-PHASE-01","count":68+n,
                "result_reserved_bytes":7919894528+n*B.RESERVATION}:
        raise ValueError("strict offset phase accounting")
    if submit:
        N.validate_counter(data,N.authorization())
    return data


def changes():
    return (("V1 (Vp 0) vsource dc=500m", "V1 (Vp 0) vsource dc="+VALUES[CASE][0]),
            ("V2 (Vm 0) vsource dc=500m", "V2 (Vm 0) vsource dc="+VALUES[CASE][1]))


def verify():
    authorization()
    before=json.loads(B.read(JOB+"/before.json",65536))
    if before["protected"] != protected():
        raise ValueError("protected source ADE PDK old results drift")
    expected=68+max(0,CASES.index(CASE)-1)
    if before["counter"] != {"campaign_id":"AUTO-PHASE-01","count":expected,
            "result_reserved_bytes":7919894528+(expected-68)*B.RESERVATION}:
        raise ValueError("prior admission accounting")
    text=B.read(JOB+"/netlist/input.scs")
    if CASE!="zero":
        for old,new in changes():
            if text.count(new.encode("ascii"))!=1:
                raise ValueError("effective offset substitution")
            text=text.replace(new.encode("ascii"),old.encode("ascii"))
    if B.sha(text)!=INPUT_SHA:
        raise ValueError("reverse original DC input identity")
    source()


def begin():
    digest=authorization()
    B.environment_preflight()
    data=counter(CASE!="zero")
    index=max(0,CASES.index(CASE)-1)
    if data["count"]!=68+index or os.path.lexists(JOB):
        raise ValueError("offset replay or order")
    before={"protected":protected(),"counter":data}
    source()
    text=B.read(B.NETDIR+"/input.scs")
    if B.sha(text)!=INPUT_SHA:
        raise ValueError("pinned source DC bytes")
    if CASE!="zero":
        for old,new in changes():
            if text.count(old.encode("ascii"))!=1:
                raise ValueError("fixed replacement boundary")
            text=text.replace(old.encode("ascii"),new.encode("ascii"))
    psf=B.JOB+"/psf" if CASE=="zero" else JOB+"/psf"
    M.contained(RUNTIME)
    if not os.path.exists(RUNTIME): os.mkdir(RUNTIME,0o700)
    os.mkdir(JOB,0o700); os.mkdir(JOB+"/netlist",0o700)
    if CASE!="zero": os.mkdir(JOB+"/psf",0o700)
    B.save(JOB+"/before.json",before)
    B.save(JOB+"/admission.json",{"case":CASE,"source_job_id":SOURCE_ID,"policy_sha256":digest})
    B.write_new(JOB+"/netlist/input.scs",text)
    template=B.read(VERSION+"/extract.ocn").decode("ascii")
    B.write_new(JOB+"/extract.ocn",template.replace("@JOB@",JOB).replace("@PSF@",psf))
    verify()


def reserve():
    if CASE=="zero": raise ValueError("zero reuses existing simulation")
    B.environment_preflight(); verify()
    data=counter(True)
    if os.path.lexists(JOB+"/attempt-reserved") or data["count"]!=68+CASES.index(CASE)-1:
        raise ValueError("offset reservation replay")
    data["count"]+=1; data["result_reserved_bytes"]+=B.RESERVATION
    B.save(JOB+"/attempt-reserved",data)
    B.save(B.COUNTER+".ade-tmp",data); os.rename(B.COUNTER+".ade-tmp",B.COUNTER)


def parse(frame):
    lines=frame.decode("ascii").splitlines()
    names=("Vop","Vom","Vp","Vm","VDD")
    if len(lines)!=7 or lines[0]!="BEGIN" or lines[-1]!="END":
        raise ValueError("bounded offset DC frame")
    rows={}
    for name,line in zip(names,lines[1:-1]):
        parts=line.split("|")
        if len(parts)!=2 or parts[0]!=name: raise ValueError("fixed DC signal order")
        v=float(parts[1])
        if math.isnan(v) or math.isinf(v): raise ValueError("finite DC scalar")
        rows[name]=v
    if (abs(rows["Vp"]-float(VALUES[CASE][0][:-1])*0.001)>1e-12
            or abs(rows["Vm"]-float(VALUES[CASE][1][:-1])*0.001)>1e-12
            or abs((rows["Vp"]+rows["Vm"])/2-0.5)>1e-12
            or abs(rows["VDD"]-1)>1e-12):
        raise ValueError("measured effective inputs or rail")
    return rows


def receipt():
    N.N.CAND.tree(JOB)
    rows=[]
    for current,dirs,files in os.walk(JOB):
        for name in dirs: rows.append(["d",os.path.relpath(os.path.join(current,name),JOB)])
        for name in files:
            p=os.path.join(current,name)
            if p!=JOB+"/complete.json":
                rows.append(["f",os.path.relpath(p,JOB),B.sha(B.read(p,B.RESERVATION))])
    return sorted(rows)


def finish():
    verify(); current=counter()
    if CASE!="zero":
        log=B.read(JOB+"/spectre.log").decode("latin-1")
        summaries=B.guard().SUMMARY.findall(log)
        warnings=[l for l in log.splitlines() if "WARNING" in l]
        if (len(summaries)!=1 or int(summaries[0][0]) or len(warnings)!=int(summaries[0][1])
                or len(warnings)>2 or any("WARNING (CMI-2477):" not in l for l in warnings)):
            raise ValueError("offset simulation quality")
        psf=N.N.CAND.tree(JOB+"/psf")["sha256"]
        notices=int(summaries[0][2])
        marker=json.loads(B.read(JOB+"/attempt-reserved",1024))
        if current!=marker: raise ValueError("offset completion admission")
    else:
        src=source()
        psf=PSF_SHA; warnings=list(range(src["warnings"])); notices=src["notices"]; marker=current
    ocean=B.read(JOB+"/ocean.log",2*1024**2).decode("latin-1")
    if any("*Error*" in l for l in ocean.splitlines() if not l.startswith("\\i ")):
        raise ValueError("offset extraction error")
    frame=B.read(JOB+"/frame.txt",4096)
    row=parse(frame)
    if N.N.CAND.tree(JOB)["total_bytes"]>=B.RESERVATION-65536:
        raise ValueError("offset result byte bound")
    B.save(JOB+"/result.json",{"schema_version":1,"case":CASE,"source_job_id":SOURCE_ID,
        "source_input_sha256":INPUT_SHA,"source_psf_sha256":PSF_SHA,
        "input_sha256":B.sha(B.read(JOB+"/netlist/input.scs")),"psf_sha256":psf,
        "frame_sha256":B.sha(frame),"scalars":row,"counter":marker,
        "new_simulation":CASE!="zero","warnings":len(warnings),"notices":notices,
        "protected_unchanged":True})
    B.save(JOB+"/complete.json",receipt())


def result():
    authorization(); counter()
    rows=[]
    for case in CASES:
        configure(case); verify()
        if json.loads(B.read(JOB+"/complete.json",65536))!=receipt():
            raise ValueError("offset whole result identity")
        r=json.loads(B.read(JOB+"/result.json",8192))
        if r["scalars"]!=parse(B.read(JOB+"/frame.txt",4096)):
            raise ValueError("offset extraction drift")
        rows.append(r)
    print(json.dumps({"schema_version":1,"cases":rows},sort_keys=True))


def postflight():
    authorization()
    jobs={}
    for case in CASES:
        configure(case)
        if os.path.lexists(JOB):
            verify()
            if json.loads(B.read(JOB+"/complete.json",65536))!=receipt():
                raise ValueError("incomplete offset evidence")
            p=subprocess.Popen(["du","-sk",JOB],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            out,err=p.communicate()
            if p.returncode or err or len(out)>1024: raise ValueError("bounded allocation")
            jobs[case]={"tree":N.N.CAND.tree(JOB),"allocated_bytes":int(out.split()[0])*1024}
    print(json.dumps({"protected":protected(),"counter":counter(),"jobs":jobs},sort_keys=True))


if __name__=="__main__":
    try:
        if len(sys.argv)==3 and sys.argv[1] in ("begin","reserve","finish"):
            configure(sys.argv[2]); globals()[sys.argv[1]]()
        elif sys.argv[1:]==["result"]: result()
        elif sys.argv[1:]==["postflight"]: postflight()
        else: raise ValueError("fixed offset action")
    except (IOError,OSError,ValueError,KeyError,TypeError,IndexError,ZeroDivisionError):
        sys.stderr.write("bounded offset operation failed\n"); sys.exit(69)
