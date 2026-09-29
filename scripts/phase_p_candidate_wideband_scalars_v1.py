"""Read the existing candidate wideband AC PSF without another simulation."""

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
import phase_e_copied_dc_v2 as dc_v2
import phase_o_candidate_wideband_ac_v1 as wide

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_P_CANDIDATE_WIDEBAND_SCALARS_V1.json"
DELEGATION = ROOT / ".codex/phase-p-candidate-wideband-scalars-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/candidate-wideband-scalars-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-candidate-wideband-scalars-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/candidate-wideband-scalars-v1/run.sh",
    "scalar_helper.py": ROOT
    / "remote/phase-campaign/candidate-wideband-scalars-v1/scalar_helper.py",
    "extract.ocn": ROOT / "remote/phase-campaign/candidate-wideband-scalars-v1/extract.ocn",
}
OPERATIONS = {
    "deploy": "phasep-candidate-wideband-scalars-v1-deploy",
    "read": "phasep-candidate-wideband-scalars-v1-read",
}
PARENT_POLICY_SHA256 = "1c49ae5721fab85933151e161d6e8bd18f3f6a5c917359363faba7c88e9eb63a"
WIDEBAND_RESULT_SHA256 = "e2c51d5cf26f3546b4c21c458e9456dcea217ab47f33b10eb83d1ca9c32c33f8"
PSF_SHA256 = "3354ad0c32abdd01692471e415d2deef6b9cfd51d9a476a210353ec074a5c757"


