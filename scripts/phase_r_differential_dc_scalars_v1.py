"""Read symmetric differential DC PSFs without another Spectre run."""

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
import phase_q_differential_dc_v1 as dc

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_R_DIFFERENTIAL_DC_SCALARS_V1.json"
DELEGATION = ROOT / ".codex/phase-r-differential-dc-scalars-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/differential-dc-scalars-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-differential-dc-scalars-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/differential-dc-scalars-v1/run.sh",
    "scalar_helper.py": ROOT / "remote/phase-campaign/differential-dc-scalars-v1/scalar_helper.py",
    "extract-positive.ocn": ROOT
    / "remote/phase-campaign/differential-dc-scalars-v1/extract-positive.ocn",
    "extract-negative.ocn": ROOT
    / "remote/phase-campaign/differential-dc-scalars-v1/extract-negative.ocn",
}
OPERATIONS = {
    "deploy": "phaser-differential-dc-scalars-v1-deploy",
    "positive": "phaser-differential-dc-scalars-v1-positive",
    "negative": "phaser-differential-dc-scalars-v1-negative",
}
PARENT_POLICY_SHA256 = "1773043f2351e78872fbc4f903a966084395ee48267fcad3127c63554dde16c3"
DC_RESULTS = {
    "positive": "2983edf834e865ed7eff1afd51777feafd45b410dbd0b60e702d6c4d77070084",
    "negative": "bdb1ab3973cc3c7f60e36071bd3c8a070ccf064d319b4e07cb6c93a1d25751b4",
}
PSF_HASHES = {
    "positive": "49184d7d16301779b547af1e5281dfb45804793782bf599b05bb3a730b5393f6",
    "negative": "387501f30447f3b3fd11da3c19ca2f6dbd8da48284e677ce3105af2b15920b2a",
}
INPUTS = {"positive": (0.5000005, 0.4999995), "negative": (0.4999995, 0.5000005)}


