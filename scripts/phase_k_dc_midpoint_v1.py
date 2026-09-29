"""One fixed DC midpoint between two already observed copied-cell settings."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import phase_b_role_campaign as v1
import phase_campaign as parent
import phase_e_copied_dc_v1 as dc_v1
import phase_e_copied_dc_v2 as dc_v2
import phase_f_dc_scalars_v1 as scalars
import phase_g_candidate_ac_v1 as ac
import phase_h_ac_scalars_v1 as ac_v1
import phase_i_ac_scalars_v2 as ac_v2
import phase_j_ac_scalar_recover as prior

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_K_DC_MIDPOINT_V1.json"
DELEGATION = ROOT / ".codex/phase-k-dc-midpoint-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/dc-midpoint-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-dc-midpoint-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/dc-midpoint-v1/run.sh",
    "dc_helper.py": ROOT / "remote/phase-campaign/dc-midpoint-v1/dc_helper.py",
}
OPERATIONS = {"deploy": "phasek-dc-midpoint-v1-deploy", "run": "phasek-dc-midpoint-v1-run"}
SCALAR_RESULT_SHA256 = "9c95e9ead00c4339632afcc5f672f9edefc5eef417ebbc4be9a1436f2633ed79"
PRIOR_AC_RECOVERY_SHA256 = "6b0b87e4dc56b255673250d35e006babe6c8f8413390d54cc03453203617e051"
AC_RESULT_SHA256 = "da959247b4034b2bf5bb3461c9356a1d9176e0b0a4ba36664e483b3a0df3d103"
PARENT_POLICY_SHA256 = "dd50ce4074c2a7848aba42a8ad97b508dd892361da39576d1ebce86d7cbcf0bf"


class DcMidpointV1Error(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = prior._authority()
    if old_digest != PARENT_POLICY_SHA256:
        raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: reviewed AC recovery policy changed")
    if dc_v2._counter(state_root) != 3:
        raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: Spectre count changed")
    prior_record = parent._read_json(state_root / (prior.OPERATION + ".json"))
    prior_raw = state_root / (prior.OPERATION + ".output")
    if (
        prior_record.get("state") != "succeeded"
        or prior_record.get("policy_sha256") != old_digest
        or prior_record.get("result_status") != "observed"
        or prior_record.get("raw_sha256") != PRIOR_AC_RECOVERY_SHA256
        or prior_raw.is_symlink()
        or not prior_raw.is_file()
        or _sha(prior_raw.read_bytes()) != PRIOR_AC_RECOVERY_SHA256
    ):
        raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: prior AC recovery changed")
    read = parent._read_json(scalars._record_path(state_root, "read"))
    raw_path = state_root / (scalars.OPERATIONS["read"] + ".output")
    if (
        read.get("state") != "succeeded"
        or read.get("result_status") != "observed"
        or read.get("raw_sha256") != SCALAR_RESULT_SHA256
        or raw_path.is_symlink()
        or not raw_path.is_file()
        or _sha(raw_path.read_bytes()) != SCALAR_RESULT_SHA256
    ):
        raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: prior scalar result changed")
    candidate = parent._read_json(dc_v1._record_path(state_root, "candidate"))
    if (
        candidate.get("state") != "succeeded"
        or candidate.get("policy_sha256")
        != "b337ab3d91b9f90c45f09989deef902e9681b88cea42b3904529bb093a28c953"
        or candidate.get("result_status") != "dc_completed"
        or candidate.get("raw_sha256") != scalars.RESULT_HASHES["candidate"]
    ):
        raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: candidate DC result changed")
    for mode in ("baseline", "candidate"):
        dc_raw = state_root / (dc_v1.OPERATIONS[mode] + ".output")
        if (
            dc_raw.is_symlink()
            or not dc_raw.is_file()
            or _sha(dc_raw.read_bytes()) != scalars.RESULT_HASHES[mode]
        ):
            raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: prior DC bytes changed")
    ac_record = parent._read_json(ac._record_path(state_root, "run"))
    ac_raw = state_root / (ac.OPERATIONS["run"] + ".output")
    if (
        ac_record.get("state") != "succeeded"
        or ac_record.get("result_status") != "ac_completed"
        or ac_record.get("raw_sha256") != AC_RESULT_SHA256
        or ac_raw.is_symlink()
        or not ac_raw.is_file()
        or _sha(ac_raw.read_bytes()) != AC_RESULT_SHA256
    ):
        raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: prior AC result changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/dc-midpoint-v1",
        "scalar_result_sha256": SCALAR_RESULT_SHA256,
        "dc_result_sha256": scalars.RESULT_HASHES,
        "prior_ac_recovery_sha256": PRIOR_AC_RECOVERY_SHA256,
        "ac_result_sha256": AC_RESULT_SHA256,
        "source_fingerprint_sha256": old_policy["source_fingerprint_sha256"],
        "copy_target_sha256": old_policy["copy_target_sha256"],
        "netlist_tree_sha256": dc_v1.TREE_SHA256,
        "circuit_netlist_sha256": dc_v1.CIRCUIT_SHA256,
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "model_sha256": old_policy["model_sha256"],
        "sweep_points_mv": [[300, 650], [310, 676], [320, 702]],
        "midpoint_bias_mv": [310, 676],
        "vdd_mv": 1000,
        "input_vcm_mv": 500,
        "model_section": "NN",
        "temperature_c": 27,
        "spectre_attempt_count_before": 3,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: midpoint DC policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: DC delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: local DC bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(policy: dict[str, Any], base_policy: dict[str, Any]) -> None:
    dc_v1._preflight(parent._read_json(dc_v1.POLICY), base_policy)
    v1._ssh("cd " + dc_v2.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)
    if policy["spectre_attempt_count_before"] != 3:
        raise DcMidpointV1Error("DENY_OUT_OF_SCOPE: attempt bound changed")


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
        raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: DC midpoint operation reserved") from exc
    return path


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
            raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: DC staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasek-dc-midpoint-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: DC manifest staging failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh && chmod 600 dc_helper.py manifest.sha256"
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


def run() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: DC deployment not verified")
    _preflight(policy, base_policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    ready = json.loads(v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/dc_helper.py check"))
    if ready != {
        "status": "ready",
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
    }:
        raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: DC preflight changed")
    record = _reserve(state_root, "run", digest)
    dc_v1._increment_attempts(state_root)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=170)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: invalid DC response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_DC_MIDPOINT_V1",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
        "model_sha256": policy["model_sha256"],
        "model_section": "NN",
        "temperature_c": 27,
        "vdd_v": 1.0,
        "input_vcm_v": 0.5,
        "bias_values_v": [0.310, 0.676],
        "protected_and_copy_unchanged": True,
        "simulation_run": True,
    }
    if not isinstance(payload, dict) or any(payload.get(k) != v for k, v in expected.items()):
        raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: DC response mismatch")
    if payload.get("status") not in ("dc_completed", "simulator_failed"):
        raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: DC status invalid")
    for key in ("wrapper_sha256", "psf_tree_sha256"):
        value = payload.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise DcMidpointV1Error("BLOCKED_UNCERTAIN_STATE: DC digest invalid")
    result_bytes = payload.get("psf_bytes")
    if not isinstance(result_bytes, int) or not 0 < result_bytes <= 128 * 1024 * 1024:
        raise DcMidpointV1Error("BUDGET_REACHED: DC result bound")
    for mode in ("baseline", "candidate"):
        old_raw = state_root / (dc_v1.OPERATIONS[mode] + ".output")
        old_result = json.loads(old_raw.read_bytes())
        result_bytes += int(old_result["psf_bytes"])
    ac_raw = state_root / (ac.OPERATIONS["run"] + ".output")
    result_bytes += int(json.loads(ac_raw.read_bytes())["psf_bytes"])
    if result_bytes > dc_v1.MAX_RESULT_BYTES:
        raise DcMidpointV1Error("BUDGET_REACHED: 5 GiB results")
    output = state_root / (OPERATIONS["run"] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    value = {
        "state": "succeeded",
        "operation": OPERATIONS["run"],
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
        print("usage: phase_k_dc_midpoint_v1.py deploy|run", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else run()
    except (
        DcMidpointV1Error,
        prior.AcScalarRecoveryError,
        ac_v2.AcScalarsV2Error,
        ac_v1.AcScalarsV1Error,
        dc_v2.CopiedDcV2Error,
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
