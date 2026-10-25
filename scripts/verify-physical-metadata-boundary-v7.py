"""Preserve consumed source60 and apply four initializer-only source versions."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "a215500e9f7b2c5e20fad26b4bde9b40059e3be0"
SOURCE60 = "df522bf7c7b0a09778cc19a4ab854b1589e7a9be"
SOURCE_ROOTS = ("src", "remote")
POLICY_PATH = "docs/policy/PHYSICAL_METADATA_LIMIT_V5.json"
PRIOR_POLICY = "docs/policy/PHYSICAL_METADATA_LIMIT_V4.json"
REQUIRED_HISTORY = (
    PRIOR_POLICY,
    "scripts/verify-physical-metadata-boundary-v6.py",
    "docs/policy/PHYSICAL_METADATA_SOURCE_V6_BINDING_OBSERVER_16.json",
)
ALLOWED_SOURCE_PATHS = (
    "src/cadence_mcp_bridge/_binding_initializer.py",
    "src/cadence_mcp_bridge/binding_initializer.py",
    "src/cadence_mcp_bridge/_binding_observation.py",
    "src/cadence_mcp_bridge/binding_observation_bootstrap.py",
    "src/cadence_mcp_bridge/binding_observation_transport.py",
)
PURPOSES = (
    "INITIALIZER_TRUST_INSPECTION",
    "EXACT_INITIALIZER_PERMISSION_REMEDIATION",
    "PERMITTED_METADATA_DELTA_VALIDATION",
    "REVIEW_CORRECTION_WITHIN_INITIALIZER_SCOPE",
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
    return {
        path: sha(blob(revision, path))
        for path in git("diff", "--name-only", BASELINE, revision, "--", *SOURCE_ROOTS).splitlines()
    }


def retained_history() -> set[str]:
    if not ancestor(BASELINE, SOURCE60) or not ancestor(SOURCE60):
        raise ValueError("physical retained source60 ancestry missing")
    inventory = git("ls-tree", "-r", "--name-only", SOURCE60, "docs/policy", "scripts")
    history = {
        path
        for path in inventory.splitlines()
        if path.startswith("docs/policy/PHYSICAL_METADATA_")
        or path.startswith("scripts/verify-physical-metadata-boundary")
    }
    if not set(REQUIRED_HISTORY) <= history:
        raise ValueError("physical source60 history inventory missing")
    for path in sorted(history):
        if sha((ROOT / path).read_bytes()) != sha(blob(SOURCE60, path)):
            raise ValueError("physical immutable source60 history changed: " + path)
    retained = source_events(SOURCE60)
    if 36 + len(retained) != 60:
        raise ValueError("physical retained source60 accounting conflict")
    return retained


def load_policy() -> dict[str, object]:
    policy: dict[str, object] = json.loads((ROOT / POLICY_PATH).read_bytes())
    expected = {
        "schema_version": 5,
        "authority": "DIRECT_USER_SOURCE64_INITIALIZER_ONLY_2026_10_21",
        "base_commit": BASELINE,
        "retained_source_commit": SOURCE60,
        "retained_consumed_source_changes": 60,
        "maximum_corrections_same_change": 64,
        "maximum_new_source_versions": 4,
        "general_same_change_correction_ceiling": 20,
        "prior_limit_policy": PRIOR_POLICY,
        "prior_limit_policy_canonical_sha256": sha(
            canonical(json.loads(blob(SOURCE60, PRIOR_POLICY)))
        ),
        "scope": "CURRENT_MANAGED_STANDARD_VM_INITIALIZER_TRUST_AND_REMEDIATION_ONLY",
        "allowed_product_source_paths": list(ALLOWED_SOURCE_PATHS),
        "allowed_source_purposes": list(PURPOSES),
        "max_new_vm_accesses": 0,
        "max_new_collection_attempts": 0,
        "max_new_admin_applications": 0,
        "max_new_deployments": 0,
        "max_new_eda_starts": 0,
        "max_new_simulations": 0,
        "max_new_extractions": 0,
        "max_new_reserved_bytes": 0,
        "max_cumulative_attempts": 500,
        "max_cumulative_result_bytes": 17179869184,
        "merge_authorized": False,
        "publication_authorized": False,
        "source_checkpoint_required_for_later_product_changes": True,
        "source_lf_sha256": source_pins(SOURCE60),
    }
    for key, value in expected.items():
        if canonical(policy.get(key)) != canonical(value):
            raise ValueError("physical V5 finite policy conflict: " + key)
    if set(policy) != set(expected) | {"authority_note", "version_unit"}:
        raise ValueError("physical V5 policy inventory")
    return policy


def inspect(checkpoint_name: str | None = None) -> dict[str, object]:
    retained = retained_history()
    policy = load_policy()
    events = source_events("HEAD")
    pending = bool(git("status", "--porcelain", "--untracked-files=all", "--", *SOURCE_ROOTS))
    if not retained <= events:
        raise ValueError("physical retained source events missing")
    consumed = 36 + len(events) + int(pending)
    if consumed > 64:
        raise ValueError("physical source64 exhausted; no reset or refund")
    # Check every new event, including reverted or merged changes: a matching
    # final tree cannot hide an out-of-scope intermediate product edit.
    for event in sorted(events - retained):
        paths = git("diff", "--no-renames", "--name-only", event + "^1", event, "--", *SOURCE_ROOTS)
        if not set(paths.splitlines()) <= set(ALLOWED_SOURCE_PATHS):
            raise ValueError("physical initializer-only product scope conflict")
    changed_since = set(
        git("diff", "--no-renames", "--name-only", SOURCE60, "--", *SOURCE_ROOTS).splitlines()
    )
    untracked = set(
        git("ls-files", "--others", "--exclude-standard", "--", *SOURCE_ROOTS).splitlines()
    )
    if not changed_since | untracked <= set(ALLOWED_SOURCE_PATHS):
        raise ValueError("physical initializer-only product scope conflict")
    pins = policy["source_lf_sha256"]
    if checkpoint_name is None:
        if pending or events != retained:
            raise ValueError("physical new source requires an additive checkpoint")
    else:
        if (
            Path(checkpoint_name).name != checkpoint_name
            or not checkpoint_name.startswith("PHYSICAL_METADATA_SOURCE_V7_")
            or not checkpoint_name.endswith(".json")
        ):
            raise ValueError("physical checkpoint filename")
        checkpoint = json.loads((ROOT / "docs/policy" / checkpoint_name).read_bytes())
        expected = {
            "schema_version": 7,
            "source_version": consumed,
            "limit_policy": POLICY_PATH,
            "limit_policy_canonical_sha256": sha(canonical(policy)),
            "approval_anchor_commit": SOURCE60,
            "retained_source_changes": 60,
        }
        if (
            any(
                canonical(checkpoint.get(key)) != canonical(value)
                for key, value in expected.items()
            )
            or checkpoint.get("source_purpose") not in PURPOSES
            or set(checkpoint)
            != set(expected) | {"source_purpose", "source_lf_sha256", "authority_note"}
        ):
            raise ValueError("physical source checkpoint binding")
        pins = checkpoint["source_lf_sha256"]
    changed = set(git("diff", "--name-only", BASELINE, "--", *SOURCE_ROOTS).splitlines())
    if not isinstance(pins, dict) or changed | untracked != set(pins):
        raise ValueError("physical complete product source inventory")
    for path, digest in pins.items():
        if sha((ROOT / path).read_bytes()) != digest:
            raise ValueError("physical pinned source changed")
    return {
        "status": "PHYSICAL_METADATA_SOURCE_BOUNDARY_V7_PASS",
        "approval_anchor": SOURCE60,
        "retained_consumed": 60,
        "additional_source_versions": consumed - 60,
        "conservative_consumed": consumed,
        "ceiling": 64,
        "remaining": 64 - consumed,
        "prior_limit_and_guards_preserved": True,
        "new_vm_access_authorized": False,
        "admin_application_authorized": False,
        "merge_authorized": False,
        "publication_authorized": False,
        "ledger_modified": False,
        "remote_contact": False,
        "authority": "DIRECT_HUMAN_APPROVAL_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint")
    print(json.dumps(inspect(parser.parse_args().checkpoint), sort_keys=True))
