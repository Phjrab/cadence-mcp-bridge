#!/usr/bin/env python
"""Fixed one-axis finite-grid qualification; no original netlister/state writes."""
from __future__ import with_statement
import imp
import json
import math
import os
import subprocess
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/bias-range-qual-v1"
RUNTIME = ROOT + "/bias-range-qual-v1"
L = imp.load_source("bias_preserved_offset", ROOT+"/phase-campaign/offset-qual-v1/helper.py")
B, N, W = L.B, L.N, L.W
SOURCES = {
    "dc": (L.SOURCE_ID, L.INPUT_SHA, L.PSF_SHA),
    "ac": ("1afa2677-e264-4e80-a23d-dc722e34bb4a",
           "53dd6c3bdee80808bfd67880f7e43be289fb275abf4f5486adf5b13f6aad275a", "5f13ca23a7d49aacaef51a59c0922e570da5dc2639baef5719956499ce5909fc")}
CASES = ("lowerdc", "lowerac", "upperdc", "upperac")
CASE, JOB, MODE, VALUE = None, None, None, None


def configure(case):
    global CASE, JOB, MODE, VALUE
    if case not in CASES: raise ValueError("fixed bias qualification case")
    CASE, JOB, MODE = case, RUNTIME+"/"+case, case[-2:]
    VALUE = "319m" if case.startswith("lower") else "321m"
    L.M.contained(JOB)


def source():
    identity, input_sha, psf_sha = SOURCES[MODE]
    N.N.configure(identity, MODE)
    r = W.capture(N.N.result)
    if (r["quality"] != "valid" or r["input_sha256"] != input_sha or r["psf_sha256"] != psf_sha):
        raise ValueError("pinned valid native predecessor")
    return r


def protected():
    p = L.protected()
    p["offset"] = N.N.CAND.tree(L.RUNTIME)
    return p


def authorization():
    p = json.loads(B.read(VERSION+"/policy.json",8192))
    d = B.sha(json.dumps(p,sort_keys=True,separators=(",",":")).encode("ascii"))
    if (p.get("phase") != "BIAS-RANGE-QUAL-01" or p.get("cases") != list(CASES)
            or p.get("values_v") != ["0.319","0.320","0.321"]
            or p.get("max_new_attempts") != 4 or p.get("max_new_reserved_bytes") != 4*B.RESERVATION
            or p.get("delete_authority") is not False or p.get("publication_authority") is not False
            or json.loads(B.read(VERSION+"/activation.private.json",4096)) != {
                "phase":"BIAS-RANGE-QUAL-01","policy_sha256":d,
                "user_delegation":"explicit-in-current-task","user_instruction":"continuous_four_phases"}):
        raise ValueError("finite grid delegation/policy")
    L.authorization()
    return d


def counter(submit=False):
    data = W.counter(True)
    n = 0
    for case in CASES:
        marker = RUNTIME+"/"+case+"/attempt-reserved"
        if os.path.lexists(marker):
            n += 1
            if json.loads(B.read(marker,1024)) != {"campaign_id":"AUTO-PHASE-01","count":72+n,
                    "result_reserved_bytes":8456765440+n*B.RESERVATION}:
                raise ValueError("grid admission identity")
        elif any(os.path.lexists(RUNTIME+"/"+later+"/attempt-reserved") for later in CASES[CASES.index(case)+1:]):
            raise ValueError("out of order grid admission")
    if data != {"campaign_id":"AUTO-PHASE-01","count":72+n,
                "result_reserved_bytes":8456765440+n*B.RESERVATION}:
        raise ValueError("grid accounting conservation")
    if submit: N.validate_counter(data,N.authorization())
    return data


def verify():
    digest = authorization()
    if json.loads(B.read(JOB+"/admission.json",4096)) != {
            "case":CASE,"source_job_id":SOURCES[MODE][0],"policy_sha256":digest}:
        raise ValueError("grid admission binding")
    before = json.loads(B.read(JOB+"/before.json",65536))
    if before["protected"] != protected(): raise ValueError("protected source/prior evidence drift")
    i = CASES.index(CASE)
    if before["counter"] != {"campaign_id":"AUTO-PHASE-01","count":72+i,
            "result_reserved_bytes":8456765440+i*B.RESERVATION}:
        raise ValueError("prior grid admission")
    text = B.read(JOB+"/netlist/input.scs")
    changed = ("VBIASN="+VALUE).encode("ascii")
    if text.count(changed) != 1 or B.sha(text.replace(changed,b"VBIASN=320m")) != SOURCES[MODE][1]:
        raise ValueError("effective parameter/reverse source identity")
    source()


