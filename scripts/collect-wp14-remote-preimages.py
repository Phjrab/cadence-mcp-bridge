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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = (
    PROJECT_ROOT
    / "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_APPROVAL_PACKAGE_V2.json"
)
AUTHORIZATION = (
    PROJECT_ROOT
    / "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_AUTHORIZATION_V1.json"
)
DEPLOYMENT_PACKAGE = (
    PROJECT_ROOT
    / "docs/approvals"
    / "WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V2.json"
)
DEPLOYER = PROJECT_ROOT / "scripts/deploy-wp14-narrow.ps1"
LINEAGE = PROJECT_ROOT / "remote/config/runner-lineage.json"
AUTHORIZATION_V2 = (
    PROJECT_ROOT / "docs/approvals/WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json"
)
PACKAGE_HASH = "7b8d4d623a95e67a6d39e0391bcf5b9869c58dedbf02b0dd638c070853048223"
# Stable lineage key: version changes must never reset the predecessor's one-use ledger.
CLAIM_PACKAGE_HASH = "1906357b1ef5ba98a3d28241896fc59d0a4ff8053b64eac9f5d45f9a9bde0fcb"
DEPLOYMENT_PACKAGE_HASH = "96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431"
DEPLOYER_HASH = "3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc"
PACKAGE_BASE_MAIN_COMMIT = "59a450c63b040a604e644638ef6e02b0a9544d09"
REPOSITORY_MAIN_COMMIT = "e60ab270a5e002256f8c5bbf6b81e54f65c10a31"
SSH_ALIAS = "cadence-vm"
REMOTE_ROOT = "/home/buet/cds_work/.cadence_mcp"
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
    ("remote/lib/run-wp14-role-discovery.sh", "lib/run-wp14-role-discovery.sh", "file_or_absent"),
    ("remote/py26/actual_profile_audit.py", "py26/actual_profile_audit.py", "file_or_absent"),
    (
        "remote/py26/ade_profile_introspection.py",
        "py26/ade_profile_introspection.py",
        "file_or_absent",
    ),
    ("remote/py26/wp14_role_discovery.py", "py26/wp14_role_discovery.py", "file_or_absent"),
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


class CollectorError(RuntimeError):
    pass


def normalized_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode()).hexdigest()


def _windows_ssh_path() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise CollectorError("Windows directory identity is unavailable.")
    return Path(buffer.value) / "System32/OpenSSH/ssh.exe"


SSH_PREFIX = [str(_windows_ssh_path())]


def _local_app_data_root() -> Path:
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x001C, None, 0, buffer)
    if result != 0 or not buffer.value:
        raise CollectorError("Local application data identity is unavailable.")
    return Path(buffer.value)


def _state_root() -> Path:
    return _local_app_data_root() / "CadenceMcpBridge/wp14-preimage-evidence"


def _executor_binding() -> str:
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
        machine_guid = str(winreg.QueryValueEx(key, "MachineGuid")[0])
    identity = f"{getpass.getuser()}|{machine_guid}"
    return hashlib.sha256(identity.encode()).hexdigest()


def _assert_no_reparse_ancestors(path: Path) -> None:
    candidate = Path(os.path.abspath(path))
    for current in (candidate, *candidate.parents):
        if not current.exists():
            continue
        attributes = getattr(os.stat(current, follow_symlinks=False), "st_file_attributes", 0)
        if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise CollectorError("Reparse path rejected.")


