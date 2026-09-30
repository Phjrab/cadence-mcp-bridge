"""Journaled immutable deployment; reuses the campaign's existing ledger."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ade_qual as dc
import native_candidate as candidate
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/native-mcp-v1"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/native-mcp-v1"
JOBS = "/home/buet/cds_work/.cadence_mcp/native-mcp-v1-jobs"
POLICY = ROOT / "docs/policy/NATIVE_MCP_V1.json"
DELEGATION = ROOT / ".codex/native-mcp-v1-delegation.json"
JOURNAL = ROOT / ".codex/native-mcp-v1-deploy.json"
REFERENCE = ROOT / ".codex/native-candidate-01-result-v1.json"
REFERENCE_SHA = "8fccdd046961894e45a9788074b815839ec466892cae558fcd6ab716ebec5c88"
FILES = (
    "run.sh",
    "helper.py",
    "netlist-dc.ocn",
    "netlist-ac.ocn",
    "netlist-tran.ocn",
    "extract-ac.ocn",
    "extract-tran.ocn",
)
PREFLIGHT_ID = "00000000-0000-4000-8000-000000000000"


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "change_id": "NATIVE-MCP-01",
        "parent_policy_sha256": parent,
        "remote_version": "phase-campaign/native-mcp-v1",
        "reference_result_sha256": REFERENCE_SHA,
        "revision_id": "wp14-native-ade-v1",
        "analyses": ["dc", "ac", "tran"],
        "operating_point_id": "candidate-320-702mv-v1",
        "source_saved_bias_values_v": [0.3, 0.65],
        "fixed_applied_bias_values_v": [0.32, 0.702],
        "vdd_constraint_v": 1.0,
        "section": "NN",
        "temperature_c": 27,
        "ac": {"start_hz": 10, "stop_hz": 100000000, "dec": 10},
        "tran": {"stop_s": 0.004, "maxstep_s": 1e-5, "method": "trap"},
        "max_spectre_attempts": 100,
        "max_new_results_bytes": 5 * 1024**3,
        "reservation_bytes_per_job": 128 * 1024**2,
        "baseline_spectre_attempts": 21,
        "baseline_result_reserved_bytes": 1611661312,
        "ledger": "existing_sim_mcp_v2_counter_no_reset",
        "eda_concurrency": 1,
        "elapsed_ceiling": None,
        "maximum_corrections_same_change": 3,
        "corrections_used": 0,
        "prior_corrections_preserved": {
            "dc": "5_of_6",
            "native_ac_tran": "3_of_3",
            "candidate": "1_of_3",
        },
        "spec_evaluation": "not_evaluated",
        "paid_resources": 0,
        "files": {name: dc.digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def authority() -> tuple[dict[str, Any], str]:
    parent = campaign._load_authority()
    candidate.authority()
    if REFERENCE.is_symlink() or dc.digest(REFERENCE.read_bytes()) != REFERENCE_SHA:
        raise ValueError("preserved native candidate result changed")
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / name).is_symlink() for name in FILES):
        raise ValueError("native MCP policy or deployment bytes changed")
    digest = dc.digest(campaign._canonical(policy))
    if campaign._read_json(DELEGATION) != {
        "schema_version": 1,
        "change_id": "NATIVE-MCP-01",
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "policy_sha256": digest,
        "reference_result_sha256": REFERENCE_SHA,
        "user_delegation": "explicit-in-current-task",
        "user_selection": "proceed_native_dc_ac_tran_mcp_integration",
    }:
        raise ValueError("native MCP phase delegation absent")
    return policy, digest


def ssh(command: str, timeout: int = 90) -> bytes:
    return dc.command((*dc.SSH, command), timeout)


def postflight() -> dict[str, Any]:
    authority()
    return dc.decode_result(ssh(REMOTE + "/run.sh postflight " + PREFLIGHT_ID + " dc"))


def deploy() -> dict[str, Any]:
    policy, digest = authority()
    stage = REMOTE + ".stage"
    ssh(
        "test ! -e "
        + REMOTE
        + " && test ! -L "
        + REMOTE
        + " && test ! -e "
        + stage
        + " && test ! -L "
        + stage
        + " && test ! -e "
        + JOBS
        + " && test ! -L "
        + JOBS
    )
    before = candidate.run("postflight")
    if before["counter"]["count"] != 21 or before["active_eda"] != 0:
        raise ValueError("native MCP initial campaign checkpoint changed")
    dc.save_new(
        JOURNAL,
        {
            "state": "reserved",
            "policy_sha256": digest,
            "before": before,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    ssh("umask 077; mkdir -m 700 " + stage)
    for name in FILES:
        dc.command((*dc.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    manifest = ROOT / ".codex/native-mcp-v1-manifest.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(policy["files"][name] + "  " + name + "\n" for name in FILES).encode())
    dc.command((*dc.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    ssh(
        "cd "
        + stage
        + " && sha256sum -c manifest.sha256 >/dev/null && bash -n run.sh"
        + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
        + " && /usr/bin/python helper.py preflight "
        + PREFLIGHT_ID
        + " dc"
        + " && chmod 700 run.sh helper.py && chmod 600 *.ocn manifest.sha256 && mv "
        + stage
        + " "
        + REMOTE
        + " && mkdir -m 700 "
        + JOBS,
        120,
    )
    after = postflight()
    if after["counter"] != before["counter"]:
        raise ValueError("deployment unexpectedly changed cumulative counter")
    result = {
        "state": "succeeded",
        "policy_sha256": digest,
        "manifest_sha256": dc.digest(manifest.read_bytes()),
        "postflight": after,
        "at": datetime.now(UTC).isoformat(),
    }
    campaign._replace_record(JOURNAL, result)
    return result


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("deploy", "postflight"):
            raise ValueError("usage: deploy_native_mcp_v1.py deploy|postflight")
        print(json.dumps(deploy() if sys.argv[1] == "deploy" else postflight(), sort_keys=True))
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
