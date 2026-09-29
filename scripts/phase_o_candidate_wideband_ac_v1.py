"""One fixed wideband AC characterization on the copied WP-14 candidate netlist."""

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
import phase_k_dc_midpoint_v1 as midpoint_dc
import phase_m_ac_two_point_v1 as two_ac
import phase_n_ac_two_point_scalars_v1 as scalars

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_O_CANDIDATE_WIDEBAND_AC_V1.json"
DELEGATION = ROOT / ".codex/phase-o-candidate-wideband-ac-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/candidate-wideband-ac-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-candidate-wideband-ac-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/candidate-wideband-ac-v1/run.sh",
    "ac_helper.py": ROOT / "remote/phase-campaign/candidate-wideband-ac-v1/ac_helper.py",
}
OPERATIONS = {
    "deploy": "phaseo-candidate-wideband-ac-v1-deploy",
    "run": "phaseo-candidate-wideband-ac-v1-run",
}
PARENT_POLICY_SHA256 = "95881250a68414cfeef9f27cd00df874f2fe9d765456c9b8b027dc520a42319d"
SCALAR_RESULTS = {
    "baseline": "416e6607affef803a87892a314d59733b0b5e839d86410926c08eb3c7476bce4",
    "midpoint": "e1a6cefaf68d3bd73008bba35e57ab59bc70919f5bb64b8e7894e1cf304b632f",
}


class CandidateWidebandAcError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = scalars._authority()
    if old_digest != PARENT_POLICY_SHA256 or dc_v2._counter(state_root) != 6:
        raise CandidateWidebandAcError("BLOCKED_UNCERTAIN_STATE: parent or Spectre count changed")
    for mode, expected_sha in SCALAR_RESULTS.items():
        record = parent._read_json(scalars._record_path(state_root, mode))
        raw = state_root / (scalars.OPERATIONS[mode] + ".output")
        if (
            record.get("state") != "succeeded"
            or record.get("policy_sha256") != old_digest
            or record.get("result_status") != "observed"
            or record.get("raw_sha256") != expected_sha
            or raw.is_symlink()
            or not raw.is_file()
            or _sha(raw.read_bytes()) != expected_sha
        ):
            raise CandidateWidebandAcError("DENY_OUT_OF_SCOPE: AC scalar predecessor changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/candidate-wideband-ac-v1",
        "prior_scalar_result_sha256": SCALAR_RESULTS,
        "source_fingerprint_sha256": old_policy["source_fingerprint_sha256"],
        "copy_target_sha256": old_policy["copy_target_sha256"],
        "netlist_tree_sha256": dc_v1.TREE_SHA256,
        "circuit_netlist_sha256": dc_v1.CIRCUIT_SHA256,
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "model_sha256": old_policy["model_sha256"],
        "candidate_bias_mv": [320, 702],
        "vdd_mv": 1000,
        "input_vcm_mv": 500,
        "input_ac_differential_mv": 1000,
        "frequency_start_hz": 10,
        "frequency_stop_hz": 100000000,
        "points_per_decade": 10,
        "model_section": "NN",
        "temperature_c": 27,
        "spectre_attempt_count_before": 6,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise CandidateWidebandAcError("DENY_OUT_OF_SCOPE: wideband AC policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise CandidateWidebandAcError("DENY_OUT_OF_SCOPE: wideband delegation absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise CandidateWidebandAcError("DENY_OUT_OF_SCOPE: local wideband bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(base_policy: dict[str, Any]) -> None:
    v1._remote_preflight(base_policy)
    v1._ssh("cd " + scalars.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
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
        raise CandidateWidebandAcError(
            "BLOCKED_UNCERTAIN_STATE: wideband operation reserved"
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
            raise CandidateWidebandAcError("BLOCKED_UNCERTAIN_STATE: wideband staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phaseo-candidate-wideband-ac-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise CandidateWidebandAcError("BLOCKED_UNCERTAIN_STATE: wideband manifest staging failed")
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


def run() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise CandidateWidebandAcError("BLOCKED_UNCERTAIN_STATE: wideband deployment unverified")
    _preflight(base_policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    ready = json.loads(v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/ac_helper.py check"))
    if ready != {
        "status": "ready",
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
    }:
        raise CandidateWidebandAcError("BLOCKED_UNCERTAIN_STATE: wideband preflight changed")
    record = _reserve(state_root, "run", digest)
    dc_v1._increment_attempts(state_root)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=170)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CandidateWidebandAcError(
            "BLOCKED_UNCERTAIN_STATE: invalid wideband response"
        ) from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_CANDIDATE_WIDEBAND_AC_V1",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": policy["circuit_netlist_sha256"],
        "model_sha256": policy["model_sha256"],
        "model_section": "NN",
        "temperature_c": 27,
        "vdd_v": 1.0,
        "input_vcm_v": 0.5,
        "bias_values_v": [0.320, 0.702],
        "input_ac_differential_v": 1.0,
        "frequency_start_hz": 10,
        "frequency_stop_hz": 100000000,
        "points_per_decade": 10,
        "protected_and_copy_unchanged": True,
        "simulation_run": True,
    }
    if not isinstance(payload, dict) or any(payload.get(k) != v for k, v in expected.items()):
        raise CandidateWidebandAcError("BLOCKED_UNCERTAIN_STATE: wideband response mismatch")
    if payload.get("status") not in ("ac_completed", "simulator_failed"):
        raise CandidateWidebandAcError("BLOCKED_UNCERTAIN_STATE: wideband status invalid")
    for key in ("wrapper_sha256", "psf_tree_sha256"):
        value = payload.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise CandidateWidebandAcError("BLOCKED_UNCERTAIN_STATE: wideband digest invalid")
    result_bytes = payload.get("psf_bytes")
    if not isinstance(result_bytes, int) or not 0 < result_bytes <= 128 * 1024 * 1024:
        raise CandidateWidebandAcError("BUDGET_REACHED: wideband result bound")
    for operation in (
        dc_v1.OPERATIONS["baseline"],
        dc_v1.OPERATIONS["candidate"],
        midpoint_dc.OPERATIONS["run"],
        candidate_ac.OPERATIONS["run"],
        two_ac.OPERATIONS["baseline"],
        two_ac.OPERATIONS["midpoint"],
    ):
        prior = json.loads((state_root / (operation + ".output")).read_bytes())
        result_bytes += int(prior["psf_bytes"])
    if result_bytes > dc_v1.MAX_RESULT_BYTES:
        raise CandidateWidebandAcError("BUDGET_REACHED: 5 GiB results")
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
        print("usage: phase_o_candidate_wideband_ac_v1.py deploy|run", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else run()
    except (
        CandidateWidebandAcError,
        scalars.AcTwoPointScalarsError,
        v1.PhaseBError,
        parent.CampaignError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
