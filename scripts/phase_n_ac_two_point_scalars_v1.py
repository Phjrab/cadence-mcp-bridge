"""Read fixed baseline and midpoint AC PSFs without another Spectre run."""

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
import phase_m_ac_two_point_v1 as ac

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_N_AC_TWO_POINT_SCALARS_V1.json"
DELEGATION = ROOT / ".codex/phase-n-ac-two-point-scalars-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/ac-two-point-scalars-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-ac-two-point-scalars-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/ac-two-point-scalars-v1/run.sh",
    "scalar_helper.py": ROOT / "remote/phase-campaign/ac-two-point-scalars-v1/scalar_helper.py",
    "extract-baseline.ocn": ROOT
    / "remote/phase-campaign/ac-two-point-scalars-v1/extract-baseline.ocn",
    "extract-midpoint.ocn": ROOT
    / "remote/phase-campaign/ac-two-point-scalars-v1/extract-midpoint.ocn",
}
OPERATIONS = {
    "deploy": "phasen-ac-two-point-scalars-v1-deploy",
    "baseline": "phasen-ac-two-point-scalars-v1-baseline",
    "midpoint": "phasen-ac-two-point-scalars-v1-midpoint",
}
PARENT_POLICY_SHA256 = "1b5ba47186f11f42d42217de0a69ba201e62b883d303588bbca989ec9f99e375"
AC_RESULTS = {
    "baseline": "4d121c91cd1c1d5503791b9d64e7228215d19033455087d152458d4cd9273be7",
    "midpoint": "5c68c088c5f8a345e68c3c9709b1010ecf3d26153145016d707b835739597a55",
}
PSF_HASHES = {
    "baseline": "dab0a9889bbaa3bc4d78a3c9dbbba0cf0cb4258de66190e5944bcf14d3fd870e",
    "midpoint": "ebe6b713b0280ad03a57cd3638e9b772474bbe563e616a6173162677c40af5b7",
}


