"""Resume the pre-Spectre baseline claim, then run one fixed copied-cell candidate."""

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
import phase_e_copied_dc_v1 as previous

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_E_COPIED_DC_V2.json"
DELEGATION = ROOT / ".codex/phase-e-copied-dc-v2-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/dc-v2"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = previous.RUNTIME
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/dc-v2/run.sh",
    "dc_helper.py": ROOT / "remote/phase-campaign/dc-v2/dc_helper.py",
}
OPERATIONS = {
    "deploy": "phasee-copied-dc-v2-deploy",
    "resume-baseline": "phasee-copied-dc-v2-resume-baseline",
    "candidate": "phasee-copied-dc-v2-candidate",
}


class CopiedDcV2Error(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any], str]:
    old_policy, old_digest, state_root, base_policy = previous._authority()
    if old_digest != "b337ab3d91b9f90c45f09989deef902e9681b88cea42b3904529bb093a28c953":
        raise CopiedDcV2Error("DENY_OUT_OF_SCOPE: reviewed DC v1 policy changed")
    deployed = parent._read_json(previous._record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != old_digest:
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v1 DC deployment not verified")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/dc-v2",
        "v1_files": old_policy["files"],
        "source_fingerprint_sha256": old_policy["source_fingerprint_sha256"],
        "copy_target_sha256": old_policy["copy_target_sha256"],
        "netlist_tree_sha256": old_policy["netlist_tree_sha256"],
        "circuit_netlist_sha256": old_policy["circuit_netlist_sha256"],
        "model_sha256": old_policy["model_sha256"],
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "baseline_claim": previous.OPERATIONS["baseline"],
        "candidate_claim": previous.OPERATIONS["candidate"],
        "spectre_attempt_count_before_resume": 1,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise CopiedDcV2Error("DENY_OUT_OF_SCOPE: DC v2 policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise CopiedDcV2Error("DENY_OUT_OF_SCOPE: v2 delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise CopiedDcV2Error("DENY_OUT_OF_SCOPE: local v2 bytes changed")
    return policy, digest, state_root, base_policy, old_digest


def _counter(state_root: Path) -> int:
    value = parent._read_json(state_root / "phasee-copied-dc-v1-spectre-attempts.json")
    if value.get("campaign_id") != "AUTO-PHASE-01" or not isinstance(value.get("count"), int):
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: Spectre counter changed")
    return int(value["count"])


def _preflight(old_policy: dict[str, Any], base_policy: dict[str, Any]) -> None:
    previous._preflight(old_policy, base_policy)
    v1._ssh("cd " + previous.REMOTE_VERSION + " && sha256sum -c manifest.sha256")


def _baseline_pre_execution(state_root: Path, old_digest: str) -> None:
    claim = parent._read_json(previous._record_path(state_root, "baseline"))
    if claim.get("state") != "reserved" or claim.get("policy_sha256") != old_digest:
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: original baseline claim changed")
    if _counter(state_root) != 1:
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: baseline attempt counter changed")
    job = RUNTIME + "/baseline"
    v1._ssh(
        "set -e; test -d "
        + job
        + "; test ! -L "
        + job
        + "; test -f "
        + job
        + "/before.json; test ! -L "
        + job
        + '/before.json; test "$(stat -c %s '
        + job
        + '/before.json)" = 0'
        + '; test "$(find '
        + job
        + ' -mindepth 1 -maxdepth 1 | wc -l)" = 1'
        + "; test ! -e "
        + job
        + "/design-netlist.scs"
        + "; test ! -e "
        + job
        + "/profile.scs"
        + "; test ! -e "
        + job
        + "/spectre.log"
        + "; test ! -e "
        + job
        + "/attempt-status.txt"
        + "; test ! -e "
        + job
        + "/psf"
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
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v2 operation already reserved") from exc
    return path


def _finish(path: Path, value: dict[str, Any]) -> dict[str, Any]:
    parent._replace_record(path, value)
    return value


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def deploy() -> dict[str, Any]:
    policy, digest, state_root, base_policy, old_digest = _authority()
    _preflight(parent._read_json(previous.POLICY), base_policy)
    _baseline_pre_execution(state_root, old_digest)
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
            raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v2 staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasee-copied-dc-v2-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v2 manifest staging failed")
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


def _check_response(raw: bytes, mode: str, policy: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: invalid v2 DC response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_COPIED_DC_V1",
        "mode": mode,
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
        "model_sha256": policy["model_sha256"],
        "model_section": "NN",
        "temperature_c": 27,
        "vdd_v": 1.0,
        "input_vcm_v": 0.5,
        "bias_values_v": [0.300, 0.650] if mode == "baseline" else [0.320, 0.702],
        "protected_and_copy_unchanged": True,
        "simulation_run": True,
    }
    if not isinstance(payload, dict) or any(payload.get(k) != v for k, v in expected.items()):
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v2 DC response mismatch")
    if payload.get("status") not in ("dc_completed", "simulator_failed"):
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v2 DC status invalid")
    for key in ("wrapper_sha256", "psf_tree_sha256"):
        value = payload.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v2 DC digest invalid")
    if (
        not isinstance(payload.get("psf_bytes"), int)
        or not 0 < payload["psf_bytes"] <= 128 * 1024 * 1024
    ):
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v2 DC result bound invalid")
    return payload


def _persist_result(
    state_root: Path,
    mode: str,
    old_digest: str,
    v2_digest: str,
    raw: bytes,
    payload: dict[str, Any],
    claim: Path,
) -> dict[str, Any]:
    output = state_root / (previous.OPERATIONS[mode] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    value = {
        "state": "succeeded",
        "operation": previous.OPERATIONS[mode],
        "policy_sha256": old_digest,
        "result_status": payload["status"],
        "raw_sha256": _sha(raw),
        "raw_local_file": str(output),
        "executed_by_policy_sha256": v2_digest,
        "at": datetime.now(UTC).isoformat(),
    }
    parent._replace_record(claim, value)
    return value


def resume_baseline() -> dict[str, Any]:
    policy, digest, state_root, base_policy, old_digest = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v2 deployment not verified")
    _preflight(parent._read_json(previous.POLICY), base_policy)
    _baseline_pre_execution(state_root, old_digest)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    ready = json.loads(
        v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/dc_helper.py check baseline")
    )
    if ready != {
        "status": "ready",
        "mode": "baseline",
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
    }:
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: baseline resume preflight changed")
    own_record = _reserve(state_root, "resume-baseline", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh baseline-resume", timeout=170)
    payload = _check_response(raw, "baseline", policy)
    original = previous._record_path(state_root, "baseline")
    value = _persist_result(state_root, "baseline", old_digest, digest, raw, payload, original)
    _finish(
        own_record,
        {
            "state": "succeeded",
            "policy_sha256": digest,
            "result_status": payload["status"],
            "raw_sha256": _sha(raw),
        },
    )
    return value


def candidate() -> dict[str, Any]:
    policy, digest, state_root, base_policy, old_digest = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: v2 deployment not verified")
    baseline = parent._read_json(previous._record_path(state_root, "baseline"))
    baseline_output = state_root / (previous.OPERATIONS["baseline"] + ".output")
    if (
        baseline.get("state") != "succeeded"
        or baseline.get("policy_sha256") != old_digest
        or baseline.get("result_status") != "dc_completed"
        or baseline_output.is_symlink()
        or not baseline_output.is_file()
        or _sha(baseline_output.read_bytes()) != baseline.get("raw_sha256")
        or _counter(state_root) != 1
    ):
        raise CopiedDcV2Error("DENY_OUT_OF_SCOPE: baseline result not validated")
    baseline_payload = json.loads(baseline_output.read_bytes())
    if (
        baseline_payload.get("status") != "dc_completed"
        or baseline_payload.get("mode") != "baseline"
        or baseline_payload.get("protected_and_copy_unchanged") is not True
    ):
        raise CopiedDcV2Error("DENY_OUT_OF_SCOPE: baseline result changed")
    _preflight(parent._read_json(previous.POLICY), base_policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    ready = json.loads(
        v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/dc_helper.py check candidate")
    )
    if ready != {
        "status": "ready",
        "mode": "candidate",
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
    }:
        raise CopiedDcV2Error("BLOCKED_UNCERTAIN_STATE: candidate preflight changed")
    own_record = _reserve(state_root, "candidate", digest)
    original = previous._reserve(state_root, "candidate", old_digest)
    previous._increment_attempts(state_root)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh candidate", timeout=170)
    payload = _check_response(raw, "candidate", policy)
    if baseline_payload["psf_bytes"] + payload["psf_bytes"] > previous.MAX_RESULT_BYTES:
        raise CopiedDcV2Error("BUDGET_REACHED: 5 GiB new results")
    value = _persist_result(state_root, "candidate", old_digest, digest, raw, payload, original)
    _finish(
        own_record,
        {
            "state": "succeeded",
            "policy_sha256": digest,
            "result_status": payload["status"],
            "raw_sha256": _sha(raw),
        },
    )
    return value


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        print("usage: phase_e_copied_dc_v2.py deploy|resume-baseline|candidate", file=sys.stderr)
        return 2
    try:
        if sys.argv[1] == "deploy":
            result = deploy()
        elif sys.argv[1] == "resume-baseline":
            result = resume_baseline()
        else:
            result = candidate()
    except (CopiedDcV2Error, previous.CopiedDcV1Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