def begin():
    digest = authorization()
    B.environment_preflight()
    data = counter(True)
    if data["count"] != 72+CASES.index(CASE) or os.path.lexists(JOB):
        raise ValueError("grid replay/order")
    before = {"protected":protected(),"counter":data}
    source()
    text = B.read(B.NETDIR+"/input.scs")
    if B.sha(text) != SOURCES[MODE][1] or text.count(b"VBIASN=320m") != 1:
        raise ValueError("fixed original input")
    text = text.replace(b"VBIASN=320m",("VBIASN="+VALUE).encode("ascii"))
    L.M.contained(RUNTIME)
    if not os.path.exists(RUNTIME): os.mkdir(RUNTIME,0o700)
    os.mkdir(JOB,0o700); os.mkdir(JOB+"/netlist",0o700); os.mkdir(JOB+"/psf",0o700)
    B.save(JOB+"/before.json",before)
    B.save(JOB+"/admission.json",{"case":CASE,"source_job_id":SOURCES[MODE][0],"policy_sha256":digest})
    B.write_new(JOB+"/netlist/input.scs",text)
    template = B.read(VERSION+"/extract-"+MODE+".ocn").decode("ascii")
    B.write_new(JOB+"/extract.ocn",template.replace("@JOB@",JOB))
    verify()


def reserve():
    B.environment_preflight(); verify()
    data = counter(True)
    if os.path.lexists(JOB+"/attempt-reserved") or data["count"] != 72+CASES.index(CASE):
        raise ValueError("grid reservation replay")
    data["count"] += 1; data["result_reserved_bytes"] += B.RESERVATION
    B.save(JOB+"/attempt-reserved",data)
    B.save(B.COUNTER+".ade-tmp",data); os.rename(B.COUNTER+".ade-tmp",B.COUNTER)


def finite(value):
    n=float(value)
    if math.isnan(n) or math.isinf(n): raise ValueError("finite bounded extraction")
    return n


def parse_dc(frame):
    lines=frame.decode("ascii").splitlines()
    nodes=("Vop","Vom","Vp","Vm","VDD","Vbiasn","Vbiasp")
    if len(lines)!=15 or lines[0]!="BEGIN" or lines[-1]!="END": raise ValueError("fixed DC frame")
    scalars={}
    for name,line in zip(nodes,lines[1:8]):
        parts=line.split("|")
        if len(parts)!=3 or parts[:2]!=["NODE",name]: raise ValueError("registered DC node")
        scalars[name]=finite(parts[2])
    expected={"Vp":0.5,"Vm":0.5,"VDD":1.0,"Vbiasn":float(VALUE[:-1])*0.001,"Vbiasp":0.702}
    if any(abs(scalars[n]-v)>1e-9 for n,v in expected.items()): raise ValueError("effective DC grid input")
    sources=[]
    specs=(("vdd","VDD",1.0,"supply"),("vss","VSS",0.0,"supply"),
           ("bias-n","Vbiasn",expected["Vbiasn"],"bias"),("bias-p","Vbiasp",0.702,"bias"),
           ("input-p","Vp",0.5,"stimulus"),("input-m","Vm",0.5,"stimulus"))
    for line,(alias,node,v,role) in zip(lines[8:14],specs):
        parts=line.split("|")
        if len(parts)!=4 or parts[:2]!=["SOURCE",alias]: raise ValueError("complete source inventory")
        voltage,current=finite(parts[2]),finite(parts[3])
        if abs(voltage-v)>1e-9: raise ValueError("signed source voltage")
        sources.append({"source_id":alias,"role":role,"voltage_v":voltage,"current_a":current})
    return {"scalars":scalars,"sources":sources}


def parse(frame):
    return parse_dc(frame) if MODE=="dc" else {"spectrum":B.guard().ac_result(frame.decode("ascii"))}