class AcTwoPointScalarsError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    base_policy, _base_digest, state_root = v1._authority()
    if dc_v2._counter(state_root) != 6:
        raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: Spectre count changed")
    old = parent._read_json(ac.POLICY)
    if _sha(v1._canonical(old)) != PARENT_POLICY_SHA256:
        raise AcTwoPointScalarsError("DENY_OUT_OF_SCOPE: reviewed AC policy changed")
    for mode in AC_RESULTS:
        record = parent._read_json(ac._record_path(state_root, mode))
        raw_path = state_root / (ac.OPERATIONS[mode] + ".output")
        if (
            record.get("state") != "succeeded"
            or record.get("policy_sha256") != PARENT_POLICY_SHA256
            or record.get("result_status") != "ac_completed"
            or record.get("raw_sha256") != AC_RESULTS[mode]
            or raw_path.is_symlink()
            or not raw_path.is_file()
            or _sha(raw_path.read_bytes()) != AC_RESULTS[mode]
        ):
            raise AcTwoPointScalarsError("DENY_OUT_OF_SCOPE: AC predecessor changed")
        result = json.loads(raw_path.read_bytes())
        if (
            result.get("mode") != mode
            or result.get("psf_tree_sha256") != PSF_HASHES[mode]
            or result.get("psf_bytes") != 4556
            or result.get("spectre_errors") != 0
            or result.get("protected_and_copy_unchanged") is not True
        ):
            raise AcTwoPointScalarsError("DENY_OUT_OF_SCOPE: AC evidence changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/ac-two-point-scalars-v1",
        "ac_result_sha256": AC_RESULTS,
        "psf_tree_sha256": PSF_HASHES,
        "source_fingerprint_sha256": old["source_fingerprint_sha256"],
        "copy_target_sha256": old["copy_target_sha256"],
        "state_tree_sha256": old["state_tree_sha256"],
        "model_sha256": old["model_sha256"],
        "frequencies_hz": [1000, 10000],
        "spectre_attempt_count": 6,
        "new_simulation": False,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise AcTwoPointScalarsError("DENY_OUT_OF_SCOPE: scalar policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise AcTwoPointScalarsError("DENY_OUT_OF_SCOPE: scalar delegation absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise AcTwoPointScalarsError("DENY_OUT_OF_SCOPE: local scalar bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(base_policy: dict[str, Any], operation: str) -> None:
    v1._remote_preflight(base_policy)
    v1._ssh("cd " + ac.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    for mode in AC_RESULTS:
        expected = AC_RESULTS[mode]
        actual = v1._ssh("sha256sum " + ac.RUNTIME + "/" + mode + "/result.json")
        if actual.split(b" ", 1)[0].decode("ascii") != expected:
            raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: remote AC result changed")
    if operation == "deploy" or operation == "baseline":
        v1._ssh("test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)
    else:
        v1._ssh(
            "test -s "
            + RUNTIME
            + "/baseline/result.json && test ! -e "
            + RUNTIME
            + "/midpoint && test ! -L "
            + RUNTIME
            + "/midpoint"
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
        raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: scalar operation reserved") from exc
    return path


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def deploy() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    _preflight(base_policy, "deploy")
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
            raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: scalar staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasen-ac-two-point-scalars-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: scalar manifest staging failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh"
        " && chmod 600 scalar_helper.py extract-baseline.ocn"
        " extract-midpoint.ocn manifest.sha256"
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


def read(mode: str) -> dict[str, Any]:
    if mode not in AC_RESULTS:
        raise AcTwoPointScalarsError("DENY_OUT_OF_SCOPE: scalar mode not allowlisted")
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: scalar deployment not verified")
    _preflight(base_policy, mode)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    if mode == "midpoint":
        predecessor = parent._read_json(_record_path(state_root, "baseline"))
        if (
            predecessor.get("state") != "succeeded"
            or predecessor.get("result_status") != "observed"
        ):
            raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: baseline scalar not observed")
        remote = v1._ssh("sha256sum " + RUNTIME + "/baseline/result.json")
        if remote.split(b" ", 1)[0].decode("ascii") != predecessor.get("raw_sha256"):
            raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: baseline scalar changed")
    snapshot = json.loads(
        v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/scalar_helper.py preflight " + mode)
    )
    if (
        snapshot.get("locks") != []
        or snapshot.get("target", {}).get("sha256") != policy["copy_target_sha256"]
        or snapshot.get("protected", {}).get("source_cellview_tree")
        != policy["source_fingerprint_sha256"]
        or snapshot.get("protected", {}).get("ade_state_tree") != policy["state_tree_sha256"]
        or snapshot.get("psf", {}).get("sha256") != PSF_HASHES[mode]
    ):
        raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: scalar preflight changed")
    record = _reserve(state_root, mode, digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh " + mode, timeout=125)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: invalid scalar response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_TWO_POINT_AC_SCALARS_V1",
        "status": "observed",
        "mode": mode,
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "psf_sha256": PSF_HASHES[mode],
        "protected_and_result_unchanged": True,
        "simulation_run": False,
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in expected.items()
    ):
        raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: scalar response mismatch")
    points = payload.get("points")
    if not isinstance(points, list) or len(points) != 2:
        raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: scalar points invalid")
    for index, point in enumerate(points):
        if not isinstance(point, dict) or point.get("frequency_hz") != [1000.0, 10000.0][index]:
            raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: frequency invalid")
        for key in ("input_diff_mag_v", "output_diff_mag_v", "gain_v_per_v", "gain_phase_deg"):
            number = point.get(key)
            if (
                not isinstance(number, (int, float))
                or not math.isfinite(number)
                or abs(number) > 1e12
            ):
                raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: scalar value invalid")
        if abs(point["input_diff_mag_v"] - 1.0) > 1e-6:
            raise AcTwoPointScalarsError("BLOCKED_UNCERTAIN_STATE: input magnitude invalid")
    output = state_root / (OPERATIONS[mode] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    value = {
        "state": "succeeded",
        "operation": OPERATIONS[mode],
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
        print("usage: phase_n_ac_two_point_scalars_v1.py deploy|baseline|midpoint", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read(sys.argv[1])
    except (AcTwoPointScalarsError, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
