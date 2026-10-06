"""Fixed operator discovery of preserved TRAN and installed step controls."""

from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path
from typing import Any

import ade_qual as io
import bandwidth_qualification as bw
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "eca78308-8af8-4810-b848-94c0ad936afe"
INPUT_SHA = "3efc38f937a7fb8e662eb71a82464ea8fff45e50d5d5fcd11d9a453b1c1ce975"
PSF_SHA = "6b3bde9514941767b2fd573649621322ba5b53333dbe9ce77978e0119c0a679a"
POLICY = ROOT / "docs/policy/ANALOG_SLEW_AUDIT_V2.json"
DELEGATION = ROOT / ".codex/slew01-audit-delegation-v2.private.json"
REMOTE_CODE = r"""
import imp,json,os,fcntl,subprocess
R="/home/buet/cds_work/.cadence_mcp"
lock=R+"/run.lock"
if os.path.realpath(lock)!=lock or not os.path.isfile(lock):raise ValueError("lock identity")
fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW)
fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
p=subprocess.Popen(["ps","-eo","comm"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
out,err=p.communicate()
if p.returncode or err or len(out)>65536:raise ValueError("worker unknown")
if any(x.strip() in ("spectre","ocean","virtuoso") for x in out.splitlines()):
 raise ValueError("active EDA")
for v in ("bandwidth-qual-v1","native-mcp-v3","native-mcp-v2","native-mcp-v1",
          "native-candidate-v2","native-ac-tran-v4","native-ac-tran-v3","ade-qual-v6","sim-mcp-v2","role-v1"):
 p=subprocess.Popen(["sha256sum","-c","manifest.sha256"],cwd=R+"/phase-campaign/"+v,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 out,err=p.communicate()
 if p.returncode or err:raise ValueError("immutable manifest")
m=imp.load_source("slew_audit_bw",R+"/phase-campaign/bandwidth-qual-v1/helper.py")
m.authorization()
before=m.checkpoint()
m.N.N.configure("eca78308-8af8-4810-b848-94c0ad936afe","tran")
result=m.capture(m.N.N.result)
if (result["input_sha256"]!=
 "3efc38f937a7fb8e662eb71a82464ea8fff45e50d5d5fcd11d9a453b1c1ce975" or
 result["psf_sha256"]!="6b3bde9514941767b2fd573649621322ba5b53333dbe9ce77978e0119c0a679a"):
 raise ValueError("pinned TRAN")
text=m.B.read(m.B.NETDIR+"/input.scs",16384).decode("latin-1")
helps={}
for topic in ("tran","vsource"):
 p=subprocess.Popen(["timeout","20","/home/buet/cadence/MMSIM121/tools/bin/spectre","-h",topic],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 out,err=p.communicate()
 if len(out)+len(err)>32768:raise ValueError("help bound")
 helps[topic]={"returncode":p.returncode,"stdout":out.decode("latin-1"),"stderr":err.decode("latin-1")}
if before!=m.checkpoint():raise ValueError("protected drift")
print(json.dumps({"input":text,"help":helps,"counter":m.counter(True),"protected_unchanged":True},sort_keys=True))
"""


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "phase": "ANALOG-SLEW-01",
        "operation": "inspect_preserved_tran_and_installed_controls",
        "parent_policy_sha256": parent,
        "source_job_id": SOURCE_ID,
        "source_input_sha256": INPUT_SHA,
        "source_psf_sha256": PSF_SHA,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "new_attempt_ceiling": 0,
        "new_reserved_bytes": 0,
        "delete_authority": False,
        "publication_authority": False,
    }


def inspect() -> dict[str, Any]:
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(campaign._load_authority()) or Path(__file__).is_symlink():
        raise ValueError("fixed discovery policy drift")
    digest = hashlib.sha256(campaign._canonical(policy)).hexdigest()
    if campaign._read_json(DELEGATION) != {
        "phase": "ANALOG-SLEW-01",
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "proceed",
    }:
        raise ValueError("discovery delegation missing")
    io.save_new(ROOT / ".codex/slew01-audit-intent-v2.private.json", {"policy_sha256": digest})
    before = bw.postflight()
    raw = io.decode_result(
        io.command((*io.SSH, "/usr/bin/python -c " + shlex.quote(REMOTE_CODE)), 75)
    )
    io.save_new(ROOT / ".codex/slew01-audit-raw-v2.private.json", raw)
    if hashlib.sha256(raw["input"].encode("latin-1")).hexdigest() != INPUT_SHA:
        raise ValueError("TRAN bytes drift")
    after = bw.postflight()
    for key in ("counter", "jobs", "native_jobs", "protected_unchanged", "phase_attempts"):
        if before[key] != after[key]:
            raise ValueError("protected discovery drift")
    io.save_new(
        ROOT / ".codex/slew01-audit-result-v2.private.json",
        {
            "state": "PASS",
            "before": before,
            "after": after,
            "policy_sha256": digest,
            "input_sha256": INPUT_SHA,
            "protected_unchanged": True,
        },
    )
    return {"state": "PASS", "counter": after["counter"], "new_attempts": 0}


if __name__ == "__main__":
    print(json.dumps(inspect(), sort_keys=True))
