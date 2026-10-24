"""Bounded inventories/storage; optional disposable CI mount, never VM/EDA."""

import errno
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_binding_observation_worker import controlled_inventory, root, selected

from cadence_mcp_bridge import _binding_observation as observer

__all__ = ["controlled_inventory", "root", "selected"]


@pytest.mark.parametrize("stop", ["bound", "deadline", "cancel", "visibility"])
def test_streaming_process_inventory_stops_and_closes_before_materialization(
    selected, monkeypatch, stop,
):
    worker, _, _ = selected
    read, closed = [], []

    def names(path):
        assert path == "/proc"
        try:
            while True:
                read.append(len(read))
                yield "not-a-pid" if stop != "visibility" else "98765"
        finally:
            closed.append(True)

    monkeypatch.setattr(worker, "_stage_directory_entries", names)
    monkeypatch.setattr(observer.os, "listdir", lambda *a: pytest.fail("unbounded listdir"))
    monkeypatch.setattr(observer.os, "getpid", lambda: 1)
    monkeypatch.setattr(observer.os, "getuid", lambda: 1000, raising=False)
    worker._deadline = 5 if stop == "deadline" else None
    monkeypatch.setattr(observer.os, "times", lambda: (0, 0, 0, 0, len(read)))
    worker._cancelled = lambda: stop == "cancel" and len(read) >= 3
    if stop == "visibility":
        def denied(path):
            raise OSError(errno.EACCES, "synthetic process visibility failure")

        monkeypatch.setattr(observer.os, "stat", denied)
    expected = OSError if stop == "visibility" else ValueError
    with pytest.raises(expected):
        worker._check_conflicting_processes()
    assert len(read) == {"bound": 4097, "deadline": 5, "cancel": 3, "visibility": 1}[stop]
    assert closed == [True]


@pytest.mark.parametrize("cleanup", [False, True])
@pytest.mark.parametrize("stop", [
    "bound", "scan-deadline", "enumeration-error", "uid-error", "identity-error",
    "close-error", "early-active", "empty",
])
def test_group_inventory_preserves_helper_semantics_bounds_and_restores_module_os(
    selected, monkeypatch, cleanup, stop,
):
    worker, _, _ = selected
    original_os, real_listdir = worker._process_module.os, observer.os.listdir
    module_os = SimpleNamespace(**original_os.__dict__)
    module_os.getuid = lambda: 12345
    monkeypatch.setattr(worker._process_module, "os", module_os)
    process = SimpleNamespace(pid=45678)
    identity = ("S", process.pid, process.pid, "retained-start")
    monkeypatch.setattr(worker.processes, "process_identity", lambda pid: identity)

    def uid(pid):
        if stop == "uid-error":
            raise OSError(errno.EACCES, "synthetic uid inspection failure")
        return (12345,) * 4

    monkeypatch.setattr(worker.processes, "process_uid", uid)
    if stop == "identity-error":
        monkeypatch.setattr(worker.processes, "process_identity",
                            lambda pid: ("S", process.pid + 1, process.pid, "wrong-start"))
    now, consumed, closed = [0], [], []
    monkeypatch.setattr(observer.os, "times", lambda: (0, 0, 0, 0, now[0]))
    monkeypatch.setattr(observer, "OUTER_SECONDS", 3)
    # Cleanup must still inspect a group after both observation stop conditions.
    worker._deadline = -1 if cleanup else 100
    worker._cancelled = lambda: cleanup

    def names(path):
        assert path == "/proc"
        assert worker._process_module.os is not module_os
        assert observer.os.listdir is real_listdir
        try:
            if stop == "empty":
                return
            while True:
                consumed.append(True)
                if stop == "scan-deadline":
                    now[0] += 1
                if stop == "enumeration-error":
                    raise OSError(errno.EACCES, "synthetic inventory failure")
                yield str(process.pid) if stop in ("early-active", "uid-error", "close-error") \
                    else "not-a-pid"
        finally:
            closed.append(True)
            if stop == "close-error":
                raise OSError(errno.EIO, "synthetic inventory close failure")

    monkeypatch.setattr(worker, "_stage_directory_entries", names)
    try:
        if stop in ("early-active", "empty"):
            assert worker._group_active(process, identity, cleanup=cleanup) is (
                stop == "early-active")
        else:
            expected = OSError if stop in (
                "enumeration-error", "uid-error", "close-error",
            ) else ValueError
            with pytest.raises(expected):
                worker._group_active(process, identity, cleanup=cleanup)
    finally:
        assert worker._process_module.os is module_os
        assert observer.os.listdir is real_listdir
    assert len(consumed) == {
        "bound": 4097, "scan-deadline": 3, "enumeration-error": 1, "uid-error": 1,
        "close-error": 1, "identity-error": 0, "early-active": 1, "empty": 0,
    }[stop]
    assert closed == ([] if stop == "identity-error" else [True])