def receipt():
    N.N.CAND.tree(JOB)
    rows=[]
    for current,dirs,files in os.walk(JOB):
        for name in dirs: rows.append(["d",os.path.relpath(os.path.join(current,name),JOB)])
        for name in files:
            path=os.path.join(current,name)
            if path!=JOB+"/complete.json": rows.append(["f",os.path.relpath(path,JOB),B.sha(B.read(path,B.RESERVATION))])
    return sorted(rows)


def finish():
    verify(); current=counter()
    marker=json.loads(B.read(JOB+"/attempt-reserved",1024))
    if current!=marker: raise ValueError("grid completion admission")
    log=B.read(JOB+"/spectre.log").decode("latin-1")
    summary=B.guard().SUMMARY.findall(log)
    warnings=[l for l in log.splitlines() if "WARNING" in l]
    if (len(summary)!=1 or int(summary[0][0]) or len(warnings)!=int(summary[0][1])
            or len(warnings)>2 or any("WARNING (CMI-2477):" not in l for l in warnings)
            or int(summary[0][2])!=0): raise ValueError("grid simulation quality")
    ocean=B.read(JOB+"/ocean.log",2*1024**2).decode("latin-1")
    if any("*Error*" in l for l in ocean.splitlines() if not l.startswith("\\i ")): raise ValueError("grid extraction error")
    frame=B.read(JOB+("/frame.txt" if MODE=="dc" else "/scalars.txt"),65536)
    if N.N.CAND.tree(JOB)["total_bytes"]>=B.RESERVATION-65536: raise ValueError("grid reservation bound")
    B.save(JOB+"/result.json",dict({"schema_version":1,"case":CASE,"analysis":MODE,
        "requested_vbiasn_v":str(float(VALUE[:-1])*0.001),"source_job_id":SOURCES[MODE][0],
        "source_input_sha256":SOURCES[MODE][1],"source_psf_sha256":SOURCES[MODE][2],
        "input_sha256":B.sha(B.read(JOB+"/netlist/input.scs")),"psf_sha256":N.N.CAND.tree(JOB+"/psf")["sha256"],
        "frame_sha256":B.sha(frame),"counter":marker,"warnings":len(warnings),"notices":0,
        "protected_unchanged":True},**parse(frame)))
    B.save(JOB+"/complete.json",receipt())


def postflight():
    authorization(); jobs={}
    for case in CASES:
        configure(case)
        if os.path.lexists(JOB):
            verify()
            if json.loads(B.read(JOB+"/complete.json",65536))!=receipt(): raise ValueError("incomplete grid evidence")
            p=subprocess.Popen(["du","-sk",JOB],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            out,err=p.communicate()
            if p.returncode or err or len(out)>1024: raise ValueError("bounded allocation")
            jobs[case]={"tree":N.N.CAND.tree(JOB),"allocated_bytes":int(out.split()[0])*1024}
    print(json.dumps({"protected":protected(),"counter":counter(),"jobs":jobs},sort_keys=True))


def result():
    authorization(); counter(); rows=[]
    for case in CASES:
        configure(case); verify()
        if json.loads(B.read(JOB+"/complete.json",65536))!=receipt(): raise ValueError("whole result receipt drift")
        r=json.loads(B.read(JOB+"/result.json",65536))
        parsed=parse(B.read(JOB+("/frame.txt" if MODE=="dc" else "/scalars.txt"),65536))
        if any(r[k]!=v for k,v in parsed.items()): raise ValueError("extraction drift")
        rows.append(r)
    text=json.dumps({"schema_version":1,"cases":rows},sort_keys=True)
    if len(text)>65536: raise ValueError("bounded grid result")
    print(text)


if __name__=="__main__":
    try:
        if len(sys.argv)==3 and sys.argv[1] in ("begin","reserve","finish"):
            configure(sys.argv[2]); globals()[sys.argv[1]]()
        elif sys.argv[1:]==["result"]: result()
        elif sys.argv[1:]==["postflight"]: postflight()
        else: raise ValueError("fixed grid action")
    except (IOError,OSError,ValueError,KeyError,TypeError,IndexError,ZeroDivisionError):
        sys.stderr.write("bounded grid qualification failed\n"); sys.exit(69)
