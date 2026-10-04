"""Fixed journaled deployment of the explicitly delegated 500-attempt adapter."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ade_pvt_diag as diag
import ade_qual as dc
import deploy_native_mcp_v1 as previous
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/native-mcp-v2"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/native-mcp-v2"
LIMIT = ROOT / "docs/policy/PHASE_SPECTRE_LIMIT_V3.json"
LIMIT_SHA = "b534b0ade1d17c75cfa711911feca6b8625f2662dde91c621a60fb1fa43d9a8b"
POLICY = ROOT / "docs/policy/NATIVE_MCP_V2.json"
DELEGATION = ROOT / ".codex/native-mcp-v2-delegation.json"
JOURNAL = ROOT / ".codex/native-mcp-v2-deploy.json"
FILES = previous.FILES


def activation() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "change_id": "SPECTRE-LIMIT-500-01",
        "policy_sha256": LIMIT_SHA,
        "user_delegation": "explicit-in-current-task",
    }


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "change_id": "SPECTRE-LIMIT-500-01",
        "parent_policy_sha256": parent,
        "spectre_limit_policy_sha256": LIMIT_SHA,
        "remote_version": "phase-campaign/native-mcp-v2",
        "replay_domain": "existing_native_mcp_v1_jobs_no_reset",
        "ledger": "existing_sim_mcp_v2_counter_no_reset",
        "baseline_counter": diag.COUNTER,
        "new_spectre_attempts": 0,
        "max_spectre_attempts": 500,
        "max_new_results_bytes": 5 * 1024**3,
        "reservation_bytes_per_job": 128 * 1024**2,
        "elapsed_ceiling": None,
        "maximum_corrections_same_change": 3,
        "corrections_used": 0,
        "prior_corrections": "all_preserved_no_reset",
        "request_and_result_contracts": "unchanged_fixed_nn_320_702mv_dc_ac_tran",
        "files": {name: dc.digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def authority() -> tuple[dict[str, Any], str]:
    parent = campaign._load_authority()
    diag.authority()
    previous.authority()
    limit = campaign._read_json(LIMIT)
    if dc.digest(campaign._canonical(limit)) != LIMIT_SHA:
        raise ValueError("explicit Spectre-only ceiling policy drift")
    if campaign._read_json(ROOT / ".codex/phase-spectre-limit-v3-delegation.json") != activation():
        raise ValueError("user Spectre ceiling delegation missing")
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / name).is_symlink() for name in FILES):
        raise ValueError("versioned budget adapter bytes drift")
    digest = dc.digest(campaign._canonical(policy))
    if campaign._read_json(DELEGATION) != {
        **activation(),
        "deployment_policy_sha256": digest,
        "user_selection": "proceed_bias_headroom_preparation_and_raise_spectre_total_to_500",
    }:
        raise ValueError("budget adapter deployment delegation missing")
    return policy, digest


def postflight() -> dict[str, Any]:
    authority()
    protected = diag.run("postflight")
    native = dc.decode_result(
        previous.ssh(REMOTE + "/run.sh postflight " + previous.PREFLIGHT_ID + " dc")
    )
    if (
        native["counter"] != diag.COUNTER
        or protected["counter"] != diag.COUNTER
        or native["active_eda"] != 0
        or not native["protected_unchanged"]
        or not native["reference_results_unchanged"]
    ):
        raise ValueError("budget migration changed protected state or cumulative use")
    return {"native": native, "protected_corner_jobs": protected}


def deploy() -> dict[str, Any]:
    policy, digest = authority()
    before = diag.run("postflight")
    if before["counter"] != diag.COUNTER:
        raise ValueError("budget migration baseline drift")
    dc.save_new(
        JOURNAL,
        {
            "state": "reserved",
            "policy_sha256": digest,
            "before": before,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    stage = REMOTE + ".stage"
    previous.ssh(
        "test ! -e "
        + REMOTE
        + " && test ! -L "
        + REMOTE
        + " && test ! -e "
        + stage
        + " && test ! -L "
        + stage
    )
    previous.ssh("umask 077; mkdir -m 700 " + stage)
    for name in FILES:
        dc.command((*dc.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    private = ROOT / ".codex"
    manifest = private / "native-mcp-v2-manifest.sha256"
    activated = private / "native-mcp-v2-activation.private.json"
    dc.save_new(activated, activation())
    extra = {
        "budget-policy.json": (LIMIT, dc.digest(LIMIT.read_bytes())),
        "activation.private.json": (activated, dc.digest(activated.read_bytes())),
    }
    for name, (source, _) in extra.items():
        dc.command((*dc.SCP, str(source), "cadence-vm:" + stage + "/" + name))
    encoded = "".join(policy["files"][name] + "  " + name + "\n" for name in FILES)
    encoded += "".join(digest + "  " + name + "\n" for name, (_, digest) in extra.items())
    with manifest.open("xb") as stream:
        stream.write(encoded.encode())
    dc.command((*dc.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    previous.ssh(
        "cd "
        + stage
        + " && sha256sum -c manifest.sha256 >/dev/null && bash -n run.sh"
        + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
        + " && chmod 700 helper.py run.sh && chmod 600 *.ocn *.json manifest.sha256"
        + " && mv "
        + stage
        + " "
        + REMOTE
    )
    after = postflight()
    result = {
        "state": "succeeded",
        "policy_sha256": digest,
        "after": after,
        "manifest_sha256": dc.digest(manifest.read_bytes()),
    }
    campaign._replace_record(JOURNAL, result)
    return result


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("deploy", "postflight"):
            raise ValueError("fixed budget adapter action required")
        print(json.dumps(deploy() if sys.argv[1] == "deploy" else postflight(), sort_keys=True))
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