@pytest.mark.parametrize("stop", ["cancel", "cancel-midscan", "outer-deadline", "empty-late"])
def test_normal_group_inventory_checks_stop_conditions_before_and_after_helper(
    selected, monkeypatch, stop,
):
    worker, _, _ = selected
    original_os = worker._process_module.os
    inspected, consumed, closed, now = [], [], [], [0]
    monkeypatch.setattr(observer.os, "times", lambda: (0, 0, 0, 0, now[0]))
    worker._deadline = 2
    worker._cancelled = lambda: stop == "cancel" or (
        stop == "cancel-midscan" and len(consumed) >= 3)
    if stop == "outer-deadline":
        now[0] = 2

    def names(path):
        try:
            while stop == "cancel-midscan":
                consumed.append(True)
                yield "not-a-pid"
        finally:
            closed.append(True)

    def helper(process, identity):
        inspected.append(True)
        assert list(worker._process_module.os.listdir("/proc")) == []
        now[0] = 2
        return False

    monkeypatch.setattr(worker, "_stage_directory_entries", names)
    monkeypatch.setattr(worker.processes, "group_active", helper)
    with pytest.raises(ValueError, match="cancelled|process_inventory_deadline"):
        worker._group_active(SimpleNamespace(pid=1), ("S", 1, 1, "start"))
    assert inspected == ([True] if stop in ("empty-late", "cancel-midscan") else [])
    assert closed == ([True] if stop in ("empty-late", "cancel-midscan") else [])
    assert len(consumed) == (3 if stop == "cancel-midscan" else 0)
    assert worker._process_module.os is original_os


