"""Operator-only immutable finite-grid deployment and composed conservation check."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import ade_qual as io
import phase_campaign as campaign

from cadence_mcp_bridge.amplifier_sweeps import DEFINITION_SHA, REGISTRY_SHA

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/amplifier-sweep-v1"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/amplifier-sweep-v1"
JOBS = "/home/buet/cds_work/.cadence_mcp/amplifier-sweep-v1-jobs"
POLICY = ROOT / "docs/policy/AMPLIFIER_SWEEP_V1.json"
DELEGATION = ROOT / ".codex/amplifier-sweep01-qual-delegation-v1.private.json"
FILES = ("helper.py", "run.sh", "extract-dc.ocn", "extract-ac.ocn")
BASE_COUNTER = {"campaign_id": "AUTO-PHASE-01", "count": 76,
                "result_reserved_bytes": 8993636352}


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1, "phase": "REAL-AMPLIFIER-SWEEP-01",
        "parent_policy_sha256": parent, "grid_v": ["0.319", "0.32", "0.321"],
        "fixed": {"vbiasp": "0.702", "vdd": "1", "vcm": "0.5", "corner": "NN",
                  "temperature_c": 27},
        "definition_sha256": DEFINITION_SHA, "registry_sha256": REGISTRY_SHA,
        "baseline_counter": BASE_COUNTER, "max_new_attempts": 6,
        "reservation_bytes_per_job": 128 * 1024**2,
        "max_new_reserved_bytes": 6 * 128 * 1024**2,
        "correction_ceiling": 20, "delete_authority": False, "publication_authority": False,
        "cancellation": "pending_points_only_active_job_not_terminated",
        "qualification_scope": "finite_nominal_simulation_grid_only",
        "files": {n: hashlib.sha256((LOCAL / n).read_bytes()).hexdigest() for n in FILES},
    }


def activation(digest: str) -> dict[str, str]:
    return {"phase": "REAL-AMPLIFIER-SWEEP-01", "policy_sha256": digest,
            "user_delegation": "explicit-in-current-task",
            "user_instruction": "continuous_four_phases"}


def authority() -> str:
    p = campaign._read_json(POLICY)
    if p != expected_policy(campaign._load_authority()) or any(
        (LOCAL / n).is_symlink() for n in FILES
    ):
        raise ValueError("compiled amplifier policy/deployment drift")
    digest = hashlib.sha256(campaign._canonical(p)).hexdigest()
    if campaign._read_json(DELEGATION) != activation(digest):
        raise ValueError("explicit amplifier delegation missing")
    d = campaign._read_json(ROOT / ".codex/amplifier-sweep01-delegation-v1.private.json")
    if (d.get("authority") != "explicit_user_continuous_four_phase_instruction"
        or d.get("grid") != p["grid_v"] or d.get("fixed") != p["fixed"]
        or d.get("max_new_attempts") != 6 or d.get("no_expansion") is not True
        or d.get("delete") is not False or d.get("publication") is not False
        or d.get("target") is not None):
        raise ValueError("explicit bounded user delegation changed")
    return digest


def deploy() -> None:
    digest = authority()
    io.save_new(ROOT / ".codex/amplifier-sweep01-deploy-intent-v1.private.json",
                {"policy_sha256": digest})
    stage = REMOTE + ".stage"
    absent = " && ".join("test ! -e " + p + " && test ! -L " + p
                         for p in (REMOTE, stage, JOBS))
    io.command((*io.SSH, absent))
    io.command((*io.SSH, "umask 077; mkdir -m 700 " + stage))
    for name in FILES:
        io.command((*io.SCP, str(LOCAL / name), "cadence-vm:" + stage + "/" + name))
    io.command((*io.SCP, str(POLICY), "cadence-vm:" + stage + "/policy.json"))
    io.command((*io.SCP, str(DELEGATION), "cadence-vm:" + stage + "/activation.private.json"))
    hashes = expected_policy("")["files"] | {
        "policy.json": hashlib.sha256(POLICY.read_bytes()).hexdigest(),
        "activation.private.json": hashlib.sha256(DELEGATION.read_bytes()).hexdigest(),
    }
    manifest = ROOT / ".codex/amplifier-sweep01-manifest-v1.private.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(v + "  " + n + "\n" for n, v in hashes.items()).encode("ascii"))
    io.command((*io.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    io.command((*io.SSH, "cd " + stage + " && sha256sum -c manifest.sha256 >/dev/null"
                + " && bash -n run.sh && /usr/bin/python -c "
                + "'compile(open(\"helper.py\",\"rb\").read(),\"helper.py\",\"exec\")'"
                + " && chmod 700 helper.py run.sh && chmod 600 extract-dc.ocn extract-ac.ocn"
                + " policy.json activation.private.json manifest.sha256"
                + " && mv " + stage + " " + REMOTE + " && mkdir -m 700 " + JOBS))
    io.save_new(ROOT / ".codex/amplifier-sweep01-deployed-v1.private.json", {"state": "verified"})


def postflight() -> dict[str, Any]:
    authority()
    r = io.decode_result(io.command((*io.SSH, REMOTE + "/run.sh postflight"), 120))
    baseline = json.loads((ROOT / ".codex/amplifier-sweep01-baseline-v1.private.json").read_bytes())
    for k, v in baseline["live"]["protected"].items():
        if r["protected"].get(k) != v:
            raise ValueError("original/ADE/PDK/prior evidence drift")
    for name, digest in baseline["prior_private_sha256"].items():
        path = ROOT / ".codex" / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("prior private evidence drift")
    frozen = ROOT / ".codex/amplifier-sweep01-live-protected-v1.private.json"
    if frozen.exists():
        if r["protected"] != campaign._read_json(frozen):
            raise ValueError("whole prior protected checkpoint changed")
    else:
        if r["jobs"] or r["counter"] != BASE_COUNTER:
            raise ValueError("initial amplifier checkpoint must precede execution")
        io.save_new(frozen, r["protected"])
    return r


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", "postflight"))
    if parser.parse_args().action == "deploy":
        deploy()
    else:
        print(json.dumps(postflight(), sort_keys=True))
