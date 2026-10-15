"""A failed deployed collector remains spent across retries and Git histories."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from test_post_native_corrections import command, commit
from test_post_native_corrections import scenario as scenario

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def m2_scenario(
    scenario: tuple[ModuleType, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> tuple[ModuleType, Path, Path]:
    post, repository, reconciliation = scenario
    spec = importlib.util.spec_from_file_location(
        "m2_corrections", ROOT / "scripts/verify-m2-native-corrections.py"
    )
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    monkeypatch.setattr(guard, "ROOT", repository)
    monkeypatch.setattr(guard, "load_post", lambda: post)
    base = command(repository, "rev-parse", "HEAD")
    collector = repository / guard.SOURCES[0]
    collector.write_text("fixed_collector = 1\n", encoding="utf-8")
    deployed = commit(repository, "synthetic failed fixed collector")
    policy = json.loads((ROOT / "docs/policy/M2_NATIVE_CORRECTION_LIMIT_V8.json").read_bytes())
    policy["base_commit"] = base
    checkpoint = json.loads(
        (ROOT / "docs/policy/M2_NATIVE_CORRECTION_CONSUMED_V1.json").read_bytes()
    )
    checkpoint.update(
        base_commit=base,
        collector_commit=deployed,
        collector_module_lf_sha256=hashlib.sha256(
            collector.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
    )
    for name, value in (
        ("M2_NATIVE_CORRECTION_LIMIT_V8.json", policy),
        ("M2_NATIVE_CORRECTION_CONSUMED_V1.json", checkpoint),
    ):
        (repository / "docs/policy" / name).write_text(json.dumps(value), encoding="utf-8")
    commit(repository, "synthetic M2 accounting checkpoint")
    return guard, repository, reconciliation


def test_failed_collector_repeat_preserves25(m2_scenario: tuple[ModuleType, Path, Path]) -> None:
    guard, repository, reconciliation = m2_scenario
    before = command(repository, "status", "--porcelain")
    value = guard.inspect(reconciliation)
    assert value == guard.inspect(reconciliation)
    assert value["conservative_consumed"] == 25
    assert value["generator_versions"] == 0
    assert value["remaining"] == 1
    assert value["ledger_modified"] is False
    assert command(repository, "status", "--porcelain") == before


def test_collector_correction_rejects_even_with_one_remaining(
    m2_scenario: tuple[ModuleType, Path, Path],
) -> None:
    guard, repository, reconciliation = m2_scenario
    (repository / guard.SOURCES[0]).write_text("corrected = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="deployed collector differs"):
        guard.inspect(reconciliation)


@pytest.mark.parametrize("committed", [False, True])
def test_only_one_generator_version(
    m2_scenario: tuple[ModuleType, Path, Path], committed: bool
) -> None:
    guard, repository, reconciliation = m2_scenario
    generator = repository / guard.SOURCES[1]
    generator.write_text("fixed_generator = 1\n", encoding="utf-8")
    assert guard.inspect(reconciliation)["conservative_consumed"] == 26
    commit(repository, "synthetic generator")
    assert guard.inspect(reconciliation)["conservative_consumed"] == 26
    generator.write_text("corrected_generator = 2\n", encoding="utf-8")
    if committed:
        commit(repository, "synthetic extra correction")
    with pytest.raises(ValueError, match="version exhausted"):
        guard.inspect(reconciliation)


def test_squash_does_not_refund_failed_collector(
    m2_scenario: tuple[ModuleType, Path, Path],
) -> None:
    guard, repository, reconciliation = m2_scenario
    policy = json.loads(
        (repository / "docs/policy/M2_NATIVE_CORRECTION_LIMIT_V8.json").read_bytes()
    )
    command(repository, "checkout", "-b", "squashed", policy["base_commit"])
    command(repository, "merge", "--squash", "source")
    commit(repository, "synthetic squash")
    with pytest.raises(ValueError, match="history missing.*without refund"):
        guard.inspect(reconciliation)
