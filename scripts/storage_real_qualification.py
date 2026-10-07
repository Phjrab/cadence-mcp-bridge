"""Operator-only sealed native synthetic preparation; no destructive action."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import ade_qual as io
import phase_campaign as campaign
from storage_deploy import authority as storage_authority

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".codex"
LOCAL = ROOT / "remote/phase-campaign/storage-real-qual-v1"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/storage-real-qual-v1"
POLICY = ROOT / "docs/policy/STORAGE_REAL_QUAL_V1.json"
DELEGATION = PRIVATE / "storage-real01-delegation-v1.private.json"
FILES = {"helper.py": LOCAL / "helper.py", "run.sh": LOCAL / "run.sh",
         "policy.json": POLICY}


def authority() -> dict[str, Any]:
    storage_authority()
    policy = campaign._read_json(POLICY)
    if (policy["phase"] != "STORAGE-REAL-QUAL-01"
        or policy["delete_authority"] is not False
        or policy["max_new_payload_bytes"] != 20480
        or policy["max_new_simulations"] != 0
        or policy["max_new_reserved_bytes"] != 0):
        raise ValueError("bounded preparation policy absent")
    paths = {**FILES, "operator": Path(__file__).resolve()}
    if any(p.is_symlink() or b"\r" in p.read_bytes() for p in paths.values()):
        raise ValueError("sealed LF sources required")
    expected = {
        "phase": "STORAGE-REAL-QUAL-01",
        "policy_sha256": hashlib.sha256(campaign._canonical(policy)).hexdigest(),
        "user_delegation": "explicit-synthetic-preparation-no-delete",
        "files": {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in paths.items()},
        "parent_storage_authority_sha256": hashlib.sha256(
            campaign._canonical(storage_authority())).hexdigest(),
    }
    if campaign._read_json(DELEGATION) != expected:
        raise ValueError("exact reviewed fixture delegation absent")
    return expected


def deploy() -> dict[str, Any]:
    sealed = authority()
    io.save_new(PRIVATE / "storage-real01-deploy-intent-v1.private.json", sealed)
    stage = REMOTE + ".stage"
    io.command((*io.SSH, "test ! -e " + REMOTE + " && test ! -L " + REMOTE
                + " && test ! -e " + stage + " && test ! -L " + stage))
    io.command((*io.SSH, "umask 077; mkdir -m 700 " + stage))
    activation = PRIVATE / "storage-real01-activation-v1.private.json"
    io.save_new(activation, {k: sealed[k] for k in
                            ("phase", "policy_sha256", "user_delegation")})
    files = {**FILES, "activation.private.json": activation}
    manifest = PRIVATE / "storage-real01-manifest-v1.private.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + n + "\n"
                             for n, p in files.items()).encode("ascii"))
    for n, p in {**files, "manifest.sha256": manifest}.items():
        io.command((*io.SCP, str(p), "cadence-vm:" + stage + "/" + n))
    io.command((*io.SSH, "cd " + stage + " && sha256sum -c manifest.sha256 >/dev/null"
                + " && bash -n run.sh && /usr/bin/python -c "
                + "'compile(open(\"helper.py\",\"rb\").read(),\"helper\",\"exec\")'"
                + " && chmod 700 run.sh && chmod 600 helper.py *.json manifest.sha256"
                + " && mv " + stage + " " + REMOTE))
    result = {"state": "DEPLOYED", "new_simulations": 0, "deleted_artifacts": 0}
    io.save_new(PRIVATE / "storage-real01-deployed-v1.private.json", result)
    return result


def run(action: str) -> dict[str, Any]:
    if action not in ("prepare", "inspect"):
        raise ValueError("closed fixture operation required")
    sealed = authority()
    if action == "prepare":
        io.save_new(PRIVATE / "storage-real01-prepare-intent-v1.private.json", sealed)
    return io.decode_result(io.command((*io.SSH, REMOTE + "/run.sh " + action), 120))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", "prepare", "inspect"))
    args = parser.parse_args()
    print(json.dumps(deploy() if args.action == "deploy" else run(args.action)))
