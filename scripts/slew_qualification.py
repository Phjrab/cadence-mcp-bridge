"""Operator-only four-step study, with immutable deployment and one-shot admissions."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import ade_qual as io
import phase_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "remote/phase-campaign/slew-qual-v4"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/slew-qual-v4"
RUNTIME = "/home/buet/cds_work/.cadence_mcp/slew-qual-v3"
POLICY = ROOT / "docs/policy/ANALOG_SLEW_QUAL_V4.json"
DELEGATION = ROOT / ".codex/slew-qual-delegation-v4.private.json"
FILES = ("helper.py", "run.sh", "extract.ocn", "analysis.py")
SOURCE_ID = "eca78308-8af8-4810-b848-94c0ad936afe"


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 4,
        "preserved_runtime_version": "slew-qual-v3",
        "refinement_maxstep_s": ["0.0000000002", "0.0000000001", "0.0000000001"],
        "refinement_reason": (
            "coarse_crossing_bracket_insufficient_no_rate; fixed finer controls before new runs"
        ),
        "phase": "ANALOG-SLEW-01",
        "parent_policy_sha256": parent,
        "source_job_id": SOURCE_ID,
        "cases": ["coarse", "medium", "fine", "fast"],
        "baseline_counter": {
            "campaign_id": "AUTO-PHASE-01",
            "count": 64,
            "result_reserved_bytes": 7383023616,
        },
        "stop_s": "0.00001",
        "input_vcm_v": "0.5",
        "differential_endpoints_v": ["-0.1", "0.1"],
        "output": "Vop_minus_Vom",
        "load": "existing_topology_no_added_external_load",
        "window_fraction": ["0.2", "0.8"],
        "empirical_relative_change_ceiling": "0.01",
        "subwindow_rate_ratio_ceiling": "1.2",
        "new_attempt_ceiling": 4,
        "reservation_bytes_per_job": 128 * 1024**2,
        "correction_ceiling": 20,
        "delete_authority": False,
        "publication_authority": False,
        "files": {n: hashlib.sha256((LOCAL / n).read_bytes()).hexdigest() for n in FILES},
    }


def activation(digest: str) -> dict[str, str]:
    return {
        "phase": "ANALOG-SLEW-01",
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "proceed",
    }


def authority() -> str:
    parent = campaign._load_authority()
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(parent) or any((LOCAL / n).is_symlink() for n in FILES):
        raise ValueError("step policy or deployment bytes changed")
    digest = hashlib.sha256(campaign._canonical(policy)).hexdigest()
    if campaign._read_json(DELEGATION) != activation(digest):
        raise ValueError("step phase delegation missing")
    return digest


def deploy() -> None:
    digest = authority()
    io.save_new(
        ROOT / ".codex/slew-qual-deploy-v4.private.json",
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
            + " && test -d "
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
    manifest = ROOT / ".codex/slew-qual-manifest-v4.private.sha256"
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
            + " && chmod 700 helper.py run.sh && chmod 600 extract.ocn policy.json"
            + " activation.private.json manifest.sha256 && mv "
            + stage
            + " "
            + REMOTE,
        )
    )
    io.save_new(
        ROOT / ".codex/slew-qual-deployed-v4.private.json",
        {"state": "verified", "policy_sha256": digest},
    )


def run(action: str) -> None:
    digest = authority()
    if action not in ("coarse", "medium", "fine", "fast", "result", "recover-coarse"):
        raise ValueError("fixed step operation")
    journal = ROOT / (".codex/slew-qual-" + action + "-intent-v4.private.json")
    io.save_new(journal, {"state": "reserved", "policy_sha256": digest, "action": action})
    command = (
        REMOTE
        + "/run.sh "
        + ("run " + action if action not in ("result", "recover-coarse") else action)
    )
    done = subprocess.run((*io.SSH, command), capture_output=True, timeout=300, check=False)
    # Never retry an uncertain simulation; admission and all failures stay preserved.
    io.save_new(
        ROOT / (".codex/slew-qual-" + action + "-transport-v4.private.json"),
        {
            "returncode": done.returncode,
            "stdout": done.stdout.decode("utf-8", "replace")[:65536],
            "stderr": done.stderr.decode("utf-8", "replace")[:65536],
        },
    )
    if done.returncode or len(done.stdout) + len(done.stderr) > 65536:
        raise ValueError("fixed step operation failed; inspect preserved state before recovery")
    if action == "result":
        io.save_new(
            ROOT / ".codex/slew-qual-extraction-v4.private.json", io.decode_result(done.stdout)
        )


def postflight() -> dict[str, Any]:
    """Strict new-domain sequence; preserved old phase verifiers are unchanged."""
    authority()
    result = io.decode_result(io.command((*io.SSH, REMOTE + "/run.sh postflight"), 120))
    baseline = ROOT / ".codex/slew01-protected-baseline-v3.private.json"
    result["protected"]["native"].pop("counter")
    original = campaign._read_json(baseline)["protected"]
    original["native"].pop("counter")
    if baseline.exists() and result["protected"] != original:
        raise ValueError("preserved evidence drift")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "deploy",
            "coarse",
            "medium",
            "fine",
            "fast",
            "result",
            "postflight",
            "recover-coarse",
        ),
    )
    selected = parser.parse_args().action
    if selected == "deploy":
        deploy()
    elif selected == "postflight":
        print(json.dumps(postflight(), sort_keys=True))
    else:
        run(selected)
    print(json.dumps({"state": "verified", "action": selected}))
