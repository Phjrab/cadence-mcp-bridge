"""Fixed finite one-axis reference bias qualification using pinned DC/AC copies."""

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
LOCAL = ROOT / "remote/phase-campaign/bias-range-qual-v1"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/bias-range-qual-v1"
RUNTIME = "/home/buet/cds_work/.cadence_mcp/bias-range-qual-v1"
POLICY = ROOT / "docs/policy/BIAS_RANGE_QUAL_V1.json"
DELEGATION = ROOT / ".codex/bias-range01-qual-delegation-v1.private.json"
CASES = ("lowerdc", "lowerac", "upperdc", "upperac")
FILES = ("helper.py", "run.sh", "extract-dc.ocn", "extract-ac.ocn")


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": "BIAS-RANGE-QUAL-01",
        "parent_policy_sha256": parent,
        "source_job_id": "f154d798-0f7f-47d6-9323-6b046394eef6",
        "cases": list(CASES),
        "values_v": ["0.319", "0.320", "0.321"],
        "fixed_vbiasp_v": "0.702",
        "vdd_v": "1",
        "input_common_mode_v": "0.5",
        "baseline_counter": {
            "campaign_id": "AUTO-PHASE-01",
            "count": 72,
            "result_reserved_bytes": 8456765440,
        },
        "max_new_attempts": 4,
        "max_new_reserved_bytes": 4 * 128 * 1024**2,
        "qualification_scope": "finite_grid_simulation_only_not_continuous_or_device_ratings",
        "stop_on_first_invalid_or_unknown": True,
        "correction_ceiling": 20,
        "delete_authority": False,
        "publication_authority": False,
        "files": {n: hashlib.sha256((LOCAL / n).read_bytes()).hexdigest() for n in FILES},
    }


def activation(digest: str) -> dict[str, str]:
    return {
        "phase": "BIAS-RANGE-QUAL-01",
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "continuous_four_phases",
    }


def authority() -> str:
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(campaign._load_authority()) or any(
        (LOCAL / n).is_symlink() for n in FILES
    ):
        raise ValueError("fixed grid policy/deployment drift")
    digest = hashlib.sha256(campaign._canonical(policy)).hexdigest()
    if campaign._read_json(DELEGATION) != activation(digest):
        raise ValueError("grid phase delegation missing")
    delegation = campaign._read_json(ROOT / ".codex/bias-range01-delegation-v1.private.json")
    if (
        delegation.get("authority") != "explicit_user_continuous_four_phase_instruction"
        or delegation.get("values_v") != ["0.319", "0.320", "0.321"]
        or delegation.get("max_new_attempts") != 4
        or delegation.get("no_expansion") is not True
    ):
        raise ValueError("explicit bounded grid delegation missing")
    return digest


def deploy() -> None:
    digest = authority()
    io.save_new(
        ROOT / ".codex/bias-range01-deploy-intent-v1.private.json", {"policy_sha256": digest}
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
    manifest = ROOT / ".codex/bias-range01-manifest-v1.private.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(v + "  " + n + "\n" for n, v in hashes.items()).encode("ascii"))
    io.command((*io.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    io.command(
        (
            *io.SSH,
            "cd "
            + stage
            + " && sha256sum -c manifest.sha256 >/dev/null && bash -n run.sh"
            + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
            + " && chmod 700 helper.py run.sh"
            + " && chmod 600 extract-dc.ocn extract-ac.ocn policy.json"
            + " activation.private.json manifest.sha256 && mv "
            + stage
            + " "
            + REMOTE,
        )
    )
    io.save_new(ROOT / ".codex/bias-range01-deployed-v1.private.json", {"state": "verified"})


def run(action: str) -> None:
    digest = authority()
    if action not in (*CASES, "result"):
        raise ValueError("fixed grid action")
    io.save_new(
        ROOT / (".codex/bias-range01-" + action + "-intent-v1.private.json"),
        {"state": "reserved", "policy_sha256": digest, "action": action},
    )
    command = REMOTE + "/run.sh " + ("result" if action == "result" else "run " + action)
    done = subprocess.run((*io.SSH, command), capture_output=True, timeout=300, check=False)
    io.save_new(
        ROOT / (".codex/bias-range01-" + action + "-transport-v1.private.json"),
        {
            "returncode": done.returncode,
            "stdout": done.stdout.decode("utf-8", "replace")[:65536],
            "stderr": done.stderr.decode("utf-8", "replace")[:65536],
        },
    )
    if done.returncode or len(done.stdout) + len(done.stderr) > 65536:
        raise ValueError("fixed grid operation failed; preserve admission, no blind retry")
    if action == "result":
        io.save_new(
            ROOT / ".codex/bias-range01-extraction-v1.private.json", io.decode_result(done.stdout)
        )


def postflight() -> dict[str, Any]:
    authority()
    r = io.decode_result(io.command((*io.SSH, REMOTE + "/run.sh postflight"), 120))
    baseline_path = ROOT / ".codex/bias-range01-baseline-v1.private.json"
    if baseline_path.is_symlink() or not 0 < baseline_path.stat().st_size <= 1024**2:
        raise ValueError("bounded private phase baseline required")
    baseline = json.loads(baseline_path.read_bytes())["live"]
    original = baseline["protected"]
    # The previous local postflight removed its ledger field already.
    for k, v in original.items():
        if r["protected"].get(k) != v:
            raise ValueError("old source/ADE/PDK/native/sizing/bandwidth drift")
    frozen = ROOT / ".codex/bias-range01-live-protected-v1.private.json"
    if frozen.exists():
        if r["protected"] != campaign._read_json(frozen):
            raise ValueError("entire prior protected evidence changed")
    else:
        if r["jobs"] or r["counter"] != baseline["counter"]:
            raise ValueError("initial grid protection baseline must precede jobs")
        io.save_new(frozen, r["protected"])
    return r


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", *CASES, "result", "postflight"))
    action = parser.parse_args().action
    if action == "deploy":
        deploy()
    elif action == "postflight":
        print(json.dumps(postflight(), sort_keys=True))
    else:
        run(action)
