"""Fixed operator-only eight-pair qualification; immutable deployment and requests."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ade_pvt_prep as prep
import ade_qual as dc
import deploy_native_mcp_v1 as native
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
VERSION = "ade-pvt-qual-v1"
LOCAL = ROOT / "remote/phase-campaign" / VERSION
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/" + VERSION
JOBS = "/home/buet/cds_work/.cadence_mcp/" + VERSION + "-jobs"
POLICY = ROOT / "docs/policy/ADE_PVT_QUAL_V1.json"
DELEGATION = ROOT / ".codex/ade-pvt-qual-v1-delegation.json"
PLAN = ROOT / ".codex/ade-pvt-qual-v1-plan.json"
JOURNAL = ROOT / ".codex/ade-pvt-qual-v1-deploy.json"
FILES = ("run.sh", "helper.py", "netlist-dc.ocn", "netlist-ac.ocn", "extract-ac.ocn")
PAIRS = tuple(
    (corner, analysis) for corner in ("FF", "SS", "FS", "SF") for analysis in ("dc", "ac")
)
REFERENCE = ROOT / ".codex/ade-pvt-prep-pr97-merge-checkpoint.json"
PREFLIGHT = "00000000-0000-4000-8000-000000000000"


def save_bytes(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "ADE-PVT-QUAL-01",
        "parent_policy_sha256": parent,
        "remote_version": "phase-campaign/" + VERSION,
        "corners": ["FF", "SS", "FS", "SF"],
        "analyses": ["dc", "ac"],
        "source_saved_bias_values_v": [0.3, 0.65],
        "fixed_applied_bias_values_v": [0.32, 0.702],
        "source_saved_section": "NN",
        "temperature_c": 27,
        "vdd_constraint_v": 1.0,
        "ac": {"start_hz": 10, "stop_hz": 100000000, "dec": 10},
        "max_phase_spectre_attempts": 8,
        "max_spectre_attempts": 100,
        "baseline_counter": prep.COUNTER,
        "max_new_results_bytes": 5 * 1024**3,
        "reservation_bytes_per_job": 128 * 1024**2,
        "ledger": "existing_sim_mcp_v2_counter_no_reset",
        "reference_checkpoint_sha256": dc.digest(REFERENCE.read_bytes()),
        "model_manifest_sha256": "4a1fda45bb3738fc7253429903aee30b9c65f40439aee28f6cf22047178fd0d0",
        "eda_concurrency": 1,
        "elapsed_ceiling": None,
        "paid_resources": 0,
        "maximum_corrections_same_change": 3,
        "corrections_used": 0,
        "prior_corrections_preserved": {
            "dc": "5_of_6",
            "native_ac_tran": "3_of_3",
            "candidate": "1_of_3",
            "native_mcp": "1_of_3",
            "pvt_prep": "3_of_3",
        },
        "spec_evaluation": "not_evaluated",
        "nn_results": "preserved_no_rerun",
        "files": {name: dc.digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def authority() -> tuple[dict[str, Any], str]:
    parent = campaign._load_authority()
    prep.authority()
    checkpoint = campaign._read_json(REFERENCE)
    if checkpoint.get("pr") != 97 or checkpoint.get("state") != "complete":
        raise ValueError("prepared inventory not integrated")
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / name).is_symlink() for name in FILES):
        raise ValueError("corner policy or fixed source drift")
    digest = dc.digest(campaign._canonical(policy))
    if campaign._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "ADE-PVT-QUAL-01",
        "policy_sha256": digest,
        "parent_policy_sha256": parent,
        "user_delegation": "explicit-in-current-task",
        "user_reply": "proceed_ADE-PVT-QUAL-01",
    }:
        raise ValueError("explicit corner phase delegation absent")
    return policy, digest


def validate_plan(plan: Any, digest: str) -> list[dict[str, str]]:
    if (
        not isinstance(plan, dict)
        or set(plan) != {"policy_sha256", "jobs"}
        or plan["policy_sha256"] != digest
    ):
        raise ValueError("corner plan policy binding")
    jobs = plan["jobs"]
    if not isinstance(jobs, list) or len(jobs) != 8:
        raise ValueError("eight fixed corner jobs required")
    ids = set()
    for item, pair in zip(jobs, PAIRS, strict=True):
        if not isinstance(item, dict) or set(item) != {"job_id", "corner", "analysis"}:
            raise ValueError("corner job schema")
        job_id = item["job_id"]
        parsed = uuid.UUID(job_id)
        if str(parsed) != job_id or parsed.version != 4 or job_id in ids:
            raise ValueError("corner job UUID4 identity")
        if (item["corner"], item["analysis"]) != pair:
            raise ValueError("corner job allowlist and order")
        ids.add(job_id)
    return jobs


def jobs() -> list[dict[str, str]]:
    _, digest = authority()
    return validate_plan(campaign._read_json(PLAN), digest)


def deploy() -> dict[str, Any]:
    policy, digest = authority()
    jobs()
    stage = REMOTE + ".stage"
    native.ssh(
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
    before = native.postflight()
    if before["counter"] != prep.COUNTER or before["active_eda"] != 0:
        raise ValueError("corner initial budget checkpoint changed")
    dc.save_new(
        JOURNAL,
        {
            "state": "reserved",
            "policy_sha256": digest,
            "before": before,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    native.ssh("umask 077; mkdir -m 700 " + stage)
    for name in FILES:
        dc.command((*dc.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    manifest = ROOT / ".codex/ade-pvt-qual-v1-manifest.sha256"
    save_bytes(
        manifest, "".join(policy["files"][name] + "  " + name + "\n" for name in FILES).encode()
    )
    dc.command((*dc.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    native.ssh(
        "cd "
        + stage
        + " && sha256sum -c manifest.sha256 >/dev/null && bash -n run.sh"
        + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
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
        raise ValueError("deployment consumed simulator budget")
    result = {
        "state": "succeeded",
        "policy_sha256": digest,
        "manifest_sha256": dc.digest(manifest.read_bytes()),
        "postflight": after,
        "at": datetime.now(UTC).isoformat(),
    }
    campaign._replace_record(JOURNAL, result)
    return result


def run(action: str, index: int) -> dict[str, Any]:
    if action not in ("submit", "status", "result") or type(index) is not int or not 0 <= index < 8:
        raise ValueError("fixed corner operation")
    _, digest = authority()
    item = jobs()[index]
    journal = campaign._read_json(JOURNAL)
    if journal.get("state") != "succeeded" or journal.get("policy_sha256") != digest:
        raise ValueError("qualified corner deployment required")
    if action == "submit":
        for prior_index in range(index):
            previous = run("status", prior_index)
            if previous.get("state") != "succeeded":
                raise ValueError("preceding corner not completed; preserve checkpoint")
    response = dc.decode_result(
        native.ssh(
            REMOTE
            + "/run.sh "
            + action
            + " "
            + item["job_id"]
            + " "
            + item["analysis"]
            + " "
            + item["corner"],
            90,
        )
    )
    if action == "result":
        destination = ROOT / (".codex/ade-pvt-qual-v1-" + str(index) + "-result.json")
        data = campaign._canonical(response)
        if destination.exists():
            if destination.read_bytes() != data:
                raise ValueError("immutable local corner result drift")
        else:
            save_bytes(destination, data)
    return response


def postflight() -> dict[str, Any]:
    authority()
    existing = native.postflight()
    if existing["active_eda"] != 0:
        raise ValueError("active EDA checkpoint")
    return dc.decode_result(native.ssh(REMOTE + "/run.sh postflight " + PREFLIGHT + " dc FF"))


if __name__ == "__main__":
    try:
        if len(sys.argv) == 2 and sys.argv[1] in ("deploy", "postflight"):
            result = deploy() if sys.argv[1] == "deploy" else postflight()
        elif len(sys.argv) == 3:
            result = run(sys.argv[1], int(sys.argv[2]))
        else:
            raise ValueError("fixed operator arguments")
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
