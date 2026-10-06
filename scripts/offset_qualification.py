"""Selected nominal offset qualification using fixed owned DC copies only."""

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
LOCAL = ROOT / "remote/phase-campaign/offset-qual-v1"
REMOTE = "/home/buet/cds_work/.cadence_mcp/phase-campaign/offset-qual-v1"
RUNTIME = "/home/buet/cds_work/.cadence_mcp/offset-qual-v1"
POLICY = ROOT / "docs/policy/ANALOG_OFFSET_QUAL_V1.json"
DELEGATION = ROOT / ".codex/offset01-qual-delegation-v1.private.json"
CASES = ("zero", "minus1", "plus1", "minus05", "plus05")
FILES = ("helper.py", "run.sh", "extract.ocn")


def expected_policy(parent: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": "ANALOG-OFFSET-01",
        "parent_policy_sha256": parent,
        "source_job_id": "f154d798-0f7f-47d6-9323-6b046394eef6",
        "cases": list(CASES),
        "definition": "nominal-open-loop-input-nulling-v1",
        "input_differential_v": ["0", "-0.000001", "0.000001", "-0.0000005", "0.0000005"],
        "zero_case": "reuse_existing_admitted_DC_PSF_no_new_simulation",
        "input_common_mode_v": "0.5",
        "baseline_counter": {
            "campaign_id": "AUTO-PHASE-01",
            "count": 68,
            "result_reserved_bytes": 7919894528,
        },
        "new_attempt_ceiling": 4,
        "reservation_bytes_per_job": 128 * 1024**2,
        "root_pair_agreement_v": "0.00000001",
        "local_gain_relative_difference_ceiling": "0.01",
        "local_output_window_v": "0.1",
        "correction_ceiling": 20,
        "delete_authority": False,
        "publication_authority": False,
        "files": {n: hashlib.sha256((LOCAL / n).read_bytes()).hexdigest() for n in FILES},
    }


def activation(digest: str) -> dict[str, str]:
    return {
        "phase": "ANALOG-OFFSET-01",
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
        "user_instruction": "input_nulling",
    }


def authority() -> str:
    policy = campaign._read_json(POLICY)
    if policy != expected_policy(campaign._load_authority()) or any(
        (LOCAL / n).is_symlink() for n in FILES
    ):
        raise ValueError("fixed offset policy/deployment drift")
    digest = hashlib.sha256(campaign._canonical(policy)).hexdigest()
    if campaign._read_json(DELEGATION) != activation(digest):
        raise ValueError("offset phase delegation missing")
    selected = campaign._read_json(ROOT / ".codex/offset01-user-selection-v1.private.json")
    if selected != {
        "phase": "ANALOG-OFFSET-01",
        "user_instruction": "input_referred_offset",
        "scientific_definition": "applied_Vp_minus_Vm_where_Vop_minus_Vom_zero_nominal_open_loop",
        "selected_by": "explicit_user_question_reply",
        "numerical_target": None,
    }:
        raise ValueError("explicit scientific choice missing")
    return digest


def deploy() -> None:
    digest = authority()
    io.save_new(ROOT / ".codex/offset01-deploy-intent-v1.private.json", {"policy_sha256": digest})
    stage = REMOTE + ".stage"
    io.command(
        (*io.SSH, "test ! -e " + REMOTE + " && test ! -L " + REMOTE
         + " && test ! -e " + stage + " && test ! -L " + stage
         + " && test ! -e " + RUNTIME + " && test ! -L " + RUNTIME)
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
    manifest = ROOT / ".codex/offset01-manifest-v1.private.sha256"
    with manifest.open("xb") as stream:
        stream.write("".join(v + "  " + n + "\n" for n, v in hashes.items()).encode("ascii"))
    io.command((*io.SCP, str(manifest), "cadence-vm:" + stage + "/manifest.sha256"))
    io.command(
        (*io.SSH, "cd " + stage + " && sha256sum -c manifest.sha256 >/dev/null && bash -n run.sh"
         + ' && /usr/bin/python -c \'compile(open("helper.py","rb").read(),"helper.py","exec")\''
         + " && chmod 700 helper.py run.sh && chmod 600 extract.ocn policy.json"
         + " activation.private.json manifest.sha256 && mv " + stage + " " + REMOTE)
    )
    io.save_new(ROOT / ".codex/offset01-deployed-v1.private.json", {"state": "verified"})


def run(action: str) -> None:
    digest = authority()
    if action not in (*CASES, "result"):
        raise ValueError("fixed offset action")
    io.save_new(
        ROOT / (".codex/offset01-" + action + "-intent-v1.private.json"),
        {"state": "reserved", "policy_sha256": digest, "action": action},
    )
    command = REMOTE + "/run.sh " + ("result" if action == "result" else "run " + action)
    done = subprocess.run((*io.SSH, command), capture_output=True, timeout=300, check=False)
    io.save_new(
        ROOT / (".codex/offset01-" + action + "-transport-v1.private.json"),
        {"returncode": done.returncode, "stdout": done.stdout.decode("utf-8", "replace")[:65536],
         "stderr": done.stderr.decode("utf-8", "replace")[:65536]},
    )
    if done.returncode or len(done.stdout) + len(done.stderr) > 65536:
        raise ValueError("fixed offset operation failed; preserve admission, no blind retry")
    if action == "result":
        io.save_new(
            ROOT / ".codex/offset01-extraction-v1.private.json", io.decode_result(done.stdout)
        )


def postflight() -> dict[str, Any]:
    authority()
    r = io.decode_result(io.command((*io.SSH, REMOTE + "/run.sh postflight"), 120))
    baseline_path = ROOT / ".codex/offset01-baseline-v1.private.json"
    if baseline_path.is_symlink() or not 0 < baseline_path.stat().st_size <= 1024**2:
        raise ValueError("bounded private phase baseline required")
    baseline = json.loads(baseline_path.read_bytes())["live"]
    original = baseline["protected"]
    # The previous local postflight removed its ledger field already.
    for k, v in original.items():
        if r["protected"].get(k) != v:
            raise ValueError("old source/ADE/PDK/native/sizing/bandwidth drift")
    frozen = ROOT / ".codex/offset01-live-protected-v1.private.json"
    if frozen.exists():
        if r["protected"] != campaign._read_json(frozen):
            raise ValueError("entire prior slew evidence changed")
    else:
        if r["jobs"] or r["counter"] != baseline["counter"]:
            raise ValueError("initial offset protection baseline must precede jobs")
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
