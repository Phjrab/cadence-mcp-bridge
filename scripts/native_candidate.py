"""One fixed candidate pair through native owned ADE state copies."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ade_qual as dc
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
VERSION = "native-candidate-v2"
CHANGE = "NATIVE-CANDIDATE-01"
LOCAL = ROOT / "remote/phase-campaign" / VERSION
POLICY = ROOT / "docs/policy/NATIVE_CANDIDATE_V2.json"
DELEGATION = ROOT / ".codex/native-candidate-v2-delegation.json"
PREVIOUS_POLICY_SHA = "6a61fa3a74cb089a0b17726bfcc54a2db23fd2e3d6f00065c48404209ca12baf"
FAILURE_SHA = "21d6d8fa6ad4f447f6de25f64743bdbd2e60d0c3bf792c534a4b4bdfd7db4d3a"
REUSED = {
    "dc": "b401e57eac543e505dadf135753bd62c09a2fceb05b96a00615d3d6403350dd5",
    "netlist-ac": "76ebe3b768a4a684cd932e1a26fa3a82a636d2a9b29925b168e603fe2196d172",
}
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/" + VERSION
BASELINE = ROOT / ".codex/native-ac-tran-01-result-v2.json"
BASELINE_SHA = "b09d1faa742dda4f39371a4373057ce58ef780796f184f84a58571c30e4f9e82"
FILES = (
    "run.sh",
    "helper.py",
    "netlist-tran.ocn",
    "extract-ac.ocn",
    "extract-tran.ocn",
)
ACTIONS = (
    "deploy",
    "recover-ac",
    "netlist-tran",
    "tran",
    "status-ac",
    "status-tran",
    "postflight",
)


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "change_id": CHANGE,
        "remote_version": "phase-campaign/" + VERSION,
        "baseline_result_sha256": BASELINE_SHA,
        "previous_policy_sha256": PREVIOUS_POLICY_SHA,
        "failure_checkpoint_sha256": FAILURE_SHA,
        "reused_result_sha256": REUSED,
        "ac_recovery": "preserved_failed_job_copy_extraction_only",
        "source_saved_variables_v": {"VBIASN": 0.3, "VBIASP": 0.65},
        "fixed_candidate_variables_v": {"VBIASN": 0.32, "VBIASP": 0.702},
        "candidate_application": "two_expressions_in_owned_ADE_state_copy",
        "analysis_bundle": ["dc", "ac", "tran"],
        "section": "NN",
        "temperature_c": 27,
        "vdd_constraint_v": 1.0,
        "ac": {"start_hz": 10, "stop_hz": 1e8, "dec": 10},
        "tran": {"stop_s": 0.004, "maxstep_s": 1e-5, "method": "trap"},
        "spec_evaluation": "not_evaluated",
        "max_spectre_attempts": 100,
        "max_new_results_bytes": 5 * 1024**3,
        "reservation_bytes_per_job": 128 * 1024**2,
        "maximum_corrections_same_change": 3,
        "corrections_used": 1,
        "elapsed_ceiling": None,
        "prior_native_change_corrections_preserved": "3_of_3",
        "dc_corrections_preserved": "5_of_6",
        "files": {name: dc.digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def authority() -> tuple[dict[str, Any], str]:
    parent = campaign._load_authority()
    dc.authority()
    previous = campaign._read_json(ROOT / "docs/policy/NATIVE_CANDIDATE_V1.json")
    if dc.digest(campaign._canonical(previous)) != PREVIOUS_POLICY_SHA:
        raise ValueError("previous candidate policy drift")
    failure = ROOT / ".codex/native-candidate-01-ac-failure-v1.json"
    if failure.is_symlink() or dc.digest(failure.read_bytes()) != FAILURE_SHA:
        raise ValueError("preserved AC failure drift")
    for action, expected in REUSED.items():
        journal = campaign._read_json(ROOT / f".codex/native-candidate-v1-{action}.json")
        output = ROOT / f".codex/native-candidate-v1-{action}.output"
        if (
            journal.get("state") != "succeeded"
            or journal.get("policy_sha256") != PREVIOUS_POLICY_SHA
            or journal.get("output_sha256") != expected
            or output.is_symlink()
            or dc.digest(output.read_bytes()) != expected
        ):
            raise ValueError("candidate reuse journal drift")
    failed_journal = campaign._read_json(ROOT / ".codex/native-candidate-v1-ac.json")
    if (
        failed_journal.get("state") != "reserved"
        or failed_journal.get("policy_sha256") != PREVIOUS_POLICY_SHA
    ):
        raise ValueError("failed AC replay guard drift")
    if BASELINE.is_symlink() or dc.digest(BASELINE.read_bytes()) != BASELINE_SHA:
        raise ValueError("native baseline drift")
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent):
        raise ValueError("candidate policy or fixed bytes changed")
    policy_hash = dc.digest(campaign._canonical(policy))
    if campaign._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "change_id": CHANGE,
        "parent_policy_sha256": parent,
        "policy_sha256": policy_hash,
        "user_delegation": "explicit-in-current-task",
        "user_selection": "proceed_native_candidate_dc_ac_tran_comparison",
        "baseline_result_sha256": BASELINE_SHA,
        "previous_policy_sha256": PREVIOUS_POLICY_SHA,
        "failure_checkpoint_sha256": FAILURE_SHA,
    }:
        raise ValueError("candidate delegation absent")
    return policy, policy_hash


def correction_record(policy_hash: str) -> dict[str, Any]:
    return {
        "change_id": CHANGE,
        "ordinal": 1,
        "maximum": 3,
        "state": "consumed",
        "policy_sha256": policy_hash,
        "previous_policy_sha256": PREVIOUS_POLICY_SHA,
        "failure_checkpoint_sha256": FAILURE_SHA,
    }


def deploy(policy: dict[str, Any]) -> bytes:
    stage = REMOTE + ".stage"
    dc.command(
        (
            *dc.SSH,
            "test ! -e "
            + REMOTE
            + " && test ! -L "
            + REMOTE
            + " && test ! -e "
            + stage
            + " && test ! -L "
            + stage,
        )
    )
    # The fixed deployment preflight does not read or print any license value.
    dc.command(
        (
            *dc.SSH,
            "if ps -eo comm | grep -Eq '^(spectre|ocean|virtuoso)$'; then exit 75; fi; "
            + '/usr/bin/python -c \'import imp; m=imp.load_source("guard","'
            + '/home/buet/cds_work/.cadence_mcp/phase-campaign/ade-qual-v6/helper.py"); '
            + "m.environment_preflight(); m.snapshot()'",
        )
    )
    dc.command((*dc.SSH, "umask 077; mkdir -m 700 " + stage))
    for name in FILES:
        dc.command((*dc.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    manifest = ROOT / (".codex/" + VERSION + "-manifest.sha256")
    with manifest.open("xb") as stream:
        stream.write("".join(policy["files"][name] + "  " + name + "\n" for name in FILES).encode())
    dc.command((*dc.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    dc.command(
        (
            *dc.SSH,
            "cd "
            + stage
            + " && sha256sum -c manifest.sha256 >/dev/null"
            + " && bash -n run.sh"
            + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
            + " && chmod 700 run.sh helper.py && chmod 600 *.ocn manifest.sha256 && mv "
            + stage
            + " "
            + REMOTE,
        )
    )
    return b'{"deployment":"verified"}\n'


def predecessor(action: str) -> str:
    return {"recover-ac": "deploy", "netlist-tran": "recover-ac", "tran": "netlist-tran"}[
        action
    ]


def run(action: str) -> dict[str, Any]:
    if action not in ACTIONS:
        raise ValueError("closed candidate action")
    policy, policy_hash = authority()
    correction = ROOT / ".codex/native-candidate-correction-1.json"
    if action != "deploy" and campaign._read_json(correction) != correction_record(policy_hash):
        raise ValueError("consumed correction binding missing")
    if action.startswith("status-") or action == "postflight":
        operation, analysis = (
            ("postflight", "ac") if action == "postflight" else ("status", action[7:])
        )
        return dc.decode_result(
            dc.command((*dc.SSH, REMOTE + "/run.sh " + operation + " " + analysis))
        )
    if action != "deploy":
        prior = predecessor(action)
        previous = campaign._read_json(ROOT / f".codex/{VERSION}-{prior}.json")
        output = ROOT / f".codex/{VERSION}-{prior}.output"
        if (
            previous.get("state") != "succeeded"
            or previous.get("policy_sha256") != policy_hash
            or output.is_symlink()
            or previous.get("output_sha256") != dc.digest(output.read_bytes())
        ):
            raise ValueError("candidate predecessor required")
    journal = ROOT / f".codex/{VERSION}-{action}.json"
    dc.save_new(
        journal,
        {
            "state": "reserved",
            "change_id": CHANGE,
            "policy_sha256": policy_hash,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    if action == "deploy":
        dc.save_new(correction, correction_record(policy_hash))
        data = deploy(policy)
    else:
        operation = (
            "recover" if action == "recover-ac" else "netlist" if action == "netlist-tran"
            else "simulate"
        )
        analysis = "ac" if action == "recover-ac" else "tran"
        data = dc.command(
            (*dc.SSH, REMOTE + "/run.sh " + operation + " " + analysis), 400
        )
    with journal.with_suffix(".output").open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    value = dc.decode_result(data)
    temporary = journal.with_suffix(".new")
    dc.save_new(
        temporary,
        {
            "state": "succeeded",
            "change_id": CHANGE,
            "policy_sha256": policy_hash,
            "output_sha256": dc.digest(data),
            "at": datetime.now(UTC).isoformat(),
        },
    )
    os.replace(temporary, journal)
    return value


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("one fixed candidate action required")
        result = run(sys.argv[1])
        print(json.dumps({"action": sys.argv[1], "state": result.get("state", "succeeded")}))
    except (OSError, ValueError, campaign.CampaignError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
