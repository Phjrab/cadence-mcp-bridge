"""Fixed one-shot operator qualification of native ADE L state-driven DC."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/ade-qual-v4"
POLICY = ROOT / "docs/policy/ADE_QUAL_V4.json"
DELEGATION = ROOT / ".codex/ade-qual-v4-delegation.json"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/ade-qual-v4"
FILES = ("run.sh", "helper.py", "netlist.ocn")
SSH = ("ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "cadence-vm")
SCP = ("scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def expected_policy(parent: str) -> dict:
    return {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "remote_version": "phase-campaign/ade-qual-v4",
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
        "files": {name: digest((LOCAL / name).read_bytes()) for name in FILES},
    }


def authority() -> tuple[dict, str]:
    parent = campaign._load_authority()
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


def save_new(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def deploy(policy: dict) -> bytes:
    stage = REMOTE + ".stage"
    command((*SSH, "test ! -e " + REMOTE + " && test ! -e " + stage))
    command((*SSH, "umask 077; mkdir -m 700 " + stage))
    for name in FILES:
        command((*SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    manifest = ROOT / ".codex/ade-qual-v4-manifest.sha256"
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


def run(action: str) -> dict:
    if action not in ("deploy", "netlist", "dc", "status"):
        raise ValueError("only fixed deploy/netlist/dc/status actions are accepted")
    policy, policy_hash = authority()
    if action == "status":
        return json.loads(command((*SSH, REMOTE + "/run.sh status")))
    if action != "deploy":
        predecessor = "deploy" if action == "netlist" else "netlist"
        previous = campaign._read_json(ROOT / f".codex/ade-qual-v4-{predecessor}.json")
        output = ROOT / f".codex/ade-qual-v4-{predecessor}.output"
        if (
            previous.get("state") != "succeeded"
            or previous.get("policy_sha256") != policy_hash
            or output.is_symlink()
            or not output.is_file()
            or previous.get("output_sha256") != digest(output.read_bytes())
        ):
            raise ValueError("verified predecessor required")
    journal = ROOT / (".codex/ade-qual-v4-" + action + ".json")
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
    result = json.loads(data)
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
