"""Operator-only two-grid study, with immutable deployment and one-shot admissions."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

import ade_qual as io
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/bandwidth-qual-v1"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/bandwidth-qual-v1"
RUNTIME = "/home/buet/cds_work/.cadence_mcp/bandwidth-qual-v1"
POLICY = ROOT / "docs/policy/BANDWIDTH_QUAL_V1.json"
DELEGATION = ROOT / ".codex/bandwidth-qual-delegation-v1.private.json"
FILES = ("helper.py", "run.sh", "extract.ocn")
SOURCE_ID = "1afa2677-e264-4e80-a23d-dc722e34bb4a"


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": "BANDWIDTH-QUAL-02",
        "parent_policy_sha256": parent,
        "source_job_id": SOURCE_ID,
        "grids": [50, 100],
        "start_hz": 10,
        "stop_hz": 1000000,
        "new_attempt_ceiling": 2,
        "reservation_bytes_per_job": 128 * 1024**2,
        "correction_ceiling": 20,
        "delete_authority": False,
        "publication_authority": False,
        "files": {n: hashlib.sha256((LOCAL / n).read_bytes()).hexdigest() for n in FILES},
    }


def activation(digest: str) -> dict[str, str]:
    return {
        "phase": "BANDWIDTH-QUAL-02",
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "proceed",
    }


def authority() -> str:
    parent = campaign._load_authority()
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / n).is_symlink() for n in FILES):
        raise ValueError("bandwidth policy or deployment bytes changed")
    digest = hashlib.sha256(campaign._canonical(policy)).hexdigest()
    if campaign._read_json(DELEGATION) != activation(digest):
        raise ValueError("bandwidth phase delegation missing")
    return digest


def deploy() -> None:
    digest = authority()
    io.save_new(
        ROOT / ".codex/bandwidth-qual-deploy-v1.private.json",
        {"state": "reserved", "policy_sha256": digest},
    )
    stage = REMOTE + ".stage"
    io.command(
        (
            *io.SSH,
            "test ! -e "
            + REMOTE
            + " && test ! -L "
            + REMOTE
            + " && test ! -e "
            + stage
            + " && test ! -L "
            + stage
            + " && test ! -e "
            + RUNTIME
            + " && test ! -L "
            + RUNTIME,
        )
    )
    io.command((*io.SSH, "umask 077; mkdir -m 700 " + stage))
    for name in FILES:
        io.command((*io.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    io.command((*io.SCP, str(POLICY), "cadence-vm:" + stage + "/policy.json"))
    io.command((*io.SCP, str(DELEGATION), "cadence-vm:" + stage + "/activation.private.json"))
    hashes = expected_policy("")["files"] | {
        "policy.json": hashlib.sha256(POLICY.read_bytes()).hexdigest(),
        "activation.private.json": hashlib.sha256(DELEGATION.read_bytes()).hexdigest(),
    }
    manifest = ROOT / ".codex/bandwidth-qual-manifest-v1.private.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(v + "  " + n + "\n" for n, v in hashes.items()).encode("ascii"))
    io.command((*io.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    io.command(
        (
            *io.SSH,
            "cd "
            + stage
            + " && sha256sum -c manifest.sha256 >/dev/null"
            + " && bash -n run.sh"
            + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
            + " && chmod 700 helper.py run.sh && chmod 600 extract.ocn policy.json"
            + " activation.private.json manifest.sha256 && mv "
            + stage
            + " "
            + REMOTE,
        )
    )
    io.save_new(
        ROOT / ".codex/bandwidth-qual-deployed-v1.private.json",
        {"state": "verified", "policy_sha256": digest},
    )


def run(action: str) -> None:
    digest = authority()
    if action not in ("run50", "run100", "result"):
        raise ValueError("fixed bandwidth operation")
    journal = ROOT / (".codex/bandwidth-qual-" + action + "-intent-v1.private.json")
    io.save_new(journal, {"state": "reserved", "policy_sha256": digest, "action": action})
    command = REMOTE + "/run.sh " + ("run " + action[3:] if action.startswith("run") else action)
    done = subprocess.run((*io.SSH, command), capture_output=True, timeout=300, check=False)
    # Never retry an uncertain simulation; admission and all failures stay preserved.
    io.save_new(
        ROOT / (".codex/bandwidth-qual-" + action + "-transport-v1.private.json"),
        {
            "returncode": done.returncode,
            "stdout": done.stdout.decode("utf-8", "replace")[:65536],
            "stderr": done.stderr.decode("utf-8", "replace")[:65536],
        },
    )
    if done.returncode or len(done.stdout) + len(done.stderr) > 65536:
        raise ValueError(
            "fixed bandwidth operation failed; inspect preserved state before recovery"
        )
    if action == "result":
        io.save_new(
            ROOT / ".codex/bandwidth-qual-extraction-v1.private.json", io.decode_result(done.stdout)
        )


def postflight() -> dict[str, Any]:
    """Compose immutable historical fingerprints with the two new reservations.

    The sealed FS phase's original usage() intentionally knows only its own
    attempts and fails after a later phase advances the shared ledger. Retain
    that failure. Do not monkeypatch it or pretend that its full check passed.
    Reuse unchanged protected checks, request/status and complete job tree identity
    from the verified pre-study baseline; validate current conservation separately.
    """
    authority()
    code = r"""
