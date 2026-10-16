"""Source40 and ten additional collections cannot refund retained consumption."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from test_physical_metadata_boundary import command, commit

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    spec = importlib.util.spec_from_file_location(
        "physical_v3_guard", ROOT / "scripts/verify-physical-metadata-boundary-v3.py"
    )
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    repository = tmp_path / "r"
    directory = repository / "docs/policy"
    directory.mkdir(parents=True)
    command(repository, "init", "-q")
    command(repository, "config", "user.name", "Synthetic Test")
    command(repository, "config", "user.email", "synthetic@example.invalid")
    source36 = {}
    for name in ("_physical_metadata.py", "physical_metadata.py"):
        path = "src/cadence_mcp_bridge/" + name
        file = repository / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"# synthetic source36\n")
        source36[path] = guard.sha(file.read_bytes())
    for name in guard.HISTORY:
        value = json.loads((ROOT / "docs/policy" / name).read_bytes())
        if name == "PHYSICAL_METADATA_CONSUMED_V3.json":
            value["source_lf_sha256"] = source36
        (directory / name).write_bytes(guard.canonical(value))
    commit(repository)
    baseline = command(repository, "rev-parse", "HEAD")
    policy = json.loads((ROOT / "docs/policy/PHYSICAL_METADATA_LIMIT_V3.json").read_bytes())
    policy.update(base_commit=baseline, retained_source_commit=baseline)
    for path in policy["source_lf_sha256"]:
        file = repository / path
        file.write_bytes(b"# synthetic source37\n")
        policy["source_lf_sha256"][path] = guard.sha(file.read_bytes())
    (directory / "PHYSICAL_METADATA_LIMIT_V3.json").write_bytes(guard.canonical(policy))
    monkeypatch.setattr(guard, "ROOT", repository)
    monkeypatch.setattr(guard, "BASELINE", baseline)
    monkeypatch.setattr(guard, "SOURCE36", baseline)
    return guard, repository


def repin(guard: ModuleType, repository: Path) -> None:
    path = repository / "docs/policy/PHYSICAL_METADATA_LIMIT_V3.json"
    policy = json.loads(path.read_bytes())
    for source in policy["source_lf_sha256"]:
        policy["source_lf_sha256"][source] = guard.sha((repository / source).read_bytes())
    path.write_bytes(guard.canonical(policy))


def test_pending_commit_and_restart_retain37(scenario: Any) -> None:
    guard, repository = scenario
    result = guard.inspect()
    assert result["conservative_consumed"] == 37 and result["remaining"] == 3
    assert result["cumulative_collection_ceiling"] == 11
    commit(repository)
    assert guard.inspect() == result


def test_fifth_source_version_cannot_hide_behind_new_pins_or_revert(scenario: Any) -> None:
    guard, repository = scenario
    source = repository / "src/cadence_mcp_bridge/physical_metadata.py"
    for number in range(1, 6):
        source.write_bytes(f"# source version {number}\n".encode("ascii"))
        repin(guard, repository)
        if number <= 4:
            assert guard.inspect()["conservative_consumed"] == 36 + number
        else:
            with pytest.raises(ValueError, match="exhausted"):
                guard.inspect()
        commit(repository)
    source.write_bytes(b"# synthetic source36\n")
    repin(guard, repository)
    with pytest.raises(ValueError, match="exhausted"):
        guard.inspect()


@pytest.mark.parametrize(
    "key,value",
    [
        ("retained_consumed_source_changes", 0),
        ("retained_collection_attempts", 0),
        ("maximum_corrections_same_change", 41),
        ("maximum_additional_collection_attempts", 11),
        ("maximum_stage_and_query_attempts", 12),
        ("max_new_simulations", 1),
        ("merge_authorized", True),
        ("publication_authorized", True),
    ],
)
def test_v3_bounds_cannot_expand(scenario: Any, key: str, value: object) -> None:
    guard, repository = scenario
    path = repository / "docs/policy/PHYSICAL_METADATA_LIMIT_V3.json"
    policy = json.loads(path.read_bytes())
    policy[key] = value
    path.write_bytes(guard.canonical(policy))
    with pytest.raises(ValueError, match="finite policy conflict"):
        guard.inspect()


def test_old_failure_history_is_immutable(scenario: Any) -> None:
    guard, repository = scenario
    (repository / "docs/policy/PHYSICAL_METADATA_CONSUMED_V3.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="immutable"):
        guard.inspect()


def test_uncounted_new_runtime_helper_is_rejected(scenario: Any) -> None:
    guard, repository = scenario
    (repository / "src/hidden_collector.py").write_bytes(b"# not in fixed inventory\n")
    with pytest.raises(ValueError, match="complete product source inventory"):
        guard.inspect()
