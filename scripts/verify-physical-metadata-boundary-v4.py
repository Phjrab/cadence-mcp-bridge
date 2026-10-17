"""Qualify a new pinned source without rewriting the immutable source37 V3 limit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "a215500e9f7b2c5e20fad26b4bde9b40059e3be0"
SOURCE36 = "759d84ec435d7ef3636024f78608b34aee13000b"
SOURCE37 = "d456bf8228647a1171c028e3bea9d92b9377e9c0"
SOURCE_ROOTS = ("src", "remote")
HISTORY = (
    "docs/policy/PHYSICAL_METADATA_LIMIT_V1.json",
    "docs/policy/PHYSICAL_METADATA_LIMIT_V2.json",
    "docs/policy/PHYSICAL_METADATA_CONSUMED_V1.json",
    "docs/policy/PHYSICAL_METADATA_CONSUMED_V2.json",
    "docs/policy/PHYSICAL_METADATA_CONSUMED_V3.json",
    "docs/policy/PHYSICAL_METADATA_DISCLOSURE_V1.json",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def blob(revision: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT)


def inspect(checkpoint_name: str = "PHYSICAL_METADATA_SOURCE_V4.json") -> dict[str, object]:
    if Path(checkpoint_name).name != checkpoint_name:
        raise ValueError("physical checkpoint filename")
    policy_path = "docs/policy/PHYSICAL_METADATA_LIMIT_V3.json"
    policy = json.loads((ROOT / policy_path).read_bytes())
    if canonical(policy) != canonical(json.loads(blob(SOURCE37, policy_path))):
        raise ValueError("physical immutable V3 limit changed")
    guard_path = "scripts/verify-physical-metadata-boundary-v3.py"
    if sha((ROOT / guard_path).read_bytes()) != sha(blob(SOURCE37, guard_path)):
        raise ValueError("physical immutable V3 guard changed")
    # V3 is the user's unchanged40/+10 instruction. Source pins in that document
    # describe source37 historically; this new checkpoint pins the newer source.
    if (
        policy["retained_consumed_source_changes"] != 36
        or policy["maximum_corrections_same_change"] != 40
        or policy["maximum_new_source_versions"] != 4
        or policy["retained_collection_attempts"] != 1
        or policy["maximum_additional_collection_attempts"] != 10
        or policy["maximum_stage_and_query_attempts"] != 11
    ):
        raise ValueError("physical retained finite limits conflict")
    for revision in (SOURCE36, BASELINE):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, "HEAD"], cwd=ROOT, check=False
        ).returncode:
            raise ValueError("physical retained source history missing")
    for path in HISTORY:
        if canonical(json.loads((ROOT / path).read_bytes())) != canonical(
            json.loads(blob(BASELINE, path))
        ):
            raise ValueError("physical immutable history changed")
    consumed = json.loads((ROOT / HISTORY[4]).read_bytes())
    if (
        consumed["conservative_consumed_source_changes"] != 36
        or consumed["actual_collector_queries"] != 1
    ):
        raise ValueError("physical retained consumption conflict")
    for path, digest in consumed["source_lf_sha256"].items():
        if sha(blob(SOURCE36, path)) != digest or sha(blob(BASELINE, path)) != digest:
            raise ValueError("physical source36 snapshot changed")
    for path, digest in policy["source_lf_sha256"].items():
        if sha(blob(SOURCE37, path)) != digest:
            raise ValueError("physical source37 snapshot changed")
    commits = git(
        "log",
        "--full-history",
        "--no-merges",
        "--format=%H",
        BASELINE + "..HEAD",
        "--",
        *SOURCE_ROOTS,
    ).splitlines()
    used = len(set(commits)) + int(bool(git("status", "--porcelain", "--", *SOURCE_ROOTS)))
    for revision in git("rev-list", "--merges", BASELINE + "..HEAD").splitlines():
        if git("diff", "--name-only", revision + "^1", revision, "--", *SOURCE_ROOTS):
            used += 1
    if used > 4:
        raise ValueError("physical source40 exhausted; no reset or refund")
    checkpoint = json.loads((ROOT / "docs/policy" / checkpoint_name).read_bytes())
    if (
        checkpoint["schema_version"] != 4
        or checkpoint["source_version"] != 36 + used
        or checkpoint["limit_policy"] != policy_path
        or checkpoint["limit_policy_canonical_sha256"] != sha(canonical(policy))
    ):
        raise ValueError("physical source checkpoint binding")
    changed = set(git("diff", "--name-only", BASELINE, "--", *SOURCE_ROOTS).splitlines())
    untracked = set(
        git("ls-files", "--others", "--exclude-standard", "--", *SOURCE_ROOTS).splitlines()
    )
    if changed | untracked != set(checkpoint["source_lf_sha256"]):
        raise ValueError("physical complete product source inventory")
    for path, digest in checkpoint["source_lf_sha256"].items():
        if sha((ROOT / path).read_bytes()) != digest:
            raise ValueError("physical pinned source changed")
    return {
        "status": "PHYSICAL_METADATA_SOURCE_BOUNDARY_V4_PASS",
        "retained_consumed": 36,
        "additional_source_versions": used,
        "conservative_consumed": 36 + used,
        "ceiling": 40,
        "remaining": 4 - used,
        "retained_collection_attempts": 1,
        "maximum_additional_collection_attempts": 10,
        "cumulative_collection_ceiling": 11,
        "prior_limit_and_guards_preserved": True,
        "ledger_modified": False,
        "remote_contact": False,
        "authority": "DIRECT_HUMAN_APPROVAL_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default="PHYSICAL_METADATA_SOURCE_V4.json")
    print(json.dumps(inspect(parser.parse_args().checkpoint), sort_keys=True))
