"""Explicit operator API for one fixed, non-EDA filesystem inventory.

No MCP registration, import/startup action or arbitrary remote target input.
Preparation is local; collection requires the operator's separate authorization.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import math
import os
import shlex
import stat
from contextlib import suppress
from importlib.resources import files
from pathlib import Path
from typing import Any

from cadence_mcp_bridge import _native_setup as setup
from cadence_mcp_bridge import _physical_metadata as collector
from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.environments import EnvironmentProfile, load_environment
from cadence_mcp_bridge.native_runtime import source_assets
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.ssh_backend import OpenSshBackend


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _operator_home() -> Path:
    # OS account database, never HOME/USERPROFILE, the plan, CWD or an SSH alias.
    if os.name == "nt":
        from ctypes import wintypes as w

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        profiles = ctypes.WinDLL("userenv", use_last_error=True)
        kernel.GetCurrentProcess.restype = w.HANDLE
        kernel.CloseHandle.argtypes = [w.HANDLE]
        api.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
        profiles.GetUserProfileDirectoryW.argtypes = [w.HANDLE, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        token = w.HANDLE()
        if not api.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise ValueError("physical_operator_home")
        folder = ctypes.create_unicode_buffer(32768)
        size = w.DWORD(len(folder))
        try:
            if not profiles.GetUserProfileDirectoryW(token, folder, ctypes.byref(size)):
                raise ValueError("physical_operator_home")
        finally:
            kernel.CloseHandle(token)
        if not folder.value:
            raise ValueError("physical_operator_home")
        return Path(folder.value)
    import pwd

    return Path(pwd.getpwuid(os.getuid()).pw_dir)  # type: ignore[attr-defined]


def _windows_private(path: Path, ancestor: bool = False) -> None:
    """Require current-token ownership and no non-admin write-capable allow ACE."""
    from ctypes import wintypes as w

    api = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [pointer], pointer
    kernel.CloseHandle.argtypes = [w.HANDLE]
    api.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    api.GetTokenInformation.argtypes = [
        w.HANDLE,
        ctypes.c_int,
        pointer,
        w.DWORD,
        ctypes.POINTER(w.DWORD),
    ]
    api.GetNamedSecurityInfoW.argtypes = [
        w.LPWSTR,
        ctypes.c_int,
        w.DWORD,
        ctypes.POINTER(pointer),
        pointer,
        ctypes.POINTER(pointer),
        pointer,
        ctypes.POINTER(pointer),
    ]
    api.GetNamedSecurityInfoW.restype = w.DWORD
    api.ConvertSidToStringSidW.argtypes = [pointer, ctypes.POINTER(pointer)]
    api.GetAce.argtypes = [pointer, w.DWORD, ctypes.POINTER(pointer)]

    def sid_text(sid: Any) -> str:
        value = pointer()
        if not api.ConvertSidToStringSidW(sid, ctypes.byref(value)):
            raise ValueError("physical_intent_security")
        try:
            return ctypes.wstring_at(value)
        finally:
            kernel.LocalFree(value)

    token = w.HANDLE()
    if not api.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ValueError("physical_intent_security")
    try:
        size = w.DWORD()
        api.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not api.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise ValueError("physical_intent_security")
        user = sid_text(pointer.from_buffer(buffer))
    finally:
        kernel.CloseHandle(token)
    owner, acl, descriptor = pointer(), pointer(), pointer()
    if api.GetNamedSecurityInfoW(
        str(path),
        1,
        5,
        ctypes.byref(owner),
        None,
        ctypes.byref(acl),
        None,
        ctypes.byref(descriptor),
    ):
        raise ValueError("physical_intent_security")
    try:
        owners = {user, "S-1-5-18", "S-1-5-32-544"} if ancestor else {user}
        if not owner or sid_text(owner) not in owners or not acl:
            raise ValueError("physical_intent_security")
        # ACL header: revision/reserved/size/ACE count. Reject unhandled ACE types.
        assert acl.value is not None
        count = ctypes.c_ushort.from_address(acl.value + 4).value
        for index in range(count):
            ace = pointer()
            if not api.GetAce(acl, index, ctypes.byref(ace)) or not ace.value:
                raise ValueError("physical_intent_security")
            kind, flags = ctypes.string_at(ace, 2)
            if flags & 8 or kind == 1:  # inherit-only / deny cannot grant access
                continue
            if kind != 0:
                raise ValueError("physical_intent_security")
            mask = ctypes.c_uint32.from_address(ace.value + 4).value
            if mask & 0x500D0156 and sid_text(ace.value + 8) not in {
                user,
                "S-1-5-18",
                "S-1-5-32-544",
                "S-1-3-4",  # OWNER RIGHTS; owner was required to equal this token
            }:
                raise ValueError("physical_intent_security")
    finally:
        kernel.LocalFree(descriptor)


def _intent_metadata(path: Path, directory: bool) -> tuple[int, int, int, int, int]:
    _local_path(path)
    info = path.lstat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)) or (
        not directory and info.st_nlink != 1
    ):
        raise ValueError("physical_intent_type")
    if os.name == "nt":
        _windows_private(path)
    elif info.st_uid != os.getuid() or info.st_mode & 0o077:  # type: ignore[attr-defined]
        raise ValueError("physical_intent_permissions")
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)  # type: ignore[attr-defined]
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _claim_intent(
    environment: EnvironmentProfile, collector_sha: str, expected_plan: str, request_sha: str
) -> None:
    # The key follows the existing VM resource domain, not mutable bundle/grant IDs.
    key = _sha(
        _canonical(
            {
                "hostname": environment.host.hostname.lower().rstrip("."),
                "architecture": environment.host.architecture,
                "user": environment.host.user,
                "collector_sha256": collector_sha,
            }
        )
    )
    home = _local_path(_operator_home())
    # Home may be traversable on POSIX, but no other account may write it.
    home_info = home.stat()
    if os.name == "nt":
        _windows_private(home, ancestor=True)
    elif home_info.st_uid != os.getuid() or home_info.st_mode & 0o022:  # type: ignore[attr-defined]
        raise ValueError("physical_intent_home_permissions")
    directory = home / ".cadence-mcp-physical-intents-v1"
    _local_path(directory)
    with suppress(FileExistsError):
        directory.mkdir(mode=0o700)
    before = _intent_metadata(directory, True)
    _sync_directory(home)
    if _intent_metadata(directory, True) != before:
        raise ValueError("physical_intent_drift")
    target = directory / (key + ".private.json")
    # Any preexisting entry, including malformed/partial/symlink, is spent.
    # O_EXCL arbitrates independent processes. Never remove or overwrite it.
    data = _canonical(
        {
            "schema_version": 1,
            "status": "ATTEMPT_SPENT_NO_RETRY",
            "identity_sha256": key,
            "plan_sha256": expected_plan,
            "request_sha256": request_sha,
        }
    )
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
        held = os.fstat(stream.fileno())
        named = _intent_metadata(target, False)
        _sync_directory(directory)
        if (
            named[:2] != (held.st_dev, held.st_ino)
            or _payload(target) != data
            or _intent_metadata(target, False) != named
            or _intent_metadata(directory, True) != before
            or (home.stat().st_dev, home.stat().st_ino) != (home_info.st_dev, home_info.st_ino)
        ):
            raise ValueError("physical_intent_drift")


def _resource(name: str) -> bytes:
    return files("cadence_mcp_bridge").joinpath(name).read_bytes().replace(b"\r\n", b"\n")


def _read(path: Path) -> bytes:
    return installer.regular(str(_local_path(path)))  # type: ignore[no-any-return,no-untyped-call]


def _payload(path: Path) -> bytes:
    path = _local_path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError("physical_payload_file")
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(collector.LIMIT + 1)
        after = path.lstat()

    def identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    if (
        len(raw) > collector.LIMIT
        or identity(before)[:4] != identity(opened)[:4]
        or (os.name != "nt" and before.st_ctime_ns != opened.st_ctime_ns)
        or identity(before) != identity(after)
    ):
        raise ValueError("physical_payload_drift_or_bound")
    return raw


def _load_bundle(bundle: Path, expected: str) -> tuple[dict[str, bytes], dict[str, str]]:
    bundle = _local_path(bundle)
    names = (*setup.FILES, "manifest.json")
    if {p.name for p in bundle.iterdir()} != set(names):
        raise ValueError("physical_bundle_inventory")
    assets = {name: _read(bundle / name) for name in names}
    known = {name: _sha(raw) for name, raw in source_assets().items()}
    setup.inventory(assets, expected, known)  # type: ignore[no-untyped-call]
    return assets, known


def _plan(
    assets: dict[str, bytes], expected: str, known: dict[str, str]
) -> tuple[bytes, dict[str, Any]]:
    profile = json.loads(assets["profile.json"])
    registration = json.loads(assets["registration.json"])
    roots, tools = collector.targets(profile, registration)  # type: ignore[no-untyped-call]
    environment = EnvironmentProfile.model_validate_json(assets["profile.json"])
    request = {
        "schema_version": 1,
        "operation": "physical-metadata-once-v1",
        "manifest_sha256": expected,
        "files": {name: base64.b64encode(data).decode("ascii") for name, data in assets.items()},
    }
    envelope = {
        "request": request,
        "setup": base64.b64encode(_resource("_native_setup.py")).decode("ascii"),
        "collector": base64.b64encode(_resource("_physical_metadata.py")).decode("ascii"),
    }
    payload = _canonical(envelope)
    if len(payload) > collector.LIMIT:
        raise ValueError("physical_request_bound")
    plan = {
        "schema_version": 1,
        "kind": "PHYSICAL_METADATA_ONCE_V1",
        "manifest_sha256": expected,
        "request_sha256": _sha(payload),
        "setup_sha256": _sha(_resource("_native_setup.py")),
        "collector_sha256": _sha(_resource("_physical_metadata.py")),
        "known_native_sources": known,
        "environment_id": environment.environment_id,
        "environment_sha256": _sha(assets["profile.json"]),
        "pdk_sha256": registration["pdk_sha256"],
        "directory_targets": roots,
        "tool_targets": tools,
        "max_entries": 128,
        "timeout_seconds": 60,
        "output_limit_bytes": collector.LIMIT,
        "candidate_content_reads": False,
        "eda_execution": False,
    }
    return payload, plan


def prepare(bundle: Path, expected: str, output: Path) -> dict[str, object]:
    """Freeze the exact existing bundle and one package collector locally."""
    assets, known = _load_bundle(bundle, expected)
    _, raw = load_environment(bundle / "profile.json")
    if raw != assets["profile.json"]:
        raise ValueError("physical_profile_drift")
    payload, plan = _plan(assets, expected, known)
    roots = plan["directory_targets"]
    output = _local_path(output)
    output.mkdir(mode=0o700, exist_ok=False)
    for name, data in (("request.private.json", payload), ("plan.private.json", _canonical(plan))):
        with (output / name).open("xb") as stream:
            stream.write(data)
        (output / name).chmod(0o600)
    return {
        "status": "PHYSICAL_METADATA_PREPARED_LOCAL_ONLY",
        "plan_sha256": _sha(_canonical(plan)),
        "collector_sha256": plan["collector_sha256"],
        "request_bytes": len(payload),
        "directory_count": len(roots),
        "remote_contact": False,
    }


def _bootstrap(plan: dict[str, Any]) -> str:
    # The only executable sources are package assets with hashes compiled into
    # this fixed entry. Neither a public MCP caller nor request JSON chooses code.
    return (
        "import sys\n"
        "entry=sys.path[0] if sys.path else None\n"
        "sys.path[:]=[p for p in sys.path if p and p!=entry]\n"
        "import os\n"
        "sys.path[:]=[p for p in sys.path if os.path.isabs(p) and "
        "os.path.realpath(p)!=os.path.realpath(os.getcwd())]\n"
        "import json,hashlib,base64,types,signal\n"
        "signal.alarm(55)\n"
        "raw=sys.stdin.read(1048577).encode('ascii')\n"
        "assert len(raw)<=1048576\n"
        f"assert hashlib.sha256(raw).hexdigest()=={plan['request_sha256']!r}\n"
        "data=json.loads(raw.decode('ascii'))\n"
        "assert set(data)==set(('request','setup','collector'))\n"
        "loaded={}\n"
        f"pins={{'setup':{plan['setup_sha256']!r},'collector':{plan['collector_sha256']!r}}}\n"
        "for name in ('setup','collector'):\n"
        " source=base64.b64decode(data[name])\n"
        " assert hashlib.sha256(source).hexdigest()==pins[name]\n"
        " module=types.ModuleType('physical_'+name)\n"
        " module.__dict__['__package__']=None\n"
        " eval(compile(source,'physical_'+name+'.py','exec'),module.__dict__)\n"
        " loaded[name]=module\n"
        "encoded=data['request']['files']\n"
        "assets=dict((name,base64.b64decode(value)) for name,value in encoded.items())\n"
        f"result=loaded['collector'].run(data['request'],loaded['setup'],assets,{plan['known_native_sources']!r},base64.b64decode(data['collector']))\n"
        "sys.stdout.write(loaded['collector'].canonical(result).decode('ascii'))\n"
        "sys.stdout.write(chr(10))\n"
    )


def _validate_result(result: Any, plan: dict[str, Any]) -> None:
    fields = {
        "schema_version",
        "status",
        "manifest_sha256",
        "collector_sha256",
        "profile_sha256",
        "pdk_sha256",
        "observed_at_epoch",
        "operator_uid",
        "counter_before",
        "counter_after",
        "root_count",
        "entry_count",
        "entries",
        "metadata_unchanged",
        "metadata_scope",
        "license_assessed",
        "physical_execution_qualified",
        "candidate_file_contents_read",
        "new_attempts",
        "new_reserved_bytes",
        "new_extractions",
        "stage_files_created",
    }
    if type(result) is not dict or set(result) != fields:
        raise ValueError("physical_response_shape")
    for name, expected in (
        ("schema_version", 1),
        ("stage_files_created", 3),
        ("root_count", len(plan["directory_targets"])),
        ("new_attempts", 0),
        ("new_reserved_bytes", 0),
        ("new_extractions", 0),
    ):
        if type(result[name]) is not int or result[name] != expected:
            raise ValueError("physical_response_integer")
    for name, expected in (
        ("metadata_unchanged", True),
        ("candidate_file_contents_read", False),
        ("license_assessed", False),
        ("physical_execution_qualified", False),
    ):
        if result[name] is not expected:
            raise ValueError("physical_response_boolean")
    if (
        result["status"] != "PHYSICAL_METADATA_OBSERVED"
        or result["metadata_scope"] != "lstat_identity_mode_size_mtime_ctime_excludes_atime"
        or type(result["operator_uid"]) is not int
        or result["operator_uid"] <= 0
        or type(result["observed_at_epoch"]) not in (int, float)
        or not math.isfinite(result["observed_at_epoch"])
        or result["observed_at_epoch"] <= 0
    ):
        raise ValueError("physical_response_identity")
    for name, key in (
        ("manifest_sha256", "manifest_sha256"),
        ("collector_sha256", "collector_sha256"),
        ("profile_sha256", "environment_sha256"),
        ("pdk_sha256", "pdk_sha256"),
    ):
        if result[name] != plan[key]:
            raise ValueError("physical_response_binding")
    counter = result["counter_before"]
    if (
        type(counter) is not dict
        or set(counter) != {"campaign_id", "count", "result_reserved_bytes"}
        or type(counter["campaign_id"]) is not str
        or not counter["campaign_id"]
        or any(
            type(counter[k]) is not int or counter[k] < 0
            for k in ("count", "result_reserved_bytes")
        )
        or _canonical(counter) != _canonical(result["counter_after"])
    ):
        raise ValueError("physical_response_counter")
    entries = result["entries"]
    if (
        type(entries) is not list
        or type(result["entry_count"]) is not int
        or not 0 < result["entry_count"] <= collector.ENTRY_LIMIT
        or result["entry_count"] != len(entries)
    ):
        raise ValueError("physical_response_count")
    paths: set[str] = set()
    roots = plan["directory_targets"]
    mandatory = set(roots + plan["tool_targets"])
    for entry in entries:
        if type(entry) is not dict or set(entry) != {
            "path",
            "kind",
            "metadata",
            "resolved",
            "target_metadata",
            "ancestors",
            "target_ancestors",
            "target_shared_write",
            "target_owner_trusted",
            "metadata_sha256",
        }:
            raise ValueError("physical_entry_shape")
        path = entry["path"]
        if (
            type(path) is not str
            or path in paths
            or (path not in mandatory and path.rsplit("/", 1)[0] not in roots)
            or entry["kind"] not in ("regular", "directory", "symlink")
            or type(entry["resolved"]) is not str
            or not any(collector.inside(entry["resolved"], root) for root in roots)  # type: ignore[no-untyped-call]
            or type(entry["target_shared_write"]) is not bool
            or type(entry["target_owner_trusted"]) is not bool
        ):
            raise ValueError("physical_entry_binding")
        paths.add(path)
        value = {key: data for key, data in entry.items() if key != "metadata_sha256"}
        if entry["metadata_sha256"] != _sha(_canonical(value)):
            raise ValueError("physical_entry_digest")
    if not mandatory.issubset(paths):
        raise ValueError("physical_response_targets")


def collect(prepared: Path, expected_plan: str) -> dict[str, object]:
    """Explicit one-shot operation; preserves local and remote failed claims."""
    prepared = _local_path(prepared)
    plan_raw = _read(prepared / "plan.private.json")
    if _sha(plan_raw) != expected_plan:
        raise ValueError("physical_plan_binding")
    plan = json.loads(plan_raw)
    raw = _payload(prepared / "request.private.json")
    if len(raw) > collector.LIMIT or _sha(raw) != plan["request_sha256"]:
        raise ValueError("physical_request_binding")
    if (
        plan["collector_sha256"] != _sha(_resource("_physical_metadata.py"))
        or plan["setup_sha256"] != _sha(_resource("_native_setup.py"))
        or plan["known_native_sources"] != {k: _sha(v) for k, v in source_assets().items()}
    ):
        raise ValueError("physical_package_binding")
    envelope = json.loads(raw)
    assets = {name: base64.b64decode(data) for name, data in envelope["request"]["files"].items()}
    known = {k: _sha(v) for k, v in source_assets().items()}
    setup.inventory(assets, plan["manifest_sha256"], known)  # type: ignore[no-untyped-call]
    expected_raw, expected_value = _plan(assets, plan["manifest_sha256"], known)
    if raw != expected_raw or plan_raw != _canonical(expected_value):
        raise ValueError("physical_closed_plan_binding")
    profile_raw = assets["profile.json"]
    environment = EnvironmentProfile.model_validate_json(profile_raw)
    if _sha(profile_raw) != plan["environment_sha256"]:
        raise ValueError("physical_environment_binding")
    # Durable account-scoped intent precedes SSH and the replaceable plan marker.
    _claim_intent(environment, plan["collector_sha256"], expected_plan, _sha(raw))
    with (prepared / "collection-started.private.json").open("xb") as stream:
        stream.write(_canonical({"plan_sha256": expected_plan, "request_sha256": _sha(raw)}))
    try:
        code, stdout, stderr = run_fixed(
            _ssh(environment) + ["-c", shlex.quote(_bootstrap(plan))],
            raw,
            OpenSshBackend._ssh_environment(),
            timeout=60,
            limit=collector.LIMIT,
        )
        for name, data in (("stdout.private.json", stdout), ("stderr.private.log", stderr)):
            with (prepared / name).open("xb") as stream:
                stream.write(data)
        if code or stderr:
            raise ValueError("physical_remote_rejected")
        result = json.loads(stdout)
        _validate_result(result, plan)
        summary = {
            key: result[key]
            for key in (
                "status",
                "collector_sha256",
                "operator_uid",
                "counter_after",
                "root_count",
                "entry_count",
                "metadata_unchanged",
                "candidate_file_contents_read",
                "license_assessed",
                "physical_execution_qualified",
                "new_attempts",
                "new_reserved_bytes",
                "new_extractions",
                "stage_files_created",
            )
        }
        summary.update(remote_contact=True, evidence_sha256=_sha(stdout))
        with (prepared / "summary.private.json").open("xb") as stream:
            stream.write(_canonical(summary))
        return summary
    except Exception:
        with (prepared / "failed.private.json").open("xb") as stream:
            stream.write(_canonical({"status": "FAILED_OR_UNKNOWN_NO_AUTOMATIC_RETRY"}))
        raise ValueError("physical_collection_failed_no_retry") from None
