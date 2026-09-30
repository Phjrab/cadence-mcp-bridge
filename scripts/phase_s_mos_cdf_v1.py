"""Read fixed MOS instance CDF metadata without saving OA or exposing PDK content."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import phase_b_oa_facts_v7 as oa
import phase_b_role_campaign as v1
import phase_campaign as parent
import phase_e_copied_dc_v2 as dc_v2
import phase_r_differential_dc_scalars_v1 as scalars

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_S_MOS_CDF_V1.json"
DELEGATION = ROOT / ".codex/phase-s-mos-cdf-v1-delegation.json"
REMOTE_ROOT = v1.REMOTE_ROOT
REMOTE_VERSION = REMOTE_ROOT + "/phase-campaign/mos-cdf-v1"
REMOTE_STAGE = REMOTE_VERSION + ".stage"
RUNTIME = REMOTE_ROOT + "/wp14-mos-cdf-v1"
LOCAL_FILES = {
    "run.sh": ROOT / "remote/phase-campaign/mos-cdf-v1/run.sh",
    "cdf_helper.py": ROOT / "remote/phase-campaign/mos-cdf-v1/cdf_helper.py",
    "mos-cdf-v1.il": ROOT / "remote/phase-campaign/mos-cdf-v1/mos-cdf-v1.il",
}
OPERATIONS = {
    "deploy": "phases-mos-cdf-v1-deploy",
    "read": "phases-mos-cdf-v1-read",
}
PARENT_POLICY_SHA256 = "3b6dfa5fad1a8ce2aa76ddd2acfda0e2868373760fd3cb80e65d61377fb399fc"
OA_FACTS_SHA256 = "aceff81c134c47275fdffca1479b77e4190fda649f2749f79c0a520be4033c11"
SCALAR_SHA256 = {
    "positive": "d1deaa7d28f65c3737c3349f7d768f65155895050913cdf317cd2392f4c569c3",
    "negative": "2c8a38d866e6423316d937c60d1fa6548a6c7d6ac0ac55e28cd8e60e135405ea",
}


class MosCdfV1Error(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_path(state_root: Path, operation: str) -> Path:
    return state_root / (OPERATIONS[operation] + ".json")


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    base_policy, _base_digest, state_root = v1._authority()
    if dc_v2._counter(state_root) != 9:
        raise MosCdfV1Error("BLOCKED_UNCERTAIN_STATE: Spectre count changed")
    prior_policy = parent._read_json(scalars.POLICY)
    if _sha(v1._canonical(prior_policy)) != PARENT_POLICY_SHA256:
        raise MosCdfV1Error("DENY_OUT_OF_SCOPE: scalar parent policy changed")
    for mode, expected_sha in SCALAR_SHA256.items():
        record = parent._read_json(scalars._record_path(state_root, mode))
        raw = state_root / (scalars.OPERATIONS[mode] + ".output")
        if (
            record.get("state") != "succeeded"
            or record.get("policy_sha256") != PARENT_POLICY_SHA256
            or record.get("result_status") != "observed"
            or record.get("raw_sha256") != expected_sha
            or raw.is_symlink()
            or not raw.is_file()
            or _sha(raw.read_bytes()) != expected_sha
        ):
            raise MosCdfV1Error("DENY_OUT_OF_SCOPE: scalar predecessor changed")
    oa_record = parent._read_json(oa._record_path(state_root, "read"))
    oa_raw = state_root / (oa.OPERATIONS["read"] + ".output")
    if (
        oa_record.get("state") != "succeeded"
        or oa_record.get("result_status") != "observed"
        or oa_record.get("raw_sha256") != OA_FACTS_SHA256
        or oa_raw.is_symlink()
        or not oa_raw.is_file()
        or _sha(oa_raw.read_bytes()) != OA_FACTS_SHA256
    ):
        raise MosCdfV1Error("DENY_OUT_OF_SCOPE: OA predecessor changed")
    facts = json.loads(oa_raw.read_bytes())
    masters = [
        (item["master_lib"], item["master_cell"])
        for item in facts["instances"].values()
    ]
    if (
        masters.count(("gpdk090", "nmos1v")) != 8
        or masters.count(("gpdk090", "pmos1v")) != 6
        or facts.get("source_sha256") != prior_policy["source_fingerprint_sha256"]
    ):
        raise MosCdfV1Error("DENY_OUT_OF_SCOPE: OA MOS inventory changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "operation_ids": list(OPERATIONS.values()),
        "remote_root": REMOTE_ROOT,
        "remote_version": "phase-campaign/mos-cdf-v1",
        "prior_scalar_result_sha256": SCALAR_SHA256,
        "oa_facts_result_sha256": OA_FACTS_SHA256,
        "source_fingerprint_sha256": prior_policy["source_fingerprint_sha256"],
        "state_tree_sha256": prior_policy["state_tree_sha256"],
        "model_sha256": prior_policy["model_sha256"],
        "mos_master_counts": {"nmos1v": 8, "pmos1v": 6},
        "cdf_parameter_names": [
            "w", "l", "m", "nf", "fw", "width", "length", "fingers", "totalWidth"
        ],
        "spectre_attempt_count": 9,
        "new_simulation": False,
        "files": {name: _sha(path.read_bytes()) for name, path in LOCAL_FILES.items()},
    }
    if policy != expected:
        raise MosCdfV1Error("DENY_OUT_OF_SCOPE: CDF policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": PARENT_POLICY_SHA256,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise MosCdfV1Error("DENY_OUT_OF_SCOPE: CDF delegation absent")
    for name, path in LOCAL_FILES.items():
        if (
            path.is_symlink()
            or not path.is_file()
            or _sha(path.read_bytes()) != policy["files"][name]
        ):
            raise MosCdfV1Error("DENY_OUT_OF_SCOPE: local CDF bytes changed")
    return policy, digest, state_root, base_policy


def _preflight(base_policy: dict[str, Any]) -> None:
    v1._remote_preflight(base_policy)
    v1._ssh("cd " + scalars.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh("cd " + oa.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh(
        "set -e; test ! -e "
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
        raise MosCdfV1Error("BLOCKED_UNCERTAIN_STATE: CDF operation reserved") from exc
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
            raise MosCdfV1Error("BLOCKED_UNCERTAIN_STATE: CDF staging failed")
    manifest = _manifest(policy)
    local_manifest = state_root / "phases-mos-cdf-v1-manifest.sha256"
    with local_manifest.open("xb") as stream:
        stream.write(manifest)
        stream.flush()
        os.fsync(stream.fileno())
    copied = v1._command(
        (*v1.SCP, str(local_manifest), "cadence-vm:" + REMOTE_STAGE + "/manifest.sha256"),
        timeout=90,
    )
    if copied.returncode:
        raise MosCdfV1Error("BLOCKED_UNCERTAIN_STATE: CDF manifest staging failed")
    v1._ssh(
        "cd " + REMOTE_STAGE + " && sha256sum -c manifest.sha256"
        " && chmod 700 run.sh && chmod 600 cdf_helper.py mos-cdf-v1.il manifest.sha256"
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
        raise MosCdfV1Error("BLOCKED_UNCERTAIN_STATE: CDF deployment not verified")
    _preflight(base_policy)
    v1._ssh("cd " + REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    for mode, expected_sha in SCALAR_SHA256.items():
        remote = v1._ssh("sha256sum " + scalars.RUNTIME + "/" + mode + "/result.json")
        if remote.split(b" ", 1)[0].decode("ascii") != expected_sha:
            raise MosCdfV1Error("BLOCKED_UNCERTAIN_STATE: remote scalar changed")
    record = _reserve(state_root, "read", digest)
    raw = v1._ssh(REMOTE_VERSION + "/run.sh", timeout=135)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MosCdfV1Error("BLOCKED_UNCERTAIN_STATE: invalid CDF response") from exc
    expected = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_MOS_CDF_INVENTORY_V1",
        "status": "observed",
        "source_sha256": policy["source_fingerprint_sha256"],
        "state_tree_sha256": policy["state_tree_sha256"],
        "protected_fingerprints_unchanged": True,
        "locks_unchanged": True,
        "simulation_run": False,
    }
    if not isinstance(payload, dict) or any(
        payload.get(key) != value for key, value in expected.items()
    ):
        raise MosCdfV1Error("BLOCKED_UNCERTAIN_STATE: CDF response mismatch")
    instances = payload.get("instances")
    counts = payload.get("topology_counts")
    if (
        not isinstance(instances, dict)
        or len(instances) != 14
        or not isinstance(counts, list)
        or counts[:3] != [35, 14, 14]
        or not isinstance(payload.get("parameter_count"), int)
        or not 0 <= payload["parameter_count"] <= 126
    ):
        raise MosCdfV1Error("BLOCKED_UNCERTAIN_STATE: CDF inventory invalid")
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
        print("usage: phase_s_mos_cdf_v1.py deploy|read", file=sys.stderr)
        return 2
    try:
        result = deploy() if sys.argv[1] == "deploy" else read()
    except (MosCdfV1Error, v1.PhaseBError, parent.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