@pytest.mark.skipif(os.name != "posix", reason="actual ordinary-user owned child and cleanup")
def test_owned_child_cleanup_uses_fresh_bounded_group_scans_after_cancel_and_deadline(
    selected, controlled_inventory, monkeypatch,
):
    worker, scan, _ = selected
    if os.getuid() == 0:
        pytest.skip("ordinary-user POSIX requirement")
    executable = Path(worker.profile["tools"]["ocean"]["path"])
    executable.write_text(
        f"#!{sys.executable}\nimport os,time\nos.close(1)\nos.close(2)\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    worker.profile["tools"]["ocean"]["sha256"] = observer.digest(executable.read_bytes())
    monkeypatch.setattr(observer, "PROCESS_SECONDS", 5)
    bound_group, calls = worker._group_active, []
    original_module_os = worker._process_module.os

    def checked_group(process, identity, cleanup=False):
        calls.append(cleanup)
        if not cleanup:
            worker._deadline = -1
            worker._cancelled = lambda: True
        try:
            return bound_group(process, identity, cleanup=cleanup)
        finally:
            assert worker._process_module.os is original_module_os

    monkeypatch.setattr(worker, "_group_active", checked_group)
    before = worker._ledger()
    with worker.accounting.ReservationSession(worker.root) as session:
        stage, _, _ = worker._stage(scan, session)
        with pytest.raises(ValueError, match="binding_observation_cancelled"):
            worker._program(stage, session, scan)
        assert calls[0] is False and True in calls
        assert worker._process_receipt["new_eda_starts"] == 1
        assert worker._process_receipt["cleanup_complete"] is True
        assert worker._process_receipt["returncode"] < 0
        session.check()
        with pytest.raises(ValueError, match="process_attempt_spent"):
            worker._program(stage, session, scan)
    assert worker._ledger() == before


def info(value, **changes):
    fields = {key: getattr(value, key) for key in (
        "st_dev", "st_ino", "st_uid", "st_gid", "st_mode",
    )}
    return SimpleNamespace(**{**fields, **changes})


@pytest.fixture
def storage_case(selected, monkeypatch):
    worker, _, _ = selected
    arena = Path(worker.root) / "binding-observations"
    arena.mkdir(mode=0o700)
    actual = arena.stat()
    fake = info(actual, st_dev=actual.st_dev + 1, st_mode=stat.S_IFDIR | 0o700)
    real_stat, real_fstat, real_open = observer.os.lstat, observer.os.fstat, observer.os.open
    surrogate = arena.parent / "synthetic-directory-fd"
    surrogate.write_bytes(b"")
    descriptors = []
    monkeypatch.setattr(worker.copying, "owned_parent", lambda *a: None)
    monkeypatch.setattr(worker, "_mount_type", lambda *a: "ext2")
    monkeypatch.setattr(observer.os, "O_DIRECTORY", getattr(os, "O_DIRECTORY", 0), raising=False)
    monkeypatch.setattr(observer.os, "O_NOFOLLOW", getattr(os, "O_NOFOLLOW", 0), raising=False)
    monkeypatch.setattr(observer.os, "lstat",
                        lambda p: fake if Path(p) == arena else real_stat(p))

    def opened(path, flags):
        assert Path(path) == arena
        fd = real_open(surrogate, flags & ~getattr(os, "O_DIRECTORY", 0))
        descriptors.append(fd)
        return fd

    monkeypatch.setattr(observer.os, "open", opened)

    def held(fd):
        return fake if fd in descriptors else real_fstat(fd)

    monkeypatch.setattr(observer.os, "fstat", held)
    fs = SimpleNamespace(f_blocks=observer.STAGE_BYTES, f_frsize=1, f_files=128)
    monkeypatch.setattr(observer.os, "fstatvfs", lambda fd: fs, raising=False)
    return worker, arena, fake, fs


@pytest.mark.parametrize("case", ["bytes", "inodes", "zero", "same-device", "mode"])
def test_storage_rejects_unbounded_or_unseparated_arena(storage_case, case):
    worker, _, fake, fs = storage_case
    if case == "bytes":
        fs.f_blocks += 1
    elif case == "inodes":
        fs.f_files = observer.STAGE_INODES + 1
    elif case == "zero":
        fs.f_blocks = 0
    elif case == "same-device":
        fake.st_dev -= 1
    else:
        fake.st_mode |= 0o020
    with pytest.raises(ValueError, match="bounded_filesystem_required"):
        worker._bounded_storage()


def test_storage_guard_retains_fixed_capacity_and_mount_identity(storage_case):
    worker, _, fake, fs = storage_case
    witness = worker._bounded_storage()
    assert witness == ((fake.st_dev, fake.st_ino, fake.st_uid, fake.st_gid, fake.st_mode),
                       "ext2", observer.STAGE_BYTES, 128)
    fs.f_blocks -= 4096
    assert worker._bounded_storage() != witness


@pytest.mark.parametrize("kind", [
    "ext2", "ext3", "ext4", "tmpfs", "fuse.test", "duplicate", "oversize",
])
def test_kernel_mount_inventory_is_bounded_and_rejects_volatile_or_user_filesystems(
    selected, tmp_path, monkeypatch, kind,
):
    worker, _, _ = selected
    location = worker.root + "/binding-observations"
    line = "41 40 7:1 / " + location + " rw - " + kind + " /dev/loop0 rw\n"
    if kind == "duplicate":
        line = line.replace("duplicate", "ext2") * 2
    elif kind == "oversize":
        line = "x" * 65537 + "\n"
    metadata = tmp_path / "synthetic-mountinfo"
    metadata.write_text(line, encoding="utf-8")
    real_open, real_fstat = observer.os.open, observer.os.fstat
    owned = []

    def opened(path, flags):
        assert path == "/proc/self/mountinfo"
        fd = real_open(metadata, flags)
        owned.append(fd)
        return fd

    def kernel_owner(fd):
        real_fstat(fd)
        return SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o444)

    monkeypatch.setattr(observer.os, "open", opened)
    monkeypatch.setattr(observer.os, "fstat", kernel_owner)
    monkeypatch.setattr(observer.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(observer.os, "O_NOFOLLOW", getattr(os, "O_NOFOLLOW", 0), raising=False)
    if kind in ("ext2", "ext3", "ext4"):
        assert worker._mount_type(location) == kind
    else:
        with pytest.raises(ValueError, match="persistent_bounded_filesystem_required|mount_bound"):
            worker._mount_type(location)
    for fd in owned:
        with pytest.raises(OSError):
            real_fstat(fd)


@pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("CADENCE_TEST_BOUNDED_FS") != "1",
    reason="explicit disposable hosted-CI mount setup only; no operator VM provisioning",
)
def test_actual_kernel_capacity_includes_large_and_unlinked_open_files(selected):
    worker, _, _ = selected
    assert os.getuid() != 0
    arena = Path(worker.root) / "binding-observations"
    arena.mkdir(mode=0o700)
    image = Path(worker.root) / "synthetic-eight-mib.ext2"
    with image.open("xb") as stream:
        stream.write(b"\0" * observer.STAGE_BYTES)
        stream.flush()
        os.fsync(stream.fileno())
    assert image.stat().st_blocks * 512 >= image.stat().st_size
    subprocess.run(["/usr/sbin/mke2fs", "-F", "-q", "-t", "ext2", "-O", "none",
                    "-b", "1024", "-N", "128", "-m", "0", str(image)],
                   check=True, timeout=15)
    mounted = False
    try:
        subprocess.run(["sudo", "-n", "/bin/mount", "-t", "ext2", "-o",
                        "loop,nodev,nosuid,noexec", str(image), str(arena)], check=True, timeout=15)
        mounted = True
        subprocess.run(["sudo", "-n", "/bin/chown", str(os.getuid()) + ":" + str(os.getgid()),
                        str(arena)], check=True, timeout=10)
        subprocess.run(["sudo", "-n", "/bin/chmod", "700", str(arena)], check=True, timeout=10)
        witness = worker._bounded_storage()
        assert witness[2] <= observer.STAGE_BYTES and witness[3] <= observer.STAGE_INODES
        initial_free = os.statvfs(arena).f_bfree
        # Keep the file open after unlink: namespace scans cannot count it, but
        # the kernel must charge it and reject bytes beyond the admitted volume.
        selected_file = arena / "unlinked-open"
        fd = os.open(selected_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        selected_file.unlink()
        written = 0
        try:
            with pytest.raises(OSError) as full:
                # Bound even a broken fixture: do not fill the hosted disk
                # if the expected filesystem limit has failed to apply.
                while written <= observer.STAGE_BYTES:
                    added = os.write(fd, b"x" * 65536)
                    assert added > 0
                    written += added
            assert full.value.errno == errno.ENOSPC
            assert 0 < written <= observer.STAGE_BYTES
            # A 64KiB write can fail while smaller fragments remain free.
            # Require charged blocks and kernel rejection, not zero free.
            pressure_free = os.statvfs(arena).f_bfree
            assert pressure_free < initial_free
            assert worker._bounded_storage() == witness
        finally:
            os.close(fd)
        assert os.statvfs(arena).f_bfree > pressure_free
        assert image.stat().st_size == observer.STAGE_BYTES
    finally:
        if mounted:
            subprocess.run(["sudo", "-n", "/bin/umount", str(arena)], check=True, timeout=15)
