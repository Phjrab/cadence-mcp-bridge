"""Retain source35 and permit exactly one host-only source36 correction."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "3240cb6ac2ea31406ca2c8eb027734e6692da4c5"
SOURCE35 = "35883eba22e4d8697787a59462e497d29575be23"
SOURCES = (
    "src/cadence_mcp_bridge/_physical_metadata.py",
    "src/cadence_mcp_bridge/physical_metadata.py",
)
FROZEN = {
    "PHYSICAL_METADATA_LIMIT_V1.json": (
        "36a3e9160851c9fa79ba64e165f313d788a5864b4ab5c9c078df8f7c4e89b741"
    ),
    "PHYSICAL_METADATA_CONSUMED_V1.json": (
        "0e9d071ff548655449a15dac099608d944d1c91ff1f495ed85ae7785f69f177f"
    ),
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha(value: object) -> str:
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii"))


def prior() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "physical_v1_guard", ROOT / "scripts/verify-physical-metadata-boundary.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def inspect(reconciliation: Path) -> dict[str, object]:
    directory = ROOT / "docs/policy"
    for name, expected in FROZEN.items():
        if canonical_sha(json.loads((directory / name).read_bytes())) != expected:
            raise ValueError("physical immutable V1 history changed")
    retained = prior()
    for name, expected in retained.PRIOR.items():
        if canonical_sha(json.loads((directory / name).read_bytes())) != expected:
            raise ValueError("physical old M2 policy changed")
    old = retained.load_retained().inspect(reconciliation)
    if old["conservative_consumed"] != 34 or old["remaining"] != 0:
        raise ValueError("physical old consumption conflict")
    policy = json.loads((directory / "PHYSICAL_METADATA_LIMIT_V2.json").read_bytes())
    for key, expected in {
        "schema_version": 2,
        "base_commit": BASELINE,
        "retained_source_commit": SOURCE35,
        "scope": "CURRENT_MANAGED_STANDARD_VM_PHYSICAL_METADATA_01",
        "retained_consumed_source_changes": 35,
        "maximum_corrections_same_change": 36,
        "maximum_new_source_versions": 1,
        "host_only_correction": True,
        "remote_collector_unchanged": True,
        "maximum_stage_and_query_attempts": 1,
        "max_new_simulations": 0,
        "max_new_extractions": 0,
        "max_new_reserved_bytes": 0,
        "max_entries": 128,
        "timeout_seconds": 60,
        "max_bytes_per_output_stream": 1048576,
        "max_cumulative_attempts": 500,
        "max_cumulative_result_bytes": 17179869184,
        "automatic_corrective_redeployment": False,
        "merge_authorized": False,
        "publication_authorized": False,
        "prior_canonical_sha256": FROZEN,
    }.items():
        if canonical_sha(policy.get(key)) != canonical_sha(expected):
            raise ValueError("physical V2 finite policy conflict: " + key)
    for base in (BASELINE, SOURCE35):
        if subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=ROOT, check=False
        ).returncode:
            raise ValueError("physical V2 retained history missing")
    v1 = json.loads((directory / "PHYSICAL_METADATA_LIMIT_V1.json").read_bytes())
    if set(policy["source_lf_sha256"]) != set(SOURCES):
        raise ValueError("physical V2 source inventory")
    for path in SOURCES:
        old_raw = subprocess.check_output(["git", "show", SOURCE35 + ":" + path], cwd=ROOT)
        if sha(old_raw.replace(b"\r\n", b"\n")) != v1["source_lf_sha256"][path]:
            raise ValueError("physical source35 content not retained")
        current = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        if sha(current) != policy["source_lf_sha256"][path]:
            raise ValueError("physical V2 fixed source changed")
    if policy["source_lf_sha256"][SOURCES[0]] != v1["source_lf_sha256"][SOURCES[0]]:
        raise ValueError("physical remote collector change not authorized")
    remote_history = git(
        "log", "--full-history", "--format=%H", BASELINE + "..HEAD", "--", SOURCES[0]
    )
    if remote_history or git("status", "--porcelain", "--", SOURCES[0]):
        raise ValueError("physical remote collector source version not authorized")
    history = git(
        "log", "--full-history", "--no-merges", "--format=%H", BASELINE + "..HEAD", "--", SOURCES[1]
    ).splitlines()
    pending = bool(git("status", "--porcelain", "--", SOURCES[1]))
    if len(set(history)) + int(pending) != 1:
        raise ValueError("physical host correction exhausted or missing; no refund")
    if history and git("ls-tree", history[0], "--", SOURCES[1]) != git(
        "ls-tree", "HEAD", "--", SOURCES[1]
    ):
        raise ValueError("physical uncounted merge source change")
    return {
        "status": "PHYSICAL_METADATA_SOURCE_BOUNDARY_V2_PASS",
        "retained_consumed": 35,
        "host_correction_versions": 1,
        "conservative_consumed": 36,
        "ceiling": 36,
        "remaining": 0,
        "remote_collector_unchanged": True,
        "ledger_modified": False,
        "remote_contact": False,
        "authority": "DIRECT_HUMAN_APPROVAL_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.reconciliation), sort_keys=True))
