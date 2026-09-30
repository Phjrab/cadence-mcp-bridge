"""One-time, journaled deployment of the fixed SIM-MCP-01 VM helper."""

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
POLICY = ROOT / "docs/policy/SIM_MCP_V2.json"
DELEGATION = ROOT / ".codex/sim-mcp-v2-delegation.json"
REMOTE_ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = REMOTE_ROOT + "/phase-campaign/sim-mcp-v2"
STAGE = VERSION + ".stage"
JOBS = REMOTE_ROOT + "/sim-mcp-v2-jobs"
FILES = ("run.sh", "diagnostic.py", "extract-dc.ocn", "extract-ac.ocn")
LOCAL = ROOT / "remote/phase-campaign/sim-mcp-v2"
SSH = ("ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "cadence-vm")
SCP = ("scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes")
PREFLIGHT_ID = "00000000-0000-4000-8000-000000000000"


class DeploymentError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def command(argv: tuple[str, ...], timeout: int = 90) -> bytes:
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeploymentError("BLOCKED_UNCERTAIN_STATE: transport outcome unknown") from exc
    if len(result.stdout) + len(result.stderr) > 65536:
        raise DeploymentError("BLOCKED_UNCERTAIN_STATE: remote response exceeded limit")
    if result.returncode:
        raise DeploymentError(f"BLOCKED_UNCERTAIN_STATE: transport exit {result.returncode}")
    return result.stdout


def ssh(fixed_command: str, timeout: int = 90) -> bytes:
    return command((*SSH, fixed_command), timeout)


def authority() -> tuple[dict, str, Path]:
    parent = campaign._load_authority()
    state_root = campaign._state_root()
    policy = campaign._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "remote_version": "phase-campaign/sim-mcp-v2",
        "revision_id": "wp14-copied-netlist-v1",
        "operating_point_id": "candidate-320-702mv-v1",
        "analyses": ["dc", "ac"],
        "baseline_spectre_attempts": 9,
        "baseline_result_reserved_bytes": 1048576,
        "source_sha256": "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714",
        "copy_sha256": "a02d83653f26f2e34f1f4e402531e66e9d34b5ecc41d29ed6d38a70ed8c6983f",
        "netlist_sha256": "6189aa9d647671c05a9f03d815530697560c00b661cad95c87f7f415d482192a",
        "files": {name: sha((LOCAL / name).read_bytes()) for name in FILES},
    }
    if policy != expected:
        raise DeploymentError("DENY_OUT_OF_SCOPE: SIM-MCP policy or local files changed")
    digest = sha(canonical(policy))
    if campaign._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise DeploymentError("DENY_OUT_OF_SCOPE: phase delegation binding absent")
    for name in FILES:
        path = LOCAL / name
        if (
            path.is_symlink()
            or not path.is_file()
            or sha(path.read_bytes()) != policy["files"][name]
        ):
            raise DeploymentError("DENY_OUT_OF_SCOPE: deployment bytes changed")
    counter = campaign._read_json(state_root / "phasee-copied-dc-v1-spectre-attempts.json")
    if counter != {"campaign_id": "AUTO-PHASE-01", "count": 9}:
        raise DeploymentError("BUDGET_UNCERTAIN: prior Spectre count changed")
    return policy, digest, state_root


def reserve(path: Path, digest: str) -> None:
    try:
        with path.open("x", encoding="ascii") as stream:
            json.dump(
                {"state": "reserved", "policy_sha256": digest, "at": datetime.now(UTC).isoformat()},
                stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise DeploymentError("BLOCKED_UNCERTAIN_STATE: deployment already reserved") from exc


def verify_remote(policy: dict) -> None:
    ssh("cd " + VERSION + " && sha256sum -c manifest.sha256 >/dev/null")
    raw = ssh("cat " + JOBS + "/counter.json")
    if json.loads(raw) != {
        "campaign_id": "AUTO-PHASE-01",
        "count": policy["baseline_spectre_attempts"],
        "result_reserved_bytes": policy["baseline_result_reserved_bytes"],
    }:
        raise DeploymentError("BLOCKED_UNCERTAIN_STATE: remote counter mismatch")
    ssh("test -d " + JOBS + " && test ! -L " + JOBS + " && test ! -e " + JOBS + "/active")


def deploy() -> dict:
    policy, digest, state_root = authority()
    record = state_root / "sim-mcp-v2-deploy.json"
    ssh("test ! -e " + STAGE + " && test ! -e " + VERSION + " && test ! -e " + JOBS)
    reserve(record, digest)
    ssh("mkdir -m 700 " + STAGE)
    for name in FILES:
        command((*SCP, str(LOCAL / name), "cadence-vm:" + STAGE + "/" + name))
    manifest = "".join(policy["files"][name] + "  " + name + "\n" for name in FILES)
    manifest_path = ROOT / ".codex/sim-mcp-v2-manifest.sha256"
    with manifest_path.open("xb") as stream:
        stream.write(manifest.encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    command((*SCP, str(manifest_path), "cadence-vm:" + STAGE + "/manifest.sha256"))
    ssh(
        "cd " + STAGE + " && sha256sum -c manifest.sha256 >/dev/null"
        " && /usr/bin/python -m py_compile diagnostic.py"
        " && /usr/bin/python diagnostic.py preflight " + PREFLIGHT_ID + " dc >/dev/null",
        120,
    )
    ssh(
        "chmod 700 "
        + STAGE
        + "/run.sh && chmod 600 "
        + STAGE
        + "/diagnostic.py "
        + STAGE
        + "/extract-dc.ocn "
        + STAGE
        + "/extract-ac.ocn "
        + STAGE
        + "/manifest.sha256 && mv "
        + STAGE
        + " "
        + VERSION
        + " && mkdir -m 700 "
        + JOBS
    )
    counter_path = ROOT / ".codex/sim-mcp-v2-counter.json"
    with counter_path.open("xb") as stream:
        stream.write(
            canonical(
                {"campaign_id": "AUTO-PHASE-01", "count": 9, "result_reserved_bytes": 1048576}
            )
        )
        stream.flush()
        os.fsync(stream.fileno())
    command((*SCP, str(counter_path), "cadence-vm:" + JOBS + "/counter.json"))
    ssh("chmod 600 " + JOBS + "/counter.json")
    verify_remote(policy)
    outcome = {
        "state": "succeeded",
        "policy_sha256": digest,
        "manifest_sha256": sha(manifest.encode("ascii")),
        "at": datetime.now(UTC).isoformat(),
    }
    campaign._replace_record(record, outcome)
    return outcome


def recover() -> dict:
    policy, digest, state_root = authority()
    record = state_root / "sim-mcp-v2-deploy.json"
    current = campaign._read_json(record)
    if current.get("policy_sha256") != digest or current.get("state") not in (
        "reserved",
        "succeeded",
    ):
        raise DeploymentError("BLOCKED_UNCERTAIN_STATE: deployment journal mismatch")
    verify_remote(policy)
    if current["state"] == "succeeded":
        return current
    outcome = {
        "state": "succeeded",
        "policy_sha256": digest,
        "manifest_sha256": sha((ROOT / ".codex/sim-mcp-v2-manifest.sha256").read_bytes()),
        "at": datetime.now(UTC).isoformat(),
        "recovered": True,
    }
    campaign._replace_record(record, outcome)
    return outcome


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("deploy", "recover"):
        print("usage: deploy_sim_mcp_v2.py deploy|recover", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else recover()
    except (campaign.CampaignError, DeploymentError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
