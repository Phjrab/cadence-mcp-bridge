#!/usr/bin/env python
"""Closed compiled grid children; shared ledger, no original writes."""
from __future__ import with_statement
import imp
import json
import os
import re
import subprocess
import sys
import time

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/amplifier-sweep-v1"
JOBS = ROOT + "/amplifier-sweep-v1-jobs"
Q = imp.load_source("amplifier_preserved_bias",ROOT+"/phase-campaign/bias-range-qual-v1/helper.py")
B,N,W = Q.B,Q.N,Q.W
ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
DIGEST = re.compile(r"^[0-9a-f]{64}\Z")
VALUES = {"0.319":"319m","0.32":"320m","0.321":"321m"}
JOB,IDENTITY = None,None


def contained(path):
    if os.path.realpath(path)!=path or not path.startswith(JOBS+"/"):
        raise ValueError("amplifier no-follow containment")


def configure(identity):
    global JOB,IDENTITY
    if not ID.match(identity): raise ValueError("deterministic amplifier child")
    JOB,IDENTITY = JOBS+"/"+identity,identity
    contained(JOB)
    Q.JOB = JOB


def authorization():
    p=json.loads(B.read(VERSION+"/policy.json",8192))
    d=B.sha(json.dumps(p,sort_keys=True,separators=(",",":")).encode("ascii"))
    if (p.get("phase")!="REAL-AMPLIFIER-SWEEP-01" or p.get("grid_v")!=["0.319","0.32","0.321"]
        or p.get("max_new_attempts")!=6 or p.get("reservation_bytes_per_job")!=B.RESERVATION
        or p.get("baseline_counter")!={"campaign_id":"AUTO-PHASE-01","count":76,"result_reserved_bytes":8993636352}
        or p.get("delete_authority") is not False or p.get("publication_authority") is not False
        or not DIGEST.match(p.get("definition_sha256",""))
        or json.loads(B.read(VERSION+"/activation.private.json",4096))!={
            "phase":"REAL-AMPLIFIER-SWEEP-01","policy_sha256":d,
            "user_delegation":"explicit-in-current-task","user_instruction":"continuous_four_phases"}):
        raise ValueError("compiled grid phase delegation")
    Q.authorization()
    return p,d


def request():
    p,d=authorization()
    r=json.loads(B.read(JOB+"/request.json",4096))
    if (set(r)!=set(("job_id","analysis","value_v","plan_hash","policy_sha256"))
        or r["job_id"]!=IDENTITY or r["analysis"] not in ("dc","ac")
        or r["value_v"] not in VALUES or not DIGEST.match(r["plan_hash"])
        or r["policy_sha256"]!=d): raise ValueError("closed amplifier admission")
    Q.MODE,Q.VALUE = r["analysis"],VALUES[r["value_v"]]
    return r


def protected():
    p=Q.protected()
    p["bias_grid"]=N.N.CAND.tree(Q.RUNTIME)
    return p


def counter():
    current=W.counter(True)
    markers=[]
    for name in os.listdir(JOBS):
        if name in ("control.lock","active"): continue
        if not ID.match(name): raise ValueError("unknown amplifier root entry")
        path=JOBS+"/"+name;contained(path)
        marker=path+"/attempt-reserved"
        if os.path.lexists(marker): markers.append(json.loads(B.read(marker,1024)))
    markers.sort(key=lambda m:m["count"])
    if len(markers)>6: raise ValueError("compiled phase attempt bound")
    for i,m in enumerate(markers):
        if m!={"campaign_id":"AUTO-PHASE-01","count":77+i,
               "result_reserved_bytes":8993636352+(i+1)*B.RESERVATION}:
            raise ValueError("durable reservation sequence")
    if current!={"campaign_id":"AUTO-PHASE-01","count":76+len(markers),
                 "result_reserved_bytes":8993636352+len(markers)*B.RESERVATION}:
        raise ValueError("shared ledger conservation")
    return current


def verify_input():
    r=request()
    contained(JOB+"/netlist/input.scs")
    text=B.read(JOB+"/netlist/input.scs")
    changed=("VBIASN="+VALUES[r["value_v"]]).encode("ascii")
    if text.count(changed)!=1 or B.sha(text.replace(changed,b"VBIASN=320m"))!=Q.SOURCES[r["analysis"]][1]:
        raise ValueError("effective input/reversed original identity")
    return r


def verify():
    r=verify_input()
    before=json.loads(B.read(JOB+"/before.json",65536))
    if before["protected"]!=protected(): raise ValueError("protected prior evidence drift")
    Q.source()
    return r


