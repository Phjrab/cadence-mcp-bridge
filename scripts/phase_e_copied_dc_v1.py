"""Two fixed, journaled Spectre DC attempts from the current WP-14 work copy."""

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
import phase_d_netlist_v1 as netlist

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_E_COPIED_DC_V1.json"
DELEGATION = ROOT / ".codex/phase-e-copied-dc-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/dc-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-copied-dc-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/dc-v1/run.sh",
    "dc_helper.py": ROOT / "remote/phase-campaign/dc-v1/dc_helper.py",
}
OPERATIONS = {
    "deploy": "phasee-copied-dc-v1-deploy",
    "baseline": "phasee-copied-dc-v1-baseline",
    "candidate": "phasee-copied-dc-v1-candidate",
}
NETLIST_RESULT_SHA256 = "6cdc8ca9c365210c79afcc42a562da8b929e1492f932b6fe9a85b430fac12713"
CIRCUIT_SHA256 = "6189aa9d647671c05a9f03d815530697560c00b661cad95c87f7f415d482192a"
TREE_SHA256 = "dce155df486c1bb70f3cfd4282f6a002031696b92e0754d78e4d8ed10dfc2387"
MAX_RESULT_BYTES = 5 * 1024**3


class CopiedDcV1Error(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, mode: str) -> Path:
    return state_root / (OPERATIONS[mode] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = netlist._authority()
    if old_digest != "2a30bda217d363a27b49b7a799b3df1fba371d80757ba333e2f57bba5d334c41":
        raise CopiedDcV1Error("DENY_OUT_OF_SCOPE: reviewed netlist policy changed")
    deployed = parent._read_json(state_root / "phased-netlist-v1-deploy.json")
    observed = parent._read_json(state_root / "phased-netlist-v1-run.json")
    if (
        deployed.get("state") != "succeeded"
        or deployed.get("policy_sha256") != old_digest
        or observed.get("state") != "succeeded"
        or observed.get("policy_sha256") != old_digest
        or observed.get("result_status") != "netlisted"
        or observed.get("raw_sha256") != NETLIST_RESULT_SHA256
    ):
        raise CopiedDcV1Error("DENY_OUT_OF_SCOPE: copied netlist evidence absent")
    old_raw = state_root / "phased-netlist-v1-run.output"
    if (
        old_raw.is_symlink()
        or not old_raw.is_file()
        or _sha(old_raw.read_bytes()) != NETLIST_RESULT_SHA256
    ):
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: netlist evidence bytes changed")
    old_payload = json.loads(old_raw.read_bytes())
    if (
        not isinstance(old_payload, dict)
        or old_payload.get("status") != "netlisted"
        or old_payload.get("circuit_netlist_sha256") != CIRCUIT_SHA256
        or old_payload.get("netlist_tree_sha256") != TREE_SHA256
        or old_payload.get("target_sha256") != netlist.TARGET_SHA256
        or old_payload.get("protected_and_copy_unchanged") is not True
        or old_payload.get("simulation_run") is not False
    ):
        raise CopiedDcV1Error("DENY_OUT_OF_SCOPE: netlist result contract changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/dc-v1",
        "source_fingerprint_sha256": base_policy["source_fingerprint_sha256"],
        "installed_preflight_helper_sha256": base_policy["installed_preflight_helper_sha256"],
        "netlist_files": old_policy["files"],
        "netlist_result_sha256": NETLIST_RESULT_SHA256,
        "copy_target_sha256": netlist.TARGET_SHA256,
        "netlist_tree_sha256": TREE_SHA256,
        "circuit_netlist_sha256": CIRCUIT_SHA256,
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "model_sha256": old_policy["model_sha256"],
        "profile_sha256": old_policy["profile_sha256"],
        "baseline_bias_mv": [300, 650],
        "candidate_bias_mv": [320, 702],
        "vdd_mv": 1000,
        "input_vcm_mv": 500,
        "model_section": "NN",
        "temperature_c": 27,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise CopiedDcV1Error("DENY_OUT_OF_SCOPE: copied DC policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise CopiedDcV1Error("DENY_OUT_OF_SCOPE: DC delegation binding absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise CopiedDcV1Error("DENY_OUT_OF_SCOPE: local DC bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(policy: dict[str, Any], base_policy: dict[str, Any]) -> None:
    v1._remote_preflight(base_policy)
    v1._ssh("cd " + netlist.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    snapshot = json.loads(
        v1._ssh(
            "/usr/bin/python " + v1.REMOTE_VERSION + "/wp14_role_discovery.py preflight", timeout=90
        )
    )
    protected = snapshot.get("protected", {})
    if (
        protected.get("ade_state_tree") != policy["state_tree_sha256"]
        or protected.get("pdk_model_file") != policy["model_sha256"]
        or protected.get("fixed_profile_registry") != policy["profile_sha256"]
        or snapshot.get("locks") != []
    ):
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC protected baseline changed")
    v1._ssh(
        "set -e; test -f /home/buet/cds_work/.cadence_mcp/wp14-copied-netlist-v1/"
        "project/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist/netlist"
        "; test ! -L " + REMOTE_ROOT + "/run.lock"
        "; if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 69; fi"
    )


def _reserve(state_root: Path, mode: str, digest: str) -> Path:
    path = _record_path(state_root, mode)
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(
                {"state": "reserved", "policy_sha256": digest, "at": datetime.now(UTC).isoformat()},
                stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC operation already reserved") from exc
    return path


def _increment_attempts(state_root: Path) -> None:
    path = state_root / "phasee-copied-dc-v1-spectre-attempts.json"
    count = 0
    if path.exists():
        value = parent._read_json(path)
        if value.get("campaign_id") != "AUTO-PHASE-01" or not isinstance(value.get("count"), int):
            raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: Spectre counter changed")
        count = value["count"]
    if count < 0 or count >= 100:
        raise CopiedDcV1Error("BUDGET_REACHED: 100 Spectre attempts")
    parent._replace_record(path, {"campaign_id": "AUTO-PHASE-01", "count": count + 1})


def _manifest(policy: dict[str, Any]) -> bytes:
    return "".join(policy["files"][name] + "  " + name + "\n" for name in LOCAL_FILES).encode(
        "ascii"
    )


def deploy() -> dict[str, Any]:
    policy, digest, state_root, base_policy = _authority()
    _preflight(policy, base_policy)
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
            raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phasee-copied-dc-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC manifest staging failed")
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
    result = {
        "state": "succeeded",
        "operation": OPERATIONS["deploy"],
        "policy_sha256": digest,
        "manifest_sha256": _sha(manifest),
        "at": datetime.now(UTC).isoformat(),
    }
    parent._replace_record(record, result)
    return result


def run(mode: str) -> dict[str, Any]:
    if mode not in ("baseline", "candidate"):
        raise CopiedDcV1Error("DENY_OUT_OF_SCOPE: fixed mode only")
    policy, digest, state_root, base_policy = _authority()
    deployed = parent._read_json(_record_path(state_root, "deploy"))
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC deployment not verified")
    if mode == "candidate":
        baseline = parent._read_json(_record_path(state_root, "baseline"))
        baseline_raw = state_root / (OPERATIONS["baseline"] + ".output")
        if (
            baseline.get("state") != "succeeded"
            or baseline.get("policy_sha256") != digest
            or baseline.get("result_status") != "dc_completed"
            or baseline_raw.is_symlink()
            or not baseline_raw.is_file()
            or _sha(baseline_raw.read_bytes()) != baseline.get("raw_sha256")
        ):
            raise CopiedDcV1Error("DENY_OUT_OF_SCOPE: baseline DC not completed")
        baseline_payload = json.loads(baseline_raw.read_bytes())
        if (
            baseline_payload.get("status") != "dc_completed"
            or baseline_payload.get("mode") != "baseline"
            or baseline_payload.get("protected_and_copy_unchanged") is not True
        ):
            raise CopiedDcV1Error("DENY_OUT_OF_SCOPE: baseline DC evidence changed")
    _preflight(policy, base_policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    readiness = json.loads(
        v1._ssh("/usr/bin/python " + REMOTE_VERSION + "/dc_helper.py check " + mode)
    )
    if readiness != {
        "status": "ready",
        "mode": mode,
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": CIRCUIT_SHA256,
    }:
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC readiness changed")
    record = _reserve(state_root, mode, digest)
    _increment_attempts(state_root)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh " + mode, timeout=170)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: invalid DC response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_COPIED_DC_V1",
        "mode": mode,
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "netlist_sha256": CIRCUIT_SHA256,
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
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC response contract mismatch")
    if payload.get("status") not in ("dc_completed", "simulator_failed"):
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC status invalid")
    for key in ("wrapper_sha256", "psf_tree_sha256"):
        value = payload.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC digest invalid")
    if (
        not isinstance(payload.get("psf_bytes"), int)
        or payload["psf_bytes"] <= 0
        or payload["psf_bytes"] > 128 * 1024 * 1024
    ):
        raise CopiedDcV1Error("BLOCKED_UNCERTAIN_STATE: DC result bound invalid")
    prior_bytes = 0
    if mode == "candidate":
        prior_bytes = baseline_payload["psf_bytes"]
    if prior_bytes + payload["psf_bytes"] > MAX_RESULT_BYTES:
        raise CopiedDcV1Error("BUDGET_REACHED: 5 GiB new results")
    output = state_root / (OPERATIONS[mode] + ".output")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    result = {
        "state": "succeeded",
        "operation": OPERATIONS[mode],
        "policy_sha256": digest,
        "result_status": payload["status"],
        "raw_sha256": _sha(raw),
        "raw_local_file": str(output),
        "at": datetime.now(UTC).isoformat(),
    }
    parent._replace_record(record, result)
    return result


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
        print("usage: phase_e_copied_dc_v1.py deploy|baseline|candidate", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else run(sys.argv[1])
    except (CopiedDcV1Error, netlist.NetlistV1Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
