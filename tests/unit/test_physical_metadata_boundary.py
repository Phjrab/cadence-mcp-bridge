"""Single collector source version retains all34 earlier consumed versions."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def command(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()


def commit(root: Path) -> None:
    command(root, "add", ".")
    command(root, "commit", "-qm", "synthetic version")


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path]:
    spec = importlib.util.spec_from_file_location(
        "physical_guard", ROOT / "scripts/verify-physical-metadata-boundary.py"
    )
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    repository = tmp_path / "repository"
    directory = repository / "docs/policy"
    directory.mkdir(parents=True)
    command(repository, "init", "-q")
    command(repository, "config", "user.name", "Synthetic Test")
    command(repository, "config", "user.email", "synthetic@example.invalid")
    for name in guard.PRIOR:
        (directory / name).write_bytes((ROOT / "docs/policy" / name).read_bytes())
    commit(repository)
    policy = json.loads((ROOT / "docs/policy/PHYSICAL_METADATA_LIMIT_V1.json").read_bytes())
    policy["base_commit"] = command(repository, "rev-parse", "HEAD")
    monkeypatch.setattr(guard, "BASELINE", policy["base_commit"])
    for path in guard.SOURCES:
        source = repository / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"# synthetic fixed source\n")
        policy["source_lf_sha256"][path] = hashlib.sha256(source.read_bytes()).hexdigest()
    (directory / "PHYSICAL_METADATA_LIMIT_V1.json").write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(guard, "ROOT", repository)
    monkeypatch.setattr(
        guard,
        "load_retained",
        lambda: SimpleNamespace(inspect=lambda _: {"conservative_consumed": 34, "remaining": 0}),
    )
    return guard, repository


def test_pending_and_committed_version_keep35(scenario: tuple[ModuleType, Path]) -> None:
    guard, repository = scenario
    result = guard.inspect(Path("unused"))
    assert result["conservative_consumed"] == 35 and result["remaining"] == 0
    assert result["ledger_modified"] is False
    commit(repository)
    assert guard.inspect(Path("unused")) == result


def test_second_commit_cannot_be_hidden_by_updating_pin(scenario: tuple[ModuleType, Path]) -> None:
    guard, repository = scenario
    commit(repository)
    source = repository / guard.SOURCES[0]
    source.write_bytes(b"# corrective version\n")
    path = repository / "docs/policy/PHYSICAL_METADATA_LIMIT_V1.json"
    policy = json.loads(path.read_bytes())
    policy["source_lf_sha256"][guard.SOURCES[0]] = hashlib.sha256(source.read_bytes()).hexdigest()
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="fixed version exhausted"):
        guard.inspect(Path("unused"))
    commit(repository)
    with pytest.raises(ValueError, match="fixed version exhausted"):
        guard.inspect(Path("unused"))


@pytest.mark.parametrize(
    "key,value",
    [
        ("maximum_corrections_same_change", 36),
        ("retained_consumed_source_changes", 0),
        ("maximum_stage_and_query_attempts", 2),
        ("max_new_simulations", 1),
        ("max_entries", 129),
    ],
)
def test_policy_cannot_expand_scope(
    scenario: tuple[ModuleType, Path], key: str, value: int
) -> None:
    guard, repository = scenario
    path = repository / "docs/policy/PHYSICAL_METADATA_LIMIT_V1.json"
    policy = json.loads(path.read_bytes())
    policy[key] = value
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="finite policy conflict"):
        guard.inspect(Path("unused"))


def test_old_consumption_and_source_bytes_cannot_drift(scenario: tuple[ModuleType, Path]) -> None:
    guard, repository = scenario
    source = repository / guard.SOURCES[0]
    source.write_bytes(b"# replacement\n")
    with pytest.raises(ValueError, match="fixed source changed"):
        guard.inspect(Path("unused"))
    path = repository / "docs/policy/M2_NATIVE_CORRECTION_CONSUMED_V9.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="retained policy changed"):
        guard.inspect(Path("unused"))
