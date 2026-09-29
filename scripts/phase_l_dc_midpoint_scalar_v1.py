"""Read the existing midpoint DC PSF without another Spectre attempt."""

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
import phase_f_dc_scalars_v1 as old_scalars
import phase_k_dc_midpoint_v1 as midpoint

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_L_DC_MIDPOINT_SCALAR_V1.json"
DELEGATION = ROOT / ".codex/phase-l-dc-midpoint-scalar-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/dc-midpoint-scalar-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-dc-midpoint-scalars-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/dc-midpoint-scalar-v1/run.sh",
    "scalar_helper.py": ROOT / "remote/phase-campaign/dc-midpoint-scalar-v1/scalar_helper.py",
    "extract.ocn": ROOT / "remote/phase-campaign/dc-midpoint-scalar-v1/extract.ocn",
}
OPERATIONS = {
    "deploy": "phasel-dc-midpoint-scalar-v1-deploy",
    "read": "phasel-dc-midpoint-scalar-v1-read",
}
MIDPOINT_POLICY_SHA256 = "754a0e625fb89aebb14f2048f0b699e41c7ef229edecfe9cb1a0316102f92589"
MIDPOINT_RESULT_SHA256 = "bed3104ed38375ea3328e3473691155d656a8ce2b95e105f9c0d5bce22bb03ac"
PRIOR_SCALARS_SHA256 = midpoint.SCALAR_RESULT_SHA256
PSF_SHA256 = "5b9dd83b5b2ce2fc3d5ead2800a3c9aa125c7799eada2defcc072f644735d506"


class DcMidpointScalarV1Error(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    base_policy, _base_digest, state_root = v1._authority()
    if dc_v2._counter(state_root) != 4:
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: Spectre count changed")
    midpoint_policy = parent._read_json(midpoint.POLICY)
    if _sha(v1._canonical(midpoint_policy)) != MIDPOINT_POLICY_SHA256:
        raise DcMidpointScalarV1Error("DENY_OUT_OF_SCOPE: midpoint policy changed")
    run_record = parent._read_json(midpoint._record_path(state_root, "run"))
    run_raw = state_root / (midpoint.OPERATIONS["run"] + ".output")
    if (
        run_record.get("state") != "succeeded"
        or run_record.get("policy_sha256") != MIDPOINT_POLICY_SHA256
        or run_record.get("result_status") != "dc_completed"
        or run_record.get("raw_sha256") != MIDPOINT_RESULT_SHA256
        or run_raw.is_symlink()
        or not run_raw.is_file()
        or _sha(run_raw.read_bytes()) != MIDPOINT_RESULT_SHA256
    ):
        raise DcMidpointScalarV1Error("DENY_OUT_OF_SCOPE: midpoint run changed")
    run = json.loads(run_raw.read_bytes())
    if (
        run.get("status") != "dc_completed"
        or run.get("psf_tree_sha256") != PSF_SHA256
        or run.get("psf_bytes") != 3971
        or run.get("spectre_errors") != 0
        or run.get("vdd_v") != 1.0
        or run.get("input_vcm_v") != 0.5
        or run.get("protected_and_copy_unchanged") is not True
    ):
        raise DcMidpointScalarV1Error("DENY_OUT_OF_SCOPE: midpoint evidence changed")
    old_record = parent._read_json(old_scalars._record_path(state_root, "read"))
    old_raw = state_root / (old_scalars.OPERATIONS["read"] + ".output")
    if (
        old_record.get("state") != "succeeded"
        or old_record.get("result_status") != "observed"
        or old_record.get("raw_sha256") != PRIOR_SCALARS_SHA256
        or old_raw.is_symlink()
        or not old_raw.is_file()
        or _sha(old_raw.read_bytes()) != PRIOR_SCALARS_SHA256
    ):
        raise DcMidpointScalarV1Error("DENY_OUT_OF_SCOPE: prior scalars changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": MIDPOINT_POLICY_SHA256,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/dc-midpoint-scalar-v1",
        "midpoint_result_sha256": MIDPOINT_RESULT_SHA256,
        "prior_scalar_result_sha256": PRIOR_SCALARS_SHA256,
        "source_fingerprint_sha256": midpoint_policy["source_fingerprint_sha256"],
        "copy_target_sha256": midpoint_policy["copy_target_sha256"],
        "state_tree_sha256": midpoint_policy["state_tree_sha256"],
        "model_sha256": midpoint_policy["model_sha256"],
        "psf_tree_sha256": PSF_SHA256,
        "psf_bytes": 3971,
        "spectre_attempt_count": 4,
        "new_simulation": False,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise DcMidpointScalarV1Error("DENY_OUT_OF_SCOPE: scalar policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": MIDPOINT_POLICY_SHA256,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise DcMidpointScalarV1Error("DENY_OUT_OF_SCOPE: scalar delegation absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise DcMidpointScalarV1Error("DENY_OUT_OF_SCOPE: local scalar bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(base_policy: dict[str, Any]) -> None:
    v1._remote_preflight(base_policy)
    v1._ssh("cd " + midpoint.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh(
        "set -e; test -d "
        + midpoint.RUNTIME
        + "/psf"
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
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: scalar operation reserved") from exc
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
            raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: scalar staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasel-dc-midpoint-scalar-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: scalar manifest staging failed")
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
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: scalar deployment not verified")
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
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: scalar preflight changed")
    record = _reserve(state_root, "read", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=125)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: invalid scalar response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_DC_MIDPOINT_SCALARS_V1",
        "status": "observed",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "psf_sha256": PSF_SHA256,
        "protected_and_results_unchanged": True,
        "simulation_run": False,
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in expected.items()
    ):
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: scalar response mismatch")
    values = payload.get("values_v")
    required = {"Vop", "Vom", "VDD", "Vp", "Vm", "output_common_mode_v", "output_diff_v"}
    if not isinstance(values, dict) or set(values) != required:
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: scalar set mismatch")
    if any(
        not isinstance(n, (int, float)) or not math.isfinite(n) or abs(n) > 10
        for n in values.values()
    ):
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: nonfinite scalar")
    if (
        abs(values["VDD"] - 1.0) > 1e-6
        or abs(values["Vp"] - 0.5) > 1e-6
        or abs(values["Vm"] - 0.5) > 1e-6
        or abs(values["output_common_mode_v"] - (values["Vop"] + values["Vom"]) / 2.0) > 1e-9
        or abs(values["output_diff_v"] - (values["Vop"] - values["Vom"])) > 1e-9
    ):
        raise DcMidpointScalarV1Error("BLOCKED_UNCERTAIN_STATE: scalar relationships invalid")
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
        print("usage: phase_l_dc_midpoint_scalar_v1.py deploy|read", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read()
    except (DcMidpointScalarV1Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
