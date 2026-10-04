"""Journaled finite four-pair native execution inside the selected improvement phase."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import ade_pvt_diag as diag
import ade_qual as dc
import bias_headroom_plan as planning
import deploy_native_mcp_v1 as previous
import phase_campaign as campaign
import spectre_limit as budget

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/bias-headroom-v1"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/bias-headroom-v1"
JOBS_REMOTE = "/home/buet/cds_work/.cadence_mcp/bias-headroom-v1-jobs"
POLICY = ROOT / "docs/policy/BIAS_HEADROOM_RUN_V1.json"
DELEGATION = ROOT / ".codex/bias-headroom-v1-delegation.json"
JOBS = ROOT / ".codex/bias-headroom-v1-jobs.private.json"
SELECTION = ROOT / ".codex/bias-headroom-v1-selection.private.json"
FILES = ("helper.py", "run.sh", "netlist-dc.ocn", "netlist-ac.ocn", "extract-ac.ocn")
ZERO = "00000000-0000-4000-8000-000000000000"


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "BIAS-HEADROOM-01",
        "parent_policy_sha256": parent,
        "budget_policy_sha256": budget.LIMIT_SHA,
        "plan_sha256": dc.digest((ROOT / ".codex/bias-headroom-plan-v1.private.json").read_bytes()),
        "jobs_manifest_sha256": dc.digest(JOBS.read_bytes()),
        "baseline_counter": diag.COUNTER,
        "pairs_mv": [list(p) for p in planning.PAIRS_MV],
        "remote_version": "phase-campaign/bias-headroom-v1",
        "maximum_new_spectre_attempts": 16,
        "max_spectre_attempts": 500,
        "max_new_results_bytes": 5 * 1024**3,
        "reservation_bytes_per_job": 128 * 1024**2,
        "maximum_corrections_same_change": 3,
        "corrections_used": 0,
        "prior_corrections": "all_preserved_no_reset",
        "eda_concurrency": 1,
        "elapsed_ceiling": None,
        "paid_resources": 0,
        "vdd_constraint_v": 1.0,
        "temperature_c": 27,
        "original_candidate_mv": [320, 702],
        "spec_evaluation": "not_evaluated",
        "fields": diag.FIELDS,
        "selection": "strict_FF_and_FS_headroom_improvement_then_worst_case_rank",
        "files": {name: dc.digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def authority() -> tuple[dict[str, Any], str]:
    parent = campaign._load_authority()
    budget.authority()
    plan = campaign._read_json(ROOT / ".codex/bias-headroom-plan-v1.private.json")
    if plan != planning.run():
        raise ValueError("bounded bias plan or preserved evidence drift")
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / f).is_symlink() for f in FILES):
        raise ValueError("bias policy or source bytes drift")
    digest = dc.digest(campaign._canonical(policy))
    if campaign._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "BIAS-HEADROOM-01",
        "parent_policy_sha256": parent,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
        "user_selection": "proceed_recommended_bias_improvement_plan_and_candidate_validation",
    }:
        raise ValueError("selected bounded bias phase delegation absent")
    return policy, digest


def request(index: int) -> dict[str, Any]:
    manifest = campaign._read_json(JOBS)
    rows = manifest.get("jobs")
    if (
        not isinstance(rows, list)
        or len(rows) != 16
        or type(index) is not int
        or not 0 <= index < 16
    ):
        raise ValueError("sixteen fixed private job slots")
    row = dict(rows[index])
    if (
        set(row) != {"job_id", "corner", "analysis", "pair_index"}
        or UUID(row["job_id"]).version != 4
        or str(UUID(row["job_id"])) != row["job_id"]
    ):
        raise ValueError("fixed bias job identity")
    if index < 8:
        if (row["pair_index"], row["corner"], row["analysis"]) != (
            index // 2,
            ("FF", "FS")[index % 2],
            "dc",
        ):
            raise ValueError("screen slot binding")
    else:
        if row["pair_index"] is not None:
            raise ValueError("follow-up pair must come from preserved measurements")
        selected = campaign._read_json(SELECTION)
        if (
            selected.get("policy_sha256") != authority()[1]
            or selected.get("spec_evaluation") != "not_evaluated"
        ):
            raise ValueError("selection policy lineage drift")
        selected_pair: Any = selected["selected_pair_index"]
        if type(selected_pair) is not int or selected_pair not in range(4):
            raise ValueError("no measured improvement candidate")
        row["pair_index"] = selected_pair
        expected = (
            (("NN", "SS", "SF")[index - 8], "dc")
            if index < 11
            else (("NN", "FF", "SS", "FS", "SF")[index - 11], "ac")
        )
        if (row["corner"], row["analysis"]) != expected:
            raise ValueError("follow-up slot binding")
    return row


def fixed_command(action: str, row: dict[str, Any]) -> str:
    if (
        action not in ("submit", "status", "result")
        or str(UUID(row["job_id"])) != row["job_id"]
        or UUID(row["job_id"]).version != 4
        or row["analysis"] not in ("dc", "ac")
        or row["corner"] not in ("NN", "FF", "SS", "FS", "SF")
        or type(row["pair_index"]) is not int
        or row["pair_index"] not in range(4)
    ):
        raise ValueError("fixed bias transport action")
    return " ".join(
        (
            REMOTE + "/run.sh",
            action,
            row["job_id"],
            row["analysis"],
            row["corner"],
            str(row["pair_index"]),
        )
    )


def deploy() -> dict[str, Any]:
    policy, digest = authority()
    journal = ROOT / ".codex/bias-headroom-v1-deploy.json"
    before = budget.postflight()
    dc.save_new(
        journal,
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
        + " && test ! -e "
        + JOBS_REMOTE
        + " && test ! -L "
        + JOBS_REMOTE
    )
    previous.ssh("umask 077; mkdir -m 700 " + stage)
    for name in FILES:
        dc.command((*dc.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    manifest = ROOT / ".codex/bias-headroom-v1-manifest.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(policy["files"][n] + "  " + n + "\n" for n in FILES).encode())
    dc.command((*dc.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    previous.ssh(
        "cd "
        + stage
        + " && sha256sum -c manifest.sha256 >/dev/null && bash -n run.sh"
        + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
        + " && chmod 700 helper.py run.sh && chmod 600 *.ocn manifest.sha256"
        + " && mv "
        + stage
        + " "
        + REMOTE
        + " && mkdir -m 700 "
        + JOBS_REMOTE
    )
    after = postflight()
    output = {
        "state": "succeeded",
        "policy_sha256": digest,
        "after": after,
        "manifest_sha256": dc.digest(manifest.read_bytes()),
    }
    campaign._replace_record(journal, output)
    return output


def postflight() -> dict[str, Any]:
    authority()
    return dc.decode_result(previous.ssh(REMOTE + "/run.sh postflight " + ZERO + " dc FF 0"))


def operate(action: str, index: int) -> dict[str, Any]:
    if action == "submit":
        raise ValueError("v1 execution retired after preserved failure; use reviewed v2")
    _, digest = authority()
    row = request(index)
    journal = ROOT / f".codex/bias-headroom-v1-job-{index:02d}.json"
    if action == "submit":
        dc.save_new(
            journal,
            {
                "state": "reserved",
                "request": row,
                "policy_sha256": digest,
                "at": datetime.now(UTC).isoformat(),
            },
        )
    elif (
        campaign._read_json(journal).get("request") != row
        or campaign._read_json(journal).get("policy_sha256") != digest
    ):
        raise ValueError("bias status/result request lineage drift")
    data = dc.decode_result(previous.ssh(fixed_command(action, row), 90))
    if data.get("job_id") != row["job_id"] or data.get("analysis") != row["analysis"]:
        raise ValueError("returned bias job identity drift")
    if action == "result":
        if (
            data.get("quality") != "valid"
            or data.get("corner") != row["corner"]
            or data.get("pair_index") != row["pair_index"]
            or data.get("effective", {}).get("variables_v")
            != dict(
                zip(
                    ("VBIASN", "VBIASP"),
                    [v / 1000 for v in planning.PAIRS_MV[row["pair_index"]]],
                    strict=True,
                )
            )
            or data.get("vdd_v") != 1.0
            or data.get("spec_evaluation") != "not_evaluated"
        ):
            raise ValueError("native bias result settings drift")
        saved = ROOT / f".codex/bias-headroom-v1-job-{index:02d}-result.private.json"
        if saved.exists():
            if campaign._read_json(saved) != data:
                raise ValueError("preserved local bias result drift")
        else:
            dc.save_new(saved, data)
        campaign._replace_record(
            journal,
            {
                "state": "succeeded",
                "request": row,
                "policy_sha256": digest,
                "result_sha256": dc.digest(saved.read_bytes()),
            },
        )
    return data


def select() -> dict[str, Any]:
    _, digest = authority()
    if SELECTION.exists():
        raise ValueError("preserved selection cannot be replaced")
    for index in range(8):
        if (
            campaign._read_json(ROOT / f".codex/bias-headroom-v1-job-{index:02d}.json").get("state")
            != "succeeded"
        ):
            raise ValueError("eight verified screens required")
    value = dc.decode_result(previous.ssh(REMOTE + "/run.sh selection " + ZERO + " dc FF 0"))
    value["policy_sha256"] = digest
    dc.save_new(SELECTION, value)
    return value


if __name__ == "__main__":
    try:
        if len(sys.argv) == 2 and sys.argv[1] in ("deploy", "postflight", "selection"):
            output = (
                deploy()
                if sys.argv[1] == "deploy"
                else postflight()
                if sys.argv[1] == "postflight"
                else select()
            )
        elif len(sys.argv) == 3 and sys.argv[1] in ("submit", "status", "result"):
            output = operate(sys.argv[1], int(sys.argv[2]))
        else:
            raise ValueError("fixed bias action and optional slot index required")
        if "job_id" in output:
            output = {
                k: output[k]
                for k in ("job_id", "analysis", "state", "corner", "pair_index", "headroom")
                if k in output
            }
        print(json.dumps(output, sort_keys=True))
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
