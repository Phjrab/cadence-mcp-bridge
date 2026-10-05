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
VERSION = "/home/buet/cds_work/.cadence_mcp/phase-campaign/storage-mgmt-v6"
CONTROL = "/home/buet/cds_work/.cadence_mcp/storage-mgmt-v1"
SPOOL = "/home/buet/cds_work/.cadence_mcp/storage-disposable-v1"
POLICY = ROOT / "docs/policy/STORAGE_MGMT_V1.json"
CORRECTION = ROOT / "docs/policy/PHASE_CORRECTION_LIMIT_V5.json"
SCAN = ROOT / "docs/policy/STORAGE_SCAN_V2.json"
FILES = {
    "run.sh": ROOT / "remote/phase-campaign/storage-mgmt-v6/run.sh",
    "worker.py": ROOT / "src/cadence_mcp_bridge/_storage_worker.py",
    "policy.json": POLICY,
    "correction.json": CORRECTION,
    "scan.json": SCAN,
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
    scan = campaign._read_json(SCAN)
    if scan != {
        "contract_version": 2,
        "phase": "STORAGE-MGMT-01",
        "parent_storage_policy_sha256": io.digest(campaign._canonical(policy)),
        "registered_groups": 6,
        "max_nodes_per_group": 8192,
        "max_scan_nodes": 49152,
        "max_artifacts": 64,
        "max_response_bytes": 65536,
        "max_payload_hash_bytes": 67108864,
        "same_fixed_root_scope": True,
        "incomplete_coverage_delete_denied": True,
        "maximum_new_simulations": 0,
        "refund_cumulative_reservations": False,
    }:
        raise ValueError("fixed group scan policy drift")
    correction = campaign._read_json(CORRECTION)
    if correction != {
        "schema_version": 5,
        "campaign_id": "AUTO-PHASE-01",
        "repository": "Phjrab/cadence-mcp-bridge",
        "maximum_corrections_same_change": 20,
        "preserve_consumed_corrections": True,
        "preserve_prior_policy_and_failure_evidence": True,
        "preserve_other_limits": True,
        "historical_delete_authority": False,
        "parent_campaign_policy_sha256": io.digest(campaign.POLICY.read_bytes()),
    }:
        raise ValueError("correction overlay drift")
    extra_path = PRIVATE / "phase-correction-limit-v5-delegation.private.json"
    extra = campaign._read_json(extra_path)
    if extra != {
        "schema_version": 5,
        "campaign_id": "AUTO-PHASE-01",
        "repository": "Phjrab/cadence-mcp-bridge",
        "policy_sha256": io.digest(campaign._canonical(correction)),
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "repository_correction_limit_20",
        "consumed_history_preserved": True,
    }:
        raise ValueError("explicit correction-limit authority absent")
    if any(b"\r" in FILES[n].read_bytes() for n in ("run.sh", "worker.py")):
        raise ValueError("guest sources require LF bytes")
    expected = {
        "contract_version": 3,
        "phase": "STORAGE-MGMT-01",
        "policy_sha256": io.digest(campaign._canonical(policy)),
        "correction_sha256": io.digest(campaign._canonical(correction)),
        "scan_sha256": io.digest(campaign._canonical(scan)),
        "extra_authority_sha256": io.digest(extra_path.read_bytes()),
        "files": {n: io.digest(p.read_bytes()) for n, p in FILES.items()},
        "user_delegation": "explicit-phase-development-no-historical-deletion",
        "maximum_new_simulations": 0,
    }
    if campaign._read_json(PRIVATE / "storage-mgmt-v6-delegation.private.json") != expected:
        raise ValueError("exact storage phase delegation absent")
    return expected


def deploy() -> dict[str, Any]:
    delegation = authority()
    journal = PRIVATE / "storage-mgmt-v6-deploy.private.json"
    io.save_new(journal, {"state": "reserved", "delegation": delegation})
    stage = VERSION + ".stage"
    for target in (VERSION, stage):
        transport.ssh("test ! -e " + target + " && test ! -L " + target)
    transport.ssh(
        "test -d "
        + CONTROL
        + " && test ! -L "
        + CONTROL
        + " && test -d "
        + SPOOL
        + " && test ! -L "
        + SPOOL
        + " && test -d "
        + CONTROL
        + "/registrations"
        + " && test -d "
        + CONTROL
        + "/approvals"
        + " && test -d "
        + CONTROL
        + "/operations"
    )
    transport.ssh("umask 077; mkdir -m 700 " + stage)
    activation = PRIVATE / "storage-mgmt-v6-activation.private.json"
    io.save_new(activation, {k: v for k, v in delegation.items() if k != "files"})
    files = {**FILES, "activation.private.json": activation}
    manifest = PRIVATE / "storage-mgmt-v6-manifest.private.sha256"
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
