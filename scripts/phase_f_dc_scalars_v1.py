"""Read fixed scalar outputs from the two already completed copied-cell DC PSFs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import phase_b_role_campaign as v1
import phase_campaign as parent
import phase_e_copied_dc_v1 as dc_v1
import phase_e_copied_dc_v2 as dc_v2

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_F_DC_SCALARS_V1.json"
DELEGATION = ROOT / ".codex/phase-f-dc-scalars-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/scalar-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-dc-scalars-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/scalar-v1/run.sh",
    "scalar_helper.py": ROOT / "remote/phase-campaign/scalar-v1/scalar_helper.py",
    "extract.ocn": ROOT / "remote/phase-campaign/scalar-v1/extract.ocn",
}
OPERATIONS = {"deploy": "phasef-dc-scalars-v1-deploy", "read": "phasef-dc-scalars-v1-read"}
RESULT_HASHES = {
    "baseline": "251c6bac6674fe97360a280d5c718ed99557b93e6f3ab1e685dbdb360e451091",
    "candidate": "560a44dd7475a213e96827bf0d63b05d30dff0263ce0d60c60aaa43746586725",
}
PSF_HASHES = {
    "baseline": "3718f6ab9c09da4e0d34a7995c46704b42e7d3dc1b1c827b3d355de2d0a903c0",
    "candidate": "4e6e85cce1836659a629599aec7b8e15a339aa8886c364f7c3443ba8d26d5873",
}


class DcScalarsV1Error(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy, v1_digest = dc_v2._authority()
    if old_digest != "010a5b8439fd75fc779b49d12b4c87a4db96e68db09a72133f922602e4a09abe":
        raise DcScalarsV1Error("DENY_OUT_OF_SCOPE: reviewed DC v2 policy changed")
    if dc_v2._counter(state_root) != 2:
        raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: DC attempt count changed")
    for mode in ("baseline", "candidate"):
        record = parent._read_json(dc_v1._record_path(state_root, mode))
        raw_path = state_root / (dc_v1.OPERATIONS[mode] + ".output")
        if (
            record.get("state") != "succeeded"
            or record.get("policy_sha256") != v1_digest
            or record.get("result_status") != "dc_completed"
            or record.get("raw_sha256") != RESULT_HASHES[mode]
            or raw_path.is_symlink()
            or not raw_path.is_file()
            or _sha(raw_path.read_bytes()) != RESULT_HASHES[mode]
        ):
            raise DcScalarsV1Error("DENY_OUT_OF_SCOPE: copied DC result not verified")
        result = json.loads(raw_path.read_bytes())
        if (
            result.get("status") != "dc_completed"
            or result.get("mode") != mode
            or result.get("psf_tree_sha256") != PSF_HASHES[mode]
            or result.get("protected_and_copy_unchanged") is not True
            or result.get("vdd_v") != 1.0
        ):
            raise DcScalarsV1Error("DENY_OUT_OF_SCOPE: DC evidence changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/scalar-v1",
        "dc_v2_files": old_policy["files"],
        "baseline_result_sha256": RESULT_HASHES["baseline"],
        "candidate_result_sha256": RESULT_HASHES["candidate"],
        "psf_tree_sha256": PSF_HASHES,
        "source_fingerprint_sha256": old_policy["source_fingerprint_sha256"],
        "copy_target_sha256": old_policy["copy_target_sha256"],
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "model_sha256": old_policy["model_sha256"],
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise DcScalarsV1Error("DENY_OUT_OF_SCOPE: scalar policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise DcScalarsV1Error("DENY_OUT_OF_SCOPE: scalar delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise DcScalarsV1Error("DENY_OUT_OF_SCOPE: local scalar bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(base_policy: dict[str, Any], policy: dict[str, Any]) -> None:
    old = parent._read_json(dc_v1.POLICY)
    dc_v2._preflight(old, base_policy)
    v1._ssh("cd " + dc_v2.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh(
        "set -e; test -d "
        + dc_v1.RUNTIME
        + "/baseline/psf"
        + "; test -d "
        + dc_v1.RUNTIME
        + "/candidate/psf"
        + "; test ! -e "
        + RUNTIME
        + "; test ! -L "
        + RUNTIME
        + "; test ! -L "
        + REMOTE_ROOT
        + "/run.lock"
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
        raise DcScalarsV1Error(
            "BLOCKED_UNCERTAIN_STATE: scalar operation already reserved"
        ) from exc
    return path


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def deploy() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    _preflight(base_policy, policy)
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
            raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: scalar staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasef-dc-scalars-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: scalar manifest staging failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh && chmod 600 scalar_helper.py extract.ocn manifest.sha256"
        " && mv "
        + REMOTE_STAGE
        + " "
        + REMOTE_VERSION
        + " && cd "
        + REMOTE_VERSION
        + " && sha256sum -c manifest.sha256"
    )
    value = {
        "state": "succeeded",
        "operation": OPERATIONS["deploy"],
        "policy_sha256": digest,
        "manifest_sha256": _sha(manifest),
        "at": datetime.now(UTC).isoformat(),
    }
    parent._replace_record(record, value)
    return value


def read() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: scalar deployment not verified")
    _preflight(base_policy, policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    snapshot = json.loads(
        v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/scalar_helper.py preflight")
    )
    if (
        snapshot.get("locks") != []
        or snapshot.get("target", {}).get("sha256") != policy["copy_target_sha256"]
        or snapshot.get("protected", {}).get("source_cellview_tree")
        != policy["source_fingerprint_sha256"]
        or snapshot.get("protected", {}).get("ade_state_tree") != policy["state_tree_sha256"]
        or any(
            snapshot.get("psf", {}).get(m, {}).get("sha256") != PSF_HASHES[m] for m in PSF_HASHES
        )
    ):
        raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: scalar preflight changed")
    record = _reserve(state_root, "read", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=125)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: invalid scalar response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_COPIED_DC_SCALARS_V1",
        "status": "observed",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "psf_sha256": PSF_HASHES,
        "protected_and_results_unchanged": True,
        "simulation_run": False,
    }
    if not isinstance(payload, dict) or any(payload.get(k) != v for k, v in expected.items()):
        raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: scalar response mismatch")
    values = payload.get("values_v")
    if not isinstance(values, dict) or set(values) != {"baseline", "candidate"}:
        raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: scalar set mismatch")
    for mode in values:
        row = values[mode]
        if not isinstance(row, dict) or set(row) != {
            "Vop",
            "Vom",
            "VDD",
            "Vp",
            "Vm",
            "output_common_mode_v",
            "output_diff_v",
        }:
            raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: scalar row mismatch")
        if any(
            not isinstance(n, (int, float)) or not math.isfinite(n) or abs(n) > 10
            for n in row.values()
        ):
            raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: nonfinite scalar")
        if abs(row["VDD"] - 1) > 1e-6 or abs(row["Vp"] - 0.5) > 1e-6 or abs(row["Vm"] - 0.5) > 1e-6:
            raise DcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: supply or VCM mismatch")
    output = state_root / (OPERATIONS["read"] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    value = {
        "state": "succeeded",
        "operation": OPERATIONS["read"],
        "policy_sha256": digest,
        "result_status": payload["status"],
        "raw_sha256": _sha(raw),
        "raw_local_file": str(output),
        "at": datetime.now(UTC).isoformat(),
    }
    parent._replace_record(record, value)
    return value


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        print("usage: phase_f_dc_scalars_v1.py deploy|read", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read()
    except (DcScalarsV1Error, dc_v2.CopiedDcV2Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
