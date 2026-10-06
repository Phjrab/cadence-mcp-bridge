"""Operator-only immutable extraction of one admitted native DC result."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import ade_qual as io
import deploy_native_mcp_v1 as tx
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/analog-power-v1"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/analog-power-v1"
RUNTIME = "/home/buet/cds_work/.cadence_mcp/analog-power-v1"
POLICY = ROOT / "docs/policy/ANALOG_POWER_V1.json"
DELEGATION = ROOT / ".codex/analog-power-delegation-v1.private.json"
FILES = ("helper.py", "run.sh", "extract.ocn")


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": "ANALOG-POWER-01",
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": parent,
        "source_job_id": "f154d798-0f7f-47d6-9323-6b046394eef6",
        "new_simulations": 0,
        "new_reservations": 0,
        "extraction_allowance_bytes": 8 * 1024**2,
        "reservation_binding": "existing_native_source_job_128MiB_unused_capacity",
        "correction_ceiling": 20,
        "delete_authority": False,
        "publication_authority": False,
        "files": {n: hashlib.sha256((LOCAL / n).read_bytes()).hexdigest() for n in FILES},
    }


def authority() -> str:
    parent = campaign._load_authority()
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / n).is_symlink() for n in FILES):
        raise ValueError("power extraction policy or files changed")
    digest = hashlib.sha256(campaign._canonical(policy)).hexdigest()
    if campaign._read_json(DELEGATION) != {
        "phase": "ANALOG-POWER-01",
        "policy_sha256": digest,
        "parent_policy_sha256": parent,
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "진행",
    }:
        raise ValueError("power extraction delegation missing")
    return digest


def deploy() -> None:
    digest = authority()
    journal = ROOT / ".codex/analog-power-deploy-v1.private.json"
    # Exclusive durable admission comes before any mutation. Uncertain outcomes
    # remain reserved and require exact-state investigation, never blind retries.
    io.save_new(journal, {"state": "reserved", "policy_sha256": digest})
    stage = REMOTE + ".stage"
    tx.ssh(
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
        + RUNTIME
    )
    tx.ssh("umask 077; mkdir -m 700 " + stage)
    for name in FILES:
        io.command((*io.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    manifest = ROOT / ".codex/analog-power-manifest-v1.private.sha256"
    with manifest.open("xb") as stream:
        stream.write(
            "".join(expected_policy("")["files"][n] + "  " + n + "\n" for n in FILES).encode(
                "ascii"
            )
        )
    io.command((*io.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    tx.ssh(
        "cd "
        + stage
        + " && sha256sum -c manifest.sha256 >/dev/null"
        + " && bash -n run.sh"
        + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
        + " && chmod 700 helper.py run.sh && chmod 600 extract.ocn manifest.sha256"
        + " && mv "
        + stage
        + " "
        + REMOTE
    )
    io.save_new(
        ROOT / ".codex/analog-power-deployed-v1.private.json",
        {"state": "verified", "policy_sha256": digest},
    )


def read() -> dict[str, Any]:
    digest = authority()
    io.save_new(
        ROOT / ".codex/analog-power-read-intent-v1.private.json",
        {"state": "reserved", "policy_sha256": digest, "new_simulations": 0},
    )
    # Capture errors in private state without publishing vendor/log contents.
    done = subprocess.run(
        (*io.SSH, REMOTE + "/run.sh read"), capture_output=True, timeout=120, check=False
    )
    io.save_new(
        ROOT / ".codex/analog-power-read-transport-v1.private.json",
        {
            "returncode": done.returncode,
            "stdout": done.stdout.decode("utf-8", "replace")[:65536],
            "stderr": done.stderr.decode("utf-8", "replace")[:65536],
        },
    )
    if done.returncode or len(done.stdout) + len(done.stderr) > 65536:
        raise ValueError("power extraction failed; preserve and inspect its state")
    result = io.decode_result(done.stdout)
    io.save_new(ROOT / ".codex/analog-power-extraction-v1.private.json", result)
    return result


def expected_read_policy(parent: str) -> dict[str, Any]:
    local = ROOT / "remote/phase-campaign/analog-power-v2"
    return {
        "schema_version": 2,
        "phase": "ANALOG-POWER-01",
        "parent_policy_sha256": parent,
        "actions": ["result"],
        "new_simulations": 0,
        "new_reservations": 0,
        "preserved_receipt": "analog-power-v1",
        "files": {
            n: hashlib.sha256((local / n).read_bytes()).hexdigest() for n in ("helper.py", "run.sh")
        },
    }


def deploy_read_adapter() -> None:
    parent = authority()
    policy = expected_read_policy(parent)
    if campaign._read_json(ROOT / "docs/policy/ANALOG_POWER_READ_V2.json") != policy:
        raise ValueError("power read adapter bytes or policy changed")
    digest = hashlib.sha256(campaign._canonical(policy)).hexdigest()
    if campaign._read_json(ROOT / ".codex/analog-power-read-delegation-v2.private.json") != {
        "phase": "ANALOG-POWER-01",
        "policy_sha256": digest,
        "parent_policy_sha256": parent,
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "진행",
    }:
        raise ValueError("power read adapter delegation missing")
    io.save_new(
        ROOT / ".codex/analog-power-read-deploy-v2.private.json",
        {"state": "reserved", "policy_sha256": digest},
    )
    remote = "/home/buet/cds_work/.cadence_mcp/phase-campaign/analog-power-v2"
    stage = remote + ".stage"
    tx.ssh(
        "test ! -e "
        + remote
        + " && test ! -L "
        + remote
        + " && test ! -e "
        + stage
        + " && test ! -L "
        + stage
        + " && umask 077 && mkdir -m 700 "
        + stage
    )
    for name in policy["files"]:
        io.command(
            (
                *io.SCP,
                str(ROOT / "remote/phase-campaign/analog-power-v2" / name),
                "cadence-vm:" + stage + "/" + name,
            )
        )
    manifest = ROOT / ".codex/analog-power-read-manifest-v2.private.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(h + "  " + n + "\n" for n, h in policy["files"].items()).encode())
    io.command((*io.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    tx.ssh(
        "cd "
        + stage
        + " && sha256sum -c manifest.sha256 >/dev/null"
        + " && bash -n run.sh"
        + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
        + " && chmod 700 helper.py run.sh && chmod 600 manifest.sha256 && mv "
        + stage
        + " "
        + remote
    )
    result = io.decode_result(tx.ssh(remote + "/run.sh result", 90))
    if result != campaign._read_json(ROOT / ".codex/analog-power-extraction-v1.private.json"):
        raise ValueError("power read adapter changed the preserved receipt")
    io.save_new(
        ROOT / ".codex/analog-power-read-deployed-v2.private.json",
        {"state": "verified", "policy_sha256": digest, "receipt_equal": True},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", "read", "deploy-read-adapter"))
    action = parser.parse_args().action
    if action == "deploy":
        deploy()
        print('{"deployment":"verified"}')
    elif action == "deploy-read-adapter":
        deploy_read_adapter()
        print('{"read_adapter":"verified","receipt_equal":true}')
    else:
        result = read()
        print(
            json.dumps(
                {"status": result["status"], "reason": result["reason"], "new_simulations": 0}
            )
        )


if __name__ == "__main__":
    main()
