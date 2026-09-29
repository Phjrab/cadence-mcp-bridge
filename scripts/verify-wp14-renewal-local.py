"""Operator-only local readiness check; not collection or activation authority.

No collector/deployer import, network, artifact write, or identity persistence.
Actual invocation requires separate approval. Tests replace private providers only
in isolated fixtures; there is no production fixture switch or path argument.
"""

from __future__ import annotations

import contextlib
import ctypes
import getpass
import hashlib
import json
import msvcrt
import os
import queue
import re
import stat
import subprocess
import sys
import threading
import time
import winreg
from collections.abc import Iterator
from ctypes import wintypes
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, cast

ROOT = Path(__file__).absolute().parents[1]
MAX_SECONDS = 10
REAP_RESERVE_SECONDS = 0.75
MAX_OUTPUT = 512
MAX_CLAIM = 4096
MAX_AUTHORIZATION = 16384
MAX_PUBLIC = 131072
REQUEST = "docs/approvals/WP14_RENEWAL_SINGLE_USE_ACTIVATION_REQUEST_V1.md"
CONTRACT = "docs/approvals/WP14_REMOTE_EVIDENCE_RENEWAL_COLLECTION_REQUEST_V1.md"
PACKAGE = (
    "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_APPROVAL_PACKAGE_V2.json"
)
DEPLOYMENT_PACKAGE = (
    "docs/approvals/WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V2.json"
)
COLLECTOR = "scripts/collect-wp14-renewed-remote-preimages.py"
OLD_COLLECTOR = "scripts/collect-wp14-remote-preimages.py"
DEPLOYER = "scripts/deploy-wp14-narrow.ps1"
RECOVERY_DEPLOYER = "scripts/deploy-wp14-recovery.ps1"
PLAN = "docs/WP14_FAIL_CLOSED_EVIDENCE_RENEWAL_PLAN_V1.md"
V1_EVIDENCE = "docs/evidence/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_V1.json"
SINGLE_USE_PACKAGE = (
    "docs/approvals/"
    "WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_SINGLE_USE_APPROVAL_PACKAGE_V2.json"
)
DEPLOYMENT_AUTHORIZATION = "docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json"
DEPLOYMENT_AUTHORIZATION_HASH = "095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5"
COLLECTION_AUTHORIZATION_HASH = "631d6dff580edb449cac6b4d342930428bd49bc7fd3337053c9932737a581a20"
COLLECTION_CLAIM = "attempt-1906357b1ef5ba98a3d28241896fc59d0a4ff8053b64eac9f5d45f9a9bde0fcb.json"
DEPLOYMENT_CLAIM = "attempt-7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87.json"
DEPLOYMENT_ID = "4f06b6ca-3377-48ae-a643-aefc3fb90dbc"
DEPLOYMENT_CONSUMED_AT = "2026-09-17T08:20:37.8800486+00:00"
ABSENT_REPOSITORY = (
    "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_AUTHORIZATION_V1.json",
    "docs/approvals/WP14_NARROW_RECOVERY_AUTHORIZATION_V1.json",
    "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_RENEWAL_AUTHORIZATION_V1.json",
    "docs/evidence/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_V2.json",
)
PUBLIC_HASHES = {
    REQUEST: "9cc668d58448d8c3965751fb1bd25b3acf9f807b8fa1dc2e27547513888be04d",
    CONTRACT: "747ec5d73372f7fc8149f773638a0be106d12698fa4a1b7a45306c49a2374f4a",
    PACKAGE: "7b8d4d623a95e67a6d39e0391bcf5b9869c58dedbf02b0dd638c070853048223",
    DEPLOYMENT_PACKAGE: "96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431",
    COLLECTOR: "d814d0da7ffc3890274ea24f1b9fc946bf861ec617860c6560cab320f08a3d89",
    OLD_COLLECTOR: "b0bbcd9823e561805c1979b9e1eca3b79f96a4d0126e9c8aa32fe1db0427cc7c",
    DEPLOYER: "3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc",
    RECOVERY_DEPLOYER: "e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374",
    PLAN: "305e8a4eed2cbabb4160ebe65456b7f0ae694eb02d4a07d800d4cfc12029a432",
    V1_EVIDENCE: "0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7",
    SINGLE_USE_PACKAGE: "9b1ed3e2fc4a9ba5c05e5475bca51949a6eba0cbdcbbd47d3c54f549d576bd0f",
}
ERRORS = frozenset(
    {
        "ARGUMENTS_REJECTED",
        "REPOSITORY_INVALID",
        "IDENTITY_INVALID",
        "LINEAGE_INVALID",
        "PATH_INVALID",
        "LOCK_UNAVAILABLE",
        "COLLISION",
        "CHANGED",
        "TIMEOUT",
        "OUTPUT_LIMIT",
        "WORKER_FAILED",
        "INTERNAL_ERROR",
    }
)
SUCCESS = "LOCAL_PREFLIGHT_READY"


