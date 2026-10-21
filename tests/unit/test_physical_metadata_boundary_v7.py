"""Disposable Git histories preserve consumed60 under four initializer-only additions."""

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
from test_physical_metadata_boundary_v6 import boundary
from test_physical_metadata_boundary_v6 import checkpoint as checkpoint60

__all__ = ["boundary", "current", "retained", "scenario"]
ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = "PHYSICAL_METADATA_SOURCE_V7_TEST.json"


@pytest.fixture
def source64(boundary: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    prior, repository = boundary
    source = repository / "src/cadence_mcp_bridge/physical_metadata.py"
    for version in range(41, 61):
        source.write_bytes(f"# synthetic retained version{version}\n".encode("ascii"))
        commit(repository)
    path = checkpoint60(prior, repository, 60)
    path.rename(repository / "docs/policy/PHYSICAL_METADATA_SOURCE_V6_BINDING_OBSERVER_16.json")
    script = "scripts/verify-physical-metadata-boundary-v6.py"
    (repository / script).write_bytes((ROOT / script).read_bytes())
    commit(repository)
    source60 = command(repository, "rev-parse", "HEAD")
    spec = importlib.util.spec_from_file_location(
        "physical_v7_guard", ROOT / "scripts/verify-physical-metadata-boundary-v7.py"
    )
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    for name, value in {
        "ROOT": repository,
        "BASELINE": prior.BASELINE,
        "SOURCE60": source60,
    }.items():
        monkeypatch.setattr(guard, name, value)
    policy = json.loads((ROOT / guard.POLICY_PATH).read_bytes())
    policy.update(
        base_commit=guard.BASELINE,
        retained_source_commit=source60,
        prior_limit_policy_canonical_sha256=guard.sha(
            guard.canonical(json.loads(guard.blob(source60, guard.PRIOR_POLICY)))
        ),
        source_lf_sha256=guard.source_pins(source60),
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
        "schema_version": 7,
        "source_version": version,
        "limit_policy": guard.POLICY_PATH,
        "limit_policy_canonical_sha256": guard.sha(guard.canonical(policy)),
        "approval_anchor_commit": guard.SOURCE60,
        "retained_source_changes": 60,
        "source_purpose": "INITIALIZER_TRUST_INSPECTION",
        "source_lf_sha256": {path: guard.sha((repository / path).read_bytes()) for path in paths},
        "authority_note": "Synthetic record; not independent approval.",
    }
    path = repository / "docs/policy" / CHECKPOINT
    path.write_bytes(guard.canonical(value))
    return path


def test_retained60_gets_only_four_additions_and_no_execution_authority(source64: Any) -> None:
    guard, _ = source64
    result = guard.inspect()
    assert result["retained_consumed"] == result["conservative_consumed"] == 60
    assert result["additional_source_versions"] == 0
    assert result["ceiling"] == 64 and result["remaining"] == 4
    assert all(
        result[key] is False
        for key in (
            "new_vm_access_authorized",
            "admin_application_authorized",
            "merge_authorized",
            "publication_authorized",
            "ledger_modified",
            "remote_contact",
        )
    )


@pytest.mark.parametrize(
    "path",
    [
        "docs/policy/PHYSICAL_METADATA_LIMIT_V4.json",
        "docs/policy/PHYSICAL_METADATA_SOURCE_V6_BINDING_OBSERVER_16.json",
        "scripts/verify-physical-metadata-boundary-v6.py",
    ],
)
def test_source60_policy_guard_and_checkpoint_remain_immutable(source64: Any, path: str) -> None:
    guard, repository = source64
    (repository / path).write_bytes(b"{}")
    with pytest.raises(ValueError, match="immutable source60 history"):
        guard.inspect()


@pytest.mark.parametrize(
    "key,value",
    [
        ("retained_consumed_source_changes", 0),
        ("maximum_corrections_same_change", 65),
        ("maximum_new_source_versions", 5),
        ("max_new_vm_accesses", 1),
        ("max_new_admin_applications", 1),
        ("merge_authorized", True),
        ("max_cumulative_result_bytes", 17179869185),
    ],
)
def test_policy_cannot_reset_or_expand_the_direct_approval(
    source64: Any, key: str, value: object
) -> None:
    guard, repository = source64
    path = repository / guard.POLICY_PATH
    policy = json.loads(path.read_bytes())
    policy[key] = value
    path.write_bytes(guard.canonical(policy))
    with pytest.raises(ValueError, match="finite policy conflict"):
        guard.inspect()


def test_available_source60_object_cannot_replace_required_ancestry(source64: Any) -> None:
    guard, repository = source64
    alternate = command(
        repository,
        "commit-tree",
        guard.SOURCE60 + "^{tree}",
        "-p",
        guard.BASELINE,
        "-m",
        "unapproved replacement",
    )
    command(repository, "checkout", "--detach", alternate)
    with pytest.raises(ValueError, match="source60 ancestry missing"):
        guard.inspect()


def test_pending_product_counts_once_and_checkpoint_binds_full_inventory(source64: Any) -> None:
    guard, repository = source64
    command(repository, "config", "status.showUntrackedFiles", "no")
    source = repository / guard.ALLOWED_SOURCE_PATHS[0]
    source.write_bytes(b"# synthetic initializer trust\n")
    with pytest.raises(ValueError, match="additive checkpoint"):
        guard.inspect()
    checkpoint(guard, repository, 61)
    result = guard.inspect(CHECKPOINT)
    assert result["conservative_consumed"] == 61 and result["remaining"] == 3
    commit(repository)
    assert guard.inspect(CHECKPOINT) == result
    source.write_bytes(b"# changed bytes after checkpoint\n")
    with pytest.raises(ValueError, match="checkpoint binding"):
        guard.inspect(CHECKPOINT)
    checkpoint(guard, repository, 62)
    source.write_bytes(b"# same source version but changed pin\n")
    with pytest.raises(ValueError, match="pinned source changed"):
        guard.inspect(CHECKPOINT)


def test_reverts_do_not_refund_and_fifth_pending_version_rejects(source64: Any) -> None:
    guard, repository = source64
    source = repository / guard.ALLOWED_SOURCE_PATHS[0]
    for version in range(61, 65):
        source.write_bytes(f"# synthetic alternating{version % 2}\n".encode("ascii"))
        commit(repository)
    checkpoint(guard, repository, 64)
    assert guard.inspect(CHECKPOINT)["remaining"] == 0
    source.write_bytes(b"# forbidden source65\n")
    with pytest.raises(ValueError, match="source64 exhausted"):
        guard.inspect(CHECKPOINT)


def test_out_of_scope_edit_cannot_be_hidden_by_reverting_its_tree(source64: Any) -> None:
    guard, repository = source64
    source = repository / "remote/unrelated.py"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(b"# synthetic out of scope\n")
    with pytest.raises(ValueError, match="initializer-only product scope"):
        guard.inspect()
    commit(repository)
    source.unlink()
    commit(repository)
    checkpoint(guard, repository, 62)
    with pytest.raises(ValueError, match="initializer-only product scope"):
        guard.inspect(CHECKPOINT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_version", 60),
        ("retained_source_changes", 0),
        ("source_purpose", "ARBITRARY_NEW_FEATURE"),
        ("limit_policy_canonical_sha256", "0" * 64),
        ("maximum_new_source_versions", 999),
    ],
)
def test_forged_checkpoint_cannot_grant_capacity(source64: Any, field: str, value: object) -> None:
    guard, repository = source64
    (repository / guard.ALLOWED_SOURCE_PATHS[0]).write_bytes(b"# synthetic initializer\n")
    path = checkpoint(guard, repository, 61)
    record = json.loads(path.read_bytes())
    record[field] = value
    path.write_bytes(guard.canonical(record))
    with pytest.raises(ValueError, match="checkpoint binding"):
        guard.inspect(CHECKPOINT)


def test_checkpoint_cannot_omit_an_allowed_new_helper(source64: Any) -> None:
    guard, repository = source64
    (repository / guard.ALLOWED_SOURCE_PATHS[0]).write_bytes(b"# synthetic initializer\n")
    path = checkpoint(guard, repository, 61)
    record = json.loads(path.read_bytes())
    del record["source_lf_sha256"][guard.ALLOWED_SOURCE_PATHS[0]]
    path.write_bytes(guard.canonical(record))
    with pytest.raises(ValueError, match="complete product source inventory"):
        guard.inspect(CHECKPOINT)


def test_rename_into_allowed_path_cannot_hide_out_of_scope_deletion(source64: Any) -> None:
    guard, repository = source64
    command(
        repository,
        "mv",
        "src/cadence_mcp_bridge/physical_metadata.py",
        guard.ALLOWED_SOURCE_PATHS[0],
    )
    with pytest.raises(ValueError, match="initializer-only product scope"):
        guard.inspect()
    commit(repository)
    with pytest.raises(ValueError, match="initializer-only product scope"):
        guard.inspect()
