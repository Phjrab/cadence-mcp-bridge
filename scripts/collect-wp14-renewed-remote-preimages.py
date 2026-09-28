from __future__ import annotations

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
from ctypes import wintypes
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    PROJECT_ROOT
    / "docs/approvals/WP14_REMOTE_EVIDENCE_RENEWAL_COLLECTION_REQUEST_V1.md"
)
PLAN = PROJECT_ROOT / "docs/WP14_FAIL_CLOSED_EVIDENCE_RENEWAL_PLAN_V1.md"
PACKAGE = (
    PROJECT_ROOT
    / "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_APPROVAL_PACKAGE_V2.json"
)
SINGLE_USE_PACKAGE = (
    PROJECT_ROOT
    / "docs/approvals"
    / "WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_SINGLE_USE_APPROVAL_PACKAGE_V2.json"
)
DEPLOYMENT_PACKAGE = (
    PROJECT_ROOT
    / "docs/approvals"
    / "WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V2.json"
)
OLD_COLLECTOR = PROJECT_ROOT / "scripts/collect-wp14-remote-preimages.py"
DEPLOYER = PROJECT_ROOT / "scripts/deploy-wp14-narrow.ps1"
RECOVERY_DEPLOYER = PROJECT_ROOT / "scripts/deploy-wp14-recovery.ps1"
LINEAGE = PROJECT_ROOT / "remote/config/runner-lineage.json"
PREDECESSOR_EVIDENCE = (
    PROJECT_ROOT / "docs/evidence/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_V1.json"
)
LEGACY_COLLECTION_AUTHORIZATION = (
    PROJECT_ROOT
    / "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_AUTHORIZATION_V1.json"
)
DEPLOYMENT_AUTHORIZATION = (
    PROJECT_ROOT / "docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json"
)
RECOVERY_AUTHORIZATION = (
    PROJECT_ROOT / "docs/approvals/WP14_NARROW_RECOVERY_AUTHORIZATION_V1.json"
)
RENEWAL_AUTHORIZATION = (
    PROJECT_ROOT
    / "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_RENEWAL_AUTHORIZATION_V1.json"
)
RENEWAL_EVIDENCE = (
    PROJECT_ROOT / "docs/evidence/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_V2.json"
)

CONTRACT_HASH = "747ec5d73372f7fc8149f773638a0be106d12698fa4a1b7a45306c49a2374f4a"
PLAN_HASH = "305e8a4eed2cbabb4160ebe65456b7f0ae694eb02d4a07d800d4cfc12029a432"
PACKAGE_HASH = "7b8d4d623a95e67a6d39e0391bcf5b9869c58dedbf02b0dd638c070853048223"
SINGLE_USE_PACKAGE_HASH = "9b1ed3e2fc4a9ba5c05e5475bca51949a6eba0cbdcbbd47d3c54f549d576bd0f"
DEPLOYMENT_PACKAGE_HASH = "96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431"
OLD_COLLECTOR_HASH = "b0bbcd9823e561805c1979b9e1eca3b79f96a4d0126e9c8aa32fe1db0427cc7c"
DEPLOYER_HASH = "3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc"
RECOVERY_DEPLOYER_HASH = "e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374"
PREDECESSOR_EVIDENCE_HASH = (
    "0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7"
)
LEGACY_COLLECTION_AUTHORIZATION_HASH = (
    "631d6dff580edb449cac6b4d342930428bd49bc7fd3337053c9932737a581a20"
)
DEPLOYMENT_AUTHORIZATION_HASH = (
    "095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5"
)
LEGACY_COLLECTION_CLAIM_NAME = (
    "attempt-1906357b1ef5ba98a3d28241896fc59d0a4ff8053b64eac9f5d45f9a9bde0fcb.json"
)
DEPLOYMENT_CLAIM_NAME = (
    "attempt-7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87.json"
)
RENEWAL_CLAIM_NAME = "collection-renewal-v1.json"
RECOVERY_CLAIM_NAME = "recovery-v1.json"
RENEWAL_GENERATION = "collection-renewal-v1"
SSH_ALIAS = "cadence-vm"
REMOTE_ROOT = "/home/buet/cds_work/.cadence_mcp"
MAX_JSON_BYTES = 32768
MAX_AUTHORIZATION_BYTES = 16384
MAX_CLAIM_BYTES = 4096
MAX_OUTPUT_BYTES = 32768
MAX_WALL_SECONDS = 60

