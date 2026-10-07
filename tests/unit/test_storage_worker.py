"""Exercise cleanup state machine with actual temporary leaf data.

Windows tests emulate POSIX descriptor/permission metadata, not libc qualification.
The production PosixIO uses Linux dirfds; actual guest qualification is separate.
"""

from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from cadence_mcp_bridge import _storage_worker as w


class TestIO:
    __test__ = False

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.paths: dict[int, Path] = {}
        self.next_fd = -100
        self.root_path = root
        self.rename_hook: Any = None
        self.fail_unlink = False
        self.emulated_unlinked_fds: set[int] = set()
        self.real_close = os.close
        self.bad_permission: set[str] = set()
        real_fstat, real_close, real_fsync = os.fstat, os.close, os.fsync

        def fstat(fd: int) -> Any:
            s = self.paths[fd].stat() if fd < 0 else real_fstat(fd)
            mode = s.st_mode
            if stat.S_ISDIR(mode):
                mode = stat.S_IFDIR | 0o700
            if stat.S_ISREG(mode):
                mode = stat.S_IFREG | (
                    0o644 if str(self.paths.get(fd)) in self.bad_permission else 0o600
                )
            return SimpleNamespace(
                st_dev=s.st_dev,
                st_ino=s.st_ino,
                st_mode=mode,
                st_nlink=s.st_nlink,
                st_size=s.st_size,
                st_mtime=s.st_mtime,
                st_ctime=s.st_ctime,
                st_uid=os.getuid() if hasattr(os, "getuid") else 0,
                st_blocks=(s.st_size + 511) // 512,
            )

        def close(fd: int) -> None:
            if fd in self.emulated_unlinked_fds:
                self.emulated_unlinked_fds.remove(fd)
            elif fd >= 0:
                real_close(fd)
            self.paths.pop(fd, None)

        monkeypatch.setattr(w.os, "fstat", fstat)
        monkeypatch.setattr(w.os, "close", close)
        monkeypatch.setattr(w.os, "fsync", lambda fd: real_fsync(fd) if fd >= 0 else None)
        monkeypatch.setattr(w.os, "getuid", lambda: 0, raising=False)
        monkeypatch.setattr(
            w.os,
            "fstatvfs",
            lambda fd: SimpleNamespace(f_bavail=1000000, f_frsize=4096, f_blocks=2000000),
            raising=False,
        )

    def open(self, parent: int, name: str, directory: bool = False, create: bool = False) -> int:
        if not name or name in (".", "..") or "/" in name or "\x00" in name:
            raise ValueError("unsafe component")
        path = self.paths[parent] / name
        if path.is_symlink():
            raise OSError(errno.ELOOP, "link denied")
        if directory or path.is_dir():
            if not path.is_dir():
                raise OSError(
                    errno.ENOENT if not path.exists() else errno.ENOTDIR, "directory denied"
                )
            return self.directory(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL if create else os.O_RDONLY)
        self.paths[fd] = path
        return fd

    def directory(self, path: Path) -> int:
        self.next_fd -= 1
        self.paths[self.next_fd] = path
        return self.next_fd

    def names(self, fd: int) -> list[str]:
        names = sorted(p.name for p in self.paths[fd].iterdir())
        if len(names) > w.MAX_NODES:
            raise ValueError("directory bound")
        return names

    def mkdir(self, parent: int, name: str) -> None:
        (self.paths[parent] / name).mkdir()

    def rename(self, parent: int, name: str, destination: int, leaf: str) -> None:
        source = self.paths[parent] / name
        if self.rename_hook:
            self.rename_hook(source)
        target = self.paths[destination] / leaf
        source.rename(target)
        # POSIX open descriptors retain the renamed inode. Track that move so
        # Windows emulation closes every handle before unlink, including the
        # original fingerprint handle and the reopened quarantine handle.
        for fd, path in self.paths.items():
            if fd >= 0 and path == source:
                self.paths[fd] = target

    def unlink(self, parent: int, name: str) -> None:
        if self.fail_unlink:
            raise OSError(errno.EIO, "injected delete failure")
        target = self.paths[parent] / name
        # Emulate POSIX unlink of an open file on Windows, which otherwise rejects it.
        for fd, path in self.paths.items():
            if fd >= 0 and path == target:
                self.real_close(fd)
                self.emulated_unlinked_fds.add(fd)
        target.unlink()


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestIO, int, Path]:
    for directory in (
        "sim-mcp-v2-jobs",
        "jobs",
        w.SPOOL,
        w.CONTROL + "/registrations",
        w.CONTROL + "/approvals",
        w.CONTROL + "/operations",
    ):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    (tmp_path / "sim-mcp-v2-jobs/counter.json").write_bytes(
        w.canonical(dict(campaign_id="AUTO-PHASE-01", count=62, result_reserved_bytes=7114588160))
    )
    io = TestIO(tmp_path, monkeypatch)
    return io, io.directory(tmp_path), tmp_path


