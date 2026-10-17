"""Retain source40 history and apply the human-approved source60 ceiling additively."""

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
SOURCE38 = "d64a5ea25f17465ef910a35c06f9a16e2d2269d6"
ANCHOR = "4ba577fe141fddd44fd0a9dd28d6ab326776a130"
MAIN = "9a10f66db9a2fb27d0810a8dee2217dd85d5cbad"
SOURCE_ROOTS = ("src", "remote")
POLICY_PATH = "docs/policy/PHYSICAL_METADATA_LIMIT_V4.json"
HISTORY = (
    "docs/policy/PHYSICAL_METADATA_LIMIT_V1.json",
    "docs/policy/PHYSICAL_METADATA_LIMIT_V2.json",
    "docs/policy/PHYSICAL_METADATA_LIMIT_V3.json",
    "docs/policy/PHYSICAL_METADATA_CONSUMED_V1.json",
    "docs/policy/PHYSICAL_METADATA_CONSUMED_V2.json",
    "docs/policy/PHYSICAL_METADATA_CONSUMED_V3.json",
    "docs/policy/PHYSICAL_METADATA_DISCLOSURE_V1.json",
    "docs/policy/PHYSICAL_METADATA_SOURCE_V4.json",
    "scripts/verify-physical-metadata-boundary.py",
    "scripts/verify-physical-metadata-boundary-v2.py",
    "scripts/verify-physical-metadata-boundary-v3.py",
    "scripts/verify-physical-metadata-boundary-v4.py",
    "scripts/verify-physical-metadata-boundary-v5.py",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def blob(revision: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT)


def ancestor(revision: str, descendant: str = "HEAD") -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, descendant], cwd=ROOT, check=False
        ).returncode
        == 0
    )


def source_events(revision: str) -> set[str]:
    events = set(
        git(
            "log",
            "--full-history",
            "--no-merges",
            "--format=%H",
            BASELINE + ".." + revision,
            "--",
            *SOURCE_ROOTS,
        ).splitlines()
    )
    for merge in git("rev-list", "--merges", BASELINE + ".." + revision).splitlines():
        if git("diff", "--name-only", merge + "^1", merge, "--", *SOURCE_ROOTS):
            events.add(merge)
    return events


def source_pins(revision: str) -> dict[str, str]:
    paths = git("diff", "--name-only", BASELINE, revision, "--", *SOURCE_ROOTS).splitlines()
    return {path: sha(blob(revision, path)) for path in paths}


def retained_history() -> set[str]:
    for revision in (BASELINE, SOURCE36, SOURCE37, SOURCE38, MAIN, ANCHOR):
        if not ancestor(revision):
            raise ValueError("physical retained source ancestry missing")
    # Check the original files as well as every later immutable guard/checkpoint.
    # No old guard is patched or run with a substituted ceiling/checkpoint.
    for path in HISTORY:
        if sha((ROOT / path).read_bytes()) != sha(blob(ANCHOR, path)):
            raise ValueError("physical immutable history changed: " + path)
    for path in HISTORY[:2] + HISTORY[3:7]:
        if sha(blob(ANCHOR, path)) != sha(blob(BASELINE, path)):
            raise ValueError("physical baseline history conflict")
    for path in (HISTORY[2], HISTORY[10]):
        if sha(blob(ANCHOR, path)) != sha(blob(SOURCE37, path)):
            raise ValueError("physical source37 history conflict")
    for path in (HISTORY[7], HISTORY[11]):
        if sha(blob(ANCHOR, path)) != sha(blob(SOURCE38, path)):
            raise ValueError("physical source38 history conflict")
    consumed = json.loads(blob(BASELINE, HISTORY[5]))
    if (
        consumed["conservative_consumed_source_changes"] != 36
        or consumed["actual_collector_queries"] != 1
    ):
        raise ValueError("physical retained consumption conflict")
    for path, digest in consumed["source_lf_sha256"].items():
        if sha(blob(SOURCE36, path)) != digest or sha(blob(BASELINE, path)) != digest:
            raise ValueError("physical source36 snapshot changed")
    old_policy = json.loads(blob(SOURCE37, HISTORY[2]))
    for path, digest in old_policy["source_lf_sha256"].items():
        if sha(blob(SOURCE37, path)) != digest:
            raise ValueError("physical source37 snapshot changed")
    events = source_events(ANCHOR)
    if len(events) != 4:
        raise ValueError("physical retained source40 accounting conflict")
    return events