import imp,json,os,subprocess
root="/home/buet/cds_work/.cadence_mcp"
for version in ("bandwidth-qual-v1", "fs-sizing-screen-02-v2", "native-mcp-v3",
                "native-mcp-v2", "native-mcp-v1", "native-candidate-v2",
                "native-ac-tran-v4", "native-ac-tran-v3", "ade-qual-v6", "sim-mcp-v2", "role-v1"):
    process=subprocess.Popen(["sha256sum", "-c", "manifest.sha256"],
        cwd=root+"/phase-campaign/"+version, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out,err=process.communicate()
    if process.returncode or err: raise ValueError("immutable manifest")
m=imp.load_source("bw_postflight",root+"/phase-campaign/bandwidth-qual-v1/helper.py")
m.authorization()
native=m.checkpoint()
f=imp.load_source("bw_preserved_sizing",root+"/phase-campaign/fs-sizing-screen-02-v2/helper.py")
f.configure("00000000-0000-4000-8000-000000000000", "dc", "FS")
policy=f.authority()
f.protection()
if os.path.lexists(f.JOBS+"/active"): raise ValueError("active sizing job")
rows=json.loads(f.read(f.VERSION+"/jobs.private.json",4096))["jobs"]
known=dict((r["job_id"],r) for r in rows)
intents=[]
summaries={}
for name in os.listdir(f.JOBS):
    if name in ("control.lock","review-24.private.json","review-22.private.json"): continue
    if name not in known: raise ValueError("unknown sizing identity")
    row=known[name]
    f.configure(name,row["analysis"],row["corner"])
    item=f.status()
    if item["state"] in ("running","unknown"): raise ValueError("active or uncertain sizing job")
    marker=f.JOB+"/attempt-reserved"
    if os.path.lexists(marker): intents.append(json.loads(f.read(marker,1024)))
    if item["state"]=="succeeded": item["result_sha256"]=f.B.sha(f.read(f.JOB+"/result.json",32768))
    item["tree"]=f.C.tree(f.RECORD)
    if item["tree"]["total_bytes"]>f.B.RESERVATION: raise ValueError("sizing byte bound")
    summaries[name]=item
baseline=policy["baseline_counter"]
intents.sort(key=lambda x:x["count"])
if len(intents)!=4: raise ValueError("historical attempt identity")
for index,intent in enumerate(intents):
    if intent!={"campaign_id":"AUTO-PHASE-01","count":baseline["count"]+index+1,
       "result_reserved_bytes":baseline["result_reserved_bytes"]+(index+1)*m.B.RESERVATION}:
        raise ValueError("historical reservation sequence")
current=m.counter(True)
for index,grid in enumerate(("50","100")):
    m.configure(grid)
    m.verify()
    if json.loads(m.B.read(m.JOB+"/complete.json",65536))!=m.receipt():
        raise ValueError("refinement completion drift")
    intent=json.loads(m.B.read(m.JOB+"/attempt-reserved",1024))
    if intent!={"campaign_id":"AUTO-PHASE-01","count":baseline["count"]+5+index,
       "result_reserved_bytes":baseline["result_reserved_bytes"]+(5+index)*m.B.RESERVATION}:
        raise ValueError("refinement reservation sequence")
if current!={"campaign_id":"AUTO-PHASE-01","count":64,"result_reserved_bytes":7383023616}:
    raise ValueError("whole study conservation")
disk=os.statvfs(root)
print(json.dumps({"protected_unchanged":True,"counter":current,"phase_attempts":4,
 "jobs":summaries,"native_jobs":native["native"]["jobs"],
 "free_bytes":disk.f_bavail*disk.f_frsize,"total_bytes":disk.f_blocks*disk.f_frsize,
 "spec_evaluation":"not_evaluated","verification":"preserved_fingerprints_plus_explicit_new_reservations"},sort_keys=True))
"""
    result = io.decode_result(io.command((*io.SSH, "/usr/bin/python -c " + shlex.quote(code)), 120))
    before = campaign._read_json(ROOT / ".codex/bw-predeploy-v1.private.json")["before"]
    if (
        result["protected_unchanged"] is not True
        or result["jobs"] != before["jobs"]
        or result["counter"]
        != {
            "campaign_id": "AUTO-PHASE-01",
            "count": before["counter"]["count"] + 2,
            "result_reserved_bytes": before["counter"]["result_reserved_bytes"] + 268435456,
        }
    ):
        raise ValueError("preserved sizing evidence or study accounting drift")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", "run50", "run100", "result"))
    selected = parser.parse_args().action
    deploy() if selected == "deploy" else run(selected)
    print(json.dumps({"state": "verified", "action": selected}))
