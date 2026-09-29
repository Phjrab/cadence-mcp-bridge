"""One-shot copied-WP14 OCEAN netlist, bound to the original campaign clock."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import phase_b_role_campaign as v1
import phase_c_copy_v1 as prior
import phase_campaign as parent

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_D_NETLIST_V1.json"
DELEGATION = ROOT / ".codex/phase-d-netlist-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/netlist-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-copied-netlist-v1"
TARGET = prior.TARGET_CELL + "/schematic"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/netlist-v1/run.sh",
    "netlist_helper.py": ROOT / "remote/phase-campaign/netlist-v1/netlist_helper.py",
    "copied-netlist.ocn": ROOT / "remote/phase-campaign/netlist-v1/copied-netlist.ocn",
}
OPERATIONS = {"deploy": "phased-netlist-v1-deploy", "netlist": "phased-netlist-v1-run"}
COPY_RESULT_SHA256 = "ba79066b0edb0f94f21baf175508acffec33ce78450f5918f9e5a931f60708d1"
TARGET_SHA256 = "a02d83653f26f2e34f1f4e402531e66e9d34b5ecc41d29ed6d38a70ed8c6983f"


class NetlistV1Error(RuntimeError):
    pass


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = prior._authority()
    if old_digest != "cd6ce5e553fe2c30ff6cfa9e2f32c781d873139b991a45ede2882175528fdfe1":
        raise NetlistV1Error("DENY_OUT_OF_SCOPE: reviewed copy policy changed")
    deployed = parent._read_json(state_root / "phasec-copy-v1-deploy.json")
    copied = parent._read_json(state_root / "phasec-copy-v1-run.json")
    if (
        deployed.get("state") != "succeeded"
        or deployed.get("policy_sha256") != old_digest
        or copied.get("state") != "succeeded"
        or copied.get("policy_sha256") != old_digest
        or copied.get("result_status") != "copied"
        or copied.get("raw_sha256") != COPY_RESULT_SHA256
    ):
        raise NetlistV1Error("DENY_OUT_OF_SCOPE: one-shot copy evidence absent")
    raw_copy = state_root / "phasec-copy-v1-run.output"
    if (
        raw_copy.is_symlink()
        or not raw_copy.is_file()
        or _sha(raw_copy.read_bytes()) != COPY_RESULT_SHA256
    ):
        raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: copy result bytes changed")
    copy_payload = json.loads(raw_copy.read_bytes())
    if (
        not isinstance(copy_payload, dict)
        or copy_payload.get("target_tree_sha256") != TARGET_SHA256
        or copy_payload.get("source_and_protected_unchanged") is not True
        or copy_payload.get("target_instance_and_net_signatures_equal") is not True
    ):
        raise NetlistV1Error("DENY_OUT_OF_SCOPE: copied OA evidence changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/netlist-v1",
        "source_fingerprint_sha256": base_policy["source_fingerprint_sha256"],
        "installed_preflight_helper_sha256": base_policy["installed_preflight_helper_sha256"],
        "copy_files": old_policy["files"],
        "copy_result_sha256": COPY_RESULT_SHA256,
        "copy_target_sha256": TARGET_SHA256,
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "model_sha256": old_policy["model_sha256"],
        "profile_sha256": old_policy["profile_sha256"],
        "target_cellview": TARGET,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise NetlistV1Error("DENY_OUT_OF_SCOPE: netlist policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise NetlistV1Error("DENY_OUT_OF_SCOPE: netlist delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise NetlistV1Error("DENY_OUT_OF_SCOPE: local netlist bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(policy: dict[str, Any], base_policy: dict[str, Any]) -> None:
    v1._remote_preflight(base_policy)
    v1._ssh("cd " + prior.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
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
        raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: protected baseline changed")
    v1._ssh(
        "set -e; test -d "
        + TARGET
        + "; test ! -L "
        + TARGET
        + '; test "$(stat -c %U:%G '
        + prior.TARGET_CELL
        + ')" = buet:buet'
        + "; test ! -e /home/buet/simulation/WP14_AUTO_PHASE_01_TB2"
        + "; test ! -e "
        + RUNTIME
        + "; test ! -L "
        + RUNTIME
        + "; test ! -L "
        + REMOTE_ROOT
        + "/phase-campaign/eda.lock"
    )


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
        raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: netlist operation already reserved") from exc
    return path


def _finish(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    parent._replace_record(path, payload)
    return payload


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def deploy() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    _preflight(policy, base_policy)
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
        copied = v1._command(
            (*v1.SCP, str(source), "cadence-vm:" + REMOTE_STAGE + "/" + name), timeout=90
        )
        if copied.returncode:
            raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: netlist staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phased-netlist-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: netlist manifest staging failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh && chmod 600 netlist_helper.py copied-netlist.ocn manifest.sha256"
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


def netlist() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: netlist deployment not verified")
    _preflight(policy, base_policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    record = _reserve(state_root, "netlist", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=230)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: invalid netlist response") from exc
    if not isinstance(payload, dict) or any(
        (
            payload.get(key) != value
            for key, value in {
                "schema_version": 1,
                "plan_id": "WP14_FIXED_COPIED_NETLIST_V1",
                "status": "netlisted",
                "source_sha256": policy["source_fingerprint_sha256"],
                "target_sha256": TARGET_SHA256,
                "state_tree_sha256": policy["state_tree_sha256"],
                "protected_and_copy_unchanged": True,
                "simulation_run": False,
            }.items()
        )
    ):
        raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: netlist response contract mismatch")
    for key in ("netlist_tree_sha256", "circuit_netlist_sha256", "input_scs_sha256"):
        value = payload.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: netlist digest invalid")
    if (
        not isinstance(payload.get("netlist_entries"), int)
        or payload["netlist_entries"] < 3
        or not isinstance(payload.get("netlist_bytes"), int)
        or not 0 < payload["netlist_bytes"] <= 128 * 1024 * 1024
    ):
        raise NetlistV1Error("BLOCKED_UNCERTAIN_STATE: netlist bound invalid")
    output = state_root / (OPERATIONS["netlist"] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return _finish(
        record,
        {
            "state": "succeeded",
            "operation": OPERATIONS["netlist"],
            "policy_sha256": digest,
            "result_status": payload["status"],
            "raw_sha256": _sha(raw),
            "raw_local_file": str(output),
            "at": datetime.now(UTC).isoformat(),
        },
    )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        print("usage: phase_d_netlist_v1.py deploy|netlist", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else netlist()
    except (NetlistV1Error, prior.CopyV1Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
