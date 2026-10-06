"""Operator-only preserved offset reader, with immutable deployment and one-shot admissions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import ade_qual as io
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/offset-read-v1"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/offset-read-v1"
RUNTIME = "/home/buet/cds_work/.cadence_mcp/offset-read-v1"
POLICY = ROOT / "docs/policy/ANALOG_OFFSET_READ_V1.json"
DELEGATION = ROOT / ".codex/offset-read-delegation-v1.private.json"
FILES = ("helper.py", "run.sh")
SOURCE_ID = "f154d798-0f7f-47d6-9323-6b046394eef6"


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": "ANALOG-OFFSET-01",
        "parent_policy_sha256": parent,
        "operation": "read_preserved_offset_receipts",
        "source_job_id": SOURCE_ID,
        "max_new_attempts": 0,
        "max_new_reserved_bytes": 0,
        "delete_authority": False,
        "publication_authority": False,
        "files": {n: hashlib.sha256((LOCAL / n).read_bytes()).hexdigest() for n in FILES},
    }


def activation(digest: str) -> dict[str, str]:
    return {
        "phase": "ANALOG-OFFSET-01",
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "proceed",
    }


def authority() -> str:
    parent = campaign._load_authority()
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / n).is_symlink() for n in FILES):
        raise ValueError("offset policy or deployment bytes changed")
    digest = hashlib.sha256(campaign._canonical(policy)).hexdigest()
    if campaign._read_json(DELEGATION) != activation(digest):
        raise ValueError("offset phase delegation missing")
    return digest


def deploy() -> None:
    digest = authority()
    io.save_new(
        ROOT / ".codex/offset-read-deploy-v1.private.json",
        {"state": "reserved", "policy_sha256": digest},
    )
    stage = REMOTE + ".stage"
    io.command(
        (
            *io.SSH,
            "test ! -e "
            + REMOTE
            + " && test ! -L "
            + REMOTE
            + " && test ! -e "
            + stage
            + " && test ! -L "
            + stage
            + " && test ! -e "
            + RUNTIME
            + " && test ! -L "
            + RUNTIME,
        )
    )
    io.command((*io.SSH, "umask 077; mkdir -m 700 " + stage))
    for name in FILES:
        io.command((*io.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    io.command((*io.SCP, str(POLICY), "cadence-vm:" + stage + "/policy.json"))
    io.command((*io.SCP, str(DELEGATION), "cadence-vm:" + stage + "/activation.private.json"))
    hashes = expected_policy("")["files"] | {
        "policy.json": hashlib.sha256(POLICY.read_bytes()).hexdigest(),
        "activation.private.json": hashlib.sha256(DELEGATION.read_bytes()).hexdigest(),
    }
    manifest = ROOT / ".codex/offset-read-manifest-v1.private.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(v + "  " + n + "\n" for n, v in hashes.items()).encode("ascii"))
    io.command((*io.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    io.command(
        (
            *io.SSH,
            "cd "
            + stage
            + " && sha256sum -c manifest.sha256 >/dev/null"
            + " && bash -n run.sh"
            + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
            + " && chmod 700 helper.py run.sh && chmod 600 policy.json"
            + " activation.private.json manifest.sha256 && mv "
            + stage
            + " "
            + REMOTE,
        )
    )
    io.save_new(
        ROOT / ".codex/offset-read-deployed-v1.private.json",
        {"state": "verified", "policy_sha256": digest},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy",))
    parser.parse_args()
    deploy()
    print(json.dumps({"state": "verified", "operation": "read_only_offset_deployment"}))
