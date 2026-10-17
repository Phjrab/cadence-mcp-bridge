"""New source checkpoints preserve the original40/+10 limit and source37 pins."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from test_physical_metadata_boundary import command, commit
from test_physical_metadata_boundary_v3 import scenario

__all__ = ["scenario"]
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def current(scenario: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    old, repository = scenario
    guard_path = repository / "scripts/verify-physical-metadata-boundary-v3.py"
    guard_path.parent.mkdir()
    guard_path.write_bytes((ROOT / "scripts/verify-physical-metadata-boundary-v3.py").read_bytes())
    commit(repository)
    source37 = command(repository, "rev-parse", "HEAD")
    spec = importlib.util.spec_from_file_location(
        "physical_v4_guard", ROOT / "scripts/verify-physical-metadata-boundary-v4.py"
    )
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    monkeypatch.setattr(guard, "ROOT", repository)
    monkeypatch.setattr(guard, "BASELINE", old.BASELINE)
    monkeypatch.setattr(guard, "SOURCE36", old.SOURCE36)
    monkeypatch.setattr(guard, "SOURCE37", source37)
    path = repository / "src/cadence_mcp_bridge/physical_metadata.py"
    path.write_bytes(b"# synthetic source38\n")
    policy = json.loads((repository / "docs/policy/PHYSICAL_METADATA_LIMIT_V3.json").read_bytes())
    checkpoint = {
        "schema_version": 4,
        "source_version": 38,
        "limit_policy": "docs/policy/PHYSICAL_METADATA_LIMIT_V3.json",
        "limit_policy_canonical_sha256": guard.sha(guard.canonical(policy)),
        "source_lf_sha256": {
            name: guard.sha((repository / name).read_bytes()) for name in policy["source_lf_sha256"]
        },
    }
    (repository / "docs/policy/PHYSICAL_METADATA_SOURCE_V4.json").write_bytes(
        guard.canonical(checkpoint)
    )
    return guard, repository


def test38_pending_committed_and_restarted(current: Any) -> None:
    guard, repository = current
    before = guard.inspect()
    assert before["conservative_consumed"] == 38 and before["remaining"] == 2
    assert before["cumulative_collection_ceiling"] == 11
    assert before["prior_limit_and_guards_preserved"]
    commit(repository)
    assert guard.inspect() == before


@pytest.mark.parametrize(
    "path",
    [
        "docs/policy/PHYSICAL_METADATA_LIMIT_V3.json",
        "scripts/verify-physical-metadata-boundary-v3.py",
    ],
)
def test_old_v3_limit_and_guard_are_immutable(current: Any, path: str) -> None:
    guard, repository = current
    (repository / path).write_bytes(b"{}")
    with pytest.raises(ValueError, match="immutable V3"):
        guard.inspect()


def test_updated_hashes_cannot_hide_refunded_source_counter(current: Any) -> None:
    guard, repository = current
    path = repository / "docs/policy/PHYSICAL_METADATA_SOURCE_V4.json"
    checkpoint = json.loads(path.read_bytes())
    checkpoint["source_version"] = 37
    path.write_bytes(guard.canonical(checkpoint))
    with pytest.raises(ValueError, match="checkpoint binding"):
        guard.inspect()


def test_fourth_version_allowed_but_fifth_never_refunded(current: Any) -> None:
    guard, repository = current
    path = repository / "docs/policy/PHYSICAL_METADATA_SOURCE_V4.json"
    checkpoint = json.loads(path.read_bytes())
    commit(repository)  # source38
    source = repository / "src/cadence_mcp_bridge/physical_metadata.py"
    for number in (39, 40, 41):
        source.write_bytes(f"# synthetic source{number}\n".encode("ascii"))
        checkpoint["source_version"] = number
        checkpoint["source_lf_sha256"][source.relative_to(repository).as_posix()] = guard.sha(
            source.read_bytes()
        )
        path.write_bytes(guard.canonical(checkpoint))
        if number <= 40:
            assert guard.inspect()["conservative_consumed"] == number
        else:
            with pytest.raises(ValueError, match="exhausted"):
                guard.inspect()
        commit(repository)


def test_new_hidden_helper_cannot_escape_complete_inventory(current: Any) -> None:
    guard, repository = current
    (repository / "src/extra_remote_variant.py").write_bytes(b"# uncounted variant\n")
    with pytest.raises(ValueError, match="complete product source inventory"):
        guard.inspect()
