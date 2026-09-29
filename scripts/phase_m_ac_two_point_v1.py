"""Two sequential fixed AC diagnostics on copied netlists for the WP-14 sweep."""

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
import phase_g_candidate_ac_v1 as candidate_ac
import phase_l_dc_midpoint_scalar_v1 as scalar

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_M_AC_TWO_POINT_V1.json"
DELEGATION = ROOT / ".codex/phase-m-ac-two-point-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/ac-sweep-two-point-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-ac-sweep-two-point-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/ac-sweep-two-point-v1/run.sh",
    "ac_helper.py": ROOT / "remote/phase-campaign/ac-sweep-two-point-v1/ac_helper.py",
}
OPERATIONS = {
    "deploy": "phasem-ac-two-point-v1-deploy",
    "baseline": "phasem-ac-two-point-v1-baseline",
    "midpoint": "phasem-ac-two-point-v1-midpoint",
}
MODES = {"baseline": [0.300, 0.650], "midpoint": [0.310, 0.676]}
PARENT_POLICY_SHA256 = "3611730a8e20ea679f9ddcf3e5c3a814245b37e5beac8160146ad5a697abc15e"
PRIOR_SCALAR_SHA256 = "9c6096a5bd14b8e6b3b302b340924093cbcfa4a84699be2533d62b769d79d368"
PRIOR_AC_SHA256 = "da959247b4034b2bf5bb3461c9356a1d9176e0b0a4ba36664e483b3a0df3d103"