def load_policy() -> dict[str, object]:
    policy: dict[str, object] = json.loads((ROOT / POLICY_PATH).read_bytes())
    expected = {
        "schema_version": 4,
        "authority": "DIRECT_USER_SOURCE60_AND_PR162_NORMAL_INTEGRATION_2026_10_17",
        "base_commit": BASELINE,
        "retained_source_commit": ANCHOR,
        "normal_merge_base_commit": MAIN,
        "scope": "CURRENT_MANAGED_STANDARD_VM_PHYSICAL_METADATA_03",
        "retained_consumed_source_changes": 40,
        "maximum_corrections_same_change": 60,
        "maximum_new_source_versions": 20,
        "general_same_change_correction_ceiling": 20,
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
        "merge_authorized": True,
        "merge_scope": "PR162_NORMAL_INTEGRATION_ONLY_NO_PROTECTION_BYPASS",
        "publication_authorized": False,
        "source_checkpoint_required_for_later_product_changes": True,
        "source_lf_sha256": source_pins(ANCHOR),
    }
    for key, value in expected.items():
        if canonical(policy.get(key)) != canonical(value):
            raise ValueError("physical V4 finite policy conflict: " + key)
    if set(policy) != set(expected) | {"authority_note", "version_unit"}:
        raise ValueError("physical V4 policy inventory")
    return policy


def is_normal_integration(merge: str) -> bool:
    parents = git("show", "--no-patch", "--format=%P", merge).split()
    if len(parents) != 2:
        return False
    first, second = parents
    # Policy/docs/test commits may follow the approved candidate and main.
    # Their product trees must remain exactly the approved input trees.
    return (
        ancestor(MAIN, first)
        and ancestor(ANCHOR, second)
        and not git("diff", "--name-only", MAIN, first, "--", *SOURCE_ROOTS)
        and not git("diff", "--name-only", ANCHOR, second, "--", *SOURCE_ROOTS)
        and not git("diff", "--name-only", ANCHOR, merge, "--", *SOURCE_ROOTS)
    )


def inspect(checkpoint_name: str | None = None) -> dict[str, object]:
    retained = retained_history()
    policy = load_policy()
    events = source_events("HEAD")
    pending = bool(git("status", "--porcelain", "--", *SOURCE_ROOTS))
    if not retained <= events:
        raise ValueError("physical retained source events missing")
    consumed = 36 + len(events) + int(pending)
    if consumed > 60:
        raise ValueError("physical source60 exhausted; no reset or refund")
    pins = policy["source_lf_sha256"]
    if checkpoint_name is None:
        additional = events - retained
        if (
            pending
            or len(additional) > 1
            or any(not is_normal_integration(event) for event in additional)
        ):
            raise ValueError("physical new source requires an additive checkpoint")
    else:
        if (
            Path(checkpoint_name).name != checkpoint_name
            or not checkpoint_name.startswith("PHYSICAL_METADATA_SOURCE_V6_")
            or not checkpoint_name.endswith(".json")
        ):
            raise ValueError("physical checkpoint filename")
        checkpoint = json.loads((ROOT / "docs/policy" / checkpoint_name).read_bytes())
        if (
            checkpoint.get("schema_version") != 6
            or checkpoint.get("source_version") != consumed
            or checkpoint.get("limit_policy") != POLICY_PATH
            or checkpoint.get("limit_policy_canonical_sha256") != sha(canonical(policy))
            or checkpoint.get("approval_anchor_commit") != ANCHOR
            or checkpoint.get("retained_source_changes") != 40
        ):
            raise ValueError("physical source checkpoint binding")
        pins = checkpoint.get("source_lf_sha256")
    changed = set(git("diff", "--name-only", BASELINE, "--", *SOURCE_ROOTS).splitlines())
    untracked = set(
        git("ls-files", "--others", "--exclude-standard", "--", *SOURCE_ROOTS).splitlines()
    )
    if not isinstance(pins, dict) or changed | untracked != set(pins):
        raise ValueError("physical complete product source inventory")
    for path, digest in pins.items():
        if sha((ROOT / path).read_bytes()) != digest:
            raise ValueError("physical pinned source changed")
    return {
        "status": "PHYSICAL_METADATA_SOURCE_BOUNDARY_V6_PASS",
        "approval_anchor": ANCHOR,
        "retained_consumed": 40,
        "additional_source_versions": consumed - 40,
        "conservative_consumed": consumed,
        "ceiling": 60,
        "remaining": 60 - consumed,
        "retained_collection_attempts": 1,
        "maximum_additional_collection_attempts": 10,
        "cumulative_collection_ceiling": 11,
        "prior_limit_and_guards_preserved": True,
        "merge_authority_scope": "PR162_NORMAL_INTEGRATION_ONLY",
        "publication_authorized": False,
        "ledger_modified": False,
        "remote_contact": False,
        "authority": "DIRECT_HUMAN_APPROVAL_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint")
    print(json.dumps(inspect(parser.parse_args().checkpoint), sort_keys=True))
