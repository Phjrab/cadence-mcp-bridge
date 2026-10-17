"""Preserve source36 and failed query1; enforce explicit source40/query11 limits."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "a215500e9f7b2c5e20fad26b4bde9b40059e3be0"
SOURCE36 = "759d84ec435d7ef3636024f78608b34aee13000b"
HISTORY = (
    "PHYSICAL_METADATA_LIMIT_V1.json",
    "PHYSICAL_METADATA_LIMIT_V2.json",
    "PHYSICAL_METADATA_CONSUMED_V1.json",
    "PHYSICAL_METADATA_CONSUMED_V2.json",
    "PHYSICAL_METADATA_CONSUMED_V3.json",
    "PHYSICAL_METADATA_DISCLOSURE_V1.json",
)
SOURCE_ROOTS = ("src", "remote")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def blob(revision: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT)


def inspect() -> dict[str, object]:
    directory = ROOT / "docs/policy"
    policy = json.loads((directory / "PHYSICAL_METADATA_LIMIT_V3.json").read_bytes())
    expected = {
        "schema_version": 3,
        "base_commit": BASELINE,
        "retained_source_commit": SOURCE36,
        "scope": "CURRENT_MANAGED_STANDARD_VM_PHYSICAL_METADATA_02",
        "retained_consumed_source_changes": 36,
        "maximum_corrections_same_change": 40,
        "maximum_new_source_versions": 4,
        "retained_collection_attempts": 1,
        "maximum_additional_collection_attempts": 10,
        "maximum_stage_and_query_attempts": 11,
        "max_new_simulations": 0,
        "max_new_extractions": 0,
        "max_new_reserved_bytes": 0,
        "max_entries": 128,
        "timeout_seconds": 60,
        "max_bytes_per_output_stream": 1048576,
        "max_cumulative_attempts": 500,
        "max_cumulative_result_bytes": 17179869184,
        "merge_authorized": False,
        "publication_authorized": False,
    }
    for key, value in expected.items():
        if canonical(policy.get(key)) != canonical(value):
            raise ValueError("physical V3 finite policy conflict: " + key)
    for revision in (SOURCE36, BASELINE):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, "HEAD"], cwd=ROOT, check=False
        ).returncode:
            raise ValueError("physical retained source history missing")
    for name in HISTORY:
        path = "docs/policy/" + name
        if canonical(json.loads((ROOT / path).read_bytes())) != canonical(
            json.loads(blob(BASELINE, path))
        ):
            raise ValueError("physical immutable policy history changed")
    consumed = json.loads((directory / "PHYSICAL_METADATA_CONSUMED_V3.json").read_bytes())
    if (
        consumed["conservative_consumed_source_changes"] != 36
        or consumed["actual_collector_queries"] != 1
    ):
        raise ValueError("physical retained consumption conflict")
    for path, digest in consumed["source_lf_sha256"].items():
        if sha(blob(SOURCE36, path)) != digest or sha(blob(BASELINE, path)) != digest:
            raise ValueError("physical source36 snapshot changed")
    # Every runtime/product commit counts, even if a later commit reverts it.
    commits = git(
        "log",
        "--full-history",
        "--no-merges",
        "--format=%H",
        BASELINE + "..HEAD",
        "--",
        *SOURCE_ROOTS,
    ).splitlines()
    pending = bool(git("status", "--porcelain", "--", *SOURCE_ROOTS))
    used = len(set(commits)) + int(pending)
    if used > 4:
        raise ValueError("physical source40 exhausted; no reset or refund")
    for revision in git("rev-list", "--merges", BASELINE + "..HEAD").splitlines():
        # A merge bringing in product changes is also one consumed source version.
        if git("diff", "--name-only", revision + "^1", revision, "--", *SOURCE_ROOTS):
            used += 1
    if used > 4:
        raise ValueError("physical merged source40 exhausted")
    changed = set(git("diff", "--name-only", BASELINE, "--", *SOURCE_ROOTS).splitlines())
    untracked = set(
        git("ls-files", "--others", "--exclude-standard", "--", *SOURCE_ROOTS).splitlines()
    )
    if changed | untracked != set(policy["source_lf_sha256"]):
        raise ValueError("physical V3 complete product source inventory")
    for path, digest in policy["source_lf_sha256"].items():
        if sha((ROOT / path).read_bytes()) != digest:
            raise ValueError("physical V3 fixed source changed")
    return {
        "status": "PHYSICAL_METADATA_SOURCE_BOUNDARY_V3_PASS",
        "retained_consumed": 36,
        "additional_source_versions": used,
        "conservative_consumed": 36 + used,
        "ceiling": 40,
        "remaining": 4 - used,
        "retained_collection_attempts": 1,
        "maximum_additional_collection_attempts": 10,
        "cumulative_collection_ceiling": 11,
        "ledger_modified": False,
        "remote_contact": False,
        "authority": "DIRECT_HUMAN_APPROVAL_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    print(json.dumps(inspect(), sort_keys=True))
