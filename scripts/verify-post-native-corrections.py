"""Read-only POST guard over the retained reconciliation and consumed checkpoint.

Run before native stage/update. This neither creates a journal nor grants authority.
No installation defaults or remote runtime budgets are changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "5e642986b10a11aa5f38d462bc39127fb280fd91"
POLICY = ROOT / "docs/policy/POST_NATIVE_CORRECTION_LIMIT_V7.json"
CHECKPOINT = ROOT / "docs/policy/POST_NATIVE_CORRECTION_CONSUMED_V1.json"
NATIVE_PATHS = [
    "src/cadence_mcp_bridge/" + name
    for name in (
        "_native_dispatch.py",
        "_native_operations.py",
        "_native_gate.py",
        "_native_eda_worker.py",
        "_native_rendering.py",
        "_native_copy.py",
        "_native_setup.py",
        "_operator_confirmation.py",
        "native_runtime.py",
        "native_service.py",
        "native_sweeps.py",
        "_native_recovery.py",
        "extraction_recovery.py",
    )
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def require_ancestor(commit: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("retained source history missing; reconciliation required without refund")


def inspect(reconciliation: Path) -> dict[str, object]:
    policy = json.loads(POLICY.read_bytes())
    checkpoint = json.loads(CHECKPOINT.read_bytes())
    for name, key in (
        ("PHASE_CORRECTION_LIMIT_V5.json", "prior_correction_policy_sha256"),
        ("PHASE_RESULT_LIMIT_V6.json", "prior_result_policy_sha256"),
    ):
        prior = json.loads((POLICY.parent / name).read_bytes())
        if canonical_sha256(prior) != policy[key]:
            raise ValueError("historical policy changed")
    retained_raw = reconciliation.read_bytes()
    retained = json.loads(retained_raw)
    commits = retained["source_commits"]
    if (
        retained["conservative_recorded_source_changes"] != 20
        or len(commits) != 20
        or (
            len({row.split()[0] for row in commits}) != 20
            or not any(row.startswith(BASELINE + " ") for row in commits)
            or policy["retained_consumed_source_changes"] != 20
            or policy["maximum_corrections_same_change"] != 24
        )
    ):
        raise ValueError("retained consumption/policy conflict")
    known = checkpoint["retained_post_source_commits"]
    if (
        checkpoint["schema_version"] != 1
        or checkpoint["baseline_commit"] != BASELINE
        or checkpoint["retained_reconciliation_sha256"] != hashlib.sha256(retained_raw).hexdigest()
        or checkpoint["policy_sha256"] != canonical_sha256(policy)
        or type(checkpoint["retained_consumed_source_changes"]) is not int
        or checkpoint["retained_consumed_source_changes"] != 24
        or type(known) is not list
        or len(known) != 4
        or any(
            type(commit) is not str or re.fullmatch("[0-9a-f]{40}", commit) is None
            for commit in known
        )
        or len(set(known)) != 4
        or checkpoint["source_paths"] != NATIVE_PATHS
        or checkpoint["authority"] != "CONSUMPTION_RECORD_NOT_EXECUTION_AUTHORITY"
    ):
        raise ValueError("retained correction checkpoint conflict")
    # The externally retained identities survive squash/rebase, even when they
    # disappear from HEAD's ancestry. Never reinterpret that disappearance as
    # restored capacity. Normal merges preserve all these original identities.
    require_ancestor(BASELINE)
    for commit in known:
        require_ancestor(commit)
    added = sorted(
        set(
            git(
                "log", "--no-merges", "--format=%H", BASELINE + "..HEAD", "--", *NATIVE_PATHS
            ).splitlines()
        )
    )
    # Uncommitted fixed source is conservatively one pending change, never free.
    pending = bool(git("status", "--porcelain", "--", *NATIVE_PATHS))
    consumed = 20 + len(set(known) | set(added)) + int(pending)
    if consumed > policy["maximum_corrections_same_change"]:
        raise ValueError("native source change ceiling exceeded")
    # History-only counting also misses content introduced by merge conflict
    # resolution. At this fully consumed checkpoint, any selected-tree drift
    # requires a new reconciliation/allowance; a matching tree grants no work.
    source_tree = git("ls-tree", "HEAD", "--", *NATIVE_PATHS)
    if hashlib.sha256(source_tree.encode("utf-8")).hexdigest() != checkpoint["source_tree_sha256"]:
        raise ValueError("retained source tree differs; reconciliation required without refund")
    return {
        "status": "POST_NATIVE_SOURCE_BOUNDARY_PASS",
        "baseline_consumed": 20,
        "new_source_commits": added,
        "pending_source_change": pending,
        "retained_consumed": 24,
        "retained_post_source_commits": sorted(known),
        "retained_checkpoint_sha256": canonical_sha256(checkpoint),
        "source_tree_matched": True,
        "conservative_consumed": consumed,
        "ceiling": 24,
        "remaining": 24 - consumed,
        "ledger_modified": False,
        "remote_contact": False,
        "authority": "DIRECT_USER_CONFIRMATION_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(inspect(arguments.reconciliation), sort_keys=True))