def register(
    store: tuple[TestIO, int, Path], payload: bytes = b"disposable simulation intermediate"
) -> str:
    io, root, path = store
    identity = str(uuid4())
    directory = path / w.SPOOL / identity
    directory.mkdir()
    (directory / "payload.bin").write_bytes(payload)
    leaf = io.open(root, w.SPOOL, directory=True)
    child = io.open(leaf, identity, directory=True)
    try:
        fingerprint, _, content = w.payload_fingerprint(io, child)
    finally:
        os.close(child)
        os.close(leaf)
    record = dict(
        contract_version=1,
        artifact_uuid=identity,
        analysis_type="tran",
        measurement_extracted=True,
        replay_dependency=False,
        evidence_dependency=False,
        active_dependency=False,
        fingerprint=fingerprint,
        content_sha256=content,
    )
    (path / w.CONTROL / "registrations" / (identity + ".json")).write_bytes(w.canonical(record))
    return identity


def request_for(store: tuple[TestIO, int, Path], *identities: str) -> dict[str, Any]:
    io, root, _ = store
    s = w.snapshot(io, root, False)
    ids = ["sa-" + w.digest(["disposable", name]) for name in identities]
    selection = dict(snapshot_id=s["snapshot_id"], artifact_ids=ids)
    p = w.plan(s, selection)
    return dict(
        selection=selection,
        cleanup_plan_id=p["cleanup_plan_id"],
        plan_sha256=p["plan_sha256"],
        selected_artifact_ids=ids,
        operation_id=str(uuid4()),
        dry_run=False,
    )


def approve(store: tuple[TestIO, int, Path], request: dict[str, Any]) -> None:
    _, _, path = store
    approval = dict(
        contract_version=1,
        request_sha256=w.digest(request),
        selected_artifact_ids=request["selected_artifact_ids"],
        plan_sha256=request["plan_sha256"],
        user_selection="explicit-selected-items",
    )
    (path / w.CONTROL / "approvals" / (request["operation_id"] + ".json")).write_bytes(
        w.canonical(approval)
    )


def test_selected_leaf_delete_audit_and_restart_replay(store: tuple[TestIO, int, Path]) -> None:
    io, root, path = store
    a, b = register(store, b"A" * 5000), register(store, b"B" * 7000)
    request = request_for(store, a, b)
    # User selects only A from the concrete two-item plan.
    request["selected_artifact_ids"] = request["selected_artifact_ids"][:1]
    approve(store, request)
    ledger = (path / "sim-mcp-v2-jobs/counter.json").read_bytes()
    result = w.cleanup(io, root, request, False)
    assert result["state"] == "COMPLETE" and result["removed_logical_bytes"] == 5000
    assert result["actual_reclaimed_bytes"] is None and result["unlinked_allocated_bytes"] >= 5000
    assert not (path / w.SPOOL / a / "payload.bin").exists()
    assert (path / w.SPOOL / b / "payload.bin").read_bytes() == b"B" * 7000
    assert result["audit_recorded"] and result["reservation_refunded_bytes"] == 0
    assert (path / "sim-mcp-v2-jobs/counter.json").read_bytes() == ledger
    assert w.cleanup(io, root, json.loads(json.dumps(request)), False) == result
    forged = {**request, "selected_artifact_ids": ["sa-" + "f" * 64]}
    with pytest.raises(ValueError):
        w.cleanup(io, root, forged, False)


def test_missing_or_wrong_approval_and_dry_run_never_delete(
    store: tuple[TestIO, int, Path],
) -> None:
    io, root, path = store
    identity = register(store)
    request = request_for(store, identity)
    assert w.cleanup(io, root, request, False)["state"] == "DENIED"
    dry = w.cleanup(io, root, {**request, "dry_run": True}, False)
    assert (
        dry["state"] == "DRY_RUN" and not dry["removed_artifact_ids"] and not dry["audit_recorded"]
    )
    assert not list((path / w.CONTROL / "operations").iterdir())
    approve(store, request)
    approval = path / w.CONTROL / "approvals" / (request["operation_id"] + ".json")
    data = json.loads(approval.read_bytes())
    data["request_sha256"] = "0" * 64
    approval.write_bytes(w.canonical(data))
    assert w.cleanup(io, root, request, False)["state"] == "DENIED"
    assert (path / w.SPOOL / identity / "payload.bin").exists()


