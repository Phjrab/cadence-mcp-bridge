"""Read-only POST source-change guard over the retained20-change reconciliation.

Run before native stage/update. This neither creates a journal nor grants authority.
No installation defaults or remote runtime budgets are changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "5e642986b10a11aa5f38d462bc39127fb280fd91"
POLICY = ROOT / "docs/policy/POST_NATIVE_CORRECTION_LIMIT_V7.json"
NATIVE_PATHS = [
    "src/cadence_mcp_bridge/" + name for name in (
        "_native_dispatch.py", "_native_operations.py", "_native_gate.py",
        "_native_eda_worker.py", "_native_rendering.py", "_native_copy.py", "_native_setup.py",
        "_operator_confirmation.py", "native_runtime.py", "native_service.py",
        "native_sweeps.py", "_native_recovery.py", "extraction_recovery.py",
    )
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def inspect(reconciliation: Path) -> dict[str, object]:
    policy = json.loads(POLICY.read_bytes())
    for name, key in (
        ("PHASE_CORRECTION_LIMIT_V5.json", "prior_correction_policy_sha256"),
        ("PHASE_RESULT_LIMIT_V6.json", "prior_result_policy_sha256"),
    ):
        prior = json.loads((POLICY.parent / name).read_bytes())
        raw = json.dumps(prior, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("ascii")
        if hashlib.sha256(raw).hexdigest() != policy[key]:
            raise ValueError("historical policy changed")
    retained = json.loads(reconciliation.read_bytes())
    commits = retained["source_commits"]
    if retained["conservative_recorded_source_changes"] != 20 or len(commits) != 20 or (
        len({row.split()[0] for row in commits}) != 20
        or not any(row.startswith(BASELINE + " ") for row in commits)
        or policy["retained_consumed_source_changes"] != 20
        or policy["maximum_corrections_same_change"] != 24
    ):
        raise ValueError("retained consumption/policy conflict")
    subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE, "HEAD"], cwd=ROOT,
                   check=True, capture_output=True)
    added = sorted(set(git("log", "--no-merges", "--format=%H", BASELINE + "..HEAD",
                           "--", *NATIVE_PATHS).splitlines()))
    # Uncommitted fixed source is conservatively one pending change, never free.
    pending = bool(git("status", "--porcelain", "--", *NATIVE_PATHS))
    consumed = 20 + len(added) + int(pending)
    if consumed > policy["maximum_corrections_same_change"]:
        raise ValueError("native source change ceiling exceeded")
    return {
        "status": "POST_NATIVE_SOURCE_BOUNDARY_PASS", "baseline_consumed": 20,
        "new_source_commits": added, "pending_source_change": pending,
        "conservative_consumed": consumed, "ceiling": 24, "remaining": 24 - consumed,
        "ledger_modified": False, "remote_contact": False,
        "authority": "DIRECT_USER_CONFIRMATION_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(inspect(arguments.reconciliation), sort_keys=True))
