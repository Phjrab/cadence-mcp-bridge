"""Read-only M2 overlay; preserve POST's frozen24 and count each new source version."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("src/cadence_mcp_bridge/m2_cdf.py", "src/cadence_mcp_bridge/m2_inverter.py")


def inspect(reconciliation: Path) -> dict[str, object]:
    spec = importlib.util.spec_from_file_location(
        "post_guard", ROOT / "scripts/verify-post-native-corrections.py"
    )
    assert spec is not None and spec.loader is not None
    post = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(post)
    retained = post.inspect(reconciliation)
    policy = json.loads((ROOT / "docs/policy/M2_NATIVE_CORRECTION_LIMIT_V8.json").read_bytes())
    if (
        retained["conservative_consumed"] != 24
        or policy["retained_consumed_source_changes"] != 24
        or policy["maximum_corrections_same_change"] != 26
        or policy["maximum_collector_versions"] != 1
        or policy["maximum_generator_versions"] != 1
        or policy["max_cumulative_result_bytes"] != 17179869184
        or policy["max_cumulative_attempts"] != 500
    ):
        raise ValueError("M2 retained source/policy conflict")
    post.require_ancestor(policy["base_commit"])
    counts = []
    for path in SOURCES:
        commits = set(
            post.git(
                "log",
                "--full-history",
                "--no-merges",
                "--format=%H",
                policy["base_commit"] + "..HEAD",
                "--",
                path,
            ).splitlines()
        )
        pending = bool(post.git("status", "--porcelain", "--", path))
        count = len(commits) + int(pending)
        if count > 1:
            raise ValueError("M2 fixed source version exhausted; retain failure and stop")
        # Detect source introduced/changed by a merge without a counted source commit.
        if commits:
            commit = next(iter(commits))
            if post.git("ls-tree", commit, "--", path) != post.git("ls-tree", "HEAD", "--", path):
                raise ValueError("M2 source changed through merge; reconciliation required")
        elif post.git("ls-tree", "HEAD", "--", path):
            raise ValueError("M2 source without version history")
        counts.append(count)
    return {
        "status": "M2_NATIVE_SOURCE_BOUNDARY_PASS",
        "retained_consumed": 24,
        "collector_versions": counts[0],
        "generator_versions": counts[1],
        "conservative_consumed": 24 + sum(counts),
        "ceiling": 26,
        "remaining": 2 - sum(counts),
        "ledger_modified": False,
        "remote_contact": False,
        "authority": "DIRECT_HUMAN_APPROVAL_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.reconciliation), sort_keys=True))
