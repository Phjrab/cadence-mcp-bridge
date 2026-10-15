"""Disposable Git histories cannot refund already recorded source corrections."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def command(repository: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", *arguments],
        cwd=repository,
        text=True,
        encoding="utf-8",
        stderr=subprocess.PIPE,
        timeout=15,
    ).strip()


def commit(repository: Path, message: str) -> str:
    command(repository, "add", "--all")
    command(repository, "commit", "-m", message)
    return command(repository, "rev-parse", "HEAD")


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path, Path]:
    spec = importlib.util.spec_from_file_location(
        "post_correction_guard", ROOT / "scripts/verify-post-native-corrections.py"
    )
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    repository = tmp_path / "repository"
    repository.mkdir()
    command(repository, "init", "-b", "source")
    command(repository, "config", "user.name", "Synthetic Correction Fixture")
    command(repository, "config", "user.email", "fixture@example.invalid")
    source = repository / guard.NATIVE_PATHS[0]
    source.parent.mkdir(parents=True)
    source.write_text("baseline = 0\n", encoding="utf-8")
    baseline = commit(repository, "synthetic retained baseline")
    known = []
    for number in range(1, 5):
        source.write_text(f"correction = {number}\n", encoding="utf-8")
        known.append(commit(repository, f"synthetic correction {number}"))
    policy_dir = repository / "docs/policy"
    policy_dir.mkdir(parents=True)
    for name in (
        "POST_NATIVE_CORRECTION_LIMIT_V7.json",
        "PHASE_CORRECTION_LIMIT_V5.json",
        "PHASE_RESULT_LIMIT_V6.json",
    ):
        (policy_dir / name).write_bytes((ROOT / "docs/policy" / name).read_bytes())
    reconciliation = tmp_path / "synthetic-reconciliation.json"
    reconciliation.write_text(
        json.dumps(
            {
                "conservative_recorded_source_changes": 20,
                "source_commits": [baseline + " synthetic baseline"]
                + [f"{number:040x} synthetic historical identity" for number in range(1, 20)],
            }
        ),
        encoding="utf-8",
    )
    checkpoint = json.loads(
        (ROOT / "docs/policy/POST_NATIVE_CORRECTION_CONSUMED_V1.json").read_bytes()
    )
    checkpoint.update(
        baseline_commit=baseline,
        retained_reconciliation_sha256=hashlib.sha256(reconciliation.read_bytes()).hexdigest(),
        retained_post_source_commits=known,
        source_tree_sha256=hashlib.sha256(
            command(repository, "ls-tree", "HEAD", "--", *guard.NATIVE_PATHS).encode("utf-8")
        ).hexdigest(),
    )
    checkpoint_path = policy_dir / "POST_NATIVE_CORRECTION_CONSUMED_V1.json"
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    # The guard's own inputs are versioned documents, not pending native source.
    commit(repository, "synthetic checkpoint documents")
    monkeypatch.setattr(guard, "ROOT", repository)
    monkeypatch.setattr(guard, "BASELINE", baseline)
    monkeypatch.setattr(guard, "POLICY", policy_dir / "POST_NATIVE_CORRECTION_LIMIT_V7.json")
    monkeypatch.setattr(guard, "CHECKPOINT", checkpoint_path)
    return guard, repository, reconciliation


def test_retained_checkpoint_repeats_without_writes_or_new_authority(
    scenario: tuple[ModuleType, Path, Path],
) -> None:
    guard, repository, reconciliation = scenario
    before = {path: path.read_bytes() for path in (reconciliation, guard.POLICY, guard.CHECKPOINT)}
    first = guard.inspect(reconciliation)
    assert first == guard.inspect(reconciliation)
    assert first["conservative_consumed"] == first["retained_consumed"] == 24
    assert first["remaining"] == 0
    assert first["ledger_modified"] is False and first["remote_contact"] is False
    assert first["authority"] == "DIRECT_USER_CONFIRMATION_NOT_THIS_GUARD"
    assert all(path.read_bytes() == value for path, value in before.items())
    assert command(repository, "status", "--porcelain") == ""


def test_squash_cannot_turn_four_consumed_changes_into_one(
    scenario: tuple[ModuleType, Path, Path],
) -> None:
    guard, repository, reconciliation = scenario
    checkpoint = guard.CHECKPOINT.read_bytes()
    assert guard.inspect(reconciliation)["conservative_consumed"] == 24
    command(repository, "checkout", "-b", "squashed", guard.BASELINE)
    command(repository, "merge", "--squash", "source")
    commit(repository, "one squashed commit preserves source but not accounting history")
    legacy = command(
        repository,
        "log",
        "--no-merges",
        "--format=%H",
        guard.BASELINE + "..HEAD",
        "--",
        *guard.NATIVE_PATHS,
    )
    assert 20 + len(legacy.splitlines()) == 21  # Reproduces the old refund bug.
    with pytest.raises(ValueError, match="history missing.*without refund"):
        guard.inspect(reconciliation)
    assert guard.CHECKPOINT.read_bytes() == checkpoint


def test_normal_merge_preserves_all_consumed_identities(
    scenario: tuple[ModuleType, Path, Path],
) -> None:
    guard, repository, reconciliation = scenario
    command(repository, "checkout", "-b", "main", guard.BASELINE)
    (repository / "unrelated.md").write_text("synthetic unrelated host docs\n", encoding="utf-8")
    commit(repository, "unrelated documentation")
    command(repository, "merge", "--no-ff", "source", "-m", "normal feature merge")
    assert guard.inspect(reconciliation)["conservative_consumed"] == 24


@pytest.mark.parametrize("committed", [False, True])
def test_further_selected_source_change_exceeds_exhausted_allowance(
    scenario: tuple[ModuleType, Path, Path],
    committed: bool,
) -> None:
    guard, repository, reconciliation = scenario
    (repository / guard.NATIVE_PATHS[0]).write_text("extra = 5\n", encoding="utf-8")
    if committed:
        commit(repository, "another source correction")
    with pytest.raises(ValueError, match="ceiling exceeded"):
        guard.inspect(reconciliation)


def test_merge_only_source_edit_is_not_hidden_by_no_merges_log(
    scenario: tuple[ModuleType, Path, Path],
) -> None:
    guard, repository, reconciliation = scenario
    command(repository, "checkout", "-b", "main", guard.BASELINE)
    (repository / "unrelated.md").write_text("unrelated\n", encoding="utf-8")
    commit(repository, "unrelated docs")
    command(repository, "merge", "--no-ff", "--no-commit", "source")
    (repository / guard.NATIVE_PATHS[0]).write_text(
        "unrecorded_merge_change = 5\n", encoding="utf-8"
    )
    commit(repository, "merge introduces unrecorded source edit")
    with pytest.raises(ValueError, match="source tree differs.*without refund"):
        guard.inspect(reconciliation)


@pytest.mark.parametrize(
    "tamper", ["retained-count", "missing-identity", "policy", "reconciliation"]
)
def test_stale_or_modified_consumption_inputs_are_rejected(
    scenario: tuple[ModuleType, Path, Path],
    tamper: str,
) -> None:
    guard, _, reconciliation = scenario
    checkpoint = json.loads(guard.CHECKPOINT.read_bytes())
    if tamper == "retained-count":
        checkpoint["retained_consumed_source_changes"] = 23
    elif tamper == "missing-identity":
        checkpoint["retained_post_source_commits"].pop()
    elif tamper == "policy":
        policy = json.loads(guard.POLICY.read_bytes())
        policy["scope"] = "not_the_reviewed_scope"
        guard.POLICY.write_text(json.dumps(policy), encoding="utf-8")
    else:
        reconciliation.write_bytes(reconciliation.read_bytes() + b"\n")
    guard.CHECKPOINT.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(ValueError, match="checkpoint conflict"):
        guard.inspect(reconciliation)