class CheckError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code if code in ERRORS else "INTERNAL_ERROR"
        super().__init__(self.code)


def _envelope(code: str) -> bytes:
    if code != SUCCESS and code not in ERRORS:
        code = "INTERNAL_ERROR"
    return (
        json.dumps({"success": code == SUCCESS, "code": code}, separators=(",", ":")) + "\n"
    ).encode("ascii")


def _normalized(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _no_reparse(path: Path) -> None:
    for candidate in (path, *path.parents):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        if metadata.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise CheckError("PATH_INVALID")


class _FileInfo(ctypes.Structure):
    _fields_ = [
        ("attributes", wintypes.DWORD),
        ("created", wintypes.FILETIME),
        ("accessed", wintypes.FILETIME),
        ("written", wintypes.FILETIME),
        ("volume", wintypes.DWORD),
        ("size_high", wintypes.DWORD),
        ("size_low", wintypes.DWORD),
        ("links", wintypes.DWORD),
        ("index_high", wintypes.DWORD),
        ("index_low", wintypes.DWORD),
    ]


def _open_existing(path: Path, *, lock: bool = False) -> BinaryIO:
    """OPEN_EXISTING only; deny write/delete sharing and reject redirected handles."""
    _no_reparse(path)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    info_call = kernel.GetFileInformationByHandle
    info_call.argtypes = [wintypes.HANDLE, ctypes.POINTER(_FileInfo)]
    final_path = kernel.GetFinalPathNameByHandleW
    final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    handle = create(
        str(path), 0xC0000000 if lock else 0x80000000, 0 if lock else 1, None, 3, 0x00200000, None
    )
    code = "LOCK_UNAVAILABLE" if lock else "PATH_INVALID"
    if handle == ctypes.c_void_p(-1).value:
        raise CheckError(code)
    try:
        info = _FileInfo()
        buffer = ctypes.create_unicode_buffer(32768)
        length = final_path(handle, buffer, len(buffer), 0)
        if not info_call(handle, ctypes.byref(info)) or not 0 < length < len(buffer):
            raise CheckError(code)
        if info.attributes & (stat.FILE_ATTRIBUTE_REPARSE_POINT | stat.FILE_ATTRIBUTE_DIRECTORY):
            raise CheckError(code)
        if info.links != 1 or os.path.normcase(buffer.value.removeprefix("\\\\?\\")) != (
            os.path.normcase(os.path.abspath(path))
        ):
            raise CheckError(code)
        fd = msvcrt.open_osfhandle(int(handle), (os.O_RDWR if lock else os.O_RDONLY) | os.O_BINARY)
        handle = None
        return os.fdopen(fd, "r+b" if lock else "rb", buffering=0)
    finally:
        if handle is not None:
            close(handle)


def _read(path: Path, limit: int) -> bytes:
    with _open_existing(path) as stream:
        raw = stream.read(limit + 1)
    if not raw or len(raw) > limit:
        raise CheckError("LINEAGE_INVALID")
    return raw


def _json(raw: bytes) -> dict[str, object]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        seen: set[str] = set()
        for key, value in items:
            if key.lower() in seen:
                raise CheckError("LINEAGE_INVALID")
            seen.add(key.lower())
            result[key] = value
        return result

    value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs)
    if type(value) is not dict:
        raise CheckError("LINEAGE_INVALID")
    return value


def _absent(path: Path) -> None:
    _no_reparse(path)
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise CheckError("COLLISION")


def _private_roots() -> tuple[Path, Path]:
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 0x001C, None, 0, buffer) != 0:
        raise CheckError("PATH_INVALID")
    if not buffer.value:
        raise CheckError("PATH_INVALID")
    root = Path(buffer.value) / "CadenceMcpBridge"
    roots = root / "wp14-narrow", root / "wp14-preimage-evidence"
    for path in roots:
        _no_reparse(path)
        if not stat.S_ISDIR(path.lstat().st_mode):
            raise CheckError("PATH_INVALID")
    return roots