class DifferentialDcScalarsError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    base_policy, _base_digest, state_root = v1._authority()
    if dc_v2._counter(state_root) != 9:
        raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: Spectre count changed")
    old = parent._read_json(dc.POLICY)
    if _sha(v1._canonical(old)) != PARENT_POLICY_SHA256:
        raise DifferentialDcScalarsError("DENY_OUT_OF_SCOPE: reviewed DC policy changed")
    for mode in DC_RESULTS:
        record = parent._read_json(dc._record_path(state_root, mode))
        raw_path = state_root / (dc.OPERATIONS[mode] + ".output")
        if (
            record.get("state") != "succeeded"
            or record.get("policy_sha256") != PARENT_POLICY_SHA256
            or record.get("result_status") != "dc_completed"
            or record.get("raw_sha256") != DC_RESULTS[mode]
            or raw_path.is_symlink()
            or not raw_path.is_file()
            or _sha(raw_path.read_bytes()) != DC_RESULTS[mode]
        ):
            raise DifferentialDcScalarsError("DENY_OUT_OF_SCOPE: DC predecessor changed")
        result = json.loads(raw_path.read_bytes())
        if (
            result.get("mode") != mode
            or result.get("psf_tree_sha256") != PSF_HASHES[mode]
            or result.get("psf_bytes") != 3966
            or result.get("spectre_errors") != 0
            or result.get("input_dc_differential_v") != dc.MODES[mode]
            or result.get("bias_values_v") != [0.320, 0.702]
            or result.get("vdd_v") != 1.0
            or result.get("input_vcm_v") != 0.5
            or result.get("protected_and_copy_unchanged") is not True
        ):
            raise DifferentialDcScalarsError("DENY_OUT_OF_SCOPE: DC evidence changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/differential-dc-scalars-v1",
        "dc_result_sha256": DC_RESULTS,
        "psf_tree_sha256": PSF_HASHES,
        "source_fingerprint_sha256": old["source_fingerprint_sha256"],
        "copy_target_sha256": old["copy_target_sha256"],
        "state_tree_sha256": old["state_tree_sha256"],
        "model_sha256": old["model_sha256"],
        "input_dc_differential_uv": [1, -1],
        "spectre_attempt_count": 9,
        "new_simulation": False,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise DifferentialDcScalarsError("DENY_OUT_OF_SCOPE: scalar policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise DifferentialDcScalarsError("DENY_OUT_OF_SCOPE: scalar delegation absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise DifferentialDcScalarsError("DENY_OUT_OF_SCOPE: local scalar bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(base_policy: dict[str, Any], operation: str) -> None:
    v1._remote_preflight(base_policy)
    v1._ssh("cd " + dc.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    for mode in DC_RESULTS:
        expected = DC_RESULTS[mode]
        actual = v1._ssh("sha256sum " + dc.RUNTIME + "/" + mode + "/result.json")
        if actual.split(b" ", 1)[0].decode("ascii") != expected:
            raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: remote DC result changed")
    if operation == "deploy" or operation == "positive":
        v1._ssh("test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)
    else:
        v1._ssh(
            "test -s "
            + RUNTIME
            + "/positive/result.json && test ! -e "
            + RUNTIME
            + "/negative && test ! -L "
            + RUNTIME
            + "/negative"
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
        raise DifferentialDcScalarsError(
            "BLOCKED_UNCERTAIN_STATE: scalar operation reserved"
        ) from exc
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
            raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: scalar staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phaser-differential-dc-scalars-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: scalar manifest staging failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh"
        " && chmod 600 scalar_helper.py extract-positive.ocn"
        " extract-negative.ocn manifest.sha256"
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
    if mode not in DC_RESULTS:
        raise DifferentialDcScalarsError("DENY_OUT_OF_SCOPE: scalar mode not allowlisted")
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: scalar deployment not verified")
    _preflight(base_policy, mode)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    if mode == "negative":
        predecessor = parent._read_json(_record_path(state_root, "positive"))
        if (
            predecessor.get("state") != "succeeded"
            or predecessor.get("result_status") != "observed"
        ):
            raise DifferentialDcScalarsError(
                "BLOCKED_UNCERTAIN_STATE: positive scalar not observed"
            )
        remote = v1._ssh("sha256sum " + RUNTIME + "/positive/result.json")
        if remote.split(b" ", 1)[0].decode("ascii") != predecessor.get("raw_sha256"):
            raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: positive scalar changed")
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
        raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: scalar preflight changed")
    record = _reserve(state_root, mode, digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh " + mode, timeout=125)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DifferentialDcScalarsError(
            "BLOCKED_UNCERTAIN_STATE: invalid scalar response"
        ) from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_DIFFERENTIAL_DC_SCALARS_V1",
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
        raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: scalar response mismatch")
    values = payload.get("values_v")
    required = {"Vop", "Vom", "VDD", "Vp", "Vm", "output_common_mode_v", "output_diff_v"}
    if not isinstance(values, dict) or set(values) != required:
        raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: scalar set invalid")
    if any(
        not isinstance(n, (int, float)) or not math.isfinite(n) or abs(n) > 10
        for n in values.values()
    ):
        raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: nonfinite scalar")
    vp, vm = INPUTS[mode]
    if (
        abs(values["VDD"] - 1.0) > 1e-6
        or abs(values["Vp"] - vp) > 2e-7
        or abs(values["Vm"] - vm) > 2e-7
        or abs((values["Vp"] - values["Vm"]) - (vp - vm)) > 2e-7
        or abs(values["output_common_mode_v"] - (values["Vop"] + values["Vom"]) / 2) > 1e-9
        or abs(values["output_diff_v"] - (values["Vop"] - values["Vom"])) > 1e-9
    ):
        raise DifferentialDcScalarsError("BLOCKED_UNCERTAIN_STATE: scalar relationships invalid")
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
        print(
            "usage: phase_r_differential_dc_scalars_v1.py deploy|positive|negative",
            file=sys.stderr,
        )
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read(sys.argv[1])
    except (DifferentialDcScalarsError, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