ASSETS = (
    ("remote/bin/cadence-runner", "bin/cadence-runner", "file"),
    ("remote/lib/runner-common.sh", "lib/runner-common.sh", "file"),
    (
        "remote/lib/run-ade-profile-introspection.sh",
        "lib/run-ade-profile-introspection.sh",
        "file_or_absent",
    ),
    (
        "remote/lib/run-wp14-role-discovery.sh",
        "lib/run-wp14-role-discovery.sh",
        "file_or_absent",
    ),
    ("remote/py26/actual_profile_audit.py", "py26/actual_profile_audit.py", "file_or_absent"),
    (
        "remote/py26/ade_profile_introspection.py",
        "py26/ade_profile_introspection.py",
        "file_or_absent",
    ),
    (
        "remote/py26/wp14_role_discovery.py",
        "py26/wp14_role_discovery.py",
        "file_or_absent",
    ),
    (
        "remote/discovery/ade-profile-introspection.il",
        "discovery/ade-profile-introspection.il",
        "file_or_absent",
    ),
    (
        "remote/discovery/wp14-role-discovery.il",
        "discovery/wp14-role-discovery.il",
        "file_or_absent",
    ),
    ("remote/config/runner-lineage.json", "config/runner-lineage.json", "file_or_absent"),
    (
        "remote/profiles/actual-differential-amplifier-tb2-transient/profile.json",
        "profiles/actual-differential-amplifier-tb2-transient/profile.json",
        "file_or_absent",
    ),
)

ERROR_CODES = frozenset(
    {
        "ARGUMENTS_REJECTED",
        "REPOSITORY_BOUNDARY_INVALID",
        "ACTIVATION_MISSING",
        "ACTIVATION_INVALID",
        "ACTIVATION_TIME_INVALID",
        "IDENTITY_BINDING_INVALID",
        "EVIDENCE_COLLISION",
        "LEDGER_INVALID",
        "LOCK_UNAVAILABLE",
        "LINEAGE_INVALID",
        "LINEAGE_CHANGED",
        "ATTEMPT_CONSUMED",
        "CLAIM_WRITE_FAILED",
        "TRANSPORT_LAUNCH_FAILED",
        "TRANSPORT_TIMEOUT",
        "TRANSPORT_OUTPUT_LIMIT",
        "TRANSPORT_STDERR",
        "TRANSPORT_NONZERO",
        "TRANSPORT_UTF8_INVALID",
        "EVIDENCE_INVALID",
        "INTERNAL_ERROR",
    }
)


class CollectorError(RuntimeError):
    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            code = "INTERNAL_ERROR"
        self.code = code
        super().__init__(code)


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("file_attributes", wintypes.DWORD),
        ("creation_time", wintypes.FILETIME),
        ("last_access_time", wintypes.FILETIME),
        ("last_write_time", wintypes.FILETIME),
        ("volume_serial_number", wintypes.DWORD),
        ("file_size_high", wintypes.DWORD),
        ("file_size_low", wintypes.DWORD),
        ("number_of_links", wintypes.DWORD),
        ("file_index_high", wintypes.DWORD),
        ("file_index_low", wintypes.DWORD),
    ]


def normalized_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode()).hexdigest()


def exact_hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _windows_ssh_path() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise CollectorError("TRANSPORT_LAUNCH_FAILED")
    return Path(buffer.value) / "System32/OpenSSH/ssh.exe"


def _ssh_prefix() -> list[str]:
    return [str(_windows_ssh_path())]


def _local_app_data_root() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x001C, None, 0, buffer)
    if result != 0 or not buffer.value:
        raise CollectorError("LEDGER_INVALID")
    return Path(buffer.value)


def _collection_state_root() -> Path:
    return _local_app_data_root() / "CadenceMcpBridge/wp14-preimage-evidence"


def _deployment_state_root() -> Path:
    return _local_app_data_root() / "CadenceMcpBridge/wp14-narrow"


def _executor_binding() -> str:
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
        machine_guid = str(winreg.QueryValueEx(key, "MachineGuid")[0])
    identity = f"{getpass.getuser()}|{machine_guid}"
    return hashlib.sha256(identity.encode()).hexdigest()


def _assert_no_reparse_ancestors(path: Path, code: str) -> None:
    candidate = Path(os.path.abspath(path))
    for current in (candidate, *candidate.parents):
        if not current.exists():
            continue
        try:
            attributes = getattr(os.stat(current, follow_symlinks=False), "st_file_attributes", 0)
        except OSError as exc:
            raise CollectorError(code) from exc
        if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise CollectorError(code)