def _read_identity() -> tuple[str, str, str]:
    """Same digest input as renewal, with an additional native-user consistency gate."""
    buffer = ctypes.create_unicode_buffer(257)
    size = wintypes.DWORD(len(buffer))
    if not ctypes.windll.advapi32.GetUserNameW(buffer, ctypes.byref(size)):
        raise CheckError("IDENTITY_INVALID")
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
        guid, kind = winreg.QueryValueEx(key, "MachineGuid")
    if kind != winreg.REG_SZ or type(guid) is not str:
        raise CheckError("IDENTITY_INVALID")
    return getpass.getuser(), buffer.value, guid


def _binding(identity: tuple[str, str, str]) -> bytes:
    username, native, guid = identity
    if (
        type(username) is not str
        or type(native) is not str
        or type(guid) is not str
        or username != native
        or not 1 <= len(username) <= 256
        or any(ord(char) < 32 or ord(char) == 127 or char == "|" for char in username)
        or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", guid)
    ):
        raise CheckError("IDENTITY_INVALID")
    return hashlib.sha256(f"{username}|{guid}".encode()).digest()


def _claim(raw: bytes, *, deployment: bool) -> None:
    record = _json(raw)
    implementation = "deployer_sha256" if deployment else "collector_sha256"
    keys = {
        "state",
        "authorization_id",
        "authorization_sha256",
        "package_sha256",
        implementation,
        "consumed_at",
    }
    if set(record) != keys or any(type(value) is not str for value in record.values()):
        raise CheckError("LINEAGE_INVALID")
    expected = {
        "state": "consumed_before_transport",
        "authorization_sha256": (
            DEPLOYMENT_AUTHORIZATION_HASH if deployment else COLLECTION_AUTHORIZATION_HASH
        ),
        "package_sha256": PUBLIC_HASHES[DEPLOYMENT_PACKAGE if deployment else PACKAGE],
        implementation: PUBLIC_HASHES[DEPLOYER if deployment else OLD_COLLECTOR],
    }
    if deployment:
        expected.update(authorization_id=DEPLOYMENT_ID, consumed_at=DEPLOYMENT_CONSUMED_AT)
    if any(record[key] != value for key, value in expected.items()):
        raise CheckError("LINEAGE_INVALID")
    identifier = cast(str, record["authorization_id"])
    consumed_at = cast(str, record["consumed_at"])
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", identifier):
        raise CheckError("LINEAGE_INVALID")
    timestamp = datetime.fromisoformat(consumed_at.replace("Z", "+00:00"))
    if (
        timestamp.tzinfo is None
        or timestamp.utcoffset() != timedelta(0)
        or timestamp > datetime.now(UTC)
    ):
        raise CheckError("LINEAGE_INVALID")
    # Derive only in memory; no external expected digest exists before separate approval.
    hashlib.sha256(raw).digest()


@contextlib.contextmanager
def _held_lock(path: Path) -> Iterator[None]:
    with _open_existing(path, lock=True) as stream:
        before = stream.read(MAX_CLAIM + 1)
        if len(before) > MAX_CLAIM:
            raise CheckError("LOCK_UNAVAILABLE")
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise CheckError("LOCK_UNAVAILABLE") from exc
        try:
            yield
        finally:
            try:
                stream.seek(0)
                if stream.read(MAX_CLAIM + 1) != before:
                    raise CheckError("CHANGED")
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _check() -> None:
    snapshots: dict[Path, tuple[bytes, int]] = {}

    def remember(path: Path, limit: int) -> bytes:
        raw = _read(path, limit)
        snapshots[path] = raw, limit
        return raw

    for relative, digest in PUBLIC_HASHES.items():
        if _normalized(remember(ROOT / relative, MAX_PUBLIC)) != digest:
            raise CheckError("REPOSITORY_INVALID")
    lineage = _json(remember(ROOT / "remote/config/runner-lineage.json", MAX_AUTHORIZATION))
    if lineage.get("deployment_enabled") is not False:
        raise CheckError("REPOSITORY_INVALID")
    for relative in ABSENT_REPOSITORY:
        _absent(ROOT / relative)
    deployment, collection = _private_roots()
    absences = (deployment / "recovery-v1.json", collection / "collection-renewal-v1.json")
    # Use the two existing namespaces; do not create a third lock or an attempt record.
    with _held_lock(deployment / "operation.lock"), _held_lock(collection / "operation.lock"):
        for path in absences:
            _absent(path)
        first = _binding(_read_identity())
        try:
            raw = remember(ROOT / DEPLOYMENT_AUTHORIZATION, MAX_AUTHORIZATION)
            if _normalized(raw) != DEPLOYMENT_AUTHORIZATION_HASH:
                raise CheckError("LINEAGE_INVALID")
            _claim(remember(collection / COLLECTION_CLAIM, MAX_CLAIM), deployment=False)
            _claim(remember(deployment / DEPLOYMENT_CLAIM, MAX_CLAIM), deployment=True)
            if first != _binding(_read_identity()):
                raise CheckError("IDENTITY_INVALID")
        finally:
            for path, (before, limit) in snapshots.items():
                if _read(path, limit) != before:
                    raise CheckError("CHANGED")
            for path in (*absences, *(ROOT / value for value in ABSENT_REPOSITORY)):
                _absent(path)


