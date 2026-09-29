"""Recover a reserved AC scalar read with a new bounded diagnostic extractor."""

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
import phase_g_candidate_ac_v1 as ac
import phase_h_ac_scalars_v1 as old

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_I_AC_SCALARS_V2.json"
DELEGATION = ROOT / ".codex/phase-i-ac-scalars-v2-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/ac-scalar-v2"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-ac-scalars-v2"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/ac-scalar-v2/run.sh",
    "scalar_helper.py": ROOT / "remote/phase-campaign/ac-scalar-v2/scalar_helper.py",
    "extract.ocn": ROOT / "remote/phase-campaign/ac-scalar-v2/extract.ocn",
}
OPERATIONS = {"deploy": "phasei-ac-scalars-v2-deploy", "read": "phasei-ac-scalars-v2-read"}
OLD_POLICY_SHA256 = "e521105da86124be05e26ffdb7372e6cf3ada9e2b18065b9b03edfca96d4c5ff"
OLD_BEFORE_SHA256 = "328a81742fb811764b51b387da0638facb48b27025ded1bfbe538607fc34f466"
OLD_OCEAN_LOG_SHA256 = "59200270c30d7ca848ea26007c58d74f75db47774feb914bbb4665b183cf772a"
OLD_ATTEMPT_SHA256 = "51b585dcc2ce5599de3a06ecbb07a134176555d8b32a12448489992f046e03ce"
PSF_SHA256 = old.PSF_SHA256


class AcScalarsV2Error(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = old._authority()
    if old_digest != OLD_POLICY_SHA256:
        raise AcScalarsV2Error("DENY_OUT_OF_SCOPE: reviewed AC scalar v1 policy changed")
    deployed = parent._read_json(old._record_path(state_root, "deploy"))
    reserved = parent._read_json(old._record_path(state_root, "read"))
    if (
        deployed.get("state") != "succeeded"
        or deployed.get("policy_sha256") != old_digest
        or reserved.get("state") != "reserved"
        or reserved.get("policy_sha256") != old_digest
        or (state_root / (old.OPERATIONS["read"] + ".output")).exists()
    ):
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: v1 read state changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/ac-scalar-v2",
        "v1_scalar_files": old_policy["files"],
        "ac_result_sha256": old_policy["ac_result_sha256"],
        "psf_tree_sha256": PSF_SHA256,
        "source_fingerprint_sha256": old_policy["source_fingerprint_sha256"],
        "copy_target_sha256": old_policy["copy_target_sha256"],
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "model_sha256": old_policy["model_sha256"],
        "v1_before_sha256": OLD_BEFORE_SHA256,
        "v1_ocean_log_sha256": OLD_OCEAN_LOG_SHA256,
        "v1_attempt_status_sha256": OLD_ATTEMPT_SHA256,
        "v1_scalar_bytes": 0,
        "frequencies_hz": [1000, 10000],
        "spectre_attempt_count": 3,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise AcScalarsV2Error("DENY_OUT_OF_SCOPE: AC scalar policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise AcScalarsV2Error("DENY_OUT_OF_SCOPE: AC scalar delegation absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise AcScalarsV2Error("DENY_OUT_OF_SCOPE: local AC scalar bytes changed")
    return policy, digest, state_root, base_policy


def _failed_v1_remote_state() -> None:
    previous = old.RUNTIME
    v1._ssh(
        "set -e; test -d "
        + previous
        + "; test -f "
        + previous
        + "/scalars.txt"
        + '; test "$(stat -c %s '
        + previous
        + '/scalars.txt)" = 0'
        + "; test ! -e "
        + previous
        + "/result.json"
        + "; grep -qx 'ocean_exit=1' "
        + previous
        + "/attempt-status.txt"
    )
    paths = [previous + "/" + name for name in ("before.json", "ocean.log", "attempt-status.txt")]
    raw = v1._ssh("sha256sum " + " ".join(paths)).decode("ascii")
    actual = [line.split(" ", 1)[0] for line in raw.splitlines()]
    if actual != [OLD_BEFORE_SHA256, OLD_OCEAN_LOG_SHA256, OLD_ATTEMPT_SHA256]:
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: v1 failure artifacts changed")


def _preflight(policy: dict[str, Any], base_policy: dict[str, Any]) -> dict[str, Any]:
    dc_v1._preflight(parent._read_json(dc_v1.POLICY), base_policy)
    v1._ssh("cd " + ac.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    _failed_v1_remote_state()
    v1._ssh("test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)
    snapshot = json.loads(
        v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/scalar_helper.py preflight")
    )
    if not isinstance(snapshot, dict):
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC scalar preflight invalid")
    if (
        snapshot.get("locks") != []
        or snapshot.get("target", {}).get("sha256") != policy["copy_target_sha256"]
        or snapshot.get("psf", {}).get("sha256") != PSF_SHA256
        or snapshot.get("protected", {}).get("ade_state_tree") != policy["state_tree_sha256"]
    ):
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC scalar preflight changed")
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
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC scalar operation reserved") from exc
    return path


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def deploy() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    dc_v1._preflight(parent._read_json(dc_v1.POLICY), base_policy)
    _failed_v1_remote_state()
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
            raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC scalar staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasei-ac-scalars-v2-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC scalar manifest staging failed")
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
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: invalid AC scalar response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_CANDIDATE_AC_SCALARS_V2",
        "status": "observed",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "psf_sha256": PSF_SHA256,
        "protected_and_result_unchanged": True,
        "simulation_run": False,
    }
    if not isinstance(result, dict) or any(result.get(k) != v for k, v in expected.items()):
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC scalar response mismatch")
    points = result.get("points")
    if not isinstance(points, list) or len(points) != 2:
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC points invalid")
    for index, point in enumerate(points):
        if not isinstance(point, dict) or point.get("frequency_hz") != [1000, 10000][index]:
            raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC frequency mismatch")
        for key in ("input_diff_mag_v", "output_diff_mag_v", "gain_v_per_v", "gain_phase_deg"):
            value = point.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC value invalid")
        if abs(point["input_diff_mag_v"] - 1.0) > 1e-6:
            raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC input differs")
        db = point.get("gain_db")
        if db is not None and (not isinstance(db, (int, float)) or not math.isfinite(db)):
            raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC dB invalid")
    return result


def read() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise AcScalarsV2Error("BLOCKED_UNCERTAIN_STATE: AC scalar deployment absent")
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
        print("usage: phase_i_ac_scalars_v2.py deploy|read", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read()
    except (
        AcScalarsV2Error,
        old.AcScalarsV1Error,
        dc_v1.CopiedDcV1Error,
        v1.PhaseBError,
        parent.CampaignError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
