"""Complete a consumed netlist journal from fixed, already generated evidence.

This path performs no OCEAN or Spectre run and creates no remote output.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import phase_b_role_campaign as v1
import phase_campaign as parent
import phase_d_netlist_v1 as phase

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/policy/PHASE_D_NETLIST_RECOVERY_V1.json"
DELEGATION = ROOT / ".codex/phase-d-netlist-recovery-v1-delegation.json"
BASE = phase.RUNTIME
PROJECT = BASE + "/project"
NETLIST_DIR = PROJECT + "/WP14_AUTO_PHASE_01_TB2/spectre/schematic/netlist"
NETLIST = NETLIST_DIR + "/netlist"
INPUT = NETLIST_DIR + "/input.scs"
PSF = PROJECT + "/WP14_AUTO_PHASE_01_TB2/spectre/schematic/psf"


class NetlistRecoveryError(RuntimeError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _authority() -> tuple[dict[str, Any], str, Path, dict[str, Any]]:
    old_policy, old_digest, state_root, base_policy = phase._authority()
    if old_digest != "2a30bda217d363a27b49b7a799b3df1fba371d80757ba333e2f57bba5d334c41":
        raise NetlistRecoveryError("DENY_OUT_OF_SCOPE: reviewed netlist policy changed")
    deployed = parent._read_json(state_root / "phased-netlist-v1-deploy.json")
    attempt = parent._read_json(state_root / "phased-netlist-v1-run.json")
    if (
        deployed.get("state") != "succeeded"
        or deployed.get("policy_sha256") != old_digest
        or attempt.get("state") != "reserved"
        or attempt.get("policy_sha256") != old_digest
        or (state_root / "phased-netlist-v1-run.output").exists()
    ):
        raise NetlistRecoveryError("BLOCKED_UNCERTAIN_STATE: consumed netlist record changed")
    policy = parent._read_json(POLICY)
    expected = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "operation": phase.OPERATIONS["netlist"],
        "target_sha256": phase.TARGET_SHA256,
        "source_sha256": base_policy["source_fingerprint_sha256"],
        "state_tree_sha256": old_policy["state_tree_sha256"],
        "before_sha256": "0fa357c2e92e20e5a835cc3707668c1fda275e625b4afcd7a4ba905132ee115a",
        "status_sha256": "0271fa428632d8bcfd8f4a9024045c5a73f83ef05a8a1d91ca31fd0649fb1139",
        "ocean_log_sha256": "b1925f5087e9e83298813b3a2ee0d5a8a638fc7334ec2cd2fde0c4601f3d3226",
        "netlist_tree_sha256": "dce155df486c1bb70f3cfd4282f6a002031696b92e0754d78e4d8ed10dfc2387",
        "circuit_netlist_sha256": (
            "6189aa9d647671c05a9f03d815530697560c00b661cad95c87f7f415d482192a"
        ),
        "input_scs_sha256": "d65e913f92e936603dfd4091883100abfb8ee772e12ecc9b6dd1ab43b1c8e445",
    }
    if policy != expected:
        raise NetlistRecoveryError("DENY_OUT_OF_SCOPE: recovery evidence policy changed")
    digest = _sha(v1._canonical(policy))
    if parent._read_json(DELEGATION) != {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "parent_policy_sha256": old_digest,
        "policy_sha256": digest,
        "user_delegation": "explicit-in-current-task",
    }:
        raise NetlistRecoveryError("DENY_OUT_OF_SCOPE: recovery delegation binding absent")
    return policy, digest, state_root, old_policy


def _evidence(policy: dict[str, Any], old_policy: dict[str, Any]) -> dict[str, Any]:
    v1._remote_preflight(
        {
            "source_fingerprint_sha256": policy["source_sha256"],
            "installed_preflight_helper_sha256": old_policy["installed_preflight_helper_sha256"],
        }
    )
    v1._ssh("cd " + phase.REMOTE_VERSION + " && sha256sum -c manifest.sha256")
    v1._ssh(
        "set -e; test -d "
        + BASE
        + "; test ! -L "
        + BASE
        + "; test -d "
        + PROJECT
        + "; test ! -L "
        + PROJECT
        + '; test "$(cd '
        + PROJECT
        + ' && pwd -P)" = '
        + PROJECT
        + "; test -f "
        + NETLIST
        + "; test ! -L "
        + NETLIST
        + "; test -f "
        + INPUT
        + "; test ! -L "
        + INPUT
        + "; test ! -e "
        + BASE
        + "/result.json"
        + "; test ! -e /home/buet/simulation/WP14_AUTO_PHASE_01_TB2"
        + '; test -z "$(ls -A '
        + PSF
        + ')"'
    )
    before = v1._ssh("cat " + BASE + "/before.json")
    status = v1._ssh("cat " + BASE + "/attempt-status.txt")
    log = v1._ssh("cat " + BASE + "/ocean.log")
    if (
        _sha(before) != policy["before_sha256"]
        or _sha(status) != policy["status_sha256"]
        or _sha(log) != policy["ocean_log_sha256"]
        or status != b"ocean_exit=0\nparser_exit=69\n"
        or log.count(b"MCP_WP14_COPIED_NETLIST|true") != 1
        or re.search(rb"Errors: 0\s+Warnings: 0", log) is None
    ):
        raise NetlistRecoveryError("BLOCKED_UNCERTAIN_STATE: OCEAN evidence mismatch")
    after = v1._ssh(
        "/usr/bin/python " + phase.REMOTE_VERSION + "/netlist_helper.py preflight", timeout=90
    )
    first = json.loads(before)
    second = json.loads(after)
    if (
        first != second
        or first.get("locks") != []
        or first.get("target", {}).get("sha256") != policy["target_sha256"]
        or first.get("protected", {}).get("source_cellview_tree") != policy["source_sha256"]
        or first.get("protected", {}).get("ade_state_tree") != policy["state_tree_sha256"]
    ):
        raise NetlistRecoveryError("BLOCKED_UNCERTAIN_STATE: protected or copy drift")
    command = (
        '/usr/bin/python -c \'import imp,json; m=imp.load_source("role","'
        + v1.REMOTE_VERSION
        + '/wp14_role_discovery.py"); '
        + 'print(json.dumps(m._tree_fingerprint("'
        + PROJECT
        + "\"),sort_keys=True))'"
    )
    tree = json.loads(v1._ssh(command))
    if tree != {
        "entry_count": 52,
        "sha256": policy["netlist_tree_sha256"],
        "total_bytes": 64788,
    }:
        raise NetlistRecoveryError("BLOCKED_UNCERTAIN_STATE: netlist tree changed")
    circuit = v1._ssh("cat " + NETLIST)
    input_scs = v1._ssh("cat " + INPUT)
    if (
        len(circuit) != 2100
        or len(input_scs) != 2976
        or _sha(circuit) != policy["circuit_netlist_sha256"]
        or _sha(input_scs) != policy["input_scs_sha256"]
        or b"VBIASN" not in circuit
        or b"VBIASP" not in circuit
        or b"gpdk090" not in input_scs
    ):
        raise NetlistRecoveryError("BLOCKED_UNCERTAIN_STATE: netlist artifacts changed")
    return {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_COPIED_NETLIST_V1",
        "status": "netlisted",
        "source_sha256": policy["source_sha256"],
        "target_sha256": policy["target_sha256"],
        "state_tree_sha256": policy["state_tree_sha256"],
        "netlist_tree_sha256": tree["sha256"],
        "netlist_entries": tree["entry_count"],
        "netlist_bytes": tree["total_bytes"],
        "circuit_netlist_sha256": _sha(circuit),
        "input_scs_sha256": _sha(input_scs),
        "protected_and_copy_unchanged": True,
        "simulation_run": False,
        "recovered_from_parser_artifact_count": True,
    }


def recover() -> dict[str, Any]:
    policy, _digest, state_root, old_policy = _authority()
    payload = _evidence(policy, old_policy)
    raw = v1._canonical(payload) + b"\n"
    output = state_root / "phased-netlist-v1-run.output"
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    record = state_root / "phased-netlist-v1-run.json"
    parent._replace_record(
        record,
        {
            "state": "succeeded",
            "operation": phase.OPERATIONS["netlist"],
            "policy_sha256": policy["parent_policy_sha256"],
            "result_status": "netlisted",
            "raw_sha256": _sha(raw),
            "raw_local_file": str(output),
            "recovery_policy_sha256": _digest,
            "at": datetime.now(UTC).isoformat(),
        },
    )
    return {"state": "succeeded", "result_status": "netlisted", "raw_sha256": _sha(raw)}


def main() -> int:
    if len(sys.argv) != 1:
        print("usage: phase_d_netlist_recover_v1.py", file=sys.stderr)
        return 2
    try:
        result = recover()
    except (
        NetlistRecoveryError,
        phase.NetlistV1Error,
        v1.PhaseBError,
        parent.CampaignError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