def _worker() -> int:
    code = SUCCESS
    try:
        _check()
    except CheckError as exc:
        code = exc.code
    except Exception:
        code = "INTERNAL_ERROR"
    sys.stdout.buffer.write(_envelope(code))
    sys.stdout.buffer.flush()
    return 0 if code == SUCCESS else 1


def _supervise() -> str:
    """One fixed local Python child; bound all output and kill on the shared deadline."""
    deadline = time.monotonic() + MAX_SECONDS
    operation_deadline = deadline - REAP_RESERVE_SECONDS
    script = Path(__file__).absolute()
    _no_reparse(script)
    # Neither a caller path nor a user-provided program is accepted.
    bootstrap = f"import runpy; runpy.run_path({str(script)!r}, run_name='__wp14_local_worker__')"
    process = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", bootstrap],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    events: queue.Queue[tuple[str, bytes | None]] = queue.Queue(maxsize=4)
    stop = threading.Event()

    def pump(name: str, stream: BinaryIO) -> None:
        try:
            while not stop.is_set():
                chunk = os.read(stream.fileno(), MAX_OUTPUT + 1)
                while not stop.is_set():
                    try:
                        events.put((name, chunk or None), timeout=0.01)
                        break
                    except queue.Full:
                        continue
                if not chunk:
                    return
        except Exception:
            # Never send an exception message or private path to the parent output.
            stop.set()

    threads = []
    output = bytearray()
    ended: set[str] = set()
    total = 0
    try:
        for name, stream in (("out", process.stdout), ("err", process.stderr)):
            assert stream is not None
            thread = threading.Thread(target=pump, args=(name, stream), daemon=True)
            threads.append(thread)
            thread.start()
        while len(ended) < 2 or process.poll() is None:
            remaining = operation_deadline - time.monotonic()
            if remaining <= 0:
                return "TIMEOUT"
            if stop.is_set():
                return "WORKER_FAILED"
            try:
                name, chunk = events.get(timeout=min(0.01, remaining))
            except queue.Empty:
                continue
            if chunk is None:
                ended.add(name)
                continue
            total += len(chunk)
            if total > MAX_OUTPUT:
                return "OUTPUT_LIMIT"
            if name == "err":
                return "WORKER_FAILED"
            output.extend(chunk)
        if time.monotonic() >= operation_deadline:
            return "TIMEOUT"
        for code in (SUCCESS, *sorted(ERRORS)):
            if bytes(output) == _envelope(code) and process.returncode == (
                0 if code == SUCCESS else 1
            ):
                return code
        return "WORKER_FAILED"
    finally:
        stop.set()
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=min(0.5, max(0.001, deadline - time.monotonic())))
        finally:
            for thread in threads:
                thread.join(timeout=min(0.1, max(0, deadline - time.monotonic())))
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


def main() -> int:
    code = "INTERNAL_ERROR"
    try:
        code = "ARGUMENTS_REJECTED" if len(sys.argv) != 1 else _supervise()
    except CheckError as exc:
        code = exc.code
    except Exception:
        pass
    # Never forward child bytes or exception text, even after a partial failure.
    sys.stdout.buffer.write(_envelope(code))
    sys.stdout.buffer.flush()
    return 0 if code == SUCCESS else 1


if __name__ == "__wp14_local_worker__":
    raise SystemExit(_worker())
if __name__ == "__main__":
    raise SystemExit(main())
