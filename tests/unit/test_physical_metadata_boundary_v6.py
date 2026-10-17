"""Disposable real Git histories retain source40 before the additive source60 policy."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from test_physical_metadata_boundary import command, commit
from test_physical_metadata_boundary_v3 import scenario
from test_physical_metadata_boundary_v4 import current
from test_physical_metadata_boundary_v5 import retained

__all__ = ["current", "retained", "scenario"]
ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = "PHYSICAL_METADATA_SOURCE_V6_TEST.json"


@pytest.fixture
def boundary(retained: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    old, prior, repository = retained
    source38 = command(repository, "rev-parse", "HEAD")
    command(repository, "checkout", "-q", "-b", "operator-main", prior.SOURCE37)
    command(repository, "merge", "--no-ff", source38, "-m", "retained source39 integration")
    main = command(repository, "rev-parse", "HEAD")
    command(repository, "checkout", "-q", "-b", "candidate")
    source = repository / "src/cadence_mcp_bridge/physical_metadata.py"
    source.write_bytes(b"# synthetic source40\n")
    for name in (
        "verify-physical-metadata-boundary.py",
        "verify-physical-metadata-boundary-v2.py",
        "verify-physical-metadata-boundary-v5.py",
    ):
        (repository / "scripts" / name).write_bytes((ROOT / "scripts" / name).read_bytes())
    commit(repository)
    anchor = command(repository, "rev-parse", "HEAD")
    spec = importlib.util.spec_from_file_location(
        "physical_v6_guard", ROOT / "scripts/verify-physical-metadata-boundary-v6.py"
    )
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    # Only disposable fixture repository identities are substituted. The live
    # guard, finite limits and historical guard implementations are never patched.
    for name, value in {
        "ROOT": repository,
        "BASELINE": prior.BASELINE,
        "SOURCE36": prior.SOURCE36,
        "SOURCE37": prior.SOURCE37,
        "SOURCE38": old.SOURCE38,
        "ANCHOR": anchor,
        "MAIN": main,
    }.items():
        monkeypatch.setattr(guard, name, value)
    policy = json.loads((ROOT / guard.POLICY_PATH).read_bytes())
    policy.update(
        base_commit=guard.BASELINE,
        retained_source_commit=anchor,
        normal_merge_base_commit=main,
        source_lf_sha256=guard.source_pins(anchor),
    )
    (repository / guard.POLICY_PATH).write_bytes(guard.canonical(policy))
    return guard, repository


def checkpoint(guard: Any, repository: Path, version: int) -> Path:
    paths = set(
        command(
            repository, "diff", "--name-only", guard.BASELINE, "--", "src", "remote"
        ).splitlines()
    )
    paths.update(
        command(
            repository, "ls-files", "--others", "--exclude-standard", "--", "src", "remote"
        ).splitlines()
    )
    policy = json.loads((repository / guard.POLICY_PATH).read_bytes())
    value = {
        "schema_version": 6,
        "source_version": version,
        "limit_policy": guard.POLICY_PATH,
        "limit_policy_canonical_sha256": guard.sha(guard.canonical(policy)),
        "approval_anchor_commit": guard.ANCHOR,
        "retained_source_changes": 40,
        "source_lf_sha256": {path: guard.sha((repository / path).read_bytes()) for path in paths},
    }
    path = repository / "docs/policy" / CHECKPOINT
    path.write_bytes(guard.canonical(value))
    return path


def test_source40_retained_without_reset_or_remote_authority(boundary: Any) -> None:
    guard, _ = boundary
    result = guard.inspect()
    assert result["conservative_consumed"] == 40 and result["remaining"] == 20
    assert result["ceiling"] == 60 and result["cumulative_collection_ceiling"] == 11
    assert result["retained_collection_attempts"] == 1
    assert result["merge_authority_scope"] == "PR162_NORMAL_INTEGRATION_ONLY"
    assert not result["publication_authorized"]
    assert not result["ledger_modified"] and not result["remote_contact"]


def test_normal_merge_counts41_with_later_policy_docs_commit(boundary: Any) -> None:
    guard, repository = boundary
    (repository / "policy-note.md").write_text("synthetic policy/docs follow-up", encoding="utf-8")
    commit(repository)
    head = command(repository, "rev-parse", "HEAD")
    assert head != guard.ANCHOR
    command(repository, "checkout", "-q", "operator-main")
    command(repository, "merge", "--no-ff", head, "-m", "normal candidate integration")
    result = guard.inspect()
    assert result["conservative_consumed"] == 41 and result["remaining"] == 19
    assert result["additional_source_versions"] == 1
    (repository / "post-merge.md").write_text("synthetic docs only", encoding="utf-8")
    commit(repository)
    assert guard.inspect() == result


@pytest.mark.parametrize(
    "path",
    [
        "docs/policy/PHYSICAL_METADATA_CONSUMED_V3.json",
        "docs/policy/PHYSICAL_METADATA_LIMIT_V3.json",
        "docs/policy/PHYSICAL_METADATA_SOURCE_V4.json",
        "scripts/verify-physical-metadata-boundary-v5.py",
    ],
)
def test_prior_history_cannot_be_rewritten(boundary: Any, path: str) -> None:
    guard, repository = boundary
    (repository / path).write_bytes(b"{}")
    with pytest.raises(ValueError, match="immutable history"):
        guard.inspect()


@pytest.mark.parametrize(
    "key,value",
    [
        ("retained_consumed_source_changes", 0),
        ("retained_collection_attempts", 0),
        ("maximum_corrections_same_change", 61),
        ("maximum_stage_and_query_attempts", 12),
        ("max_new_simulations", 1),
        ("max_cumulative_result_bytes", 17179869185),
        ("general_same_change_correction_ceiling", 60),
        ("merge_scope", "ALL_PRS"),
        ("publication_authorized", True),
    ],
)
def test_approval_changes_only_the_explicit_bounds(boundary: Any, key: str, value: object) -> None:
    guard, repository = boundary
    path = repository / guard.POLICY_PATH
    policy = json.loads(path.read_bytes())
    policy[key] = value
    path.write_bytes(guard.canonical(policy))
    with pytest.raises(ValueError, match="finite policy conflict"):
        guard.inspect()


def test_available_anchor_object_does_not_replace_ancestry(boundary: Any) -> None:
    guard, repository = boundary
    alternate = command(
        repository,
        "commit-tree",
        guard.ANCHOR + "^{tree}",
        "-p",
        guard.MAIN,
        "-m",
        "unapproved replacement source40",
    )
    command(repository, "checkout", "--detach", alternate)
    assert command(repository, "cat-file", "-t", guard.ANCHOR) == "commit"
    with pytest.raises(ValueError, match="ancestry missing"):
        guard.inspect()


def test_new_source_needs_bound_checkpoint_before_and_after_commit(boundary: Any) -> None:
    guard, repository = boundary
    source = repository / "src/cadence_mcp_bridge/physical_metadata.py"
    source.write_bytes(b"# synthetic source41 correction\n")
    with pytest.raises(ValueError, match="additive checkpoint"):
        guard.inspect()
    checkpoint(guard, repository, 41)
    before = guard.inspect(CHECKPOINT)
    assert before["conservative_consumed"] == 41
    commit(repository)
    assert guard.inspect(CHECKPOINT) == before
    with pytest.raises(ValueError, match="additive checkpoint"):
        guard.inspect()


def test_reverted_source_stays_charged_and_needs_new_checkpoint(boundary: Any) -> None:
    guard, repository = boundary
    source = repository / "src/cadence_mcp_bridge/physical_metadata.py"
    before = source.read_bytes()
    source.write_bytes(b"# synthetic failed source41\n")
    commit(repository)
    source.write_bytes(before)
    commit(repository)
    with pytest.raises(ValueError, match="additive checkpoint"):
        guard.inspect()
    path = checkpoint(guard, repository, 40)
    with pytest.raises(ValueError, match="checkpoint binding"):
        guard.inspect(CHECKPOINT)
    value = json.loads(path.read_bytes())
    value["source_version"] = 42
    path.write_bytes(guard.canonical(value))
    assert guard.inspect(CHECKPOINT)["conservative_consumed"] == 42


def test_checkpoint_cannot_omit_new_product_helper(boundary: Any) -> None:
    guard, repository = boundary
    checkpoint(guard, repository, 41)
    (repository / "src/hidden_variant.py").write_bytes(b"# synthetic new variant\n")
    with pytest.raises(ValueError, match="complete product source inventory"):
        guard.inspect(CHECKPOINT)


@pytest.mark.parametrize("name", ["../checkpoint.json", "PHYSICAL_METADATA_SOURCE_V4.json"])
def test_new_checkpoint_cannot_alias_historical_files(boundary: Any, name: str) -> None:
    guard, _ = boundary
    with pytest.raises(ValueError, match="checkpoint filename"):
        guard.inspect(name)


def test_source60_ceiling_counts_every_commit_even_if_content_repeats(boundary: Any) -> None:
    guard, repository = boundary
    source = repository / "src/cadence_mcp_bridge/physical_metadata.py"
    for version in range(41, 61):
        source.write_bytes(f"# synthetic alternating variant {version % 2}\n".encode("ascii"))
        commit(repository)
    checkpoint(guard, repository, 60)
    result = guard.inspect(CHECKPOINT)
    assert result["conservative_consumed"] == 60 and result["remaining"] == 0
    source.write_bytes(b"# synthetic source61\n")
    with pytest.raises(ValueError, match="source60 exhausted"):
        guard.inspect(CHECKPOINT)