def _strict_json(path: Path, maximum_bytes: int) -> dict[str, Any]:
    _assert_no_reparse_ancestors(path)
    if not path.is_file() or path.stat().st_size > maximum_bytes:
        raise CollectorError("Bounded JSON input is missing or oversized.")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        lowered: set[str] = set()
        for key, value in items:
            if key.lower() in lowered:
                raise CollectorError("Duplicate JSON key rejected.")
            lowered.add(key.lower())
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CollectorError("Invalid JSON; content suppressed.") from exc

    def bounded(item: Any, depth: int = 0) -> None:
        if depth > 6:
            raise CollectorError("JSON nesting exceeds bound.")
        if isinstance(item, dict):
            for child in item.values():
                bounded(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 64:
                raise CollectorError("JSON array exceeds bound.")
            for child in item:
                bounded(child, depth + 1)

    bounded(value)
    if not isinstance(value, dict):
        raise CollectorError("JSON root must be an object.")
    return value


def _assert_package_boundary() -> None:
    for path in (PACKAGE, DEPLOYMENT_PACKAGE, DEPLOYER, LINEAGE):
        _assert_no_reparse_ancestors(path)
        if not path.is_file():
            raise CollectorError("A fixed repository input is missing.")
    if normalized_hash(PACKAGE) != PACKAGE_HASH:
        raise CollectorError("Evidence package hash mismatch.")
    if normalized_hash(DEPLOYMENT_PACKAGE) != DEPLOYMENT_PACKAGE_HASH:
        raise CollectorError("Deployment package hash mismatch.")
    if normalized_hash(DEPLOYER) != DEPLOYER_HASH:
        raise CollectorError("Hardened deployer hash mismatch.")
    package = _strict_json(PACKAGE, 32768)
    if (
        package.get("package_id")
        != "WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_APPROVAL_PACKAGE"
        or package.get("package_version") != 2
        or package.get("record_kind") != "approval_request_not_grant"
        or package.get("status") != "READY_FOR_REVIEW"
    ):
        raise CollectorError("Evidence package identity mismatch.")
    authority = package.get("authority")
    if (
        not isinstance(authority, dict)
        or not authority
        or any(value is not False for value in authority.values())
    ):
        raise CollectorError("The request package unexpectedly grants authority.")
    binding = package.get("repository_binding")
    contract = package.get("proposed_collector_contract")
    if not isinstance(binding, dict) or not isinstance(contract, dict):
        raise CollectorError("Evidence package contract is incomplete.")
    if (
        binding.get("base_main_commit") != PACKAGE_BASE_MAIN_COMMIT
        or binding.get("repository") != "Phjrab/cadence-mcp-bridge"
        or binding.get("visibility_required") != "public"
        or binding.get("deployment_enabled") is not False
        or contract.get("implemented_now") is not False
        or contract.get("ready_for_remote_use") is not False
    ):
        raise CollectorError("Evidence package boundary changed.")
    expected_assets = [
        {"path": path, "remote_relative_path": remote, "required_presence": required}
        for path, remote, required in ASSETS
    ]
    if package.get("asset_preimage_allowlist") != expected_assets:
        raise CollectorError("The fixed eleven-asset allowlist changed.")
    lineage = _strict_json(LINEAGE, 16384)
    if lineage.get("deployment_enabled") is not False:
        raise CollectorError("deployment_enabled must remain false.")
    if AUTHORIZATION_V2.exists():
        raise CollectorError("Deployment Authorization V2 must remain absent.")


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise CollectorError("Invalid authorization timestamp.")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _load_authorization() -> tuple[dict[str, Any], datetime]:
    if not AUTHORIZATION.is_file():
        raise CollectorError(
            "Remote identity/preimage collection is not authorized; "
            "the separate authorization is absent and no transport was invoked."
        )
    record = _strict_json(AUTHORIZATION, 16384)
    expected_keys = {
        "schema_version",
        "record_kind",
        "status",
        "package_normalized_lf_sha256",
        "collector_normalized_lf_sha256",
        "remote_identity_preimage_collection_authorized",
        "max_uses",
        "authorization_id",
        "executor_binding",
        "not_before",
        "expires_at",
        "repository_main_commit",
    }
    if set(record) != expected_keys:
        raise CollectorError("Invalid closed collector authorization schema.")
    string_fields = expected_keys - {
        "schema_version",
        "remote_identity_preimage_collection_authorized",
        "max_uses",
    }
    if any(type(record[field]) is not str for field in string_fields):
        raise CollectorError("Invalid scalar collector authorization field.")
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["record_kind"] != "explicit_remote_identity_preimage_collection_authorization"
        or record["status"] != "APPROVED"
        or record["package_normalized_lf_sha256"] != PACKAGE_HASH
        or record["collector_normalized_lf_sha256"] != normalized_hash(Path(__file__))
        or type(record["remote_identity_preimage_collection_authorized"]) is not bool
        or record["remote_identity_preimage_collection_authorized"] is not True
        or type(record["max_uses"]) is not int
        or record["max_uses"] != 1
        or record["repository_main_commit"] != REPOSITORY_MAIN_COMMIT
        or record["executor_binding"] != _executor_binding()
        or not re.fullmatch(
            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", record["authorization_id"]
        )
    ):
        raise CollectorError(
            "Collector authorization is invalid or not bound to this exact collector."
        )
    start = _parse_timestamp(record["not_before"])
    end = _parse_timestamp(record["expires_at"])
    now = datetime.now(UTC)
    if start > now or end <= now or end <= start or end - start > timedelta(hours=24):
        raise CollectorError(
            "Collector authorization is stale or outside its fixed validity window."
        )
    return record, end