@pytest.mark.parametrize("changed", ["content", "plan", "active", "permission", "dependency"])
def test_revalidation_denies_changed_conditions(
    store: tuple[TestIO, int, Path], changed: str
) -> None:
    io, root, path = store
    identity = register(store)
    request = request_for(store, identity)
    approve(store, request)
    payload = path / w.SPOOL / identity / "payload.bin"
    if changed == "content":
        payload.write_bytes(b"new contents")
    elif changed == "plan":
        request["plan_sha256"] = "0" * 64
        request["cleanup_plan_id"] = "sc-" + "0" * 64
    elif changed == "permission":
        io.bad_permission.add(
            str(path / w.CONTROL / "approvals" / (request["operation_id"] + ".json"))
        )
    elif changed == "dependency":
        record = path / w.CONTROL / "registrations" / (identity + ".json")
        value = json.loads(record.read_bytes())
        value["evidence_dependency"] = True
        record.write_bytes(w.canonical(value))
    if changed in ("content", "plan", "dependency", "active"):
        with pytest.raises(ValueError):
            w.cleanup(io, root, request, changed == "active")
    else:
        assert w.cleanup(io, root, request, False)["state"] == "DENIED"
    assert payload.exists()


def test_queued_job_blocks_unrelated_selected_cleanup(store: tuple[TestIO, int, Path]) -> None:
    io, root, path = store
    identity = register(store)
    queued = path / "jobs" / str(uuid4())
    queued.mkdir()
    (queued / "status.json").write_text('{"state":"queued"}', encoding="ascii")
    request = request_for(store, identity)
    approve(store, request)
    assert w.cleanup(io, root, request, False)["state"] == "DENIED"
    assert (path / w.SPOOL / identity / "payload.bin").exists()


