"""Fixed one-shot operator qualification of native ADE L state-driven DC."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/ade-qual-v6"
POLICY = ROOT / "docs/policy/ADE_QUAL_V6.json"
DELEGATION = ROOT / ".codex/ade-qual-v6-delegation.json"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/ade-qual-v6"
FILES = ("run.sh", "helper.py", "netlist.ocn")
CORRECTION_ORDINAL = 5
RENEWAL = ROOT / "docs/policy/ADE_QUAL_CORRECTION_RENEWAL_V1.json"
RENEWAL_DELEGATION = ROOT / ".codex/ade-qual-correction-renewal-v1-delegation.json"
CHECKPOINT_SHA256 = "74ff35ae46cf6434464e791b68435ebefc2282cf39f99be9acd19488db3183b6"
SSH = ("ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "cadence-vm")
SCP = ("scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "remote_version": "phase-campaign/ade-qual-v6",
        "execution_mode": "ade_state",
        "analysis_bundle": ["dc"],
        "source_mode": "verified_current_source_copy_readonly",
        "state_mode": "native_ade_window_load_owned_copy_routing_only",
        "operating_point": "current_state_observed",
        "candidate_preserved_v": [0.320, 0.702],
        "vdd_constraint_v": 1.0,
        "max_spectre_attempts": 100,
        "max_new_results_bytes": 5 * 1024**3,
        "reservation_bytes": 128 * 1024**2,
        "correction_ordinal": CORRECTION_ORDINAL,
        "correction_renewal_sha256": renewal_policy_digest(),
        "files": {name: digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def renewal_policy_digest() -> str:
    renewal = campaign._read_json(RENEWAL)
    if renewal != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "ADE-QUAL-01",
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "prior_corrections_used": 3,
        "additional_corrections": 3,
        "maximum_corrections": 6,
        "preserve_other_cumulative_budgets": True,
        "max_elapsed_hours": None,
    }:
        raise ValueError("correction renewal changed")
    return digest(campaign._canonical(renewal))


def renewal_authority() -> str:
    value = renewal_policy_digest()
    if campaign._read_json(RENEWAL_DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "phase": "ADE-QUAL-01",
        "policy_sha256": value,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "user_delegation": "explicit-in-current-task",
        "user_reply": "additional_allowance_accepted",
    }:
        raise ValueError("explicit correction renewal binding absent")
    checkpoint = ROOT / ".codex/ade-qual-01-checkpoint.json"
    if checkpoint.is_symlink() or digest(checkpoint.read_bytes()) != CHECKPOINT_SHA256:
        raise ValueError("preserved checkpoint changed")
    if type(CORRECTION_ORDINAL) is not int or not 4 <= CORRECTION_ORDINAL <= 6:
        raise ValueError("correction budget exhausted")
    return value


def reserve_correction(policy_hash: str) -> None:
    if type(CORRECTION_ORDINAL) is not int or not 4 <= CORRECTION_ORDINAL <= 6:
        raise ValueError("correction budget exhausted")
    renewal_hash = renewal_authority()
    for ordinal in range(4, CORRECTION_ORDINAL):
        record = campaign._read_json(ROOT / f".codex/ade-qual-correction-{ordinal}.json")
        if record.get("ordinal") != ordinal or record.get("renewal_sha256") != renewal_hash:
            raise ValueError("prior correction evidence missing")
    save_new(
        ROOT / f".codex/ade-qual-correction-{CORRECTION_ORDINAL}.json",
        {
            "ordinal": CORRECTION_ORDINAL,
            "renewal_sha256": renewal_hash,
            "policy_sha256": policy_hash,
            "state": "consumed",
            "at": datetime.now(UTC).isoformat(),
        },
    )


def authority() -> tuple[dict[str, Any], str]:
    parent = campaign._load_authority()
    renewal_authority()
    expected = expected_policy(parent)
    policy = campaign._read_json(POLICY)
    if policy != expected:
        raise ValueError("ADE qualification policy or local bytes changed")
    policy_hash = digest(campaign._canonical(policy))
    if campaign._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "policy_sha256": policy_hash,
        "user_delegation": "explicit-in-current-task",
    }:
        raise ValueError("ADE qualification delegation binding absent")
    return policy, policy_hash


def command(argv: tuple[str, ...], timeout: int = 60) -> bytes:
    done = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    if done.returncode != 0 or len(done.stdout) + len(done.stderr) > 65536:
        raise ValueError("remote operation failed or uncertain; use status before recovery")
    return done.stdout


def save_new(path: Path, data: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def deploy(policy: dict[str, Any]) -> bytes:
    stage = REMOTE + ".stage"
    command((*SSH, "test ! -e " + REMOTE + " && test ! -e " + stage))
    command((*SSH, "umask 077; mkdir -m 700 " + stage))
    for name in FILES:
        command((*SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    manifest = ROOT / ".codex/ade-qual-v6-manifest.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(policy["files"][name] + "  " + name + "\n" for name in FILES).encode())
    command((*SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    command(
        (
            *SSH,
            "cd " + stage + " && sha256sum -c manifest.sha256 >/dev/null"
            " && bash -n run.sh"
            ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
            " && chmod 700 run.sh helper.py && chmod 600 netlist.ocn manifest.sha256 && mv "
            + stage
            + " "
            + REMOTE,
        )
    )
    return b'{"deployment":"verified"}\n'


def decode_result(data: bytes) -> dict[str, Any]:
    result: object = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("fixed remote result is not an object")
    return result


def run(action: str) -> dict[str, Any]:
    if action not in ("deploy", "netlist", "dc", "status"):
        raise ValueError("only fixed deploy/netlist/dc/status actions are accepted")
    policy, policy_hash = authority()
    if action == "status":
        return decode_result(command((*SSH, REMOTE + "/run.sh status")))
    if action != "deploy":
        predecessor = "deploy" if action == "netlist" else "netlist"
        previous = campaign._read_json(ROOT / f".codex/ade-qual-v6-{predecessor}.json")
        output = ROOT / f".codex/ade-qual-v6-{predecessor}.output"
        if (
            previous.get("state") != "succeeded"
            or previous.get("policy_sha256") != policy_hash
            or output.is_symlink()
            or not output.is_file()
            or previous.get("output_sha256") != digest(output.read_bytes())
        ):
            raise ValueError("verified predecessor required")
    journal = ROOT / (".codex/ade-qual-v6-" + action + ".json")
    if action == "deploy":
        reserve_correction(policy_hash)
    save_new(
        journal,
        {"state": "reserved", "policy_sha256": policy_hash, "at": datetime.now(UTC).isoformat()},
    )
    data = (
        deploy(policy) if action == "deploy" else command((*SSH, REMOTE + "/run.sh " + action), 400)
    )
    output = journal.with_suffix(".output")
    with output.open("xb") as stream:
        stream.write(data)
    result = decode_result(data)
    temporary = journal.with_suffix(".new")
    save_new(
        temporary,
        {
            "state": "succeeded",
            "policy_sha256": policy_hash,
            "output_sha256": digest(data),
            "at": datetime.now(UTC).isoformat(),
        },
    )
    os.replace(temporary, journal)
    return result


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise ValueError("usage: ade_qual.py deploy|netlist|dc|status")
        result = run(sys.argv[1])
        # Protected hashes and circuit measurements stay in the private output file.
        print(json.dumps({"action": sys.argv[1], "state": result.get("state", "succeeded")}))
    except (OSError, ValueError, campaign.CampaignError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