class CandidateWidebandScalarsError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    base_policy, _base_digest, state_root = v1._authority()
    if dc_v2._counter(state_root) != 7:
        raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: Spectre count changed")
    prior_policy = parent._read_json(wide.POLICY)
    if _sha(v1._canonical(prior_policy)) != PARENT_POLICY_SHA256:
        raise CandidateWidebandScalarsError("DENY_OUT_OF_SCOPE: wideband policy changed")
    run_record = parent._read_json(wide._record_path(state_root, "run"))
    run_raw = state_root / (wide.OPERATIONS["run"] + ".output")
    if (
        run_record.get("state") != "succeeded"
        or run_record.get("policy_sha256") != PARENT_POLICY_SHA256
        or run_record.get("result_status") != "ac_completed"
        or run_record.get("raw_sha256") != WIDEBAND_RESULT_SHA256
        or run_raw.is_symlink()
        or not run_raw.is_file()
        or _sha(run_raw.read_bytes()) != WIDEBAND_RESULT_SHA256
    ):
        raise CandidateWidebandScalarsError("DENY_OUT_OF_SCOPE: wideband result changed")
    result = json.loads(run_raw.read_bytes())
    if (
        result.get("status") != "ac_completed"
        or result.get("psf_tree_sha256") != PSF_SHA256
        or result.get("psf_bytes") != 13805
        or result.get("spectre_errors") != 0
        or result.get("protected_and_copy_unchanged") is not True
        or result.get("vdd_v") != 1.0
        or result.get("input_vcm_v") != 0.5
    ):
        raise CandidateWidebandScalarsError("DENY_OUT_OF_SCOPE: wideband evidence changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/candidate-wideband-scalars-v1",
        "wideband_result_sha256": WIDEBAND_RESULT_SHA256,
        "source_fingerprint_sha256": prior_policy["source_fingerprint_sha256"],
        "copy_target_sha256": prior_policy["copy_target_sha256"],
        "state_tree_sha256": prior_policy["state_tree_sha256"],
        "model_sha256": prior_policy["model_sha256"],
        "psf_tree_sha256": PSF_SHA256,
        "psf_bytes": 13805,
        "frequency_start_hz": 10,
        "frequency_stop_hz": 100000000,
        "spectre_attempt_count": 7,
        "new_simulation": False,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise CandidateWidebandScalarsError("DENY_OUT_OF_SCOPE: wideband scalar policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise CandidateWidebandScalarsError("DENY_OUT_OF_SCOPE: scalar delegation absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise CandidateWidebandScalarsError("DENY_OUT_OF_SCOPE: local scalar bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(base_policy: dict[str, Any]) -> None:
    v1._remote_preflight(base_policy)
    v1._ssh("cd " + wide.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    remote = v1._ssh("sha256sum " + wide.RUNTIME + "/result.json")
    if remote.split(b" ", 1)[0].decode("ascii") != WIDEBAND_RESULT_SHA256:
        raise CandidateWidebandScalarsError(
            "BLOCKED_UNCERTAIN_STATE: remote wideband result changed"
        )
    v1._ssh("test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)


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
        raise CandidateWidebandScalarsError(
            "BLOCKED_UNCERTAIN_STATE: scalar operation reserved"
        ) from exc
    return path


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def deploy() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    _preflight(base_policy)
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
            raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: scalar staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasep-candidate-wideband-scalars-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise CandidateWidebandScalarsError(
            "BLOCKED_UNCERTAIN_STATE: scalar manifest staging failed"
        )
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


def _validate_points(points: Any) -> None:
    if not isinstance(points, list) or not 70 <= len(points) <= 72:
        raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: point count invalid")
    last_frequency = 0.0
    for index, point in enumerate(points):
        if not isinstance(point, dict) or set(point) != {
            "frequency_hz",
            "input_diff_mag_v",
            "output_diff_mag_v",
            "gain_v_per_v",
            "gain_db",
            "gain_phase_deg",
        }:
            raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: point schema invalid")
        for key in (
            "frequency_hz",
            "input_diff_mag_v",
            "output_diff_mag_v",
            "gain_v_per_v",
            "gain_phase_deg",
        ):
            value = point[key]
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: nonfinite point")
        freq = float(point["frequency_hz"])
        if freq <= last_frequency or freq < 10 or freq > 100000000:
            raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: frequency order invalid")
        last_frequency = freq
        if (
            abs(point["input_diff_mag_v"] - 1.0) > 1e-6
            or abs(point["output_diff_mag_v"] - point["gain_v_per_v"])
            > max(1e-4, point["gain_v_per_v"] * 1e-6)
            or not 0 <= point["gain_v_per_v"] <= 1e12
            or not -180 <= point["gain_phase_deg"] <= 180
        ):
            raise CandidateWidebandScalarsError(
                "BLOCKED_UNCERTAIN_STATE: gain relationship invalid"
            )
        gain_db = point["gain_db"]
        if point["gain_v_per_v"] > 0:
            if not isinstance(gain_db, (int, float)) or not math.isfinite(gain_db):
                raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: gain dB invalid")
            if abs(gain_db - 20 * math.log10(point["gain_v_per_v"])) > 1e-6:
                raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: gain dB mismatch")
        elif gain_db is not None:
            raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: zero gain dB invalid")
        if index == 0 and abs(freq - 10.0) > 1e-4:
            raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: start frequency invalid")
    if abs(last_frequency - 100000000.0) > 100:
        raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: stop frequency invalid")


def read() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: scalar deployment unverified")
    _preflight(base_policy)
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
        or snapshot.get("psf", {}).get("sha256") != PSF_SHA256
    ):
        raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: scalar preflight changed")
    record = _reserve(state_root, "read", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=125)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CandidateWidebandScalarsError(
            "BLOCKED_UNCERTAIN_STATE: invalid scalar response"
        ) from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_CANDIDATE_WIDEBAND_SCALARS_V1",
        "status": "observed",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "psf_sha256": PSF_SHA256,
        "protected_and_result_unchanged": True,
        "simulation_run": False,
    }
    if not isinstance(payload, dict) or any(payload.get(k) != v for k, v in expected.items()):
        raise CandidateWidebandScalarsError("BLOCKED_UNCERTAIN_STATE: scalar response mismatch")
    _validate_points(payload.get("points"))
    output = state_root / (OPERATIONS["read"] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    value = {
        "state": "succeeded",
        "operation": OPERATIONS["read"],
        "policy_sha256": digest,
        "result_status": "observed",
        "raw_sha256": _sha(raw),
        "raw_local_file": str(output),
        "at": datetime.now(UTC).isoformat(),
    }
    parent._replace_record(record, value)
    return value


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        print("usage: phase_p_candidate_wideband_scalars_v1.py deploy|read", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read()
    except (
        CandidateWidebandScalarsError,
        v1.PhaseBError,
        parent.CampaignError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