def prepare(mode,value,plan_hash):
    p,d=authorization()
    if mode not in ("dc","ac") or value not in VALUES or not DIGEST.match(plan_hash):
        raise ValueError("closed point binding")
    if os.path.lexists(JOB): raise ValueError("existing child cannot prepare again")
    B.environment_preflight()
    c=counter();N.validate_counter(c,N.authorization())
    if c["count"]>=82: raise ValueError("phase bound exhausted")
    before={"protected":protected(),"counter":c}
    Q.MODE,Q.VALUE=mode,VALUES[value]
    Q.source()
    text=B.read(B.NETDIR+"/input.scs")
    if B.sha(text)!=Q.SOURCES[mode][1] or text.count(b"VBIASN=320m")!=1:
        raise ValueError("original source input")
    text=text.replace(b"VBIASN=320m",("VBIASN="+VALUES[value]).encode("ascii"))
    os.mkdir(JOB,0o700);os.mkdir(JOB+"/netlist",0o700);os.mkdir(JOB+"/psf",0o700)
    B.save(JOB+"/request.json",{"job_id":IDENTITY,"analysis":mode,"value_v":value,
           "plan_hash":plan_hash,"policy_sha256":d})
    B.save(JOB+"/before.json",before)
    B.write_new(JOB+"/netlist/input.scs",text)
    template=B.read(VERSION+"/extract-"+mode+".ocn").decode("ascii")
    B.write_new(JOB+"/extract.ocn",template.replace("@JOB@",JOB))
    verify()
    B.save(JOB+"/state.json",{"stage":"queued","updated_at":timestamp()})


def reserve():
    B.environment_preflight();verify()
    c=counter();N.validate_counter(c,N.authorization())
    before=json.loads(B.read(JOB+"/before.json",65536))
    if before["counter"]!=c or c["count"]>=82 or os.path.lexists(JOB+"/attempt-reserved"):
        raise ValueError("reservation replay/conservation")
    c["count"]+=1;c["result_reserved_bytes"]+=B.RESERVATION
    B.save(JOB+"/attempt-reserved",c)
    B.save(B.COUNTER+".ade-tmp",c);os.rename(B.COUNTER+".ade-tmp",B.COUNTER)


def timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00",time.gmtime())


def stage(value):
    if value not in ("running","extracting","succeeded","failed"):
        raise ValueError("closed stage")
    request()
    if value=="running":
        B.environment_preflight();verify();counter()
        if B.read(JOB+"/launch",128).decode("ascii")!=IDENTITY+"\n":
            raise ValueError("owned worker launch identity")
    B.save(JOB+"/state.tmp",{"stage":value,"updated_at":timestamp()})
    os.rename(JOB+"/state.tmp",JOB+"/state.json")


def status():
    request()
    state=json.loads(B.read(JOB+"/state.json",1024))
    names={"queued":"queued","running":"running","extracting":"running",
           "succeeded":"succeeded","failed":"failed"}
    if set(state)!=set(("stage","updated_at")) or state["stage"] not in names:
        raise ValueError("registered stage identity")
    public=names[state["stage"]]
    if public=="succeeded" and os.path.lexists(JOBS+"/active"):
        if B.read(JOBS+"/active",128).decode("ascii")==IDENTITY+"\n": public="running"
    print(json.dumps({"job_id":IDENTITY,"state":public,
        "profile":"reference-amplifier-finite-grid-v1","origin":"mcp",
        "updated_at":state["updated_at"]},sort_keys=True))


def lookup():
    authorization()
    reserved=False
    if os.path.lexists(JOB):
        request();reserved=os.path.lexists(JOB+"/attempt-reserved")
        if reserved:
            m=json.loads(B.read(JOB+"/attempt-reserved",1024))
            if not 77<=m["count"]<=82 or m["result_reserved_bytes"]!=8993636352+(m["count"]-76)*B.RESERVATION:
                raise ValueError("reservation lookup marker")
    print(json.dumps({"job_id":IDENTITY,"reserved":reserved},sort_keys=True))


def allow_start():
    verify_input();counter()
    if not os.path.lexists(JOB+"/attempt-reserved"): raise ValueError("admitted reservation required")
    state=json.loads(B.read(JOB+"/state.json",1024))["stage"]
    if not os.path.lexists(JOB+"/launch"):
        if state!="queued": raise ValueError("uncertain launch cannot replay")
        verify()
        if B.read(JOBS+"/active",128).decode("ascii")!=IDENTITY+"\n":
            raise ValueError("owned worker lease unavailable")
        B.write_new(JOB+"/launch",IDENTITY+"\n")
    elif B.read(JOB+"/launch",128).decode("ascii")!=IDENTITY+"\n":
        raise ValueError("launch identity")
    status()


def effective():
    # Prepared-input proof only while our worker runs. Full original/protected
    # checks are required before launch and after extraction, never weakened.
    r=verify_input()
    if not os.path.lexists(JOB+"/attempt-reserved") or not os.path.lexists(JOB+"/launch"):
        raise ValueError("effective input requires admitted launched child")
    if B.read(JOB+"/launch",128).decode("ascii")!=IDENTITY+"\n":
        raise ValueError("owned launch identity")
    print(json.dumps({"job_id":IDENTITY,"values":{"vbiasn":r["value_v"],
                     "vbiasp":"0.702","vdd":"1"}},sort_keys=True))


