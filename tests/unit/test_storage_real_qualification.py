"""Safety of the closed fixture producer; POSIX metadata emulation on Windows."""
from __future__ import annotations

import copy
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cadence_mcp_bridge import _storage_worker as w

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fixture_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, ...]:
    spec = importlib.util.spec_from_file_location(
        "storage_test_io", ROOT / "tests/unit/test_storage_worker.py")
    assert spec and spec.loader
    emulation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(emulation)
    monkeypatch.setitem(sys.modules, "worker", w)
    helper_spec = importlib.util.spec_from_file_location(
        "fixture_helper", ROOT / "remote/phase-campaign/storage-real-qual-v1/helper.py")
    assert helper_spec and helper_spec.loader
    helper = importlib.util.module_from_spec(helper_spec)
    old_path = list(sys.path)
    try:
        helper_spec.loader.exec_module(helper)
    finally:
        sys.path[:] = old_path
    (tmp_path / w.SPOOL).mkdir()
    io = emulation.TestIO(tmp_path, monkeypatch)
    original_open = io.open

    def binary_open(parent: int, name: str, **kwargs: Any) -> int:
        fd = original_open(parent, name, **kwargs)
        if fd >= 0 and sys.platform == "win32":
            import msvcrt
            msvcrt.setmode(fd, os.O_BINARY)
        return fd

    monkeypatch.setattr(io, "open", binary_open)
    return helper, io, io.directory(tmp_path), tmp_path


def test_prepare_inspect_and_no_overwrite(fixture_store: tuple[Any, ...]) -> None:
    h, io, fd, path = fixture_store
    prepared = h.operate(io, fd, "prepare", h.EXPECTED)
    assert sum(i["size_bytes"] for i in prepared["fixtures"]) == 20480
    before = {p: p.read_bytes() for p in path.rglob("*") if p.is_file()}
    inspect = h.operate(io, fd, "inspect", h.EXPECTED)
    assert inspect["fixtures"] == prepared["fixtures"]
    assert inspect["deleted_artifacts"] == 0 and not inspect["analog_qualification"]
    with pytest.raises(ValueError, match="preexisting"):
        h.operate(io, fd, "prepare", h.EXPECTED)
    assert before == {p: p.read_bytes() for p in path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("change", ["size", "uuid", "delete", "action"])
def test_contract_rejection(fixture_store: tuple[Any, ...], change: str) -> None:
    h, io, fd, path = fixture_store
    policy = copy.deepcopy(h.EXPECTED)
    action = "prepare"
    if change == "size":
        policy["fixtures"][0]["size_bytes"] += 1
    elif change == "uuid":
        policy["fixtures"][0]["artifact_uuid"] = "../protected"
    elif change == "delete":
        policy["delete_authority"] = True
    else:
        action = "delete"
    with pytest.raises(ValueError):
        h.operate(io, fd, action, policy)
    assert list((path / w.SPOOL).iterdir()) == []
    assert not (path / h.EVIDENCE).exists()


def test_disk_floor(fixture_store: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch) -> None:
    h, io, fd, path = fixture_store
    monkeypatch.setattr(os, "fstatvfs", lambda _: SimpleNamespace(
        f_bavail=1, f_frsize=4096, f_blocks=2000000))
    with pytest.raises(ValueError, match="disk floor"):
        h.operate(io, fd, "prepare", h.EXPECTED)
    assert not (path / h.EVIDENCE).exists()


def test_existing_second_identity_preserves_everything(fixture_store: tuple[Any, ...]) -> None:
    h, io, fd, path = fixture_store
    old = path / w.SPOOL / h.EXPECTED["fixtures"][1]["artifact_uuid"]
    old.mkdir()
    (old / "protected").write_bytes(b"original")
    with pytest.raises(ValueError, match="preexisting"):
        h.operate(io, fd, "prepare", h.EXPECTED)
    assert (old / "protected").read_bytes() == b"original"
    assert not (path / h.EVIDENCE).exists()
    assert len(list((path / w.SPOOL).iterdir())) == 1


def test_partial_failure_no_blind_retry(
    fixture_store: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch,
) -> None:
    h, io, fd, path = fixture_store
    original = io.mkdir
    second = h.EXPECTED["fixtures"][1]["artifact_uuid"]

    def fail(parent: int, name: str) -> None:
        if name == second:
            raise OSError("injected partial creation")
        original(parent, name)

    monkeypatch.setattr(io, "mkdir", fail)
    with pytest.raises(OSError, match="injected"):
        h.operate(io, fd, "prepare", h.EXPECTED)
    assert (path / h.EVIDENCE / "prepare-intent.json").exists()
    assert not (path / h.EVIDENCE / "extraction.json").exists()
    with pytest.raises(ValueError, match="preexisting"):
        h.operate(io, fd, "prepare", h.EXPECTED)
    with pytest.raises(OSError):
        h.operate(io, fd, "inspect", h.EXPECTED)


def test_private_leaf_and_content_drift(fixture_store: tuple[Any, ...]) -> None:
    h, io, fd, path = fixture_store
    h.operate(io, fd, "prepare", h.EXPECTED)
    leaf = path / w.SPOOL / h.EXPECTED["fixtures"][0]["artifact_uuid"] / "payload.bin"
    leaf.write_bytes(b"changed")
    with pytest.raises(ValueError, match="mismatch"):
        h.operate(io, fd, "inspect", h.EXPECTED)


def test_extra_entry_rejected(fixture_store: tuple[Any, ...]) -> None:
    h, io, fd, path = fixture_store
    h.operate(io, fd, "prepare", h.EXPECTED)
    container = path / w.SPOOL / h.EXPECTED["fixtures"][0]["artifact_uuid"]
    (container / "extra").write_bytes(b"preserve")
    with pytest.raises(ValueError, match="isolated"):
        h.operate(io, fd, "inspect", h.EXPECTED)


def test_unsafe_parent_rejected(
    fixture_store: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch,
) -> None:
    h, io, fd, path = fixture_store
    original = io.open

    def deny(parent: int, name: str, **kwargs: Any) -> int:
        if name == w.SPOOL:
            raise OSError("injected symlink/no-follow rejection")
        return original(parent, name, **kwargs)

    monkeypatch.setattr(io, "open", deny)
    with pytest.raises(OSError, match="no-follow"):
        h.operate(io, fd, "prepare", h.EXPECTED)
    assert not (path / h.EVIDENCE).exists()
