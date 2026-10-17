"""The host-only extension cannot refund35 or expand the remote collector."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_physical_metadata_boundary import command, commit

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, Path]:
    spec = importlib.util.spec_from_file_location(
        "physical_guard_v2", ROOT / "scripts/verify-physical-metadata-boundary-v2.py"
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
    v1 = json.loads((ROOT / "docs/policy/PHYSICAL_METADATA_LIMIT_V1.json").read_bytes())
    for index, path in enumerate(guard.SOURCES):
        source = repository / path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(f"# synthetic source35 {index}\n".encode("ascii"))
        v1["source_lf_sha256"][path] = hashlib.sha256(source.read_bytes()).hexdigest()
    for name in guard.FROZEN:
        value = v1 if "LIMIT" in name else {"retained_consumed": 35}
        (directory / name).write_text(json.dumps(value), encoding="utf-8")
    frozen = {
        name: guard.canonical_sha(json.loads((directory / name).read_bytes()))
        for name in guard.FROZEN
    }
    commit(repository)
    base = command(repository, "rev-parse", "HEAD")
    v2 = json.loads((ROOT / "docs/policy/PHYSICAL_METADATA_LIMIT_V2.json").read_bytes())
    v2.update(
        base_commit=base,
        retained_source_commit=base,
        prior_canonical_sha256=frozen,
        source_lf_sha256=dict(v1["source_lf_sha256"]),
    )
    host = repository / guard.SOURCES[1]
    host.write_bytes(b"# single host correction\n")
    v2["source_lf_sha256"][guard.SOURCES[1]] = hashlib.sha256(host.read_bytes()).hexdigest()
    (directory / "PHYSICAL_METADATA_LIMIT_V2.json").write_text(json.dumps(v2), encoding="utf-8")
    monkeypatch.setattr(guard, "ROOT", repository)
    monkeypatch.setattr(guard, "BASELINE", base)
    monkeypatch.setattr(guard, "SOURCE35", base)
    monkeypatch.setattr(guard, "FROZEN", frozen)
    monkeypatch.setattr(
        guard,
        "prior",
        lambda: SimpleNamespace(
            PRIOR={},
            load_retained=lambda: SimpleNamespace(
                inspect=lambda _: {"conservative_consumed": 34, "remaining": 0}
            ),
        ),
    )
    return guard, repository


def test_pending_and_committed_correction_keep36(scenario: tuple[ModuleType, Path]) -> None:
    guard, repository = scenario
    result = guard.inspect(Path("unused"))
    assert result["conservative_consumed"] == 36 and result["remaining"] == 0
    assert result["remote_collector_unchanged"] and not result["remote_contact"]
    commit(repository)
    assert guard.inspect(Path("unused")) == result


@pytest.mark.parametrize("source_index", [0, 1])
def test_another_source_commit_cannot_hide_behind_updated_pin(
    scenario: tuple[ModuleType, Path], source_index: int
) -> None:
    guard, repository = scenario
    commit(repository)
    source = repository / guard.SOURCES[source_index]
    source.write_bytes(b"# unauthorized version\n")
    path = repository / "docs/policy/PHYSICAL_METADATA_LIMIT_V2.json"
    value = json.loads(path.read_bytes())
    value["source_lf_sha256"][guard.SOURCES[source_index]] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    path.write_text(json.dumps(value), encoding="utf-8")
    for committed in (False, True):
        if committed:
            commit(repository)
        with pytest.raises(ValueError, match="not authorized|exhausted"):
            guard.inspect(Path("unused"))


@pytest.mark.parametrize(
    "key,value",
    [
        ("retained_consumed_source_changes", 0),
        ("maximum_corrections_same_change", 37),
        ("maximum_stage_and_query_attempts", 2),
        ("max_new_simulations", 1),
        ("merge_authorized", True),
        ("publication_authorized", True),
    ],
)
def test_v2_stays_finite(scenario: tuple[ModuleType, Path], key: str, value: object) -> None:
    guard, repository = scenario
    path = repository / "docs/policy/PHYSICAL_METADATA_LIMIT_V2.json"
    policy = json.loads(path.read_bytes())
    policy[key] = value
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="finite policy conflict"):
        guard.inspect(Path("unused"))


def test_v1_consumption_immutable(scenario: tuple[ModuleType, Path]) -> None:
    guard, repository = scenario
    path = repository / "docs/policy/PHYSICAL_METADATA_CONSUMED_V1.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="immutable V1 history"):
        guard.inspect(Path("unused"))