def finish():
    r=verify();current=counter()
    marker=json.loads(B.read(JOB+"/attempt-reserved",1024))
    before=json.loads(B.read(JOB+"/before.json",65536))["counter"]
    if (current!=marker or marker["count"]!=before["count"]+1
        or marker["result_reserved_bytes"]!=before["result_reserved_bytes"]+B.RESERVATION):
        raise ValueError("completion admission conservation")
    log=B.read(JOB+"/spectre.log").decode("latin-1")
    summaries=B.guard().SUMMARY.findall(log)
    warnings=[l for l in log.splitlines() if "WARNING" in l]
    if (len(summaries)!=1 or int(summaries[0][0]) or int(summaries[0][2])
        or len(warnings)!=int(summaries[0][1]) or len(warnings)>2
        or any("WARNING (CMI-2477):" not in l for l in warnings)):
        raise ValueError("simulation quality")
    ocean=B.read(JOB+"/ocean.log",2*1024**2).decode("latin-1")
    if any("*Error*" in l for l in ocean.splitlines() if not l.startswith("\\i ")):
        raise ValueError("scientific extraction error")
    path=JOB+("/frame.txt" if r["analysis"]=="dc" else "/scalars.txt")
    frame=B.read(path,65536);parsed=Q.parse(frame)
    if N.N.CAND.tree(JOB)["total_bytes"]>=B.RESERVATION-65536:
        raise ValueError("reservation bound")
    policy,d=authorization();source=Q.SOURCES[r["analysis"]]
    data={"schema_version":2,"definition_sha256":policy["definition_sha256"],
          "revision_id":"reference-amplifier-bias-grid-v1","job_id":IDENTITY,
          "plan_hash":r["plan_hash"],"analysis":r["analysis"],"requested_vbiasn_v":r["value_v"],
          "source_job_id":source[0],"source_input_sha256":source[1],"source_psf_sha256":source[2],
          "input_sha256":B.sha(B.read(JOB+"/netlist/input.scs")),
          "psf_sha256":N.N.CAND.tree(JOB+"/psf")["sha256"],"frame_sha256":B.sha(frame),
          "counter":marker,"protected_unchanged":True,"warnings":len(warnings),"notices":0}
    data.update(parsed)
    B.save(JOB+"/result.json",data)
    stage("succeeded")
    B.save(JOB+"/complete.json",Q.receipt())


def result():
    r=verify();counter()
    if json.loads(B.read(JOB+"/state.json",1024))["stage"]!="succeeded":
        raise ValueError("completed result unavailable")
    if json.loads(B.read(JOB+"/complete.json",65536))!=Q.receipt():
        raise ValueError("whole scientific result receipt drift")
    data=json.loads(B.read(JOB+"/result.json",65536))
    parsed=Q.parse(B.read(JOB+("/frame.txt" if r["analysis"]=="dc" else "/scalars.txt"),65536))
    if any(data[k]!=v for k,v in parsed.items()): raise ValueError("extraction drift")
    text=json.dumps(data,sort_keys=True)
    if len(text)>65536: raise ValueError("bounded result")
    print(text)


def postflight():
    authorization();jobs={}
    if os.path.lexists(JOBS+"/active"): raise ValueError("active amplifier worker")
    for name in os.listdir(JOBS):
        if name=="control.lock": continue
        configure(name);verify()
        if json.loads(B.read(JOB+"/complete.json",65536))!=Q.receipt():
            raise ValueError("incomplete amplifier evidence")
        p=subprocess.Popen(["du","-sk",JOB],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        out,err=p.communicate()
        if p.returncode or err or len(out)>1024: raise ValueError("bounded allocation")
        jobs[name]={"tree":N.N.CAND.tree(JOB),"allocated_bytes":int(out.split()[0])*1024}
    print(json.dumps({"protected":protected(),"counter":counter(),"jobs":jobs},sort_keys=True))


if __name__=="__main__":
    try:
        if sys.argv[1:]==["postflight"]: postflight()
        elif len(sys.argv)>=3:
            configure(sys.argv[2]);action=sys.argv[1]
            if action=="prepare" and len(sys.argv)==6: prepare(*sys.argv[3:6])
            elif action=="stage" and len(sys.argv)==4: stage(sys.argv[3])
            elif action in ("reserve","lookup","allow_start","effective","finish","status","result") and len(sys.argv)==3:
                globals()[action]()
            else: raise ValueError("closed amplifier action")
        else: raise ValueError("closed amplifier invocation")
    except (IOError,OSError,ValueError,KeyError,TypeError,IndexError,ZeroDivisionError):
        sys.stderr.write("bounded amplifier operation failed\n");sys.exit(69)
