"""Fixed, journaled WP-14 role discovery under the existing phase campaign.

This operator entry point adds one versioned deployment and one read. It preserves
the original campaign clock and delegation; it does not reset legacy claims.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import phase_campaign as parent

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_B_ROLE_V1.json"
DELEGATION = ROOT / ".codex/phase-b-role-delegation.json"
REMOTE_ROOT = "/home/buet/cds_work/.cadence_mcp"
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/role-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
HELPER = REMOTE_ROOT + "/py26/ade_profile_introspection.py"
SSH = ("ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "cadence-vm")
SCP = ("scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes")
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/role-v1/run.sh",
    "wp14_role_discovery.py": ROOT / "remote/py26/wp14_role_discovery.py",
    "wp14-role-discovery.il": ROOT / "remote/discovery/wp14-role-discovery.il",
}
OPERATIONS = {"deploy": "phaseb-role-deploy-v1", "read": "phaseb-role-read-v1"}
MAX_OUTPUT = 65536


class PhaseBError(RuntimeError):
    pass


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _command(
    argv: tuple[str, ...] | list[str], *, timeout: int = 60
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(argv, capture_output=True, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: transport outcome unknown") from exc
    if len(result.stdout) + len(result.stderr) > MAX_OUTPUT:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: oversized response")
    return result


def _ssh(command: str, *, timeout: int = 60) -> bytes:
    result = _command((*SSH, command), timeout=timeout)
    if result.returncode:
        raise PhaseBError(
            f"BLOCKED_UNCERTAIN_STATE: fixed SSH operation failed ({result.returncode})"
        )
    return result.stdout


def _authority() -> tuple[dict[str, Any], str, Path]:
    parent_digest = parent._load_authority()
    head = _command(("git", "-C", str(ROOT), "rev-parse", "HEAD"))
    main = _command(("git", "-C", str(ROOT), "rev-parse", "origin/main"))
    dirty = _command(("git", "-C", str(ROOT), "status", "--porcelain"))
    if (
        head.returncode
        or main.returncode
        or dirty.returncode
        or head.stdout != main.stdout
        or dirty.stdout
    ):
        raise PhaseBError("DENY_OUT_OF_SCOPE: reviewed main checkout required")
    state_root = parent._state_root()
    started = parent._read_json(state_root / "started-at.json")
    if started.get("policy_sha256") != parent_digest:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: original campaign clock changed")
    try:
        start = datetime.fromisoformat(started["at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: invalid campaign clock") from exc
    now = datetime.now(UTC)
    if start > now:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: original campaign clock is in the future")

    policy = parent._read_json(POLICY)
    if policy != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/role-v1",
        "source_fingerprint_sha256": (
            "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
        ),
        "installed_preflight_helper_sha256": (
            "aade615a42d9b522bf43ed3e509b703c61ea144f4bd31988b21e88cd50ea68e3"
        ),
        "files": {
            "run.sh": "3c78e73e4d9f0cdefa8f44e0c818bf96015a66528c11f2d401b7ba2f80040878",
            "wp14_role_discovery.py": (
                "dc14b6fec53a27d401e222551502d7e894f5e35a9b29b53d802e890998ecd48e"
            ),
            "wp14-role-discovery.il": (
                "9dcdef026bc3191acd0c9256c32a8cc0875778e65d21479e80067de70daa8586"
            ),
        },
    }:
        raise PhaseBError("DENY_OUT_OF_SCOPE: phase B policy changed")
    digest = _sha(_canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise PhaseBError("DENY_OUT_OF_SCOPE: phase B delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise PhaseBError("DENY_OUT_OF_SCOPE: local deployment bytes changed")
    return policy, digest, state_root


def _reserve(state_root: Path, operation: str, digest: str) -> Path:
    path = state_root / (OPERATIONS[operation] + ".json")
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(
                {"state": "reserved", "policy_sha256": digest, "at": datetime.now(UTC).isoformat()},
                stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: operation already reserved") from exc
    return path


def _finish(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    parent._replace_record(path, payload)
    return payload


def _manifest_bytes(policy: dict[str, Any]) -> bytes:
    lines = [policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES]
    return "".join(lines).encode("ascii")


def _verify_version_files(directory: str, policy: dict[str, Any]) -> None:
    names = _ssh("ls -A " + directory).decode("ascii", errors="strict").splitlines()
    if sorted(names) != sorted([*LOCAL_FILES, "manifest.sha256"]):
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: staging file set changed")
    checks = " && ".join(
        "test -f " + directory + "/" + name + " && test ! -L " + directory + "/" + name
        for name in LOCAL_FILES
    )
    _ssh(
        "test -d "
        + directory
        + " && test ! -L "
        + directory
        + " && test -f "
        + directory
        + "/manifest.sha256"
        + " && test ! -L "
        + directory
        + "/manifest.sha256 && "
        + checks
    )
    manifest_identity = _ssh("stat -c %U:%G:%h " + directory + "/manifest.sha256").strip()
    if manifest_identity != b"buet:buet:1":
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: staging manifest identity changed")
    hashes = _ssh("cd " + directory + " && sha256sum " + " ".join(LOCAL_FILES))
    lines = hashes.decode("ascii", errors="strict").splitlines()
    expected = [policy["files"][name] + "  " + name for name in LOCAL_FILES]
    if lines != expected:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: staging bytes changed")


def _remote_preflight(policy: dict[str, Any]) -> None:
    identity = (
        _ssh(
            "set -e; id -un; hostname; test ! -L " + REMOTE_ROOT + "; "
            "cd " + REMOTE_ROOT + " && pwd -P; stat -c %U:%G " + REMOTE_ROOT + "; "
            "df -Pk " + REMOTE_ROOT + " | tail -1; "
            "sha256sum " + HELPER + "; "
            "ps -eo comm | grep -i virtuoso || true"
        )
        .decode("utf-8", errors="strict")
        .splitlines()
    )
    if len(identity) != 6 or identity[:4] != ["buet", "cadence", REMOTE_ROOT, "buet:buet"]:
        raise PhaseBError("BLOCKED_ENVIRONMENT: remote identity or active Virtuoso changed")
    columns = identity[4].split()
    if len(columns) < 4 or columns[0] != "/dev/sda1":
        raise PhaseBError("BLOCKED_ENVIRONMENT: disk observation unavailable")
    try:
        total, available = int(columns[1]), int(columns[3])
    except ValueError as exc:
        raise PhaseBError("BLOCKED_ENVIRONMENT: invalid disk observation") from exc
    if available < max(2 * 1024 * 1024, (total + 9) // 10):
        raise PhaseBError("BLOCKED_ENVIRONMENT: managed disk below free-space floor")
    helper_hash = identity[5].split()[0]
    if helper_hash != policy["installed_preflight_helper_sha256"]:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: installed preflight code changed")
    before = _ssh("/usr/bin/python " + HELPER + " preflight", timeout=90)
    try:
        snapshot = json.loads(before)
    except json.JSONDecodeError as exc:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: invalid fixed preflight") from exc
    if snapshot.get("locks") != {"source": 0, "state": 0}:
        raise PhaseBError("BLOCKED_ENVIRONMENT: source or ADE state lock")
    if snapshot.get("source_tree", {}).get("sha256") != policy["source_fingerprint_sha256"]:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: source revision changed")


def deploy() -> dict[str, Any]:
    policy, digest, state_root = _authority()
    record = _reserve(state_root, "deploy", digest)
    _remote_preflight(policy)
    _ssh(
        "test ! -e "
        + REMOTE_STAGE
        + " && test ! -e "
        + REMOTE_VERSION
        + " && mkdir -p -m 700 "
        + REMOTE_ROOT
        + "/phase-campaign"
        + " && test ! -L "
        + REMOTE_ROOT
        + "/phase-campaign"
        + " && mkdir -m 700 "
        + REMOTE_STAGE
    )
    for name, source in LOCAL_FILES.items():
        result = _command(
            (*SCP, str(source), "cadence-vm:" + REMOTE_STAGE + "/" + name), timeout=90
        )
        if result.returncode:
            raise PhaseBError("BLOCKED_UNCERTAIN_STATE: fixed staging copy failed")
    manifest = _manifest_bytes(policy)
    manifest_path = state_root / "phaseb-role-manifest.sha256"
    with manifest_path.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    result = _command((*SCP, str(manifest_path), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"))
    if result.returncode:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: manifest copy failed")
    _ssh(
        "cd "
        + REMOTE_STAGE
        + " && sha256sum -c manifest.sha256"
        + " && chmod 700 run.sh"
        + " && chmod 600 wp14_role_discovery.py wp14-role-discovery.il manifest.sha256"
        + " && mv "
        + REMOTE_STAGE
        + " "
        + REMOTE_VERSION
        + " && cd "
        + REMOTE_VERSION
        + " && sha256sum -c manifest.sha256"
    )
    return _finish(
        record,
        {
            "state": "succeeded",
            "operation": OPERATIONS["deploy"],
            "policy_sha256": digest,
            "manifest_sha256": _sha(manifest),
            "at": datetime.now(UTC).isoformat(),
        },
    )


def recover_deploy() -> dict[str, Any]:
    """Resolve only the already reserved deployment from exact staged bytes."""
    policy, digest, state_root = _authority()
    record = state_root / (OPERATIONS["deploy"] + ".json")
    prior = parent._read_json(record)
    if prior.get("state") != "reserved" or prior.get("policy_sha256") != digest:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: no matching reserved deployment")
    _remote_preflight(policy)
    locations = (
        _ssh(
            "set -e; test ! -L " + REMOTE_ROOT + "/phase-campaign; "
            "if test -d " + REMOTE_STAGE + "; then echo stage; fi; "
            "if test -d " + REMOTE_VERSION + "; then echo final; fi"
        )
        .decode("ascii", errors="strict")
        .splitlines()
    )
    if locations not in (["stage"], ["final"]):
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: deployment location is ambiguous")
    if locations == ["stage"]:
        _verify_version_files(REMOTE_STAGE, policy)
        manifest = _manifest_bytes(policy)
        path = state_root / "phaseb-role-manifest-lf.sha256"
        if path.exists():
            if path.read_bytes() != manifest:
                raise PhaseBError("BLOCKED_UNCERTAIN_STATE: recovery manifest changed")
        else:
            with path.open("xb") as stream:
                stream.write(manifest)
                stream.flush()
                os.fsync(stream.fileno())
        result = _command((*SCP, str(path), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"))
        if result.returncode:
            raise PhaseBError("BLOCKED_UNCERTAIN_STATE: recovery manifest copy failed")
        _ssh(
            "cd "
            + REMOTE_STAGE
            + " && sha256sum -c manifest.sha256"
            + " && chmod 700 run.sh"
            + " && chmod 600 wp14_role_discovery.py wp14-role-discovery.il manifest.sha256"
            + " && mv "
            + REMOTE_STAGE
            + " "
            + REMOTE_VERSION
            + " && cd "
            + REMOTE_VERSION
            + " && sha256sum -c manifest.sha256"
        )
    _verify_version_files(REMOTE_VERSION, policy)
    _ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    return _finish(
        record,
        {
            "state": "succeeded",
            "operation": OPERATIONS["deploy"],
            "policy_sha256": digest,
            "manifest_sha256": _sha(_manifest_bytes(policy)),
            "reconciled_from_reserved": True,
            "at": datetime.now(UTC).isoformat(),
        },
    )


def read() -> dict[str, Any]:
    policy, digest, state_root = _authority()
    deployed = parent._read_json(state_root / (OPERATIONS["deploy"] + ".json"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: fixed deployment not verified")
    record = _reserve(state_root, "read", digest)
    _remote_preflight(policy)
    _ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    raw = _ssh(REMOTE_VERSION + "/run.sh", timeout=90)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: invalid role discovery response") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("plan_id") != "WP14_FIXED_NAMES_ONLY_ROLE_DISCOVERY_PLAN"
    ):
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: role discovery contract mismatch")
    invariants = payload.get("invariants", {})
    private_keys = (
        "names_included",
        "paths_included",
        "raw_content_included",
        "simulation_run",
        "values_included",
    )
    if any(invariants.get(key) is not False for key in private_keys):
        raise PhaseBError("BLOCKED_UNCERTAIN_STATE: protected output contract mismatch")
    output = state_root / (OPERATIONS["read"] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    summary = {
        "state": "succeeded",
        "operation": OPERATIONS["read"],
        "policy_sha256": digest,
        "result_status": payload.get("status"),
        "raw_sha256": _sha(raw),
        "raw_local_file": str(output),
        "at": datetime.now(UTC).isoformat(),
    }
    return _finish(record, summary)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in (*OPERATIONS, "recover-deploy"):
        print("usage: phase_b_role_campaign.py deploy|recover-deploy|read", file=sys.stderr)
        return 2
    try:
        if sys.argv[1] == "deploy":
            result = deploy()
        elif sys.argv[1] == "recover-deploy":
            result = recover_deploy()
        else:
            result = read()
    except (PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
