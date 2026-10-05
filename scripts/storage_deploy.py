"""Operator-only immutable storage deployment, with exact private phase authority."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import ade_qual as io
import deploy_native_mcp_v1 as transport
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".codex"
VERSION = "/home/buet/cds_work/.cadence_mcp/phase-campaign/storage-mgmt-v2"
CONTROL = "/home/buet/cds_work/.cadence_mcp/storage-mgmt-v1"
SPOOL = "/home/buet/cds_work/.cadence_mcp/storage-disposable-v1"
POLICY = ROOT / "docs/policy/STORAGE_MGMT_V1.json"
CORRECTION = ROOT / "docs/policy/STORAGE_MGMT_CORRECTION_V2.json"
FILES = {
    "run.sh": ROOT / "remote/phase-campaign/storage-mgmt-v2/run.sh",
    "worker.py": ROOT / "src/cadence_mcp_bridge/_storage_worker.py",
    "policy.json": POLICY,
    "correction.json": CORRECTION,
}


def expected_policy() -> dict[str, Any]:
    return {
        "contract_version": 1,
        "phase": "STORAGE-MGMT-01",
        "parent_result_policy_sha256": (
            "851567cae8e50a6dbfe95ed8d1276f4b11a944d7038b72f72358d721b947b0e2"
        ),
        "max_artifacts": 64,
        "max_nodes": 8192,
        "max_depth": 16,
        "max_payload_hash_bytes": 64 * 1024**2,
        "max_selection": 16,
        "max_spectre_attempts": 500,
        "max_result_reserved_bytes": 10 * 1024**3,
        "elapsed_ceiling": None,
        "eda_concurrency": 1,
        "disk_floor_bytes": 2 * 1024**3,
        "disk_floor_percent": 10,
        "reservation_bytes_per_job": 128 * 1024**2,
        "historical_results_default": "protected_replay_evidence",
        "delete_scope": "registered_isolated_intermediate_single_payload_leaf",
        "delete_authority": "explicit_selected_plan_items_operator_record",
        "refund_cumulative_reservations": False,
        "compaction": False,
        "maximum_new_simulations": 0,
        "maximum_corrections_same_change": 3,
    }


def authority() -> dict[str, Any]:
    campaign._load_authority()
    policy = campaign._read_json(POLICY)
    if policy != expected_policy() or any(p.is_symlink() for p in FILES.values()):
        raise ValueError("storage policy/source drift")
    correction = campaign._read_json(CORRECTION)
    if correction != {
        "contract_version": 2,
        "phase": "STORAGE-MGMT-01",
        "parent_storage_policy_sha256": io.digest(campaign._canonical(policy)),
        "maximum_corrections_same_change": 4,
        "original_corrections_consumed": 3,
        "additional_corrections": 1,
        "deployment_version": "storage-mgmt-v2",
        "preserve_failed_v1_stage": True,
        "same_control_spool_identity_domain": True,
        "maximum_new_simulations": 0,
        "historical_delete_authority": False,
    }:
        raise ValueError("correction overlay drift")
    extra = campaign._read_json(PRIVATE / "storage-mgmt-extra-correction-delegation.private.json")
    if (
        extra.get("phase") != "STORAGE-MGMT-01"
        or extra.get("user_authorization")
        != "explicit-continue-after-one-extra-correction-request"
        or extra.get("maximum_corrections") != 4
        or extra.get("additional_corrections") != 1
        or extra.get("historical_delete_authority") is not False
        or extra.get("original_execution_seal_sha256")
        != io.digest((PRIVATE / "storage-mgmt-execution-seal.private.json").read_bytes())
    ):
        raise ValueError("explicit extra correction authority absent")
    if any(b"\r" in FILES[n].read_bytes() for n in ("run.sh", "worker.py")):
        raise ValueError("guest sources require LF bytes")
    expected = {
        "contract_version": 2,
        "phase": "STORAGE-MGMT-01",
        "policy_sha256": io.digest(campaign._canonical(policy)),
        "correction_sha256": io.digest(campaign._canonical(correction)),
        "extra_authority_sha256": io.digest(
            (PRIVATE / "storage-mgmt-extra-correction-delegation.private.json").read_bytes()
        ),
        "files": {n: io.digest(p.read_bytes()) for n, p in FILES.items()},
        "user_delegation": "explicit-phase-development-no-historical-deletion",
        "maximum_new_simulations": 0,
    }
    if campaign._read_json(PRIVATE / "storage-mgmt-v2-delegation.private.json") != expected:
        raise ValueError("exact storage phase delegation absent")
    return expected


def deploy() -> dict[str, Any]:
    delegation = authority()
    journal = PRIVATE / "storage-mgmt-v2-deploy.private.json"
    io.save_new(journal, {"state": "reserved", "delegation": delegation})
    stage = VERSION + ".stage"
    for target in (VERSION, stage, CONTROL, SPOOL):
        transport.ssh("test ! -e " + target + " && test ! -L " + target)
    transport.ssh("umask 077; mkdir -m 700 " + stage)
    activation = PRIVATE / "storage-mgmt-v2-activation.private.json"
    io.save_new(activation, {k: v for k, v in delegation.items() if k != "files"})
    files = {**FILES, "activation.private.json": activation}
    manifest = PRIVATE / "storage-mgmt-v2-manifest.private.sha256"
    with manifest.open("xb") as stream:
        stream.write(
            "".join(io.digest(p.read_bytes()) + "  " + n + "\n" for n, p in files.items()).encode(
                "ascii"
            )
        )
    for name, source in {**files, "manifest.sha256": manifest}.items():
        io.command((*io.SCP, str(source), "cadence-vm:" + stage + "/" + name))
    transport.ssh(
        "cd "
        + stage
        + " && sha256sum -c manifest.sha256 >/dev/null"
        + " && bash -n run.sh && /usr/bin/python -c "
        + '\'compile(open("worker.py","rb").read(),"worker","exec")\''
        + " && chmod 700 run.sh && chmod 600 worker.py *.json manifest.sha256"
        + " && mv "
        + stage
        + " "
        + VERSION
        + " && mkdir -m 700 "
        + CONTROL
        + " "
        + SPOOL
        + " && mkdir -m 700 "
        + CONTROL
        + "/registrations "
        + CONTROL
        + "/approvals "
        + CONTROL
        + "/operations"
    )
    value = {
        "state": "deployed",
        "policy_sha256": delegation["policy_sha256"],
        "payload_bytes": sum(p.stat().st_size for p in files.values()),
        "new_simulations": 0,
        "deleted_artifacts": 0,
    }
    campaign._replace_record(journal, value)
    return value


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "deploy":
        raise SystemExit("usage: storage_deploy.py deploy")
    try:
        print(json.dumps(deploy()))
    except Exception:
        print(json.dumps({"state": "blocked_or_uncertain", "automatic_retry": False}))
        raise
