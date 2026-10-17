"""Additive source35 guard; never changes the frozen POST/M2 guards or journals."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "fa8d01b418ddf71b14e677f2e010b8dd80cd0696"
SOURCES = (
    "src/cadence_mcp_bridge/_physical_metadata.py",
    "src/cadence_mcp_bridge/physical_metadata.py",
)
PRIOR = {
    "M2_NATIVE_CORRECTION_LIMIT_V16.json": (
        "e3b3838407beef92e6debaf0af73346972baca5ff321857f91e7a07cf0a2d3a2"
    ),
    "M2_NATIVE_CORRECTION_CONSUMED_V9.json": (
        "3440b60fac71c75a7dd318138fe6bf70e46d5201e353a4766e38e2f318d8cd5c"
    ),
}


def load_retained() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "retained_m2_guard", ROOT / "scripts/verify-m2-native-corrections.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()


def inspect(reconciliation: Path) -> dict[str, object]:
    directory = ROOT / "docs/policy"
    for name, expected in PRIOR.items():
        if canonical_sha(json.loads((directory / name).read_bytes())) != expected:
            raise ValueError("physical retained policy changed; no reset")
    retained = load_retained().inspect(reconciliation)
    if retained["conservative_consumed"] != 34 or retained["remaining"] != 0:
        raise ValueError("physical retained source consumption conflict")
    policy = json.loads((directory / "PHYSICAL_METADATA_LIMIT_V1.json").read_bytes())
    for key, expected in {
        "schema_version": 1,
        "base_commit": BASELINE,
        "scope": "CURRENT_MANAGED_STANDARD_VM_PHYSICAL_METADATA_01",
        "retained_consumed_source_changes": 34,
        "maximum_corrections_same_change": 35,
        "maximum_new_source_versions": 1,
        "maximum_stage_and_query_attempts": 1,
        "max_entries": 128,
        "timeout_seconds": 60,
        "max_bytes_per_output_stream": 1048576,
        "max_new_simulations": 0,
        "max_new_extractions": 0,
        "max_new_reserved_bytes": 0,
        "max_cumulative_attempts": 500,
        "max_cumulative_result_bytes": 17179869184,
        "automatic_corrective_redeployment": False,
        "merge_authorized": False,
        "publication_authorized": False,
        "prior_canonical_sha256": PRIOR,
    }.items():
        if canonical_sha(policy.get(key)) != canonical_sha(expected):
            raise ValueError("physical finite policy conflict: " + key)
    base = policy["base_commit"]
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=ROOT, check=False
    ).returncode:
        raise ValueError("physical source history missing; no refund")
    if set(policy["source_lf_sha256"]) != set(SOURCES):
        raise ValueError("physical fixed source inventory")
    commits: set[str] = set()
    pending = False
    for path in SOURCES:
        raw = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(raw).hexdigest() != policy["source_lf_sha256"][path]:
            raise ValueError("physical fixed source changed; no corrective version")
        history = git(
            "log", "--full-history", "--no-merges", "--format=%H", base + "..HEAD", "--", path
        ).splitlines()
        commits.update(history)
        pending = pending or bool(git("status", "--porcelain", "--", path))
        if history and git("ls-tree", history[0], "--", path) != git("ls-tree", "HEAD", "--", path):
            raise ValueError("physical uncounted merge source change")
        if not history and git("ls-tree", "HEAD", "--", path):
            raise ValueError("physical source without counted history")
    versions = len(commits) + int(pending)
    if versions != 1:
        raise ValueError("physical one fixed version exhausted or missing; no refund")
    return {
        "status": "PHYSICAL_METADATA_SOURCE_BOUNDARY_PASS",
        "retained_consumed": 34,
        "collector_versions": versions,
        "conservative_consumed": 34 + versions,
        "ceiling": 35,
        "remaining": 0,
        "ledger_modified": False,
        "remote_contact": False,
        "authority": "DIRECT_HUMAN_APPROVAL_NOT_THIS_GUARD",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reconciliation", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.reconciliation), sort_keys=True))
