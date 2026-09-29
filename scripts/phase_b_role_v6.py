"""Separate, one-shot ASCII role parse after diagnosed Python 2.6 failure.

The original campaign clock and prior v1/v2/v3/v4/v5 records remain untouched.
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
import phase_b_role_v4 as v4
import phase_b_role_v5 as v5
import phase_campaign as parent

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_B_ROLE_V6.json"
DELEGATION = ROOT / ".codex/phase-b-role-v6-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/role-v6"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-ascii-role-parse-v6"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/role-v6/run.sh",
    "role_v6_helper.py": ROOT / "remote/phase-campaign/role-v6/role_v6_helper.py",
}
OPERATIONS = {"deploy": "phaseb-role-v6-deploy", "read": "phaseb-role-v6-read"}


class RoleV6Error(RuntimeError):
    pass


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = v5._authority()
    if old_digest != "97e0d6ea2a6e19a6cb6905668cf0b5a1eccffaebfbab6ccd9476e3276f8b6f8b":
        raise RoleV6Error("DENY_OUT_OF_SCOPE: reviewed v5 policy changed")
    deployed = parent._read_json(state_root / "phaseb-role-v5-deploy.json")
    prior_read = parent._read_json(state_root / "phaseb-role-v5-read.json")
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != old_digest:
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: v5 deployment not verified")
    if (
        prior_read.get("state") != "succeeded"
        or prior_read.get("policy_sha256") != old_digest
        or prior_read.get("result_status") != "other_value_error"
    ):
        raise RoleV6Error("DENY_OUT_OF_SCOPE: diagnosed v5 read not verified")
    old_result = state_root / "phaseb-role-v5-read.output"
    if (
        old_result.is_symlink()
        or not old_result.is_file()
        or _sha(old_result.read_bytes()) != prior_read.get("raw_sha256")
    ):
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: v5 result bytes changed")
    old_payload = json.loads(old_result.read_bytes())
    if (
        not isinstance(old_payload, dict)
        or old_payload.get("parse_error") != "other_value_error"
        or old_payload.get("complete_regex_count") != 1
        or old_payload.get("topology_regex_count") != 1
        or old_payload.get("protected_fingerprints_unchanged") is not True
    ):
        raise RoleV6Error("DENY_OUT_OF_SCOPE: v5 parser evidence changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/role-v6",
        "source_fingerprint_sha256": base_policy["source_fingerprint_sha256"],
        "installed_preflight_helper_sha256": base_policy["installed_preflight_helper_sha256"],
        "v5_files": old_policy["files"],
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise RoleV6Error("DENY_OUT_OF_SCOPE: phase B v6 policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise RoleV6Error("DENY_OUT_OF_SCOPE: v6 delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise RoleV6Error("DENY_OUT_OF_SCOPE: local v6 bytes changed")
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
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: v6 operation already reserved") from exc
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
    v1._ssh("cd " + v4.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + v5.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    locations = (
        v1._ssh(
            "set -e; test ! -L " + RUNTIME + "; if test -e " + RUNTIME + "; then echo exists; fi"
        )
        .decode("ascii")
        .splitlines()
    )
    if locations:
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: v6 runtime already exists")


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
            raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: v6 staging copy failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phaseb-role-v6-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: v6 manifest copy failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh && chmod 600 role_v6_helper.py manifest.sha256"
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
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: v6 deployment not verified")
    _preflight(old_policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    record = _reserve(state_root, "read", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=135)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: invalid v6 response") from exc
    if not isinstance(payload, dict):
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: invalid v6 response type")
    if (
        payload.get("schema_version") != 1
        or payload.get("plan_id") != "WP14_FIXED_ASCII_ROLE_PARSE_V6"
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
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: v6 response contract mismatch")
    role_result = payload.get("role_result")
    if (
        not isinstance(role_result, dict)
        or role_result.get("schema_version") != 1
        or role_result.get("plan_id") != "WP14_FIXED_NAMES_ONLY_ROLE_DISCOVERY_PLAN"
    ):
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: role result contract mismatch")
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
        raise RoleV6Error("BLOCKED_UNCERTAIN_STATE: redaction contract mismatch")
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
        print("usage: phase_b_role_v6.py deploy|read", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read()
    except (RoleV6Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
