"""Fixed operator qualification of the separately selected native AC/TRAN bundle."""

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
VERSION = "native-ac-tran-v4"
CHANGE = "ADE-QUAL-NATIVE-AC-TRAN-01"
LOCAL = ROOT / "remote/phase-campaign" / VERSION
POLICY = ROOT / "docs/policy/NATIVE_AC_TRAN_V4.json"
DELEGATION = ROOT / ".codex/native-ac-tran-v4-delegation.json"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/" + VERSION
FILES = (
    "run.sh",
    "helper.py",
    "netlist-tran.ocn",
    "extract-tran.ocn",
)


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "change_id": CHANGE,
        "remote_version": "phase-campaign/" + VERSION,
        "analysis_bundle": ["tran"],
        "reused_ac_version": "native-ac-tran-v3",
        "execution_mode": "native_ade_state_with_job_session_analysis_override",
        "observed_saved_state": {
            "enabled": ["dc"],
            "bias_v": [0.3, 0.65],
            "section": "NN",
            "temperature_c": 27,
        },
        "ac": {"start_hz": 10, "stop_hz": 1e8, "points_per_decade": 10},
        "tran": {
            "saved_stop_s": 0.004,
            "job_maxstep_s": 1e-5,
            "maximum_extracted_points": 3000,
            "method": "trap",
        },
        "candidate_preserved_v": [0.32, 0.702],
        "vdd_constraint_v": 1.0,
        "max_spectre_attempts": 100,
        "max_new_results_bytes": 5 * 1024**3,
        "reservation_bytes_per_job": 128 * 1024**2,
        "maximum_corrections_same_change": 3,
        "corrections_used": 3,
        "previous_policy_sha256": dc.digest(
            campaign._canonical(campaign._read_json(ROOT / "docs/policy/NATIVE_AC_TRAN_V3.json"))
        ),
        "elapsed_ceiling": None,
        "qualified_dc_policy_sha256": dc.digest(
            campaign._canonical(campaign._read_json(dc.POLICY))
        ),
        "files": {name: dc.digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def authority() -> tuple[dict[str, Any], str]:
    parent = campaign._load_authority()
    dc.authority()
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent):
        raise ValueError("native policy or immutable files changed")
    policy_hash = dc.digest(campaign._canonical(policy))
    if campaign._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "change_id": CHANGE,
        "parent_policy_sha256": parent,
        "policy_sha256": policy_hash,
        "user_delegation": "explicit-in-current-task",
        "user_request": "native AC/TRAN 검증 진행해줘",
        "prior_dc_corrections_preserved": "5_of_6",
    }:
        raise ValueError("native bundle delegation absent")
    previous = campaign._read_json(ROOT / ".codex/ade-qual-v6-dc.json")
    output = ROOT / ".codex/ade-qual-v6-dc.output"
    if (
        previous.get("state") != "succeeded"
        or output.is_symlink()
        or previous.get("output_sha256") != dc.digest(output.read_bytes())
    ):
        raise ValueError("qualified DC predecessor missing")
    for analysis in ("ac", "tran"):
        record = campaign._read_json(ROOT / f".codex/native-ac-tran-v3-{analysis}.json")
        previous_output = ROOT / f".codex/native-ac-tran-v3-{analysis}.output"
        if (
            record.get("state") != "succeeded"
            or previous_output.is_symlink()
            or record.get("output_sha256") != dc.digest(previous_output.read_bytes())
        ):
            raise ValueError("preserved successful AC/TRAN predecessor required")
    return policy, policy_hash


def deploy(policy: dict[str, Any]) -> bytes:
    stage = REMOTE + ".stage"
    dc.command((*dc.SSH, "test ! -e " + REMOTE + " && test ! -e " + stage))
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
            "cd " + stage + " && sha256sum -c manifest.sha256 >/dev/null"
            " && bash -n run.sh"
            ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
            " && chmod 700 run.sh helper.py && chmod 600 *.ocn manifest.sha256 && mv "
            + stage
            + " "
            + REMOTE,
        )
    )
    return b'{"deployment":"verified"}\n'


def run(action: str) -> dict[str, Any]:
    if action not in (
        "deploy",
        "netlist-tran",
        "tran",
        "status-tran",
    ):
        raise ValueError("closed native bundle action")
    policy, policy_hash = authority()
    if action.startswith("status-"):
        return dc.decode_result(dc.command((*dc.SSH, REMOTE + "/run.sh status " + action[7:])))
    if action != "deploy":
        predecessor = "deploy" if action.startswith("netlist-") else "netlist-" + action
        previous = campaign._read_json(ROOT / f".codex/{VERSION}-{predecessor}.json")
        output = ROOT / f".codex/{VERSION}-{predecessor}.output"
        if (
            previous.get("state") != "succeeded"
            or previous.get("policy_sha256") != policy_hash
            or output.is_symlink()
            or previous.get("output_sha256") != dc.digest(output.read_bytes())
        ):
            raise ValueError("native predecessor required")
    journal = ROOT / f".codex/{VERSION}-{action}.json"
    dc.save_new(
        journal,
        {
            "state": "reserved",
            "policy_sha256": policy_hash,
            "change_id": CHANGE,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    if action == "deploy":
        previous_correction = campaign._read_json(ROOT / ".codex/native-ac-tran-correction-2.json")
        if (
            previous_correction.get("change_id") != CHANGE
            or previous_correction.get("ordinal") != 2
            or previous_correction.get("state") != "consumed"
        ):
            raise ValueError("preserved correction history absent")
        dc.save_new(
            ROOT / ".codex/native-ac-tran-correction-3.json",
            {
                "change_id": CHANGE,
                "ordinal": 3,
                "maximum_corrections": 3,
                "previous_policy_sha256": policy["previous_policy_sha256"],
                "policy_sha256": policy_hash,
                "state": "consumed",
            },
        )
        data = deploy(policy)
    else:
        analysis = action.removeprefix("netlist-")
        operation = "netlist" if action.startswith("netlist-") else "simulate"
        data = dc.command((*dc.SSH, REMOTE + "/run.sh " + operation + " " + analysis), 400)
    with journal.with_suffix(".output").open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    result = dc.decode_result(data)
    temporary = journal.with_suffix(".new")
    dc.save_new(
        temporary,
        {
            "state": "succeeded",
            "policy_sha256": policy_hash,
            "change_id": CHANGE,
            "output_sha256": dc.digest(data),
            "at": datetime.now(UTC).isoformat(),
        },
    )
    os.replace(temporary, journal)
    return result


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("one fixed native action required")
        value = run(sys.argv[1])
        print(json.dumps({"action": sys.argv[1], "state": value.get("state", "succeeded")}))
    except (OSError, ValueError, campaign.CampaignError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