def _strict_json_bytes(raw: bytes, maximum_bytes: int, code: str) -> dict[str, Any]:
    if not raw or len(raw) > maximum_bytes:
        raise CollectorError(code)

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        lowered: set[str] = set()
        for key, value in items:
            if key.lower() in lowered:
                raise CollectorError(code)
            lowered.add(key.lower())
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CollectorError(code) from exc

    def bounded(item: Any, depth: int = 0) -> None:
        if depth > 8:
            raise CollectorError(code)
        if isinstance(item, dict):
            if len(item) > 64:
                raise CollectorError(code)
            for child in item.values():
                bounded(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 64:
                raise CollectorError(code)
            for child in item:
                bounded(child, depth + 1)

    bounded(value)
    if not isinstance(value, dict):
        raise CollectorError(code)
    return value


def _read_bounded_leaf(path: Path, maximum_bytes: int, code: str) -> bytes:
    _assert_no_reparse_ancestors(path, code)
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise CollectorError(code) from exc
    invalid_size = metadata.st_size <= 0 or metadata.st_size > maximum_bytes
    if not stat.S_ISREG(metadata.st_mode) or invalid_size:
        raise CollectorError(code)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CollectorError(code) from exc


def _strict_json_file(path: Path, maximum_bytes: int, code: str) -> dict[str, Any]:
    return _strict_json_bytes(_read_bounded_leaf(path, maximum_bytes, code), maximum_bytes, code)


def _assert_absent(path: Path, code: str) -> None:
    _assert_no_reparse_ancestors(path, code)
    if path.exists() or path.is_symlink():
        raise CollectorError(code)


def _assert_repository_boundary() -> None:
    fixed_hashes = {
        CONTRACT: CONTRACT_HASH,
        PLAN: PLAN_HASH,
        PACKAGE: PACKAGE_HASH,
        SINGLE_USE_PACKAGE: SINGLE_USE_PACKAGE_HASH,
        DEPLOYMENT_PACKAGE: DEPLOYMENT_PACKAGE_HASH,
        OLD_COLLECTOR: OLD_COLLECTOR_HASH,
        DEPLOYER: DEPLOYER_HASH,
        RECOVERY_DEPLOYER: RECOVERY_DEPLOYER_HASH,
        PREDECESSOR_EVIDENCE: PREDECESSOR_EVIDENCE_HASH,
        DEPLOYMENT_AUTHORIZATION: DEPLOYMENT_AUTHORIZATION_HASH,
    }
    try:
        for path, expected in fixed_hashes.items():
            _read_bounded_leaf(path, 131072, "REPOSITORY_BOUNDARY_INVALID")
            if normalized_hash(path) != expected:
                raise CollectorError("REPOSITORY_BOUNDARY_INVALID")
        package = _strict_json_file(PACKAGE, MAX_JSON_BYTES, "REPOSITORY_BOUNDARY_INVALID")
        expected_assets = [
            {"path": path, "remote_relative_path": remote, "required_presence": required}
            for path, remote, required in ASSETS
        ]
        if package.get("asset_preimage_allowlist") != expected_assets:
            raise CollectorError("REPOSITORY_BOUNDARY_INVALID")
        lineage = _strict_json_file(LINEAGE, 16384, "REPOSITORY_BOUNDARY_INVALID")
        if lineage.get("deployment_enabled") is not False:
            raise CollectorError("REPOSITORY_BOUNDARY_INVALID")
        _assert_absent(LEGACY_COLLECTION_AUTHORIZATION, "REPOSITORY_BOUNDARY_INVALID")
        _assert_absent(RECOVERY_AUTHORIZATION, "REPOSITORY_BOUNDARY_INVALID")
        _assert_absent(RENEWAL_EVIDENCE, "EVIDENCE_COLLISION")
    except CollectorError:
        raise
    except (OSError, UnicodeError) as exc:
        raise CollectorError("REPOSITORY_BOUNDARY_INVALID") from exc


def _parse_activation_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise CollectorError("ACTIVATION_TIME_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise CollectorError("ACTIVATION_TIME_INVALID") from exc


def _parse_lineage_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CollectorError("LINEAGE_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise CollectorError("LINEAGE_INVALID")
    return parsed


def _load_activation() -> tuple[dict[str, Any], datetime]:
    _assert_no_reparse_ancestors(RENEWAL_AUTHORIZATION, "ACTIVATION_INVALID")
    if not RENEWAL_AUTHORIZATION.is_file():
        raise CollectorError("ACTIVATION_MISSING")
    record = _strict_json_file(
        RENEWAL_AUTHORIZATION, MAX_AUTHORIZATION_BYTES, "ACTIVATION_INVALID"
    )
    expected_keys = {
        "schema_version",
        "record_kind",
        "status",
        "renewal_generation",
        "contract_normalized_lf_sha256",
        "package_normalized_lf_sha256",
        "collector_normalized_lf_sha256",
        "repository_implementation_commit",
        "predecessor_evidence_normalized_lf_sha256",
        "predecessor_collection_claim_sha256",
        "predecessor_deployment_claim_sha256",
        "predecessor_deployment_authorization_normalized_lf_sha256",
        "executor_binding_rule",
        "executor_binding",
        "authorization_id",
        "not_before",
        "expires_at",
        "max_uses",
        "remote_identity_preimage_collection_authorized",
    }
    if set(record) != expected_keys:
        raise CollectorError("ACTIVATION_INVALID")
    string_fields = expected_keys - {
        "schema_version",
        "max_uses",
        "remote_identity_preimage_collection_authorized",
    }
    if any(type(record[field]) is not str for field in string_fields):
        raise CollectorError("ACTIVATION_INVALID")
    hash_fields = {
        "contract_normalized_lf_sha256",
        "package_normalized_lf_sha256",
        "collector_normalized_lf_sha256",
        "predecessor_evidence_normalized_lf_sha256",
        "predecessor_collection_claim_sha256",
        "predecessor_deployment_claim_sha256",
        "predecessor_deployment_authorization_normalized_lf_sha256",
        "executor_binding",
    }
    if any(not re.fullmatch(r"[0-9a-f]{64}", record[field]) for field in hash_fields):
        raise CollectorError("ACTIVATION_INVALID")
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 2
        or record["record_kind"]
        != "explicit_remote_identity_preimage_renewal_authorization"
        or record["status"] != "APPROVED"
        or record["renewal_generation"] != RENEWAL_GENERATION
        or record["contract_normalized_lf_sha256"] != CONTRACT_HASH
        or record["package_normalized_lf_sha256"] != PACKAGE_HASH
        or record["collector_normalized_lf_sha256"] != normalized_hash(Path(__file__))
        or not re.fullmatch(r"[0-9a-f]{40}", record["repository_implementation_commit"])
        or record["repository_implementation_commit"] == "0" * 40
        or record["predecessor_evidence_normalized_lf_sha256"]
        != PREDECESSOR_EVIDENCE_HASH
        or record["predecessor_deployment_authorization_normalized_lf_sha256"]
        != DEPLOYMENT_AUTHORIZATION_HASH
        or record["executor_binding_rule"]
        != "windows_username_pipe_machineguid_sha256_v1"
        or not re.fullmatch(
            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
            record["authorization_id"],
        )
        or type(record["max_uses"]) is not int
        or record["max_uses"] != 1
        or type(record["remote_identity_preimage_collection_authorized"]) is not bool
        or record["remote_identity_preimage_collection_authorized"] is not True
    ):
        raise CollectorError("ACTIVATION_INVALID")
    start = _parse_activation_timestamp(record["not_before"])
    end = _parse_activation_timestamp(record["expires_at"])
    now = datetime.now(UTC)
    if start > now or end <= now or end <= start or end - start > timedelta(hours=24):
        raise CollectorError("ACTIVATION_TIME_INVALID")
    try:
        binding = _executor_binding()
    except (OSError, RuntimeError, ValueError) as exc:
        raise CollectorError("IDENTITY_BINDING_INVALID") from exc
    if record["executor_binding"] != binding:
        raise CollectorError("IDENTITY_BINDING_INVALID")
    return record, end


def _open_exclusive_existing_lock(path: Path) -> BinaryIO:
    _assert_no_reparse_ancestors(path, "LOCK_UNAVAILABLE")
    kernel32 = ctypes.windll.kernel32
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80000000 | 0x40000000,
        0,
        None,
        3,
        0x00200000,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        raise CollectorError("LOCK_UNAVAILABLE")
    info = _ByHandleFileInformation()
    try:
        if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise CollectorError("LOCK_UNAVAILABLE")
        denied_attributes = stat.FILE_ATTRIBUTE_REPARSE_POINT | stat.FILE_ATTRIBUTE_DIRECTORY
        if info.file_attributes & denied_attributes:
            raise CollectorError("LOCK_UNAVAILABLE")
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDWR | os.O_BINARY)
        handle = None
        stream = os.fdopen(descriptor, "r+b", buffering=0)
        try:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return stream
        except OSError as exc:
            stream.close()
            raise CollectorError("LOCK_UNAVAILABLE") from exc
    finally:
        if handle is not None:
            kernel32.CloseHandle(handle)


def _release_lock(stream: BinaryIO) -> None:
    try:
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        stream.close()


def _lineage_paths() -> dict[str, Path]:
    collection = _collection_state_root()
    deployment = _deployment_state_root()
    for root in (collection, deployment):
        _assert_no_reparse_ancestors(root, "LEDGER_INVALID")
        try:
            metadata = root.stat(follow_symlinks=False)
        except OSError as exc:
            raise CollectorError("LEDGER_INVALID") from exc
        if not stat.S_ISDIR(metadata.st_mode):
            raise CollectorError("LEDGER_INVALID")
    return {
        "deployment_lock": deployment / "operation.lock",
        "collection_lock": collection / "operation.lock",
        "collection_claim": collection / LEGACY_COLLECTION_CLAIM_NAME,
        "deployment_claim": deployment / DEPLOYMENT_CLAIM_NAME,
        "renewal_claim": collection / RENEWAL_CLAIM_NAME,
        "recovery_claim": deployment / RECOVERY_CLAIM_NAME,
    }


def _acquire_lineage_locks(paths: dict[str, Path]) -> tuple[BinaryIO, BinaryIO]:
    deployment_lock = _open_exclusive_existing_lock(paths["deployment_lock"])
    try:
        collection_lock = _open_exclusive_existing_lock(paths["collection_lock"])
    except CollectorError:
        _release_lock(deployment_lock)
        raise
    return deployment_lock, collection_lock


def _validate_claim(
    path: Path,
    expected_digest: str,
    implementation_field: str,
    implementation_hash: str,
    fixed: dict[str, str],
) -> tuple[bytes, str]:
    raw = _read_bounded_leaf(path, MAX_CLAIM_BYTES, "LINEAGE_INVALID")
    if exact_hash_bytes(raw) != expected_digest:
        raise CollectorError("LINEAGE_INVALID")
    claim = _strict_json_bytes(raw, MAX_CLAIM_BYTES, "LINEAGE_INVALID")
    expected_keys = {
        "state",
        "authorization_id",
        "authorization_sha256",
        "package_sha256",
        implementation_field,
        "consumed_at",
    }
    if set(claim) != expected_keys or any(type(value) is not str for value in claim.values()):
        raise CollectorError("LINEAGE_INVALID")
    if (
        claim["state"] != "consumed_before_transport"
        or not re.fullmatch(
            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", claim["authorization_id"]
        )
        or claim[implementation_field] != implementation_hash
    ):
        raise CollectorError("LINEAGE_INVALID")
    for key, value in fixed.items():
        if claim.get(key) != value:
            raise CollectorError("LINEAGE_INVALID")
    _parse_lineage_timestamp(claim["consumed_at"])
    return raw, claim["consumed_at"]


def _verify_predecessors(
    paths: dict[str, Path], authorization: dict[str, Any]
) -> tuple[dict[Path, bytes], str, str]:
    _assert_absent(paths["recovery_claim"], "LINEAGE_INVALID")
    _assert_absent(paths["renewal_claim"], "ATTEMPT_CONSUMED")
    if normalized_hash(DEPLOYMENT_AUTHORIZATION) != DEPLOYMENT_AUTHORIZATION_HASH:
        raise CollectorError("LINEAGE_INVALID")
    collection_raw, collection_consumed = _validate_claim(
        paths["collection_claim"],
        authorization["predecessor_collection_claim_sha256"],
        "collector_sha256",
        OLD_COLLECTOR_HASH,
        {
            "state": "consumed_before_transport",
            "authorization_sha256": LEGACY_COLLECTION_AUTHORIZATION_HASH,
            "package_sha256": PACKAGE_HASH,
        },
    )
    deployment_raw, deployment_consumed = _validate_claim(
        paths["deployment_claim"],
        authorization["predecessor_deployment_claim_sha256"],
        "deployer_sha256",
        DEPLOYER_HASH,
        {
            "state": "consumed_before_transport",
            "authorization_id": "4f06b6ca-3377-48ae-a643-aefc3fb90dbc",
            "authorization_sha256": DEPLOYMENT_AUTHORIZATION_HASH,
            "package_sha256": DEPLOYMENT_PACKAGE_HASH,
            "consumed_at": "2026-09-17T08:20:37.8800486+00:00",
        },
    )
    activation_raw = _read_bounded_leaf(
        DEPLOYMENT_AUTHORIZATION, MAX_AUTHORIZATION_BYTES, "LINEAGE_INVALID"
    )
    snapshots = {
        paths["collection_claim"]: collection_raw,
        paths["deployment_claim"]: deployment_raw,
        DEPLOYMENT_AUTHORIZATION: activation_raw,
    }
    return snapshots, collection_consumed, deployment_consumed


def _assert_predecessors_unchanged(snapshots: dict[Path, bytes]) -> None:
    for path, expected in snapshots.items():
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise CollectorError("LINEAGE_CHANGED") from exc
        if current != expected:
            raise CollectorError("LINEAGE_CHANGED")


def _consume_attempt(
    path: Path,
    authorization: dict[str, Any],
    collection_consumed_at: str,
    deployment_consumed_at: str,
) -> None:
    _assert_no_reparse_ancestors(path, "CLAIM_WRITE_FAILED")
    claim = {
        "state": "consumed_before_transport",
        "renewal_generation": RENEWAL_GENERATION,
        "authorization_id": authorization["authorization_id"],
        "authorization_sha256": normalized_hash(RENEWAL_AUTHORIZATION),
        "contract_sha256": CONTRACT_HASH,
        "package_sha256": PACKAGE_HASH,
        "collector_sha256": normalized_hash(Path(__file__)),
        "repository_implementation_commit": authorization["repository_implementation_commit"],
        "predecessor_evidence_sha256": PREDECESSOR_EVIDENCE_HASH,
        "predecessor_collection_claim_sha256": authorization[
            "predecessor_collection_claim_sha256"
        ],
        "predecessor_deployment_claim_sha256": authorization[
            "predecessor_deployment_claim_sha256"
        ],
        "predecessor_collection_consumed_at": collection_consumed_at,
        "predecessor_deployment_consumed_at": deployment_consumed_at,
        "consumed_at": datetime.now(UTC).isoformat(),
    }
    payload = json.dumps(claim, separators=(",", ":"), ensure_ascii=True).encode()
    if len(payload) > MAX_CLAIM_BYTES:
        raise CollectorError("CLAIM_WRITE_FAILED")
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise CollectorError("ATTEMPT_CONSUMED") from exc
    except OSError as exc:
        raise CollectorError("CLAIM_WRITE_FAILED") from exc


def _fixed_remote_command() -> str:
    commands = [
        "set -f",
        "export LC_ALL=C",
        "test \"$(/bin/hostname)\" = 'cadence' || exit 42",
        "test \"$(/usr/bin/id -un)\" = 'buet' || exit 42",
        f"test -d '{REMOTE_ROOT}' && test ! -L '{REMOTE_ROOT}' || exit 42",
        f"test \"$(/usr/bin/readlink -f '{REMOTE_ROOT}')\" = '{REMOTE_ROOT}' || exit 42",
        (
            "printf 'WP14_ID\\t%s\\t%s\\t%s\\t%s\\ttrue\\tfalse\\ttrue\\n' "
            '"$(/bin/hostname)" "$(/usr/bin/id -un)" '
            f"'{REMOTE_ROOT}' \"$(/usr/bin/readlink -f '{REMOTE_ROOT}')\""
        ),
    ]
    template = (
        "if test ! -e '{path}' && test ! -L '{path}'; then "
        "printf 'WP14_ASSET\\t{index}\\tabsent\\t-\\t-\\t-\\t-\\t-\\tfalse\\ttrue\\n'; "
        "else test ! -L '{path}' && test -f '{path}' || exit 42; "
        "resolved=$(/usr/bin/readlink -f '{path}') || exit 42; "
        f"case \"$resolved\" in '{REMOTE_ROOT}'/*) ;; *) exit 42 ;; esac; "
        "sha=$(/usr/bin/sha256sum '{path}' | /usr/bin/awk '{{print $1}}') || exit 42; "
        "mode=$(/usr/bin/stat -c '%a' '{path}') || exit 42; "
        "owner=$(/usr/bin/stat -c '%U' '{path}') || exit 42; "
        "links=$(/usr/bin/stat -c '%h' '{path}') || exit 42; "
        "printf 'WP14_ASSET\\t{index}\\tfile\\t%s\\t%s\\t%s\\tregular_file\\t%s\\tfalse\\ttrue\\n' "
        '"$sha" "$mode" "$owner" "$links"; fi'
    )
    for index, (_, relative, _) in enumerate(ASSETS):
        commands.append(template.format(path=f"{REMOTE_ROOT}/{relative}", index=index))
    commands.append("printf 'WP14_END\\n'")
    return "; ".join(commands)


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired as exc:
            raise CollectorError("TRANSPORT_TIMEOUT") from exc


def _invoke_bounded_ssh(command: str, expiry: datetime, deadline: float) -> bytes:
    executable = Path(_ssh_prefix()[0])
    _assert_no_reparse_ancestors(executable, "TRANSPORT_LAUNCH_FAILED")
    argv = [
        *_ssh_prefix(),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=2",
        "--",
        SSH_ALIAS,
        command,
    ]
    if time.monotonic() >= deadline or datetime.now(UTC) >= expiry:
        raise CollectorError("TRANSPORT_TIMEOUT")
    process: subprocess.Popen[bytes] | None = None
    output = bytearray()
    events: queue.Queue[tuple[str, bytes | None, BaseException | None]] = queue.Queue(maxsize=8)

    def reader(name: str, stream: BinaryIO) -> None:
        try:
            while chunk := stream.read(4096):
                events.put((name, chunk, None))
            events.put((name, None, None))
        except BaseException as exc:  # pragma: no cover - OS pipe failure
            events.put((name, None, exc))

    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert process.stdout is not None and process.stderr is not None
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            threading.Thread(target=reader, args=(name, stream), daemon=True).start()
        ended: set[str] = set()
        total = 0
        stderr_bytes = 0
        while len(ended) != 2 or process.poll() is None:
            if time.monotonic() >= deadline or datetime.now(UTC) >= expiry:
                raise CollectorError("TRANSPORT_TIMEOUT")
            try:
                name, chunk, error = events.get(timeout=0.02)
            except queue.Empty:
                continue
            if error is not None:
                raise CollectorError("TRANSPORT_NONZERO")
            if chunk is None:
                ended.add(name)
                continue
            total += len(chunk)
            if total > MAX_OUTPUT_BYTES:
                raise CollectorError("TRANSPORT_OUTPUT_LIMIT")
            if name == "stdout":
                output.extend(chunk)
            else:
                stderr_bytes += len(chunk)
        if stderr_bytes:
            raise CollectorError("TRANSPORT_STDERR")
        if process.returncode != 0:
            raise CollectorError("TRANSPORT_NONZERO")
        return bytes(output)
    except CollectorError:
        if process is not None:
            _terminate(process)
        raise
    except (OSError, ValueError) as exc:
        if process is not None:
            _terminate(process)
        raise CollectorError("TRANSPORT_LAUNCH_FAILED") from exc


def _convert_evidence(
    raw: bytes, authorization: dict[str, Any], collection_started_at: datetime
) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict").rstrip("\r\n")
    except UnicodeDecodeError as exc:
        raise CollectorError("TRANSPORT_UTF8_INVALID") from exc
    lines = [line.rstrip("\r") for line in text.split("\n")]
    if len(lines) != 13:
        raise CollectorError("EVIDENCE_INVALID")
    identity = lines[0].split("\t")
    if identity != [
        "WP14_ID",
        "cadence",
        "buet",
        REMOTE_ROOT,
        REMOTE_ROOT,
        "true",
        "false",
        "true",
    ]:
        raise CollectorError("EVIDENCE_INVALID")
    if lines[-1] != "WP14_END":
        raise CollectorError("EVIDENCE_INVALID")
    preimages: list[dict[str, Any]] = []
    for index, (repository_path, _, required) in enumerate(ASSETS):
        fields = lines[index + 1].split("\t")
        if len(fields) != 10 or fields[:2] != ["WP14_ASSET", str(index)]:
            raise CollectorError("EVIDENCE_INVALID")
        if fields[2] == "absent":
            if (
                required == "file"
                or fields[3:8] != ["-", "-", "-", "-", "-"]
                or fields[8:] != ["false", "true"]
            ):
                raise CollectorError("EVIDENCE_INVALID")
            preimages.append(
                {
                    "path": repository_path,
                    "presence": "absent",
                    "sha256": None,
                    "mode": None,
                    "owner": None,
                    "file_type": None,
                    "hard_link_count": None,
                    "is_symlink": False,
                    "resolved_under_root": True,
                }
            )
            continue
        if (
            fields[2] != "file"
            or not re.fullmatch(r"[0-9a-f]{64}", fields[3])
            or fields[3] == "0" * 64
            or fields[4] not in {"600", "700"}
            or fields[5:] != ["buet", "regular_file", "1", "false", "true"]
        ):
            raise CollectorError("EVIDENCE_INVALID")
        preimages.append(
            {
                "path": repository_path,
                "presence": "file",
                "sha256": fields[3],
                "mode": fields[4],
                "owner": "buet",
                "file_type": "regular_file",
                "hard_link_count": 1,
                "is_symlink": False,
                "resolved_under_root": True,
            }
        )
    observed_at = datetime.now(UTC)
    if observed_at < collection_started_at or observed_at > datetime.now(UTC):
        raise CollectorError("EVIDENCE_INVALID")
    evidence = {
        "schema_version": 2,
        "record_kind": "wp14_renewed_remote_identity_preimage_evidence",
        "renewal_contract_normalized_lf_sha256": CONTRACT_HASH,
        "source_package_normalized_lf_sha256": PACKAGE_HASH,
        "collector_normalized_lf_sha256": normalized_hash(Path(__file__)),
        "repository_implementation_commit": authorization["repository_implementation_commit"],
        "predecessor_evidence_normalized_lf_sha256": PREDECESSOR_EVIDENCE_HASH,
        "collection_started_at": collection_started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observed_at": observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "remote_identity": {
            "hostname": "cadence",
            "user": "buet",
            "root": REMOTE_ROOT,
            "resolved_root": REMOTE_ROOT,
            "root_is_directory": True,
            "root_is_symlink": False,
            "verified": True,
        },
        "preimages": preimages,
        "blockers": [],
    }
    _assert_public_evidence(evidence)
    return evidence


