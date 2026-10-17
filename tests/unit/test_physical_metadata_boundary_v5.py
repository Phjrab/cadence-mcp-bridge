"""Actual disposable Git histories distinguish retained objects from ancestors."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from test_physical_metadata_boundary import command, commit
from test_physical_metadata_boundary_v3 import scenario
from test_physical_metadata_boundary_v4 import current

__all__ = ["current", "scenario"]
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def retained(current: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    old, repository = current
    raw = (ROOT / "scripts/verify-physical-metadata-boundary-v4.py").read_text(encoding="utf-8")
    pins = {
        "BASELINE": "a215500e9f7b2c5e20fad26b4bde9b40059e3be0",
        "SOURCE36": "759d84ec435d7ef3636024f78608b34aee13000b",
        "SOURCE37": "d456bf8228647a1171c028e3bea9d92b9377e9c0",
    }
    for name, pin in pins.items():
        raw = raw.replace(pin, getattr(old, name))
    (repository / "scripts/verify-physical-metadata-boundary-v4.py").write_text(
        raw, encoding="utf-8"
    )
    commit(repository)
    source38 = command(repository, "rev-parse", "HEAD")
    spec = importlib.util.spec_from_file_location(
        "physical_v5_guard", ROOT / "scripts/verify-physical-metadata-boundary-v5.py"
    )
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    monkeypatch.setattr(guard, "ROOT", repository)
    monkeypatch.setattr(guard, "SOURCE37", old.SOURCE37)
    monkeypatch.setattr(guard, "SOURCE38", source38)
    return guard, old, repository


def test_retained_sources_pass_without_extra_source_consumption(retained: Any) -> None:
    guard, old, _ = retained
    assert guard.inspect() == {
        **old.inspect(),
        "status": "PHYSICAL_METADATA_SOURCE_BOUNDARY_V5_PASS",
        "retained_source37_source38_ancestry": True,
    }


@pytest.mark.parametrize("retain_source37", [False, True])
def test_available_source_objects_cannot_replace_retained_ancestry(
    retained: Any, retain_source37: bool
) -> None:
    guard, old, repository = retained
    alternate37 = (
        old.SOURCE37
        if retain_source37
        else command(
            repository,
            "commit-tree",
            old.SOURCE37 + "^{tree}",
            "-p",
            old.BASELINE,
            "-m",
            "alternate source37 lineage",
        )
    )
    alternate38 = command(
        repository,
        "commit-tree",
        guard.SOURCE38 + "^{tree}",
        "-p",
        alternate37,
        "-m",
        "alternate source38 lineage",
    )
    command(repository, "checkout", "--detach", alternate38)
    assert command(repository, "cat-file", "-t", old.SOURCE37) == "commit"
    assert old.inspect()["conservative_consumed"] == 38  # historical V4 defect
    with pytest.raises(ValueError, match="ancestry missing"):
        guard.inspect()


@pytest.mark.parametrize(
    "path",
    [
        "scripts/verify-physical-metadata-boundary-v4.py",
        "docs/policy/PHYSICAL_METADATA_SOURCE_V4.json",
    ],
)
def test_v4_snapshot_stays_immutable(retained: Any, path: str) -> None:
    guard, _, repository = retained
    (repository / path).write_bytes(b"{}")
    with pytest.raises(ValueError, match="immutable V4"):
        guard.inspect()
