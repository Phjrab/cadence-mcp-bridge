"""Read-only M2 overlay; preserve POST's frozen24 and count each new source version."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("src/cadence_mcp_bridge/m2_cdf.py", "src/cadence_mcp_bridge/m2_inverter.py")


def load_post() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "post_guard", ROOT / "scripts/verify-post-native-corrections.py"
    )
    assert spec is not None and spec.loader is not None
    post = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(post)
    return post


def inspect(reconciliation: Path) -> dict[str, object]:
    post = load_post()
    retained = post.inspect(reconciliation)
    if (ROOT / "docs/policy/M2_NATIVE_CORRECTION_LIMIT_V9.json").exists():
        return inspect_v9(post, retained)
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
    checkpoint = json.loads(
        (ROOT / "docs/policy/M2_NATIVE_CORRECTION_CONSUMED_V1.json").read_bytes()
    )
    if (
        checkpoint["retained_consumed_source_changes"] != 25
        or checkpoint["authority"] != "CONSUMPTION_RECORD_NOT_EXECUTION_AUTHORITY"
        or checkpoint["base_commit"] != policy["base_commit"]
        or checkpoint["generator_versions_consumed"] != 0
    ):
        raise ValueError("M2 consumed checkpoint conflict; no refund")
    post.require_ancestor(checkpoint["collector_commit"])
    if (
        hashlib.sha256((ROOT / SOURCES[0]).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        != (checkpoint["collector_module_lf_sha256"])
    ):
        raise ValueError("M2 deployed collector differs; no corrective deployment")
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


def inspect_v9(post: ModuleType, retained: dict[str, object]) -> dict[str, object]:
    directory = ROOT / "docs/policy"
    old = json.loads((directory / "M2_NATIVE_CORRECTION_LIMIT_V8.json").read_bytes())
    checkpoint = json.loads((directory / "M2_NATIVE_CORRECTION_CONSUMED_V1.json").read_bytes())
    v9 = json.loads((directory / "M2_NATIVE_CORRECTION_LIMIT_V9.json").read_bytes())
    policy = v9
    consumed, ceiling = 25, 27
    latest_path = directory / "M2_NATIVE_CORRECTION_LIMIT_V10.json"
    if latest_path.exists():
        current_checkpoint = json.loads(
            (directory / "M2_NATIVE_CORRECTION_CONSUMED_V2.json").read_bytes()
        )
        policy = json.loads(latest_path.read_bytes())
        if (
            policy["prior_policy_sha256"] != post.canonical_sha256(v9)
            or policy["prior_consumed_checkpoint_sha256"]
            != post.canonical_sha256(current_checkpoint)
            or current_checkpoint["prior_consumed_checkpoint_sha256"]
            != post.canonical_sha256(checkpoint)
            or current_checkpoint["retained_consumed_source_changes"] != 26
            or current_checkpoint["generator_versions_consumed"] != 0
        ):
            raise ValueError("M2 latest policy/consumption chain conflict")
        post.require_ancestor(current_checkpoint["corrected_collector_commit"])
        previous_source = subprocess.check_output(
            ["git", "show", current_checkpoint["corrected_collector_commit"] + ":" + SOURCES[0]],
            cwd=post.ROOT,
        )
        if (
            hashlib.sha256(previous_source.replace(b"\r\n", b"\n")).hexdigest()
            != (current_checkpoint["collector_module_lf_sha256"])
        ):
            raise ValueError("M2 failed corrected collector identity changed")
        consumed, ceiling = 26, 28
        for version in (11, 12):
            next_path = directory / f"M2_NATIVE_CORRECTION_LIMIT_V{version}.json"
            if not next_path.exists():
                break
            next_checkpoint = json.loads(
                (directory / f"M2_NATIVE_CORRECTION_CONSUMED_V{version - 8}.json").read_bytes()
            )
            next_policy = json.loads(next_path.read_bytes())
            if (
                next_policy["prior_policy_sha256"] != post.canonical_sha256(policy)
                or next_policy["prior_consumed_checkpoint_sha256"]
                != post.canonical_sha256(next_checkpoint)
                or next_checkpoint["prior_consumed_checkpoint_sha256"]
                != post.canonical_sha256(current_checkpoint)
                or next_checkpoint["retained_consumed_source_changes"] != version + 16
                or next_checkpoint["generator_versions_consumed"] != 0
                or next_policy["base_commit"] != next_checkpoint["corrected_collector_commit"]
            ):
                raise ValueError("M2 V11 retained failure chain conflict")
            post.require_ancestor(next_checkpoint["corrected_collector_commit"])
            previous = subprocess.check_output(
                ["git", "show", next_checkpoint["corrected_collector_commit"] + ":" + SOURCES[0]],
                cwd=post.ROOT,
            )
            if (
                hashlib.sha256(previous.replace(b"\r\n", b"\n")).hexdigest()
                != (next_checkpoint["collector_module_lf_sha256"])
            ):
                raise ValueError("M2 source27 identity changed")
            policy = next_policy
            current_checkpoint = next_checkpoint
            consumed, ceiling = version + 16, version + 18
    generator_limit = 1
    completed = (
        json.loads((directory / "M2_NATIVE_CORRECTION_CONSUMED_V5.json").read_bytes())
        if (directory / "M2_NATIVE_CORRECTION_LIMIT_V13.json").exists()
        else {}
    )
    for version in (13, 14, 15):
        generator_extension = directory / f"M2_NATIVE_CORRECTION_LIMIT_V{version}.json"
        if not generator_extension.exists():
            break
        extension = json.loads(generator_extension.read_bytes())
        failed = json.loads(
            (directory / f"M2_NATIVE_CORRECTION_CONSUMED_V{version - 7}.json").read_bytes()
        )
        if (
            consumed != 28
            or extension["prior_policy_sha256"] != post.canonical_sha256(policy)
            or extension["prior_consumed_checkpoint_sha256"] != post.canonical_sha256(failed)
            or failed["prior_consumed_checkpoint_sha256"] != post.canonical_sha256(completed)
            or failed["retained_consumed_source_changes"] != version + 17
            or failed["generator_versions_consumed"] != version - 12
            or extension["base_commit"] != policy["base_commit"]
        ):
            raise ValueError("M2 failed generator retention chain conflict")
        post.require_ancestor(failed["generator_commit"])
        previous = subprocess.check_output(
            ["git", "show", failed["generator_commit"] + ":" + SOURCES[1]], cwd=post.ROOT
        )
        if (
            hashlib.sha256(previous.replace(b"\r\n", b"\n")).hexdigest()
            != (failed["generator_module_lf_sha256"])
        ):
            raise ValueError("M2 failed generator identity changed")
        policy, ceiling, generator_limit = extension, version + 18, version - 11
        completed = failed
    if (
        retained["conservative_consumed"] != 24
        or v9["prior_policy_sha256"] != post.canonical_sha256(old)
        or v9["prior_consumed_checkpoint_sha256"] != post.canonical_sha256(checkpoint)
        or checkpoint["retained_consumed_source_changes"] != 25
        or checkpoint["generator_versions_consumed"] != 0
        or policy["retained_consumed_source_changes"] != consumed
        or policy["maximum_corrections_same_change"] != ceiling
        or policy["maximum_collector_corrections"] != 1
        or policy["maximum_generator_versions"] != generator_limit
        or policy["max_new_attempts"] != 2
        or policy["allowed_analyses"] != ["dc", "tran"]
        or policy["max_phase_result_bytes"] != 268435456
        or policy["max_cumulative_result_bytes"] != 17179869184
        or policy["max_cumulative_attempts"] != 500
    ):
        raise ValueError("M2 V9 policy/retained consumption conflict")
    post.require_ancestor(checkpoint["collector_commit"])
    post.require_ancestor(policy["base_commit"])
    original = subprocess.check_output(
        ["git", "show", checkpoint["collector_commit"] + ":" + SOURCES[0]], cwd=post.ROOT
    )
    if (
        hashlib.sha256(original.replace(b"\r\n", b"\n")).hexdigest()
        != (checkpoint["collector_module_lf_sha256"])
    ):
        raise ValueError("retained failed collector identity changed")
    counts = []
    for path, limit in zip(SOURCES, (1, generator_limit), strict=True):
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
        if count > limit:
            raise ValueError("M2 V9 fixed source version exhausted; preserve failure")
        if commits:
            commit = post.git(
                "log",
                "--full-history",
                "--no-merges",
                "-1",
                "--format=%H",
                policy["base_commit"] + "..HEAD",
                "--",
                path,
            )
            if post.git("ls-tree", commit, "--", path) != post.git("ls-tree", "HEAD", "--", path):
                raise ValueError("M2 V9 uncounted merge source change")
        elif post.git("ls-tree", policy["base_commit"], "--", path) != (
            post.git("ls-tree", "HEAD", "--", path)
        ):
            raise ValueError("M2 V9 source change without history")
        counts.append(count)
    successful_path = directory / "M2_NATIVE_CORRECTION_CONSUMED_V5.json"
    if successful_path.exists():
        successful = json.loads(successful_path.read_bytes())
        previous_checkpoint = json.loads(
            (directory / "M2_NATIVE_CORRECTION_CONSUMED_V4.json").read_bytes()
        )
        post.require_ancestor(successful["corrected_collector_commit"])
        if (
            successful["retained_consumed_source_changes"] != 29
            or consumed != 28
            or counts[0] != 1
            or successful["prior_consumed_checkpoint_sha256"]
            != post.canonical_sha256(previous_checkpoint)
            or hashlib.sha256((ROOT / SOURCES[0]).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            != successful["collector_module_lf_sha256"]
        ):
            raise ValueError("M2 completed collector checkpoint conflict; no refund or drift")
    consumed_path = directory / "M2_NATIVE_CORRECTION_CONSUMED_V2.json"
    if consumed_path.exists() and not latest_path.exists():
        current = json.loads(consumed_path.read_bytes())
        post.require_ancestor(current["corrected_collector_commit"])
        if current["retained_consumed_source_changes"] != 26 or counts[0] != 1:
            raise ValueError("M2 corrected collector consumption missing; no refund")
        if (
            hashlib.sha256((ROOT / SOURCES[0]).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            != (current["collector_module_lf_sha256"])
        ):
            raise ValueError("M2 corrected collector source drift")
    return {
        "status": "M2_NATIVE_SOURCE_BOUNDARY_PASS",
        "retained_consumed": consumed,
        "collector_corrections": counts[0],
        "generator_versions": counts[1],
        "conservative_consumed": consumed + sum(counts),
        "ceiling": ceiling,
        "remaining": ceiling - consumed - sum(counts),
        "ledger_modified": False,
        "remote_contact": False,
        "authority": "DIRECT_HUMAN_APPROVAL_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.reconciliation), sort_keys=True))
