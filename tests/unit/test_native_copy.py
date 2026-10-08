"""Disposable worker-copy primitives; no actual OA/ADE source or VM writes."""

import os

import pytest

from cadence_mcp_bridge import _native_copy as native


@pytest.fixture
def trees(tmp_path):
    source = tmp_path / "protected-source"
    source.mkdir(mode=0o700)
    view = source / "schematic"
    view.mkdir(mode=0o700)
    (view / "sch.oa").write_bytes(b"fictional OA file, not proprietary")
    (view / "master.tag").write_bytes(b"sch.oa")
    state = source / "state1"
    state.mkdir(mode=0o700)
    (state / "variables").write_bytes(b"fictional ADE state")
    parent = tmp_path / "owned-job"
    parent.mkdir(mode=0o700)
    return str(source.resolve()), str((parent / "copy").resolve())


def test_copy_content_and_source_metadata_preserved(trees):
    source, target = trees
    before = native.snapshot(source)
    receipt = native.copy_owned(source, target, before["tree_sha256"])
    assert native.snapshot(source) == before
    copied = native.snapshot(target)
    assert copied["content_sha256"] == before["content_sha256"]
    assert copied["tree_sha256"] == receipt["copy_tree_sha256"]
    assert receipt["source_preserved"] and receipt["copy_owned"]
    if os.name != "nt":
        for row in copied["metadata"]:
            assert row[2] == (0o700 if row[0] == "directory" else 0o600)
            assert row[3] == os.getuid()
    with pytest.raises(ValueError, match="already_exists"):
        native.copy_owned(source, target, before["tree_sha256"])
    assert native.snapshot(source) == before and native.snapshot(target) == copied


def test_stale_registered_tree_creates_no_destination(trees):
    source, target = trees
    with pytest.raises(ValueError, match="registration_mismatch"):
        native.copy_owned(source, target, "0" * 64)
    assert not os.path.lexists(target)


@pytest.mark.parametrize(
    "name", ["sch.oa.cdslck", "sch.oa.cdslck.old", "task.lock", "panic.oa", "recovery.state"]
)
def test_active_or_recovery_artifact_never_copied(trees, name):
    source, target = trees
    before = native.snapshot(source)
    with open(os.path.join(source, name), "wb") as stream:
        stream.write(b"retained evidence")
    with pytest.raises(ValueError, match="active_or_recovery"):
        native.snapshot(source)
    assert not os.path.lexists(target)
    assert before["entries"] == 6


def test_source_hardlink_rejected(trees):
    source, target = trees
    os.link(os.path.join(source, "schematic", "sch.oa"), os.path.join(source, "linked.oa"))
    with pytest.raises(ValueError, match="link_bound"):
        native.snapshot(source)
    assert not os.path.lexists(target)


def test_source_symlink_rejected(trees):
    source, target = trees
    try:
        os.symlink(os.path.join(source, "schematic", "sch.oa"), os.path.join(source, "linked.oa"))
    except OSError:
        pytest.skip("Windows symlink privilege unavailable; POSIX CI covers real link")
    with pytest.raises(ValueError, match="link_or_special"):
        native.snapshot(source)
    assert not os.path.lexists(target)


@pytest.mark.parametrize("kind", ["bytes", "entries", "depth"])
def test_bounded_tree_denies_before_copy(trees, monkeypatch, kind):
    source, target = trees
    monkeypatch.setattr(
        native, {"bytes": "MAX_BYTES", "entries": "MAX_ENTRIES", "depth": "MAX_DEPTH"}[kind], 0
    )
    with pytest.raises(ValueError):
        native.snapshot(source)
    assert not os.path.lexists(target)


def test_interrupted_copy_retains_partial_target_and_source(trees, monkeypatch):
    source, target = trees
    before = native.snapshot(source)
    original = native.read_leaf
    calls = []

    def interrupted(value, expected, limit):
        calls.append(value)
        if len(calls) == 5:
            raise OSError("synthetic interruption during copy")
        return original(value, expected, limit)

    monkeypatch.setattr(native, "read_leaf", interrupted)
    with pytest.raises(OSError):
        native.copy_owned(source, target, before["tree_sha256"])
    monkeypatch.setattr(native, "read_leaf", original)
    assert os.path.isdir(target) and native.snapshot(source) == before
    with pytest.raises(ValueError, match="already_exists"):
        native.copy_owned(source, target, before["tree_sha256"])


def test_nested_source_target_denied(trees):
    source, _ = trees
    with pytest.raises(ValueError, match="overlap"):
        native.copy_owned(
            source, os.path.join(source, "nested"), native.snapshot(source)["tree_sha256"]
        )
    assert not os.path.lexists(os.path.join(source, "nested"))


def test_owned_ade_routing_changes_only_two_declared_fields():
    original = (
        b"header\n"
        b'designInfo = \'("SourceLib" "SourceCell" "schematic" "spectre")\n'
        b'projectDir = \'"~/simulation"\n'
        b"opaque-original-expression-kept\n"
    )
    expected = (
        original.replace(b"SourceLib", b"MCP_GREL_Work")
        .replace(b"SourceCell", b"Grel_test")
        .replace(b"~/simulation", b"/managed/job/project")
    )
    changed = native.remap_ade_info(
        original,
        ("SourceLib", "SourceCell", "schematic"),
        ("MCP_GREL_Work", "Grel_test", "schematic"),
        "/managed/job/project",
    )
    assert changed == expected
    assert b"opaque-original-expression-kept" in changed
    with pytest.raises(ValueError, match="routing_mismatch"):
        native.remap_ade_info(
            original,
            ("OtherLib", "SourceCell", "schematic"),
            ("MCP_GREL_Work", "Grel_test", "schematic"),
            "/managed/job/project",
        )
    with pytest.raises(ValueError, match="routing_mismatch"):
        native.remap_ade_info(
            original + b'projectDir = \'"duplicate"\n',
            ("SourceLib", "SourceCell", "schematic"),
            ("MCP_GREL_Work", "Grel_test", "schematic"),
            "/managed/job/project",
        )


@pytest.mark.parametrize(
    "value",
    [
        "relative",
        "/managed/../original",
        "/managed/./job",
        "/managed/job\nexit(0)",
        "/managed//job",
    ],
)
def test_owned_ade_project_injection_denied(value):
    with pytest.raises(ValueError, match="project"):
        native.remap_ade_info(
            b"", ("Source", "Cell", "schematic"), ("Owned", "Copy", "schematic"), value
        )
