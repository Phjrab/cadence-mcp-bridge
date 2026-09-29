"""Read fixed AC values from one already completed candidate work-copy PSF."""

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
import phase_g_candidate_ac_v1 as ac

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_H_AC_SCALARS_V1.json"
DELEGATION = ROOT / ".codex/phase-h-ac-scalars-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/ac-scalar-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-ac-scalars-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/ac-scalar-v1/run.sh",
    "scalar_helper.py": ROOT / "remote/phase-campaign/ac-scalar-v1/scalar_helper.py",
    "extract.ocn": ROOT / "remote/phase-campaign/ac-scalar-v1/extract.ocn",
}
OPERATIONS = {"deploy": "phaseh-ac-scalars-v1-deploy", "read": "phaseh-ac-scalars-v1-read"}
DC_POLICY_SHA256 = "b337ab3d91b9f90c45f09989deef902e9681b88cea42b3904529bb093a28c953"
AC_POLICY_SHA256 = "c096f9fe6392886f114480c1da11e06a21d21ef3521c52388075b331fa782779"
AC_RESULT_SHA256 = "da959247b4034b2bf5bb3461c9356a1d9176e0b0a4ba36664e483b3a0df3d103"
PSF_SHA256 = "f1ddc9b70069055babebdb12ee3b46265b70396020223abfaff71bfcaad8b3e6"


class AcScalarsV1Error(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    dc_policy, dc_digest, state_root, base_policy = dc_v1._authority()
    if dc_digest != DC_POLICY_SHA256 or dc_v2._counter(state_root) != 3:
        raise AcScalarsV1Error("DENY_OUT_OF_SCOPE: campaign DC predecessor changed")
    ac_policy = parent._read_json(ac.POLICY)
    if _sha(v1._canonical(ac_policy)) != AC_POLICY_SHA256:
        raise AcScalarsV1Error("DENY_OUT_OF_SCOPE: reviewed AC policy changed")
    for mode in ("deploy", "run"):
        record = parent._read_json(ac._record_path(state_root, mode))
        if record.get("state") != "succeeded" or record.get("policy_sha256") != AC_POLICY_SHA256:
            raise AcScalarsV1Error("DENY_OUT_OF_SCOPE: AC predecessor not verified")
    run_record = parent._read_json(ac._record_path(state_root, "run"))
    raw_path = state_root / (ac.OPERATIONS["run"] + ".output")
    if (
        run_record.get("result_status") != "ac_completed"
        or run_record.get("raw_sha256") != AC_RESULT_SHA256
        or raw_path.is_symlink()
        or not raw_path.is_file()
        or _sha(raw_path.read_bytes()) != AC_RESULT_SHA256
    ):
        raise AcScalarsV1Error("DENY_OUT_OF_SCOPE: AC result bytes changed")
    result = json.loads(raw_path.read_bytes())
    if (
        result.get("status") != "ac_completed"
        or result.get("psf_tree_sha256") != PSF_SHA256
        or result.get("psf_bytes") != 4556
        or result.get("protected_and_copy_unchanged") is not True
        or result.get("spectre_errors") != 0
    ):
        raise AcScalarsV1Error("DENY_OUT_OF_SCOPE: AC result contract changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": AC_POLICY_SHA256,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/ac-scalar-v1",
        "ac_files": ac_policy["files"],
        "ac_result_sha256": AC_RESULT_SHA256,
        "psf_tree_sha256": PSF_SHA256,
        "source_fingerprint_sha256": dc_policy["source_fingerprint_sha256"],
        "copy_target_sha256": dc_policy["copy_target_sha256"],
        "state_tree_sha256": dc_policy["state_tree_sha256"],
        "model_sha256": dc_policy["model_sha256"],
        "frequencies_hz": [1000, 10000],
        "spectre_attempt_count": 3,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise AcScalarsV1Error("DENY_OUT_OF_SCOPE: AC scalar policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": AC_POLICY_SHA256,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise AcScalarsV1Error("DENY_OUT_OF_SCOPE: AC scalar delegation absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise AcScalarsV1Error("DENY_OUT_OF_SCOPE: local AC scalar bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(policy: dict[str, Any], base_policy: dict[str, Any]) -> dict[str, Any]:
    dc_v1._preflight(parent._read_json(dc_v1.POLICY), base_policy)
    v1._ssh("cd " + ac.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)
    snapshot = json.loads(
        v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/scalar_helper.py preflight")
    )
    if not isinstance(snapshot, dict):
        raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC scalar preflight invalid")
    if (
        snapshot.get("locks") != []
        or snapshot.get("target", {}).get("sha256") != policy["copy_target_sha256"]
        or snapshot.get("psf", {}).get("sha256") != PSF_SHA256
        or snapshot.get("protected", {}).get("ade_state_tree") != policy["state_tree_sha256"]
    ):
        raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC scalar preflight changed")
    return snapshot


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
        raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC scalar operation reserved") from exc
    return path


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def deploy() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    dc_v1._preflight(parent._read_json(dc_v1.POLICY), base_policy)
    v1._ssh("test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)
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
            raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC scalar staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phaseh-ac-scalars-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC scalar manifest staging failed")
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


def _check_response(raw: bytes, policy: dict[str, Any]) -> dict[str, Any]:
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: invalid AC scalar response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_CANDIDATE_AC_SCALARS_V1",
        "status": "observed",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "psf_sha256": PSF_SHA256,
        "protected_and_result_unchanged": True,
        "simulation_run": False,
    }
    if not isinstance(result, dict) or any(result.get(k) != v for k, v in expected.items()):
        raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC scalar response mismatch")
    points = result.get("points")
    if not isinstance(points, list) or len(points) != 2:
        raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC points invalid")
    for index, point in enumerate(points):
        if not isinstance(point, dict) or point.get("frequency_hz") != [1000, 10000][index]:
            raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC frequency mismatch")
        for key in ("input_diff_mag_v", "output_diff_mag_v", "gain_v_per_v", "gain_phase_deg"):
            value = point.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC value invalid")
        if abs(point["input_diff_mag_v"] - 1.0) > 1e-6:
            raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC input differs")
        db = point.get("gain_db")
        if db is not None and (not isinstance(db, (int, float)) or not math.isfinite(db)):
            raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC dB invalid")
    return result


def read() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise AcScalarsV1Error("BLOCKED_UNCERTAIN_STATE: AC scalar deployment absent")
    _preflight(policy, base_policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    record = _reserve(state_root, "read", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=125)
    result = _check_response(raw, policy)
    output = state_root / (OPERATIONS["read"] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    value = {
        "state": "succeeded",
        "operation": OPERATIONS["read"],
        "policy_sha256": digest,
        "result_status": result["status"],
        "raw_sha256": _sha(raw),
        "raw_local_file": str(output),
        "at": datetime.now(UTC).isoformat(),
    }
    parent._replace_record(record, value)
    return value


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        print("usage: phase_h_ac_scalars_v1.py deploy|read", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read()
    except (AcScalarsV1Error, dc_v1.CopiedDcV1Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
