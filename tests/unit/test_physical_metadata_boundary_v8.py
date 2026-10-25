"""Disposable Git histories retain source64 under two timer-only source additions."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from test_physical_metadata_boundary import command, commit

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = "PHYSICAL_METADATA_SOURCE_V8_TEST.json"


def load_guard() -> Any:
    spec = importlib.util.spec_from_file_location(
        "physical_v8_guard", ROOT / "scripts/verify-physical-metadata-boundary-v8.py"
    )
    assert spec is not None and spec.loader is not None
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard


@pytest.fixture(scope="module")
def retained64_template(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, str, str]:
    """Build 28 real product events once; each test gets an independent copy.

    The synthetic baseline retains the prior36 consumption. Older guards are
    inert retained data here; their own disposable-history tests cover their
    earlier policies. This fixture exercises V8's full 36+24+4 Git accounting,
    ancestry and immutable history without replaying those unrelated suites.
    """
    guard = load_guard()
    repository = tmp_path_factory.mktemp("source64-template") / "repository"
    repository.mkdir()
    command(repository, "init", "-q")
    command(repository, "config", "user.name", "Synthetic Test")
    command(repository, "config", "user.email", "synthetic@example.invalid")
    command(repository, "config", "core.autocrlf", "false")
    command(repository, "config", "commit.gpgSign", "false")
    # The test must also work from a shallow CI checkout. Retained data comes
    # from the checkout; no actual repository ancestry or old object is assumed
    # by this synthetic fixture. The live guard separately checks its real anchor.
    history = list((ROOT / "docs/policy").glob("PHYSICAL_METADATA_*")) + list(
        (ROOT / "scripts").glob("verify-physical-metadata-boundary*.py")
    )
    for origin in history:
        path = origin.relative_to(ROOT).as_posix()
        if (
            path == guard.POLICY_PATH
            or origin.name == "verify-physical-metadata-boundary-v8.py"
            or origin.name.startswith("PHYSICAL_METADATA_SOURCE_V8_")
        ):
            continue
        destination = repository / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(origin.read_bytes())
    commit(repository)
    baseline = command(repository, "rev-parse", "HEAD")
    source = repository / "src/cadence_mcp_bridge/physical_metadata.py"
    source.parent.mkdir(parents=True)
    for version in range(37, 61):
        source.write_bytes(f"# synthetic retained metadata{version}\n".encode("ascii"))
        commit(repository)
    source60 = command(repository, "rev-parse", "HEAD")
    source = repository / guard.ALLOWED_SOURCE_PATHS[0]
    for version in range(61, 65):
        source.write_bytes(f"# synthetic retained initializer{version}\n".encode("ascii"))
        commit(repository)
    return repository, baseline, source60, command(repository, "rev-parse", "HEAD")


@pytest.fixture
def source66(
    retained64_template: tuple[Path, str, str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    template, baseline, source60, anchor = retained64_template
    repository = tmp_path / "repository"
    shutil.copytree(template, repository)
    guard = load_guard()
    for name, value in {
        "ROOT": repository,
        "BASELINE": baseline,
        "SOURCE60": source60,
        "SOURCE64": anchor,
    }.items():
        monkeypatch.setattr(guard, name, value)
    policy = json.loads((ROOT / guard.POLICY_PATH).read_bytes())
    policy.update(
        base_commit=guard.BASELINE,
        retained_source_commit=anchor,
        retained_source60_commit=guard.SOURCE60,
        prior_limit_policy_canonical_sha256=guard.sha(
            guard.canonical(json.loads(guard.blob(anchor, guard.PRIOR_POLICY)))
        ),
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
        "schema_version": 8,
        "source_version": version,
        "limit_policy": guard.POLICY_PATH,
        "limit_policy_canonical_sha256": guard.sha(guard.canonical(policy)),
        "approval_anchor_commit": guard.SOURCE64,
        "retained_source_changes": 64,
        "source_purpose": "INITIALIZER_PHASE_DEADLINE_AND_PROGRESS_DIAGNOSTICS",
        "source_lf_sha256": {path: guard.sha((repository / path).read_bytes()) for path in paths},
        "authority_note": "Disposable synthetic record; not independent approval.",
    }
    path = repository / "docs/policy" / CHECKPOINT
    path.write_bytes(guard.canonical(value))
    return path


def test_retained64_has_two_timer_additions_without_execution_authority(source66: Any) -> None:
    guard, _ = source66
    result = guard.inspect()
    assert result["retained_consumed"] == result["conservative_consumed"] == 64
    assert result["additional_source_versions"] == result["pending_source_versions"] == 0
    assert result["ceiling"] == 66 and result["remaining"] == 2
    assert result["authority"] == "DIRECT_HUMAN_APPROVAL_NOT_THIS_GUARD"
    assert all(
        result[key] is False
        for key in (
            "new_vm_access_authorized",
            "admin_application_authorized",
            "new_retries_authorized",
            "runtime_trust_widening_authorized",
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
        "docs/policy/PHYSICAL_METADATA_LIMIT_V5.json",
        "docs/policy/PHYSICAL_METADATA_SOURCE_V6_BINDING_OBSERVER_16.json",
        "docs/policy/PHYSICAL_METADATA_SOURCE_V7_BINDING_INITIALIZER_01.json",
        "docs/policy/PHYSICAL_METADATA_SOURCE_V7_BINDING_INITIALIZER_04.json",
        "scripts/verify-physical-metadata-boundary-v6.py",
        "scripts/verify-physical-metadata-boundary-v7.py",
    ],
)
def test_source60_and64_history_remains_immutable(source66: Any, path: str) -> None:
    guard, repository = source66
    (repository / path).write_bytes(b"{}")
    with pytest.raises(ValueError, match="immutable source64 history"):
        guard.inspect()


def test_committed_and_reverted_history_rewrite_is_still_rejected(source66: Any) -> None:
    guard, repository = source66
    path = repository / guard.PRIOR_POLICY
    original = path.read_bytes()
    path.write_bytes(b"{}")
    commit(repository)
    path.write_bytes(original)
    commit(repository)
    with pytest.raises(ValueError, match="history changed in committed event"):
        guard.inspect()


@pytest.mark.parametrize(
    "key,value",
    [
        ("authority", "GENERATED_PLAN_IS_APPROVAL"),
        ("retained_consumed_source_changes", 0),
        ("maximum_corrections_same_change", 67),
        ("maximum_new_source_versions", 3),
        ("max_new_vm_accesses", 1),
        ("max_new_collection_attempts", 1),
        ("max_new_admin_applications", 1),
        ("max_new_deployments", 1),
        ("max_new_eda_starts", 1),
        ("max_new_simulations", 1),
        ("max_new_extractions", 1),
        ("max_new_reserved_bytes", 1),
        ("max_cumulative_attempts", 501),
        ("max_cumulative_result_bytes", 17179869185),
        ("general_same_change_correction_ceiling", 21),
        ("new_retries_authorized", True),
        ("resource_reset_or_refund_authorized", True),
        ("runtime_trust_widening_authorized", True),
        ("merge_authorized", True),
        ("publication_authorized", True),
        ("allowed_product_source_paths", ["src/cadence_mcp_bridge/_binding_observation.py"]),
    ],
)
def test_policy_cannot_reset_or_expand_the_direct_approval(
    source66: Any, key: str, value: object
) -> None:
    guard, repository = source66
    path = repository / guard.POLICY_PATH
    policy = json.loads(path.read_bytes())
    policy[key] = value
    path.write_bytes(guard.canonical(policy))
    with pytest.raises(ValueError, match="finite policy conflict"):
        guard.inspect()


def test_same_tree_replacement_cannot_remove_retained_ancestry(source66: Any) -> None:
    guard, repository = source66
    alternate = command(
        repository,
        "commit-tree",
        guard.SOURCE64 + "^{tree}",
        "-p",
        guard.SOURCE60,
        "-m",
        "unapproved same-tree replacement",
    )
    command(repository, "checkout", "--detach", alternate)
    with pytest.raises(ValueError, match="source60/source64 ancestry missing"):
        guard.inspect()


def test_pending65_then_commit_keeps_usage_and_next_pending_counts66(source66: Any) -> None:
    guard, repository = source66
    command(repository, "config", "status.showUntrackedFiles", "no")
    source = repository / guard.ALLOWED_SOURCE_PATHS[0]
    source.write_bytes(b"# synthetic initializer timing65\n")
    with pytest.raises(ValueError, match="additive checkpoint"):
        guard.inspect()
    checkpoint(guard, repository, 65)
    pending = guard.inspect(CHECKPOINT)
    assert pending["conservative_consumed"] == 65 and pending["remaining"] == 1
    assert pending["pending_source_versions"] == 1
    commit(repository)
    committed = guard.inspect(CHECKPOINT)
    assert committed == dict(pending, pending_source_versions=0)
    source.write_bytes(b"# synthetic scoped review correction66\n")
    with pytest.raises(ValueError, match="checkpoint binding"):
        guard.inspect(CHECKPOINT)
    checkpoint(guard, repository, 66)
    result = guard.inspect(CHECKPOINT)
    assert result["conservative_consumed"] == 66 and result["remaining"] == 0
    source.write_bytes(b"# unrecorded pin drift within pending66\n")
    with pytest.raises(ValueError, match="pinned source changed"):
        guard.inspect(CHECKPOINT)


def test_revert_and_equal_final_tree_do_not_refund_the_two_versions(source66: Any) -> None:
    guard, repository = source66
    source = repository / guard.ALLOWED_SOURCE_PATHS[0]
    original = source.read_bytes()
    source.write_bytes(b"# synthetic timing65\n")
    commit(repository)
    source.write_bytes(original)
    commit(repository)
    checkpoint(guard, repository, 66)
    assert guard.inspect(CHECKPOINT)["remaining"] == 0
    source.write_bytes(b"# forbidden source67\n")
    with pytest.raises(ValueError, match="source66 exhausted; no reset or refund"):
        guard.inspect(CHECKPOINT)


def test_source_changing_merge_counts_and_docs_commit_does_not(source66: Any) -> None:
    guard, repository = source66
    command(repository, "checkout", "-q", "-b", "source64-main")
    command(repository, "checkout", "-q", "-b", "timer65")
    source = repository / guard.ALLOWED_SOURCE_PATHS[0]
    source.write_bytes(b"# synthetic side branch timer65\n")
    commit(repository)
    candidate = command(repository, "rev-parse", "HEAD")
    command(repository, "checkout", "-q", "source64-main")
    command(repository, "merge", "--no-ff", candidate, "-m", "source-changing integration66")
    checkpoint(guard, repository, 66)
    result = guard.inspect(CHECKPOINT)
    assert result["conservative_consumed"] == 66 and result["pending_source_versions"] == 0
    commit(repository)
    assert guard.inspect(CHECKPOINT) == result


def test_out_of_scope_event_cannot_be_hidden_by_reverting(source66: Any) -> None:
    guard, repository = source66
    source = repository / "remote/unrelated.py"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(b"# synthetic out of scope\n")
    with pytest.raises(ValueError, match="initializer timer-only product scope"):
        guard.inspect()
    commit(repository)
    source.unlink()
    commit(repository)
    checkpoint(guard, repository, 66)
    with pytest.raises(ValueError, match="initializer timer-only product scope"):
        guard.inspect(CHECKPOINT)


def test_rename_into_allowed_file_cannot_hide_out_of_scope_deletion(source66: Any) -> None:
    guard, repository = source66
    command(
        repository,
        "mv",
        "-f",
        "src/cadence_mcp_bridge/physical_metadata.py",
        guard.ALLOWED_SOURCE_PATHS[0],
    )
    with pytest.raises(ValueError, match="initializer timer-only product scope"):
        guard.inspect()
    commit(repository)
    with pytest.raises(ValueError, match="initializer timer-only product scope"):
        guard.inspect()


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 7),
        ("source_version", 64),
        ("retained_source_changes", 0),
        ("approval_anchor_commit", "0" * 40),
        ("source_purpose", "ARBITRARY_NEW_FEATURE"),
        ("limit_policy_canonical_sha256", "0" * 64),
        ("maximum_new_source_versions", 999),
        ("execution_authorized", True),
    ],
)
def test_checkpoint_cannot_forge_capacity_or_scope(
    source66: Any, field: str, value: object
) -> None:
    guard, repository = source66
    (repository / guard.ALLOWED_SOURCE_PATHS[0]).write_bytes(b"# synthetic timing65\n")
    path = checkpoint(guard, repository, 65)
    value_before = json.loads(path.read_bytes())
    value_before[field] = value
    path.write_bytes(guard.canonical(value_before))
    with pytest.raises(ValueError, match="checkpoint binding"):
        guard.inspect(CHECKPOINT)


@pytest.mark.parametrize("omitted", ["new", "historical"])
def test_checkpoint_must_bind_full_new_and_historical_product_inventory(
    source66: Any, omitted: str
) -> None:
    guard, repository = source66
    (repository / guard.ALLOWED_SOURCE_PATHS[0]).write_bytes(b"# synthetic timing65\n")
    path = checkpoint(guard, repository, 65)
    value = json.loads(path.read_bytes())
    omit = (
        guard.ALLOWED_SOURCE_PATHS[0]
        if omitted == "new"
        else ("src/cadence_mcp_bridge/physical_metadata.py")
    )
    del value["source_lf_sha256"][omit]
    path.write_bytes(guard.canonical(value))
    with pytest.raises(ValueError, match="complete product source inventory"):
        guard.inspect(CHECKPOINT)


@pytest.mark.parametrize(
    "name", ["../PHYSICAL_METADATA_SOURCE_V8_X.json", "PHYSICAL_METADATA_SOURCE_V7_X.json"]
)
def test_checkpoint_filename_is_closed(source66: Any, name: str) -> None:
    guard, repository = source66
    (repository / guard.ALLOWED_SOURCE_PATHS[0]).write_bytes(b"# synthetic timing65\n")
    with pytest.raises(ValueError, match="checkpoint filename"):
        guard.inspect(name)


def test_historical_batch_reads_all_binary_objects_in_request_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = load_guard()
    paths = ["docs/policy/one.json", "scripts/two.py"]
    bodies = [b"a\0b\nc", b""]
    response = b"".join(
        b"0" * 40 + b" blob " + str(len(raw)).encode() + b"\n" + raw + b"\n" for raw in bodies
    )
    calls = []

    def output(argv: list[str], *, cwd: Path, input: bytes) -> bytes:
        calls.append((argv, cwd, input))
        return response

    monkeypatch.setattr(guard.subprocess, "check_output", output)
    assert guard.blobs("a" * 40, paths) == dict(zip(paths, bodies, strict=True))
    assert calls == [
        (
            ["git", "cat-file", "--batch"],
            guard.ROOT,
            ("".join("a" * 40 + ":" + path + "\n" for path in paths)).encode(),
        )
    ]


@pytest.mark.parametrize(
    "response",
    [
        b"",
        b"missing missing\n",
        b"oid tree 3\nabc\n",
        b"oid blob unknown\n",
        b"oid blob -1\n\n",
        b"oid blob 4\nabc\n",
        b"oid blob 3\nabc",
        b"oid blob 3\nabc\nextra",
    ],
)
def test_incomplete_or_ambiguous_historical_batch_is_rejected(
    monkeypatch: pytest.MonkeyPatch, response: bytes
) -> None:
    guard = load_guard()
    monkeypatch.setattr(guard.subprocess, "check_output", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="historical blob"):
        guard.blobs("a" * 40, ["docs/policy/one.json"])


@pytest.mark.parametrize("paths", [["same", "same"], ["newline\npath"], ["nul\0path"], [""]])
def test_historical_batch_request_cannot_omit_or_inject_objects(paths: list[str]) -> None:
    guard = load_guard()
    with pytest.raises(ValueError, match="historical blob request"):
        guard.blobs("a" * 40, paths)
