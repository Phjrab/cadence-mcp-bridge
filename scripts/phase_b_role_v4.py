"""Separate, one-shot names-only role parse after observed v3 OA lifecycle.

The original campaign clock and prior v1/v2/v3 records remain untouched.
Only reviewed bytes enter a fresh version directory and runtime.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import phase_b_role_campaign as v1
import phase_b_role_v2 as v2
import phase_b_role_v3 as v3
import phase_campaign as parent

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_B_ROLE_V4.json"
DELEGATION = ROOT / ".codex/phase-b-role-v4-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/role-v4"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-role-parse-v4"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/role-v4/run.sh",
    "role_v4_helper.py": ROOT / "remote/phase-campaign/role-v4/role_v4_helper.py",
}
OPERATIONS = {"deploy": "phaseb-role-v4-deploy", "read": "phaseb-role-v4-read"}


class RoleV4Error(RuntimeError):
    pass


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = v3._authority()
    if old_digest != "dbc4ec32784966aef3e62a8698c5ebd73ace27556f12973a89015d28e214709d":
        raise RoleV4Error("DENY_OUT_OF_SCOPE: reviewed v3 policy changed")
    deployed = parent._read_json(state_root / "phaseb-role-v3-deploy.json")
    prior_read = parent._read_json(state_root / "phaseb-role-v3-read.json")
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != old_digest:
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v3 deployment not verified")
    if (
        prior_read.get("state") != "succeeded"
        or prior_read.get("policy_sha256") != old_digest
        or prior_read.get("result_status") != "observed"
    ):
        raise RoleV4Error("DENY_OUT_OF_SCOPE: observed v3 read not verified")
    old_result = state_root / "phaseb-role-v3-read.output"
    if (
        old_result.is_symlink()
        or not old_result.is_file()
        or _sha(old_result.read_bytes()) != prior_read.get("raw_sha256")
    ):
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v3 result bytes changed")
    old_payload = json.loads(old_result.read_bytes())
    if not isinstance(old_payload, dict) or any(
        old_payload.get(key) is not True
        for key in (
            "completion_marker_seen",
            "topology_marker_seen",
            "protected_fingerprints_unchanged",
            "locks_unchanged",
        )
    ):
        raise RoleV4Error("DENY_OUT_OF_SCOPE: v3 lifecycle evidence changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/role-v4",
        "source_fingerprint_sha256": base_policy["source_fingerprint_sha256"],
        "installed_preflight_helper_sha256": base_policy["installed_preflight_helper_sha256"],
        "v3_files": old_policy["files"],
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise RoleV4Error("DENY_OUT_OF_SCOPE: phase B v4 policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise RoleV4Error("DENY_OUT_OF_SCOPE: v4 delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise RoleV4Error("DENY_OUT_OF_SCOPE: local v4 bytes changed")
    return policy, digest, state_root, base_policy


def _reserve(state_root: Path, operation: str, digest: str) -> Path:
    path = _record_path(state_root, operation)
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(
                {"state": "reserved", "policy_sha256": digest, "at": datetime.now(UTC).isoformat()},
                stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v4 operation already reserved") from exc
    return path


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def _preflight(old_policy: dict[str, Any]) -> None:
    v1._remote_preflight(old_policy)
    v1._ssh("test ! -L " + REMOTE_ROOT + "/phase-campaign")
    v1._ssh("cd " + v1.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + v2.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + v3.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    locations = (
        v1._ssh(
            "set -e; test ! -L " + RUNTIME + "; if test -e " + RUNTIME + "; then echo exists; fi"
        )
        .decode("ascii")
        .splitlines()
    )
    if locations:
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v4 runtime already exists")


def _finish(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    parent._replace_record(path, payload)
    return payload


def deploy() -> dict[str, Any]:
    policy, digest, state_root, old_policy = _authority()
    _preflight(old_policy)
    record = _reserve(state_root, "deploy", digest)
    v1._ssh(
        "test ! -e "
        + REMOTE_STAGE
        + " && test ! -e "
        + REMOTE_VERSION
        + " && mkdir -m 700 "
        + REMOTE_STAGE
    )
    for name, source in LOCAL_FILES.items():
        result = v1._command(
            (*v1.SCP, str(source), "cadence-vm:" + REMOTE_STAGE + "/" + name), timeout=90
        )
        if result.returncode:
            raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v4 staging copy failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phaseb-role-v4-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v4 manifest copy failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh && chmod 600 role_v4_helper.py manifest.sha256"
        " && mv "
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


def read() -> dict[str, Any]:
    policy, digest, state_root, old_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v4 deployment not verified")
    _preflight(old_policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    record = _reserve(state_root, "read", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=135)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: invalid v4 response") from exc
    if not isinstance(payload, dict):
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: invalid v4 response type")
    if (
        payload.get("schema_version") != 1
        or payload.get("plan_id") != "WP14_FIXED_ROLE_PARSE_V4"
        or any(
            payload.get(key) is not False
            for key in (
                "names_included",
                "raw_content_included",
                "simulation_run",
                "values_included",
            )
        )
    ):
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v4 response contract mismatch")
    role_result = payload.get("role_result")
    if (
        not isinstance(role_result, dict)
        or role_result.get("schema_version") != 1
        or role_result.get("plan_id") != "WP14_FIXED_NAMES_ONLY_ROLE_DISCOVERY_PLAN"
    ):
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v4 role contract mismatch")
    invariants = role_result.get("invariants")
    if not isinstance(invariants, dict) or any(
        invariants.get(key) is not False
        for key in (
            "names_included",
            "paths_included",
            "raw_content_included",
            "simulation_run",
            "values_included",
        )
    ):
        raise RoleV4Error("BLOCKED_UNCERTAIN_STATE: v4 redaction contract mismatch")
    output = state_root / (OPERATIONS["read"] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return _finish(
        record,
        {
            "state": "succeeded",
            "operation": OPERATIONS["read"],
            "policy_sha256": digest,
            "result_status": role_result.get("status"),
            "raw_sha256": _sha(raw),
            "raw_local_file": str(output),
            "at": datetime.now(UTC).isoformat(),
        },
    )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        print("usage: phase_b_role_v4.py deploy|read", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read()
    except (RoleV4Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