class AcTwoPointV1Error(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _checked_raw(state_root: Path, operation_id: str, result_sha256: str) -> dict[str, Any]:
    record = parent._read_json(state_root / (operation_id + ".json"))
    raw_path = state_root / (operation_id + ".output")
    if (
        record.get("state") != "succeeded"
        or record.get("raw_sha256") != result_sha256
        or raw_path.is_symlink()
        or not raw_path.is_file()
        or _sha(raw_path.read_bytes()) != result_sha256
    ):
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: predecessor result changed")
    value: dict[str, Any] = json.loads(raw_path.read_bytes())
    if not isinstance(value, dict):
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: predecessor result malformed")
    return value


def _authority(operation: str) -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    if operation not in OPERATIONS:
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: AC operation not allowlisted")
    base_policy, _base_digest, state_root = v1._authority()
    count = dc_v2._counter(state_root)
    expected_count = 5 if operation == "midpoint" else 4
    if count != expected_count:
        raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: Spectre count changed")
    old_policy = parent._read_json(scalar.POLICY)
    if _sha(v1._canonical(old_policy)) != PARENT_POLICY_SHA256:
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: reviewed scalar policy changed")
    scalar_record = parent._read_json(scalar._record_path(state_root, "read"))
    if scalar_record.get("policy_sha256") != PARENT_POLICY_SHA256:
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: scalar predecessor policy changed")
    prior_scalar = _checked_raw(state_root, scalar.OPERATIONS["read"], PRIOR_SCALAR_SHA256)
    if prior_scalar.get("status") != "observed" or prior_scalar.get("simulation_run") is not False:
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: scalar predecessor status changed")
    prior_ac = _checked_raw(state_root, candidate_ac.OPERATIONS["run"], PRIOR_AC_SHA256)
    if prior_ac.get("status") != "ac_completed" or prior_ac.get("psf_bytes") != 4556:
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: candidate AC predecessor changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/ac-sweep-two-point-v1",
        "prior_scalar_result_sha256": PRIOR_SCALAR_SHA256,
        "candidate_ac_result_sha256": PRIOR_AC_SHA256,
        "source_fingerprint_sha256": old_policy["source_fingerprint_sha256"],
        "copy_target_sha256": old_policy["copy_target_sha256"],
        "netlist_tree_sha256": dc_v1.TREE_SHA256,
        "circuit_netlist_sha256": dc_v1.CIRCUIT_SHA256,
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "model_sha256": old_policy["model_sha256"],
        "bias_points_mv": [[300, 650], [310, 676]],
        "vdd_mv": 1000,
        "input_vcm_mv": 500,
        "input_ac_differential_mv": 1000,
        "frequencies_hz": [1000, 10000],
        "model_section": "NN",
        "temperature_c": 27,
        "spectre_attempt_count_before": 4,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: two-point AC policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: AC delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: local AC bytes changed")
    if operation == "midpoint":
        baseline_record = parent._read_json(_record_path(state_root, "baseline"))
        if (
            baseline_record.get("policy_sha256") != digest
            or baseline_record.get("result_status") != "ac_completed"
        ):
            raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: baseline AC not completed")
        baseline_sha = baseline_record.get("raw_sha256")
        if not isinstance(baseline_sha, str) or len(baseline_sha) != 64:
            raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: baseline AC digest invalid")
        baseline = _checked_raw(state_root, OPERATIONS["baseline"], baseline_sha)
        if baseline.get("mode") != "baseline" or baseline.get("status") != "ac_completed":
            raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: baseline AC result invalid")
    return policy, digest, state_root, base_policy


def _preflight(base_policy: dict[str, Any], operation: str) -> None:
    v1._remote_preflight(base_policy)
    v1._ssh("cd " + scalar.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    if operation in MODES:
        v1._ssh(
            "test ! -e " + RUNTIME + "/" + operation + " && test ! -L " + RUNTIME + "/" + operation
        )
    else:
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
        raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: AC operation reserved") from exc
    return path


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def deploy() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority("deploy")
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
            raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: AC staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasem-ac-two-point-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: AC manifest staging failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh && chmod 600 ac_helper.py manifest.sha256"
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


def run(mode: str) -> dict[str, Any]:
    if mode not in MODES:
        raise AcTwoPointV1Error("DENY_OUT_OF_SCOPE: AC mode not allowlisted")
    policy, digest, state_root, base_policy = _authority(mode)
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: AC deployment not verified")
    _preflight(base_policy, mode)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    if mode == "midpoint":
        baseline_record = parent._read_json(_record_path(state_root, "baseline"))
        remote_hash = v1._ssh("sha256sum " + RUNTIME + "/baseline/result.json")
        if remote_hash.split(b" ", 1)[0].decode("ascii") != baseline_record["raw_sha256"]:
            raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: remote baseline AC changed")
    ready = json.loads(v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/ac_helper.py check " + mode))
    if ready != {
        "status": "ready",
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
    }:
        raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: AC preflight changed")
    record = _reserve(state_root, mode, digest)
    dc_v1._increment_attempts(state_root)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh " + mode, timeout=170)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: invalid AC response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_TWO_POINT_AC_V1",
        "mode": mode,
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
        "model_sha256": policy["model_sha256"],
        "model_section": "NN",
        "temperature_c": 27,
        "vdd_v": 1.0,
        "input_vcm_v": 0.5,
        "bias_values_v": MODES[mode],
        "input_ac_differential_v": 1.0,
        "frequencies_hz": [1000, 10000],
        "protected_and_copy_unchanged": True,
        "simulation_run": True,
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in expected.items()
    ):
        raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: AC response mismatch")
    if payload.get("status") not in ("ac_completed", "simulator_failed"):
        raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: AC status invalid")
    for key in ("wrapper_sha256", "psf_tree_sha256"):
        value = payload.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise AcTwoPointV1Error("BLOCKED_UNCERTAIN_STATE: AC digest invalid")
    result_bytes = payload.get("psf_bytes")
    if not isinstance(result_bytes, int) or not 0 < result_bytes <= 128 * 1024 * 1024:
        raise AcTwoPointV1Error("BUDGET_REACHED: AC result bound")
    for operation_id in (
        dc_v1.OPERATIONS["baseline"],
        dc_v1.OPERATIONS["candidate"],
        candidate_ac.OPERATIONS["run"],
        "phasek-dc-midpoint-v1-run",
    ):
        prior_raw = state_root / (operation_id + ".output")
        result_bytes += int(json.loads(prior_raw.read_bytes())["psf_bytes"])
    if mode == "midpoint":
        prior_raw = state_root / (OPERATIONS["baseline"] + ".output")
        result_bytes += int(json.loads(prior_raw.read_bytes())["psf_bytes"])
    if result_bytes > dc_v1.MAX_RESULT_BYTES:
        raise AcTwoPointV1Error("BUDGET_REACHED: 5 GiB results")
    output = state_root / (OPERATIONS[mode] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    value = {
        "state": "succeeded",
        "operation": OPERATIONS[mode],
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
        print("usage: phase_m_ac_two_point_v1.py deploy|baseline|midpoint", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else run(sys.argv[1])
    except (AcTwoPointV1Error, v1.PhaseBError, parent.CampaignError, dc_v1.CopiedDcV1Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
