"""One-version, journaled installation of the bounded sweep budget guard."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/SWEEP_MCP_V1.json"
DELEGATION = ROOT / ".codex/sweep-mcp-v1-delegation.json"
JOURNAL = ROOT / ".codex/sweep-mcp-v1-deploy.json"
LOCAL = ROOT / "remote/phase-campaign/sweep-mcp-v1"
FILES = ("run.sh", "budget.py")
REMOTE = "/home/buet/cds_work/.cadence_mcp"
VERSION = REMOTE + "/phase-campaign/sweep-mcp-v1"
STAGE = VERSION + ".stage"
MARKERS = REMOTE + "/sweep-mcp-v1-reservations"
COUNTER = REMOTE + "/sim-mcp-v2-jobs/counter.json"
SSH = ("ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "cadence-vm")
SCP = ("scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes")


class DeployError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def run(argv: tuple[str, ...], timeout: int = 90) -> bytes:
    try:
        done = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeployError("BLOCKED_UNCERTAIN_STATE: transport failure") from exc
    if done.returncode or len(done.stdout) + len(done.stderr) > 65536:
        raise DeployError("BLOCKED_UNCERTAIN_STATE: remote command did not complete")
    return done.stdout


def ssh(command: str) -> bytes:
    return run((*SSH, command))


def save_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise DeployError("private deployment record missing or unsafe")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DeployError("private deployment record invalid")
    return value


def authority() -> tuple[dict, str]:
    parent = campaign._load_authority()
    policy = load(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "remote_version": "phase-campaign/sweep-mcp-v1",
        "profile_id": "fixture-rc-transient",
        "baseline_spectre_attempts": 11,
        "baseline_result_reserved_bytes": 269484032,
        "reservation_bytes_per_point": 134217728,
        "files": {name: sha((LOCAL / name).read_bytes()) for name in FILES},
    }
    if policy != expected:
        raise DeployError("DENY_OUT_OF_SCOPE: sweep policy or local helper changed")
    digest = sha(canonical(policy))
    if load(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise DeployError("DENY_OUT_OF_SCOPE: sweep delegation binding absent")
    return policy, digest


def manifest(policy: dict) -> bytes:
    return "".join(f"{policy['files'][name]}  {name}\n" for name in FILES).encode("ascii")


def verify(policy: dict) -> None:
    ssh("cd " + VERSION + " && sha256sum -c manifest.sha256 >/dev/null")
    counter = json.loads(ssh("cat " + COUNTER))
    if counter != {
        "campaign_id": "AUTO-PHASE-01",
        "count": policy["baseline_spectre_attempts"],
        "result_reserved_bytes": policy["baseline_result_reserved_bytes"],
    }:
        raise DeployError("BUDGET_UNCERTAIN: remote counter changed before sweep")
    ssh("test -d " + MARKERS + " && test ! -L " + MARKERS)


def deploy() -> None:
    policy, digest = authority()
    if JOURNAL.exists():
        raise DeployError("BLOCKED_UNCERTAIN_STATE: deployment already reserved")
    ssh("test ! -e " + STAGE + " && test ! -e " + VERSION + " && test ! -e " + MARKERS)
    counter = json.loads(ssh("cat " + COUNTER))
    if counter != {
        "campaign_id": "AUTO-PHASE-01",
        "count": 11,
        "result_reserved_bytes": 269484032,
    }:
        raise DeployError("BUDGET_UNCERTAIN: remote counter mismatch")
    ssh("test ! -e " + REMOTE + "/sim-mcp-v2-jobs/active")
    save_new(
        JOURNAL, {"state": "reserved", "policy_sha256": digest, "at": datetime.now(UTC).isoformat()}
    )
    ssh("umask 077; mkdir -m 700 " + STAGE + " " + MARKERS)
    for name in FILES:
        run((*SCP, str(LOCAL / name), "cadence-vm:" + STAGE + "/" + name))
    manifest_file = ROOT / ".codex/sweep-mcp-v1-manifest.sha256"
    if manifest_file.exists():
        raise DeployError("BLOCKED_UNCERTAIN_STATE: local manifest path already exists")
    manifest_file.write_bytes(manifest(policy))
    run((*SCP, str(manifest_file), "cadence-vm:" + STAGE + "/manifest.sha256"))
    ssh(
        "cd " + STAGE + " && sha256sum -c manifest.sha256 >/dev/null"
        " && bash -n run.sh"
        ' && /usr/bin/python -c \'compile(open("budget.py","rb").read(),"budget.py","exec")\''
        " && "
        "chmod 700 run.sh budget.py && chmod 600 manifest.sha256 && mv " + STAGE + " " + VERSION
    )
    verify(policy)
    temporary = JOURNAL.with_suffix(".tmp")
    save_new(
        temporary,
        {"state": "succeeded", "policy_sha256": digest, "at": datetime.now(UTC).isoformat()},
    )
    os.replace(temporary, JOURNAL)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["deploy"]:
            deploy()
        else:
            raise DeployError("usage: deploy_sweep_mcp_v1.py deploy")
    except (DeployError, OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
