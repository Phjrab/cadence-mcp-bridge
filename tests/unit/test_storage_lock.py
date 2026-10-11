"""Fixed-root lock binding, cleanup boundaries and retained unknown outcomes."""

from __future__ import annotations

import json
import os
import stat
import sys
from types import SimpleNamespace

import pytest
from test_storage_runtime import exact_posix_runtime as exact_posix_runtime
from test_storage_worker import approve, register, request_for
from test_storage_worker import fresh_store as fresh_store
from test_storage_worker import store as store

from cadence_mcp_bridge import _storage_worker as w


def fixed_dispatch(store, monkeypatch):
    io, _root, _path = store
    monkeypatch.setattr(w, "PosixIO", lambda: io)
    monkeypatch.setattr(w, "active_eda", lambda _root: False)
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(
        flock=lambda *_args: None, LOCK_EX=2, LOCK_NB=4,
    ))
    return io


def drift_lock(io, path, kind, monkeypatch):
    if kind == "content":
        with (path / "run.lock").open("ab") as stream:
            stream.write(b"unexpected-write")
    elif kind == "mode":
        io.bad_permission.add(str(path / "run.lock"))
    else:
        original = w.os.fstat

        def changed(fd):
            info = original(fd)
            if io.paths.get(fd) != path / "run.lock":
                return info
            values = vars(info).copy()
            values["st_nlink" if kind == "hardlink" else "st_uid"] += 1
            return SimpleNamespace(**values)

        monkeypatch.setattr(w.os, "fstat", changed)


@pytest.mark.parametrize("kind", ["mode", "hardlink", "owner", "content"])
@pytest.mark.parametrize("boundary", ["flock", "activation", "completion"])
def test_lock_drift_at_every_dispatch_boundary_is_denied(
    fresh_store, monkeypatch, kind, boundary,
):
    io = fixed_dispatch(fresh_store, monkeypatch)
    _io, _root, path = fresh_store
    snapshot = w.snapshot
    observed = []

    def change():
        drift_lock(io, path, kind, monkeypatch)

    def lock(*_args):
        if boundary == "flock":
            change()

    def before():
        if boundary == "activation":
            change()

    def inventory(*args, **kwargs):
        observed.append("inventory")
        result = snapshot(*args, **kwargs)
        if boundary == "completion":
            change()
        return result

    sys.modules["fcntl"].flock = lock
    monkeypatch.setattr(w, "snapshot", inventory)
    with pytest.raises(ValueError, match="storage lock"):
        w.execute_fixed(str(path), "inventory", {}, before=before)
    assert observed == (["inventory"] if boundary == "completion" else [])
    assert not list((path / w.CONTROL / "operations").iterdir())


@pytest.mark.parametrize("boundary", ["rename", "unlink"])
def test_lock_drift_stops_cleanup_and_keeps_payload_and_unknown_receipt(
    fresh_store, monkeypatch, boundary,
):
    io, _root, path = fresh_store
    identity = register(fresh_store)
    request = request_for(fresh_store, identity)
    approve(fresh_store, request)
    fixed_dispatch(fresh_store, monkeypatch)
    original_registration, original_rename = w.registration, io.rename
    original_remove = w.remove_leaf
    removing = []
    before_counter = (path / "sim-mcp-v2-jobs/counter.json").read_bytes()
    mutations = []

    def registration(*args, **kwargs):
        result = original_registration(*args, **kwargs)
        if boundary == "rename" and removing:
            drift_lock(io, path, "content", monkeypatch)
        return result

    def rename(*args):
        original_rename(*args)
        mutations.append("rename")
        if boundary == "unlink":
            drift_lock(io, path, "content", monkeypatch)

    def remove(*args, **kwargs):
        removing.append(True)
        try:
            return original_remove(*args, **kwargs)
        finally:
            removing.pop()

    monkeypatch.setattr(w, "registration", registration)
    monkeypatch.setattr(w, "remove_leaf", remove)
    io.rename = rename
    with pytest.raises(ValueError, match="storage lock"):
        w.execute_fixed(str(path), "cleanup", request)
    assert mutations == (["rename"] if boundary == "unlink" else [])
    retained = (path / w.SPOOL / identity / "payload.bin" if boundary == "rename" else
                path / w.CONTROL / "operations" / request["operation_id"] / "quarantine" / identity)
    assert retained.read_bytes() == b"disposable simulation intermediate"
    record = path / w.CONTROL / "operations" / request["operation_id"]
    result = json.loads((record / "result.json").read_bytes())
    assert result["state"] == "UNKNOWN" and result["removed_artifact_ids"] == []
    assert result["reservation_refunded_bytes"] == 0
    assert before_counter == (path / "sim-mcp-v2-jobs/counter.json").read_bytes()


@pytest.mark.skipif(os.name == "nt", reason="Real Linux nofollow/flock/inode fixture")
@pytest.mark.parametrize("kind", ["lock-replace", "root-replace", "hardlink", "mode"])
def test_real_named_root_and_lock_drift_after_flock_never_reaches_inventory(
    exact_posix_runtime, monkeypatch, kind,
):
    root, _script, _pin = exact_posix_runtime
    import fcntl
    original = fcntl.flock
    before_counter = (root / "sim-mcp-v2-jobs/counter.json").read_bytes()

    def lock(fd, flags):
        original(fd, flags)
        if kind == "lock-replace":
            (root / "run.lock").rename(root / "retained-lock")
            (root / "run.lock").write_bytes(b"replacement")
            (root / "run.lock").chmod(0o600)
        elif kind == "root-replace":
            retained = root.with_name("retained-root")
            root.rename(retained)
            root.mkdir(mode=0o700)
            (root / "run.lock").write_bytes(b"replacement")
            (root / "run.lock").chmod(0o600)
        elif kind == "hardlink":
            os.link(root / "run.lock", root / "retained-link")
        else:
            (root / "run.lock").chmod(0o620)

    monkeypatch.setattr(fcntl, "flock", lock)
    monkeypatch.setattr(w, "snapshot", lambda *_a, **_k: pytest.fail("inventory reached"))
    with pytest.raises(ValueError, match="storage (lock|root)"):
        w.execute_fixed(str(root), "inventory", {})
    actual_root = root.with_name("retained-root") if kind == "root-replace" else root
    assert before_counter == (actual_root / "sim-mcp-v2-jobs/counter.json").read_bytes()
    assert stat.S_ISREG((actual_root / "run.lock").stat().st_mode)
    assert not list((actual_root / w.CONTROL / "operations").iterdir())