def _assert_public_evidence(evidence: dict[str, Any]) -> bytes:
    expected_top = {
        "schema_version",
        "record_kind",
        "renewal_contract_normalized_lf_sha256",
        "source_package_normalized_lf_sha256",
        "collector_normalized_lf_sha256",
        "repository_implementation_commit",
        "predecessor_evidence_normalized_lf_sha256",
        "collection_started_at",
        "observed_at",
        "remote_identity",
        "preimages",
        "blockers",
    }
    if set(evidence) != expected_top:
        raise CollectorError("EVIDENCE_INVALID")
    encoded = json.dumps(evidence, separators=(",", ":"), ensure_ascii=True).encode()
    if len(encoded) > MAX_JSON_BYTES:
        raise CollectorError("EVIDENCE_INVALID")
    lowered = encoded.lower()
    forbidden = (
        b"authorization_id",
        b"executor_binding",
        b"machineguid",
        b"claim_sha256",
        b"cds_lic_file",
        b"lm_license_file",
        b"-----begin",
        b"github_pat_",
        b"ghp_",
        b"c:\\\\users\\\\",
    )
    if any(token in lowered for token in forbidden):
        raise CollectorError("EVIDENCE_INVALID")
    return encoded


def _run() -> bytes:
    if len(sys.argv) != 1:
        raise CollectorError("ARGUMENTS_REJECTED")
    _assert_repository_boundary()
    authorization, expiry = _load_activation()
    paths = _lineage_paths()
    deployment_lock, collection_lock = _acquire_lineage_locks(paths)
    snapshots: dict[Path, bytes] | None = None
    try:
        snapshots, collection_consumed, deployment_consumed = _verify_predecessors(
            paths, authorization
        )
        _consume_attempt(
            paths["renewal_claim"], authorization, collection_consumed, deployment_consumed
        )
        collection_started_at = datetime.now(UTC)
        deadline = time.monotonic() + MAX_WALL_SECONDS
        raw = _invoke_bounded_ssh(_fixed_remote_command(), expiry, deadline)
        evidence = _convert_evidence(raw, authorization, collection_started_at)
        if time.monotonic() > deadline or datetime.now(UTC) >= expiry:
            raise CollectorError("TRANSPORT_TIMEOUT")
        return _assert_public_evidence(evidence)
    finally:
        try:
            if snapshots is not None:
                _assert_predecessors_unchanged(snapshots)
        finally:
            try:
                _release_lock(collection_lock)
            finally:
                _release_lock(deployment_lock)


def main() -> int:
    sys.stdout.buffer.write(_run() + b"\n")
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CollectorError as exc:
        payload = {"record_kind": "wp14_renewal_collection_error", "code": exc.code}
        print(json.dumps(payload, separators=(",", ":")), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        payload = {"record_kind": "wp14_renewal_collection_error", "code": "INTERNAL_ERROR"}
        print(json.dumps(payload, separators=(",", ":")), file=sys.stderr)
        raise SystemExit(1) from None