def test_partial_delete_and_uncertain_retry_are_durable(store: tuple[TestIO, int, Path]) -> None:
    io, root, path = store
    a, b = register(store), register(store)
    request = request_for(store, a, b)
    approve(store, request)
    real_unlink = io.unlink
    calls = 0

    def failing(parent: int, name: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(errno.EIO, "second unlink failure")
        real_unlink(parent, name)

    io.unlink = failing  # type: ignore[method-assign]
    result = w.cleanup(io, root, request, False)
    assert result["state"] == "PARTIAL" and len(result["removed_artifact_ids"]) == 1
    assert w.cleanup(io, root, request, False) == result and calls == 2
    assert (
        len(
            list(
                (path / w.CONTROL / "operations" / request["operation_id"] / "quarantine").iterdir()
            )
        )
        == 1
    )


def test_race_substitution_is_quarantined_never_unlinked(store: tuple[TestIO, int, Path]) -> None:
    io, root, path = store
    identity = register(store)
    request = request_for(store, identity)
    approve(store, request)

    def substitute(payload: Path) -> None:
        payload.rename(payload.parent / "original-preserved.bin")
        payload.write_bytes(b"different inode must not be deleted")

    io.rename_hook = substitute
    result = w.cleanup(io, root, request, False)
    assert result["state"] == "UNKNOWN" and not result["removed_artifact_ids"]
    assert (path / w.SPOOL / identity / "original-preserved.bin").exists()
    moved = path / w.CONTROL / "operations" / request["operation_id"] / "quarantine" / identity
    assert moved.read_bytes() == b"different inode must not be deleted"


def test_crash_intent_prevents_blind_reexecution(store: tuple[TestIO, int, Path]) -> None:
    io, root, path = store
    identity = register(store)
    request = request_for(store, identity)
    operation = path / w.CONTROL / "operations" / request["operation_id"]
    operation.mkdir()
    (operation / "intent.json").write_bytes(
        w.canonical(dict(request_sha256=w.digest(request), expected_bytes=10))
    )
    result = w.cleanup(io, root, request, False)
    assert result["state"] == "UNKNOWN" and result["audit_recorded"]
    assert (path / w.SPOOL / identity / "payload.bin").exists()


@pytest.mark.parametrize(
    "case", ["unregistered", "extra_leaf", "hardlink", "hash_bound", "partial_inventory"]
)
def test_unknown_disposable_or_incomplete_inventory_not_eligible(
    store: tuple[TestIO, int, Path], monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    io, root, path = store
    identity = register(store)
    if case == "unregistered":
        (path / w.CONTROL / "registrations" / (identity + ".json")).unlink()
    elif case == "extra_leaf":
        (path / w.SPOOL / identity / "unexpected.bin").write_bytes(b"keep")
    elif case == "hardlink":
        os.link(path / w.SPOOL / identity / "payload.bin", path / "external-link.bin")
    elif case == "hash_bound":
        monkeypatch.setattr(w, "MAX_HASH_BYTES", 1)
    else:
        monkeypatch.setattr(w, "MAX_NODES", 1)
    s = w.snapshot(io, root, False)
    assert not any(a["deletion_status"] == "ELIGIBLE" for a in s["artifacts"])
    if case == "partial_inventory":
        assert not s["coverage_complete"]


def test_protected_roots_are_not_traversed_and_public_payload_has_no_paths(
    store: tuple[TestIO, int, Path],
) -> None:
    io, root, path = store
    protected = path / "source-oa"
    protected.mkdir()
    (protected / "secret-file").write_bytes(b"private data")
    s = w.snapshot(io, root, False)
    raw = json.dumps(s)
    assert str(path) not in raw and "secret-file" not in raw and "private data" not in raw
    assert all(a["deletion_status"] != "ELIGIBLE" for a in s["artifacts"])


def test_inventory_symlink_escape_and_component_traversal_denied(
    store: tuple[TestIO, int, Path],
) -> None:
    io, root, path = store
    for component in ("..", "/tmp", "a/b", "\x00"):
        with pytest.raises(ValueError):
            io.open(root, component)
    outside = path / "protected-outside"
    outside.mkdir()
    try:
        (path / "jobs/escape").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not permit symlink fixture")
    s = w.snapshot(io, root, False)
    assert not s["coverage_complete"] and s["group_coverage"]["legacy"] == "PARTIAL"


def test_worker_rejects_malformed_and_artifact_substitution(
    store: tuple[TestIO, int, Path],
) -> None:
    io, root, _ = store
    identity = register(store)
    request = request_for(store, identity)
    for changed in (
        {**request, "path": "/tmp"},
        {**request, "dry_run": 1},
        {**request, "operation_id": "../"},
        {**request, "selected_artifact_ids": ["sa-" + "f" * 64]},
    ):
        with pytest.raises(ValueError):
            w.cleanup(io, root, changed, False)


def test_historical_groups_over_64_preserve_all_roots_and_plan_identity(
    store: tuple[TestIO, int, Path],
) -> None:
    from cadence_mcp_bridge.storage import StorageSnapshot, snapshot_digest

    io, root, path = store
    for _ in range(70):
        job = path / "jobs" / str(uuid4())
        job.mkdir()
        (job / "status.json").write_bytes(w.canonical({"state": "succeeded"}))
        (job / "output.bin").write_bytes(b"keep")
    for group in ("native-mcp-v1-jobs", "ade-pvt-qual-v1-jobs", "bias-headroom-v1-jobs"):
        job = path / group / str(uuid4())
        job.mkdir(parents=True)
        (job / "request.json").write_bytes(w.canonical({"analysis": "ac"}))
    job = path / "sim-mcp-v2-jobs" / str(uuid4())
    job.mkdir()
    (job / "request.json").write_bytes(w.canonical({"analysis": "dc"}))
    disposable = register(store)
    s = w.snapshot(io, root, False)
    assert s["coverage_complete"] and set(s["group_coverage"].values()) == {"SCANNED"}
    assert len(s["artifacts"]) < 20 and sum(a["job_count"] for a in s["artifacts"]) == 74
    assert s["snapshot_id"] == snapshot_digest(StorageSnapshot.model_validate(s))
    for group in ("legacy", "native", "diagnostic", "pvt", "headroom"):
        items = [a for a in s["artifacts"] if a["storage_group_id"] == group]
        assert items and all(a["deletion_status"] == "PROTECTED_OR_UNKNOWN" for a in items)
        assert all(a["job_id"] is None for a in items)
    expected = sum(
        p.stat().st_size for g in w.GROUPS for p in (path / g[1]).rglob("*") if p.is_file()
    )
    assert sum(a["size_bytes"] for a in s["artifacts"]) == expected
    # A hidden member change invalidates a plan for an unrelated disposable leaf.
    request = request_for(store, disposable)
    next((path / "jobs").iterdir()).joinpath("output.bin").write_bytes(b"changed")
    with pytest.raises(ValueError, match="stale"):
        w.cleanup(io, root, request, False)


def test_grouped_inventory_budget_exhaustion_stays_partial(
    store: tuple[TestIO, int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    io, root, path = store
    for _ in range(5):
        job = path / "jobs" / str(uuid4())
        job.mkdir()
        (job / "status.json").write_bytes(w.canonical({"state": "succeeded"}))
    monkeypatch.setattr(w, "MAX_NODES", 4)
    s = w.snapshot(io, root, False)
    assert not s["coverage_complete"] and s["group_coverage"]["legacy"] == "PARTIAL"
    assert len(s["artifacts"]) <= 64


@pytest.mark.parametrize("group", [g[1] for g in w.GROUPS if g[0] != "disposable"])
def test_orphan_active_marker_in_every_historical_group_blocks_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, group: str
) -> None:
    process = SimpleNamespace(returncode=0, communicate=lambda: (b"python\n", b""))
    monkeypatch.setattr(w.subprocess, "Popen", lambda *args, **kwargs: process)
    assert not w.active_eda(str(tmp_path))
    marker = tmp_path / group / "active"
    marker.parent.mkdir()
    marker.write_bytes(b"unresolved queued operation")
    assert w.active_eda(str(tmp_path))