def _claim_attempt(authorization: dict[str, Any]) -> BinaryIO:
    state_root = _state_root()
    _assert_no_reparse_ancestors(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_ancestors(state_root)
    lock_path = state_root / "operation.lock"
    claim_path = state_root / f"attempt-{CLAIM_PACKAGE_HASH}.json"
    _assert_no_reparse_ancestors(lock_path)
    _assert_no_reparse_ancestors(claim_path)
    lock = lock_path.open("a+b")
    try:
        if lock_path.stat().st_size == 0:
            lock.write(b"\0")
            lock.flush()
            os.fsync(lock.fileno())
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        claim = {
            "state": "consumed_before_transport",
            "authorization_id": authorization["authorization_id"],
            "authorization_sha256": normalized_hash(AUTHORIZATION),
            "package_sha256": PACKAGE_HASH,
            "collector_sha256": normalized_hash(Path(__file__)),
            "consumed_at": datetime.now(UTC).isoformat(),
        }
        with claim_path.open("xb") as stream:
            stream.write(json.dumps(claim, separators=(",", ":")).encode())
            stream.flush()
            os.fsync(stream.fileno())
        return lock
    except (OSError, CollectorError) as exc:
        lock.close()
        raise CollectorError(
            "WP-14 collection attempt is already consumed, concurrent, or unavailable. No retry."
        ) from exc


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
            raise CollectorError("Local transport termination unconfirmed. No retry.") from exc


def _invoke_bounded_ssh(command: str, authorization_expiry: datetime) -> bytes:
    executable = Path(SSH_PREFIX[0])
    _assert_no_reparse_ancestors(executable)
    argv = [
        *SSH_PREFIX,
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
    started = time.monotonic()
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
            if time.monotonic() - started >= MAX_WALL_SECONDS:
                raise CollectorError(
                    "WP-14 evidence collection exceeded its fixed wall-clock limit. No retry."
                )
            if datetime.now(UTC) >= authorization_expiry:
                raise CollectorError("Collector authorization expired. No retry.")
            try:
                name, chunk, error = events.get(timeout=0.02)
            except queue.Empty:
                continue
            if error is not None:
                raise CollectorError("Transport stream failed closed; output suppressed.")
            if chunk is None:
                ended.add(name)
                continue
            total += len(chunk)
            if total > MAX_OUTPUT_BYTES:
                raise CollectorError("Transport exceeded the output limit. No retry.")
            if name == "stdout":
                output.extend(chunk)
            else:
                stderr_bytes += len(chunk)
        if process.returncode != 0 or stderr_bytes:
            raise CollectorError(
                "The fixed evidence transport failed. No retry or fallback was attempted."
            )
        return bytes(output)
    except CollectorError:
        if process is not None:
            _terminate(process)
        raise
    except (OSError, ValueError) as exc:
        if process is not None:
            _terminate(process)
        raise CollectorError(
            "WP-14 evidence transport failed closed; output suppressed. No retry."
        ) from exc


def _convert_evidence(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict").rstrip("\r\n")
    except UnicodeDecodeError as exc:
        raise CollectorError("Transport returned invalid UTF-8; output suppressed.") from exc
    lines = [line.rstrip("\r") for line in text.split("\n")]
    if len(lines) != 13:
        raise CollectorError("Evidence line count mismatch.")
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
        raise CollectorError("Remote identity evidence mismatch.")
    if lines[-1] != "WP14_END":
        raise CollectorError("Evidence terminator mismatch.")
    preimages: list[dict[str, Any]] = []
    for index, (repository_path, _, required) in enumerate(ASSETS):
        fields = lines[index + 1].split("\t")
        if len(fields) != 10 or fields[:2] != ["WP14_ASSET", str(index)]:
            raise CollectorError("Asset evidence ordering or shape mismatch.")
        if fields[2] == "absent":
            if (
                required == "file"
                or fields[3:8] != ["-", "-", "-", "-", "-"]
                or fields[8:] != ["false", "true"]
            ):
                raise CollectorError("Required or malformed absent preimage evidence.")
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
            or not re.fullmatch(r"[67]00", fields[4])
            or fields[5:] != ["buet", "regular_file", "1", "false", "true"]
        ):
            raise CollectorError("Unverified file preimage evidence.")
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
    evidence = {
        "schema_version": 1,
        "record_kind": "wp14_fresh_remote_identity_preimage_evidence",
        "collector_normalized_lf_sha256": normalized_hash(Path(__file__)),
        "repository_main_commit": REPOSITORY_MAIN_COMMIT,
        "observed_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    encoded = json.dumps(evidence, separators=(",", ":"), ensure_ascii=True).encode()
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise CollectorError("Evidence JSON exceeded its fixed size bound.")
    return evidence


def main() -> int:
    if len(sys.argv) != 1:
        raise CollectorError("This fixed collector accepts no arguments.")
    _assert_package_boundary()
    authorization, expiry = _load_authorization()
    lock = _claim_attempt(authorization)
    try:
        raw = _invoke_bounded_ssh(_fixed_remote_command(), expiry)
        print(json.dumps(_convert_evidence(raw), separators=(",", ":"), ensure_ascii=True))
        return 0
    finally:
        try:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            lock.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CollectorError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print(
            "WP-14 collector failed closed; details suppressed and no retry allowed.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
