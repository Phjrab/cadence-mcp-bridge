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


@pytest.fixture
def v9_scenario(m2_scenario: tuple[ModuleType, Path, Path]) -> tuple[ModuleType, Path, Path]:
    guard, repository, reconciliation = m2_scenario
    directory = repository / "docs/policy"
    old = json.loads((directory / "M2_NATIVE_CORRECTION_LIMIT_V8.json").read_bytes())
    checkpoint = json.loads((directory / "M2_NATIVE_CORRECTION_CONSUMED_V1.json").read_bytes())
    policy = json.loads((ROOT / "docs/policy/M2_NATIVE_CORRECTION_LIMIT_V9.json").read_bytes())
    canonical = guard.load_post().canonical_sha256
    policy.update(
        base_commit=command(repository, "rev-parse", "HEAD"),
        prior_policy_sha256=canonical(old),
        prior_consumed_checkpoint_sha256=canonical(checkpoint),
    )
    (directory / "M2_NATIVE_CORRECTION_LIMIT_V9.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    commit(repository, "synthetic explicit V9 extension retaining25")
    return guard, repository, reconciliation


def test_v9_preserves25_and_counts_one_corrected_collector(
    v9_scenario: tuple[ModuleType, Path, Path],
) -> None:
    guard, repository, reconciliation = v9_scenario
    assert guard.inspect(reconciliation)["conservative_consumed"] == 25
    (repository / guard.SOURCES[0]).write_text("corrected_collector = 2\n", encoding="utf-8")
    assert guard.inspect(reconciliation)["conservative_consumed"] == 26
    commit(repository, "synthetic corrected collector")
    assert guard.inspect(reconciliation)["conservative_consumed"] == 26
    (repository / guard.SOURCES[1]).write_text("generator = 1\n", encoding="utf-8")
    assert guard.inspect(reconciliation)["conservative_consumed"] == 27


def test_v9_does_not_allow_second_correction(
    v9_scenario: tuple[ModuleType, Path, Path],
) -> None:
    guard, repository, reconciliation = v9_scenario
    source = repository / guard.SOURCES[0]
    source.write_text("corrected_collector = 2\n", encoding="utf-8")
    commit(repository, "synthetic one approved correction")
    source.write_text("extra_collector = 3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="version exhausted"):
        guard.inspect(reconciliation)


def test_v9_cannot_rewrite_failed_consumption(v9_scenario: tuple[ModuleType, Path, Path]) -> None:
    guard, repository, reconciliation = v9_scenario
    path = repository / "docs/policy/M2_NATIVE_CORRECTION_CONSUMED_V1.json"
    checkpoint = json.loads(path.read_bytes())
    checkpoint["retained_consumed_source_changes"] = 24
    path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(ValueError, match="retained consumption conflict"):
        guard.inspect(reconciliation)


@pytest.mark.parametrize("port_correction", [0, 11, 12])
def test_current_additional_approval_preserves_both_failed_versions(
    v9_scenario: tuple[ModuleType, Path, Path],
    port_correction: int,
) -> None:
    guard, repository, reconciliation = v9_scenario
    directory = repository / "docs/policy"
    collector = repository / guard.SOURCES[0]
    collector.write_text("failed_corrected_collector = 2\n", encoding="utf-8")
    failed = commit(repository, "synthetic failed corrected collector")
    canonical = guard.load_post().canonical_sha256
    old_checkpoint = json.loads((directory / "M2_NATIVE_CORRECTION_CONSUMED_V1.json").read_bytes())
    checkpoint = json.loads(
        (ROOT / "docs/policy/M2_NATIVE_CORRECTION_CONSUMED_V2.json").read_bytes()
    )
    checkpoint.update(
        corrected_collector_commit=failed,
        collector_module_lf_sha256=hashlib.sha256(
            collector.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        prior_consumed_checkpoint_sha256=canonical(old_checkpoint),
    )
    old_policy = json.loads((directory / "M2_NATIVE_CORRECTION_LIMIT_V9.json").read_bytes())
    policy = json.loads((ROOT / "docs/policy/M2_NATIVE_CORRECTION_LIMIT_V10.json").read_bytes())
    policy.update(
        base_commit=failed,
        prior_policy_sha256=canonical(old_policy),
        prior_consumed_checkpoint_sha256=canonical(checkpoint),
    )
    for name, value in (
        ("M2_NATIVE_CORRECTION_CONSUMED_V2.json", checkpoint),
        ("M2_NATIVE_CORRECTION_LIMIT_V10.json", policy),
    ):
        (directory / name).write_text(json.dumps(value), encoding="utf-8")
    commit(repository, "synthetic bounded additional approval preserving26")
    assert guard.inspect(reconciliation)["conservative_consumed"] == 26
    collector.write_text("minimum_legacy_api_correction = 3\n", encoding="utf-8")
    assert guard.inspect(reconciliation)["conservative_consumed"] == 27
    third = commit(repository, "synthetic one additional bounded correction")
    if port_correction:
        next_checkpoint = json.loads(
            (ROOT / "docs/policy/M2_NATIVE_CORRECTION_CONSUMED_V3.json").read_bytes()
        )
        next_checkpoint.update(
            corrected_collector_commit=third,
            collector_module_lf_sha256=hashlib.sha256(
                collector.read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest(),
            prior_consumed_checkpoint_sha256=canonical(checkpoint),
        )
        next_policy = json.loads(
            (ROOT / "docs/policy/M2_NATIVE_CORRECTION_LIMIT_V11.json").read_bytes()
        )
        next_policy.update(
            base_commit=third,
            prior_policy_sha256=canonical(policy),
            prior_consumed_checkpoint_sha256=canonical(next_checkpoint),
        )
        for name, value in (
            ("M2_NATIVE_CORRECTION_CONSUMED_V3.json", next_checkpoint),
            ("M2_NATIVE_CORRECTION_LIMIT_V11.json", next_policy),
        ):
            (directory / name).write_text(json.dumps(value), encoding="utf-8")
        commit(repository, "synthetic finite port correction scope retaining27")
        assert guard.inspect(reconciliation)["conservative_consumed"] == 27
        collector.write_text("exact_basic_port_exclusion = 4\n", encoding="utf-8")
        assert guard.inspect(reconciliation)["conservative_consumed"] == 28
        fourth = commit(repository, "synthetic corrected port collection")
        if port_correction == 12:
            latest_checkpoint = json.loads(
                (ROOT / "docs/policy/M2_NATIVE_CORRECTION_CONSUMED_V4.json").read_bytes()
            )
            latest_checkpoint.update(
                corrected_collector_commit=fourth,
                collector_module_lf_sha256=hashlib.sha256(
                    collector.read_bytes().replace(b"\r\n", b"\n")
                ).hexdigest(),
                prior_consumed_checkpoint_sha256=canonical(next_checkpoint),
            )
            latest_policy = json.loads(
                (ROOT / "docs/policy/M2_NATIVE_CORRECTION_LIMIT_V12.json").read_bytes()
            )
            latest_policy.update(
                base_commit=fourth,
                prior_policy_sha256=canonical(next_policy),
                prior_consumed_checkpoint_sha256=canonical(latest_checkpoint),
            )
            for name, value in (
                ("M2_NATIVE_CORRECTION_CONSUMED_V4.json", latest_checkpoint),
                ("M2_NATIVE_CORRECTION_LIMIT_V12.json", latest_policy),
            ):
                (directory / name).write_text(json.dumps(value), encoding="utf-8")
            commit(repository, "synthetic finite host parse scope retaining28")
            collector.write_text("host_data_parser = 5\n", encoding="utf-8")
            assert guard.inspect(reconciliation)["conservative_consumed"] == 29
            commit(repository, "synthetic local parser correction")
    (repository / guard.SOURCES[1]).write_text("generator = 1\n", encoding="utf-8")
    assert guard.inspect(reconciliation)["conservative_consumed"] == (
        30 if port_correction == 12 else 29 if port_correction else 28
    )
    collector.write_text("unrecorded_extra = 4\n", encoding="utf-8")
    with pytest.raises(ValueError, match="version exhausted"):
        guard.inspect(reconciliation)
