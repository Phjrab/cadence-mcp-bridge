"""Fixed, one-shot copy of current WP-14 OA into an absent work-library cell.

The original campaign clock and prior v1-v7 records remain untouched.
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

import phase_b_oa_facts_v7 as facts_v7
import phase_b_role_campaign as v1
import phase_b_role_v2 as v2
import phase_b_role_v3 as v3
import phase_b_role_v4 as v4
import phase_b_role_v5 as v5
import phase_b_role_v6 as v6
import phase_campaign as parent

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_C_COPY_V1.json"
DELEGATION = ROOT / ".codex/phase-c-copy-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/copy-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-copy-current-oa-v1"
WORKLIB = "/home/buet/cds_work/MCP_WorkLib"
TARGET_CELL = WORKLIB + "/WP14_AUTO_PHASE_01_TB2"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/copy-v1/run.sh",
    "copy_helper.py": ROOT / "remote/phase-campaign/copy-v1/copy_helper.py",
    "copy-current-oa.il": ROOT / "remote/phase-campaign/copy-v1/copy-current-oa.il",
}
OPERATIONS = {"deploy": "phasec-copy-v1-deploy", "copy": "phasec-copy-v1-run"}


class CopyV1Error(RuntimeError):
    pass


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = facts_v7._authority()
    if old_digest != "0b2f34a85f614bcb847d980fb90257bc1cf4643ee7479eecb2228083c3cb7d74":
        raise CopyV1Error("DENY_OUT_OF_SCOPE: reviewed v7 policy changed")
    deployed = parent._read_json(state_root / "phaseb-oa-facts-v7-deploy.json")
    prior_read = parent._read_json(state_root / "phaseb-oa-facts-v7-read.json")
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != old_digest:
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: v7 deployment not verified")
    if (
        prior_read.get("state") != "succeeded"
        or prior_read.get("policy_sha256") != old_digest
        or prior_read.get("result_status") != "observed"
    ):
        raise CopyV1Error("DENY_OUT_OF_SCOPE: current v7 OA facts not verified")
    old_result = state_root / "phaseb-oa-facts-v7-read.output"
    if (
        old_result.is_symlink()
        or not old_result.is_file()
        or _sha(old_result.read_bytes()) != prior_read.get("raw_sha256")
        or prior_read.get("raw_sha256")
        != "aceff81c134c47275fdffca1479b77e4190fda649f2749f79c0a520be4033c11"
    ):
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: v7 result bytes changed")
    old_payload = json.loads(old_result.read_bytes())
    if (
        not isinstance(old_payload, dict)
        or old_payload.get("status") != "observed"
        or old_payload.get("source_sha256") != base_policy["source_fingerprint_sha256"]
        or old_payload.get("state_tree_sha256")
        != "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193"
        or old_payload.get("protected_fingerprints_unchanged") is not True
        or old_payload.get("topology", [])[:3] != [35, 14, 8]
    ):
        raise CopyV1Error("DENY_OUT_OF_SCOPE: current v7 OA evidence changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/copy-v1",
        "source_fingerprint_sha256": base_policy["source_fingerprint_sha256"],
        "installed_preflight_helper_sha256": base_policy["installed_preflight_helper_sha256"],
        "v7_files": old_policy["files"],
        "v7_result_sha256": "aceff81c134c47275fdffca1479b77e4190fda649f2749f79c0a520be4033c11",
        "state_tree_sha256": "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193",
        "model_sha256": "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f",
        "profile_sha256": "dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b",
        "work_library": WORKLIB,
        "target_cell": TARGET_CELL,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise CopyV1Error("DENY_OUT_OF_SCOPE: phase C copy policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise CopyV1Error("DENY_OUT_OF_SCOPE: copy delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise CopyV1Error("DENY_OUT_OF_SCOPE: local copy bytes changed")
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
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: copy operation already reserved") from exc
    return path


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def _preflight(policy: dict[str, Any], old_policy: dict[str, Any], *, deploy: bool) -> None:
    v1._remote_preflight(old_policy)
    v1._ssh("test ! -L " + REMOTE_ROOT + "/phase-campaign")
    v1._ssh("cd " + v1.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + v2.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + v3.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + v4.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + v5.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + v6.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + facts_v7.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    snapshot = json.loads(
        v1._ssh(
            "/usr/bin/python " + v1.REMOTE_VERSION + "/wp14_role_discovery.py preflight", timeout=90
        )
    )
    protected = snapshot.get("protected", {})
    if (
        protected.get("ade_state_tree") != policy["state_tree_sha256"]
        or protected.get("pdk_model_file") != policy["model_sha256"]
        or protected.get("fixed_profile_registry") != policy["profile_sha256"]
        or snapshot.get("locks") != []
    ):
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: protected baseline changed")
    v1._ssh(
        "set -e; test ! -L "
        + WORKLIB
        + '; test "$(realpath '
        + WORKLIB
        + ')" = '
        + WORKLIB
        + '; test "$(stat -c %U:%G '
        + WORKLIB
        + ")\" = buet:buet; grep -Fqx 'DEFINE MCP_WorkLib "
        + WORKLIB
        + "' /home/buet/cds_work/cds.lib; test ! -e "
        + TARGET_CELL
        + "; test ! -L "
        + TARGET_CELL
    )
    if deploy:
        v1._ssh("test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)
    else:
        v1._ssh("test -d " + RUNTIME + " && test ! -L " + RUNTIME)


def _finish(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    parent._replace_record(path, payload)
    return payload


def deploy() -> dict[str, Any]:
    policy, digest, state_root, old_policy = _authority()
    _preflight(policy, old_policy, deploy=True)
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
            raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: copy staging copy failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasec-copy-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: copy manifest copy failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh && chmod 600 copy_helper.py copy-current-oa.il manifest.sha256"
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


def copy() -> dict[str, Any]:
    policy, digest, state_root, old_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: copy deployment not verified")
    _preflight(policy, old_policy, deploy=False)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    record = _reserve(state_root, "copy", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=230)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: invalid copy response") from exc
    if not isinstance(payload, dict):
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: invalid copy response type")
    if (
        payload.get("schema_version") != 1
        or payload.get("plan_id") != "WP14_FIXED_CURRENT_OA_COPY_V1"
        or payload.get("status") != "copied"
        or payload.get("simulation_run") is not False
        or payload.get("source_and_protected_unchanged") is not True
        or payload.get("locks_unchanged") is not True
        or payload.get("target_topology_equal") is not True
        or payload.get("target_instance_and_net_signatures_equal") is not True
        or payload.get("source_sha256") != policy["source_fingerprint_sha256"]
        or payload.get("state_tree_sha256") != policy["state_tree_sha256"]
    ):
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: copy response contract mismatch")
    target_sha = payload.get("target_tree_sha256")
    if (
        not isinstance(target_sha, str)
        or len(target_sha) != 64
        or not all(char in "0123456789abcdef" for char in target_sha)
        or not isinstance(payload.get("target_entries"), int)
        or payload["target_entries"] < 2
        or not isinstance(payload.get("target_bytes"), int)
        or payload["target_bytes"] <= 0
    ):
        raise CopyV1Error("BLOCKED_UNCERTAIN_STATE: target fingerprint invalid")
    output = state_root / (OPERATIONS["copy"] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return _finish(
        record,
        {
            "state": "succeeded",
            "operation": OPERATIONS["copy"],
            "policy_sha256": digest,
            "result_status": payload.get("status"),
            "raw_sha256": _sha(raw),
            "raw_local_file": str(output),
            "at": datetime.now(UTC).isoformat(),
        },
    )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        print("usage: phase_c_copy_v1.py deploy|copy", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else copy()
    except (CopyV1Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
