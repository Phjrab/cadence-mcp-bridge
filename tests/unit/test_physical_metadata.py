"""Fixed filesystem-only observations and one-shot claims on disposable data."""

from __future__ import annotations

import base64
import copy
import ctypes
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from test_native_runtime import operator, operator_base, registered
from test_native_setup import confirmed_domain, prepared, root

from cadence_mcp_bridge import _native_setup as setup
from cadence_mcp_bridge import _physical_metadata as native
from cadence_mcp_bridge import _shared_reservations as accounting
from cadence_mcp_bridge import physical_metadata as host
from cadence_mcp_bridge.native_runtime import bundle

__all__ = ["operator", "operator_base", "registered", "confirmed_domain", "prepared", "root"]


@contextmanager
def current_account_owner() -> Iterator[None]:
    """Emulate ordinary-account default ownership in elevated Windows CI only.

    Changes this test process's default object owner, never an OS account, ACL or
    product guard. Child tests explicitly use the same fixture. Restore on exit.
    """
    if os.name != "nt":
        yield
        return
    from ctypes import wintypes as w

    api = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    api.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    api.GetTokenInformation.argtypes = [
        w.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        w.DWORD,
        ctypes.POINTER(w.DWORD),
    ]
    api.SetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    api.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    token = w.HANDLE()
    assert api.OpenProcessToken(kernel.GetCurrentProcess(), 0x88, ctypes.byref(token))

    def information(kind: int) -> Any:
        size = w.DWORD()
        api.GetTokenInformation(token, kind, None, 0, ctypes.byref(size))
        data = ctypes.create_string_buffer(size.value)
        assert api.GetTokenInformation(token, kind, data, size, ctypes.byref(size))
        return data

    changed = False
    previous = information(4)  # TOKEN_OWNER, retained for restoration
    user = information(1)  # TOKEN_USER
    user_sid = ctypes.c_void_p.from_buffer(user)
    try:
        assert api.SetTokenInformation(token, 4, ctypes.byref(user_sid), ctypes.sizeof(user_sid))
        changed = True
        assert api.EqualSid(ctypes.c_void_p.from_buffer(information(4)), user_sid)
        yield
    finally:
        try:
            if changed:
                assert api.SetTokenInformation(token, 4, previous, ctypes.sizeof(previous))
        finally:
            kernel.CloseHandle(token)


@pytest.fixture(autouse=True)
def isolated_intents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    with current_account_owner():
        home = tmp_path / "operator-home"
        home.mkdir(mode=0o700)
        monkeypatch.setattr(host, "_operator_home", lambda: home)
        yield home


def test_targets_exclude_user_circuits_and_unregistered_search_roots() -> None:
    profile = {
        "paths": {"protected_roots": ["/install", "/work/source"]},
        "tools": {
            name: {"path": "/install/bin/" + name} for name in ("ocean", "virtuoso", "spectre")
        },
    }
    registration = {
        "routes": [
            {
                "libraries": [
                    {"path": path}
                    for path in (
                        "/install/pdk",
                        "/work/source",
                        "/elsewhere",
                        "/installation-lookalike",
                    )
                ]
            }
        ]
    }
    roots, tools = native.targets(profile, registration)
    assert roots == ["/install", "/install/pdk"]
    assert len(tools) == 3
    broken = copy.deepcopy(profile)
    broken["paths"]["protected_roots"] = ["/work/source"]
    with pytest.raises(ValueError, match="binding_missing"):
        native.targets(broken, registration)


@pytest.mark.skipif(os.name != "posix", reason="actual Linux filesystem trust")
def test_metadata_never_opens_candidate_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "never-execute"
    candidate.write_text("raise RuntimeError('must never run or be read')")
    monkeypatch.setattr(native, "chain", lambda *_: [])
    monkeypatch.setattr("builtins.open", lambda *_args, **_kw: pytest.fail("content opened"))
    value = native.observe(str(candidate), [str(tmp_path)])
    assert value["kind"] == "regular" and value["metadata"]["size"] > 0
    assert "content_sha256" not in value


@pytest.mark.skipif(os.name != "posix", reason="actual Linux links/modes/FIFO")
def test_contained_link_and_shared_write_are_metadata_not_permission_repairs(
    tmp_path: Path,
) -> None:
    target = tmp_path / "data"
    target.write_bytes(b"unchanged")
    target.chmod(0o666)
    link = tmp_path / "link"
    link.symlink_to(target)
    before = target.stat().st_mode
    value = native.observe(str(link), [str(tmp_path)])
    assert value["kind"] == "symlink" and value["target_shared_write"]
    assert target.stat().st_mode == before
    outside = tmp_path.parent / "outside"
    outside.write_bytes(b"not read")
    link.unlink()
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="link_escape"):
        native.observe(str(link), [str(tmp_path)])
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="special_file"):
        native.observe(str(fifo), [str(tmp_path)])


@pytest.mark.skipif(os.name != "posix", reason="actual Linux directory inventory")
def test_enumeration_is_nonrecursive_and_global_entry_bound(tmp_path: Path) -> None:
    install = tmp_path / "installation"
    install.mkdir()
    nested = install / "nested"
    nested.mkdir()
    (nested / "unseen").write_bytes(b"private")
    profile = {
        "paths": {"protected_roots": [str(install)]},
        "tools": {name: {"path": str(install / name)} for name in ("ocean", "spectre", "virtuoso")},
    }
    for name in profile["tools"]:
        (install / name).write_bytes(b"do not execute")
    registration = {"routes": [{"libraries": [{"path": str(nested)}]}]}
    _, paths, _ = native.enumerate_targets(profile, registration)
    assert str(nested) in paths and str(nested / "unseen") not in paths
    for index in range(128):
        (install / ("candidate" + str(index))).write_bytes(b"")
    with pytest.raises(ValueError, match="entry_bound"):
        native.enumerate_targets(profile, {"routes": []})


def test_preparation_is_local_and_tamper_fails_before_transport(
    registered: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _, registration = registered
    exported = tmp_path / "native"
    receipt = bundle(context, registration, exported)
    output = tmp_path / "physical"
    result = host.prepare(exported, receipt["manifest_sha256"], output)
    assert result["remote_contact"] is False
    assert result["request_bytes"] <= native.LIMIT
    assert not (output / "collection-started.private.json").exists()
    monkeypatch.setattr(host, "run_fixed", lambda *_a, **_k: pytest.fail("transport called"))
    with pytest.raises(ValueError, match="plan_binding"):
        host.collect(output, "0" * 64)
    request = output / "request.private.json"
    request.write_bytes(request.read_bytes() + b" ")
    with pytest.raises(ValueError, match="request_binding"):
        host.collect(output, result["plan_sha256"])


def test_failed_transport_preserves_intent_and_prevents_retry(
    registered: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _, registration = registered
    exported = tmp_path / "native"
    receipt = bundle(context, registration, exported)
    output = tmp_path / "physical"
    result = host.prepare(exported, receipt["manifest_sha256"], output)
    calls: list[int] = []
    monkeypatch.setattr(host, "_ssh", lambda _: ["synthetic-not-executed"])

    def timeout(*_args: Any, **_kwargs: Any) -> Any:
        calls.append(1)
        raise ValueError("synthetic timeout")

    monkeypatch.setattr(host, "run_fixed", timeout)
    with pytest.raises(ValueError, match="failed_no_retry"):
        host.collect(output, result["plan_sha256"])
    assert (output / "failed.private.json").is_file()
    with pytest.raises(FileExistsError):
        host.collect(output, result["plan_sha256"])
    assert calls == [1]


def test_cross_plan_alias_and_bundle_identity_cannot_retry(
    registered: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _, registration = registered
    exported = tmp_path / "native"
    receipt = bundle(context, registration, exported)
    calls: list[int] = []
    monkeypatch.setattr(host, "_ssh", lambda _: ["synthetic-not-executed"])

    def timeout(*_args: Any, **_kwargs: Any) -> Any:
        calls.append(1)
        raise ValueError("synthetic before remote claim")

    monkeypatch.setattr(host, "run_fixed", timeout)
    for index in range(2):
        output = tmp_path / str(index)
        result = host.prepare(exported, receipt["manifest_sha256"], output)
        error = ValueError if index == 0 else FileExistsError
        with pytest.raises(error):
            host.collect(output, result["plan_sha256"])
    assert calls == [1]


def test_claim_process_restart_and_alias_independence(
    registered: Any, isolated_intents: Path
) -> None:
    context, _, _ = registered
    environment = context.contracts.environment
    # Inspect fixture's typed environment through the registered source profile.
    assert environment is not None
    raw = environment.model_dump_json()
    script = (
        "import sys; from pathlib import Path; "
        "from cadence_mcp_bridge import physical_metadata as h; "
        "from cadence_mcp_bridge.environments import EnvironmentProfile; "
        "h._operator_home=lambda:Path(sys.argv[1]); "
        "e=EnvironmentProfile.model_validate_json(sys.argv[2]); "
        "sys.path.insert(0,sys.argv[4]); "
        "from test_physical_metadata import current_account_owner\n"
        "with current_account_owner():\n"
        " h._claim_intent(e,'a'*64,sys.argv[3],'b'*64)"
    )
    for index in range(2):
        changed = environment.model_copy(
            update={"ssh_alias": "another-alias", "environment_id": "another-id"}
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                script,
                str(isolated_intents),
                raw if index == 0 else changed.model_dump_json(),
                str(index),
                str(Path(__file__).parent),
            ],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if index == 0:
            assert completed.returncode == 0, completed.stderr
        else:
            assert completed.returncode != 0 and b"FileExistsError" in completed.stderr


def test_concurrent_claims_exactly_one_winner(registered: Any) -> None:
    context, _, _ = registered
    assert context.contracts.environment is not None

    def attempt(index: int) -> bool:
        try:
            host._claim_intent(context.contracts.environment, "a" * 64, str(index), "b" * 64)
            return True
        except FileExistsError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(8))) == 1


@pytest.mark.parametrize("partial", [b"", b"{", b"{}"])
def test_partial_or_malformed_claim_remains_spent(
    registered: Any, isolated_intents: Path, partial: bytes
) -> None:
    context, _, _ = registered
    assert context.contracts.environment is not None
    host._claim_intent(context.contracts.environment, "a" * 64, "first", "b" * 64)
    claim = next((isolated_intents / ".cadence-mcp-physical-intents-v1").iterdir())
    claim.write_bytes(partial)
    with pytest.raises(FileExistsError):
        host._claim_intent(context.contracts.environment, "a" * 64, "second", "c" * 64)
    assert claim.read_bytes() == partial


def test_claim_write_failure_stays_spent(registered: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    context, _, _ = registered
    assert context.contracts.environment is not None
    monkeypatch.setattr(host, "_sync_directory", lambda _: None)

    def failed_sync(_: int) -> None:
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(host.os, "fsync", failed_sync)
    with pytest.raises(OSError, match="disk failure"):
        host._claim_intent(context.contracts.environment, "a" * 64, "first", "b" * 64)
    with pytest.raises(FileExistsError):
        host._claim_intent(context.contracts.environment, "a" * 64, "second", "b" * 64)


@pytest.mark.skipif(os.name != "posix", reason="actual POSIX ownership/modes/symlinks")
def test_untrusted_intent_directory_and_symlink_rejected(
    registered: Any, isolated_intents: Path
) -> None:
    context, _, _ = registered
    assert context.contracts.environment is not None
    directory = isolated_intents / ".cadence-mcp-physical-intents-v1"
    directory.mkdir(mode=0o777)
    directory.chmod(0o777)
    with pytest.raises(ValueError, match="permissions"):
        host._claim_intent(context.contracts.environment, "a" * 64, "first", "b" * 64)
    directory.rmdir()
    elsewhere = isolated_intents / "elsewhere"
    elsewhere.mkdir(mode=0o700)
    directory.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match="local_path_invalid"):
        host._claim_intent(context.contracts.environment, "a" * 64, "first", "b" * 64)


def test_intent_directory_replacement_during_flush_rejected(
    registered: Any, isolated_intents: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, _, _ = registered
    assert context.contracts.environment is not None
    directory = isolated_intents / ".cadence-mcp-physical-intents-v1"
    original = host.os.fsync

    def replace(fd: int) -> None:
        original(fd)
        if directory.exists():
            directory.rename(isolated_intents / "retained-detached")
            directory.mkdir(mode=0o700)

    monkeypatch.setattr(host.os, "fsync", replace)
    # Windows refuses renaming the directory while its claim handle is open.
    with pytest.raises((ValueError, OSError)):
        host._claim_intent(context.contracts.environment, "a" * 64, "first", "b" * 64)


@pytest.mark.skipif(os.name != "nt", reason="actual Windows junction and ACL")
def test_windows_junction_and_shared_write_rejected(
    registered: Any, isolated_intents: Path, tmp_path: Path
) -> None:
    context, _, _ = registered
    directory = isolated_intents / ".cadence-mcp-physical-intents-v1"
    target = tmp_path / "junction-target"
    target.mkdir()
    junction = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(directory), str(target)],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert junction.returncode == 0, junction.stderr
    with pytest.raises(ValueError, match="local_path_invalid"):
        host._claim_intent(context.contracts.environment, "a" * 64, "first", "b" * 64)
    # Remove only the exact disposable junction, never its target recursively.
    directory.rmdir()
    directory.mkdir()
    acl = subprocess.run(
        ["icacls", str(directory), "/grant", "*S-1-1-0:(OI)(CI)(M)"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert acl.returncode == 0, acl.stderr
    with pytest.raises(ValueError, match="intent_security"):
        host._claim_intent(context.contracts.environment, "a" * 64, "first", "b" * 64)


def test_synthetic_claim_does_not_consult_environment_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", "Z:/untrusted-home")
    monkeypatch.setenv("USERPROFILE", "Z:/untrusted-profile")
    # Bypass only the test's synthetic-home override, to read OS metadata. No writes.
    import importlib.util

    spec = importlib.util.spec_from_file_location("physical_os_home", host.__file__)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    try:
        home = loaded._operator_home()
    except ValueError as error:
        # An unloaded sandbox profile may reject; it must never use supplied paths.
        assert str(error) == "physical_operator_home"
    else:
        assert "untrusted" not in str(home)


@pytest.mark.skipif(os.name != "nt", reason="actual qualified Windows directory DACL")
def test_prepared_directory_has_private_protected_dacl_under_shared_parent(
    registered: Any, tmp_path: Path
) -> None:
    if sys.version_info < (3, 12, 4):
        pytest.skip("metadata slice is not qualified on pre3.12.4 Windows")
    context, _, registration = registered
    exported = tmp_path / "native"
    receipt = bundle(context, registration, exported)
    shared = tmp_path / "shared-parent"
    shared.mkdir()
    result = subprocess.run(
        ["icacls", str(shared), "/grant", "*S-1-1-0:(OI)(CI)(F)"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = shared / "plan"
    host.prepare(exported, receipt["manifest_sha256"], output)
    for path in (output, output / "request.private.json", output / "plan.private.json"):
        host._windows_private(path)
    # Verify the actual descriptor, not chmod mode bits. GetFileSecurityW is local
    # read-only metadata; SE_DACL_PROTECTED prevents Everyone inheritance.
    from ctypes import wintypes as w

    api = ctypes.WinDLL("advapi32", use_last_error=True)
    api.GetFileSecurityW.argtypes = [
        w.LPCWSTR,
        w.DWORD,
        ctypes.c_void_p,
        w.DWORD,
        ctypes.POINTER(w.DWORD),
    ]
    api.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(w.WORD),
        ctypes.POINTER(w.DWORD),
    ]
    needed = w.DWORD()
    api.GetFileSecurityW(str(output), 4, None, 0, ctypes.byref(needed))
    descriptor = ctypes.create_string_buffer(needed.value)
    assert api.GetFileSecurityW(str(output), 4, descriptor, needed, ctypes.byref(needed))
    control, revision = w.WORD(), w.DWORD()
    assert api.GetSecurityDescriptorControl(
        descriptor, ctypes.byref(control), ctypes.byref(revision)
    )
    assert control.value & 0x1000


@pytest.mark.parametrize(
    "key,value",
    [("max_entries", 129), ("eda_execution", True), ("timeout_seconds", 600), ("extra", "invalid")],
)
def test_rehashed_plan_cannot_expand_fixed_scope(
    registered: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: Any,
) -> None:
    context, _, registration = registered
    exported = tmp_path / "native"
    receipt = bundle(context, registration, exported)
    output = tmp_path / "physical"
    host.prepare(exported, receipt["manifest_sha256"], output)
    path = output / "plan.private.json"
    plan = json.loads(path.read_bytes())
    plan[key] = value
    path.write_bytes(host._canonical(plan))
    monkeypatch.setattr(host, "run_fixed", lambda *_a, **_k: pytest.fail("transport called"))
    with pytest.raises(ValueError, match="closed_plan_binding"):
        host.collect(output, host._sha(path.read_bytes()))
    assert not (output / "collection-started.private.json").exists()


def response() -> tuple[dict[str, Any], dict[str, Any]]:
    plan = {
        "directory_targets": ["/install"],
        "tool_targets": ["/install/ocean"],
        "manifest_sha256": "a" * 64,
        "collector_sha256": "b" * 64,
        "environment_sha256": "c" * 64,
        "pdk_sha256": "d" * 64,
    }
    entries = []
    for path in ("/install", "/install/ocean"):
        entry: dict[str, Any] = {
            "path": path,
            "kind": "directory",
            "resolved": path,
            "metadata": {},
            "target_metadata": {},
            "ancestors": [],
            "target_ancestors": [],
            "target_shared_write": False,
            "target_owner_trusted": True,
        }
        entry["metadata_sha256"] = host._sha(host._canonical(entry))
        entries.append(entry)
    counter = {"campaign_id": "synthetic", "count": 128, "result_reserved_bytes": 15721299968}
    result = {
        "schema_version": 1,
        "status": "PHYSICAL_METADATA_OBSERVED",
        "manifest_sha256": plan["manifest_sha256"],
        "collector_sha256": plan["collector_sha256"],
        "profile_sha256": plan["environment_sha256"],
        "pdk_sha256": plan["pdk_sha256"],
        "observed_at_epoch": 1,
        "operator_uid": 500,
        "counter_before": counter,
        "counter_after": copy.deepcopy(counter),
        "root_count": 1,
        "entry_count": 2,
        "entries": entries,
        "metadata_unchanged": True,
        "metadata_scope": "lstat_identity_mode_size_mtime_ctime_excludes_atime",
        "license_assessed": False,
        "physical_execution_qualified": False,
        "candidate_file_contents_read": False,
        "new_attempts": 0,
        "new_reserved_bytes": 0,
        "new_extractions": 0,
        "stage_files_created": 3,
    }
    return result, plan


@pytest.mark.parametrize(
    "key,value",
    [
        ("status", "/private/path"),
        ("new_attempts", False),
        ("schema_version", True),
        ("metadata_unchanged", 1),
        ("entry_count", 129),
        ("operator_uid", 0),
        ("license_assessed", True),
        ("extra", True),
        ("observed_at_epoch", float("nan")),
        ("counter_after", {}),
    ],
)
def test_response_rejects_wrong_types_drift_and_overclaim(key: str, value: Any) -> None:
    result, plan = response()
    host._validate_result(result, plan)
    result[key] = value
    with pytest.raises(ValueError, match="physical_response"):
        host._validate_result(result, plan)


def test_response_rejects_private_entry_substitution() -> None:
    result, plan = response()
    result["entries"][0]["path"] = "/elsewhere"
    with pytest.raises(ValueError, match="physical_entry_binding"):
        host._validate_result(result, plan)


@pytest.mark.skipif(os.name != "posix", reason="fixed POSIX alarm/bootstrap")
def test_bootstrap_rejects_payload_tamper_before_loading_any_source() -> None:
    code = host._bootstrap(
        {
            "request_sha256": "0" * 64,
            "setup_sha256": "0" * 64,
            "collector_sha256": "0" * 64,
            "known_native_sources": {},
        }
    )
    assert len(code) < 8192
    process = subprocess.run(
        [sys.executable, "-I", "-c", code], input=b"{}", capture_output=True, timeout=5, check=False
    )
    assert process.returncode != 0 and b"AssertionError" in process.stderr
    assert not process.stdout


@pytest.fixture
def physical_runtime(prepared: Any, tmp_path: Path) -> Any:
    root, request, _, known = prepared
    assets = {name: base64.b64decode(raw) for name, raw in request["files"].items()}
    profile = json.loads(assets["profile.json"])
    install = tmp_path / "installation"
    install.mkdir(mode=0o700)
    for name in ("ocean", "spectre", "virtuoso"):
        (install / name).write_bytes(b"not executable")
    profile["paths"]["protected_roots"] = [str(install)]
    profile["tools"] = {
        name: {"path": str(install / name)} for name in ("ocean", "spectre", "virtuoso")
    }
    assets["profile.json"] = setup.canonical(profile)
    registration = json.loads(assets["registration.json"])
    registration.update(
        environment_sha256=setup.digest(assets["profile.json"]), pdk_sha256="a" * 64
    )
    assets["registration.json"] = setup.canonical(registration)
    manifest = json.loads(assets["manifest.json"])
    manifest.update(
        profile_sha256=setup.digest(assets["profile.json"]),
        registration_sha256=setup.digest(assets["registration.json"]),
    )
    manifest["files"] = {
        name: {"sha256": setup.digest(raw), "bytes": len(raw)}
        for name, raw in assets.items()
        if name != "manifest.json"
    }
    assets["manifest.json"] = setup.canonical(manifest)
    expected = setup.digest(assets["manifest.json"])
    request.update(
        manifest_sha256=expected,
        files={name: base64.b64encode(raw).decode("ascii") for name, raw in assets.items()},
    )
    setup.apply(request, expected, known)
    accounting.write_new(
        str(root / "active-native-provider.json"),
        {"schema_version": 1, "manifest_sha256": expected},
    )
    query = {
        "schema_version": 1,
        "operation": "physical-metadata-once-v1",
        "manifest_sha256": expected,
        "files": request["files"],
    }
    return root, query, assets, known, install


@pytest.mark.skipif(os.name != "posix", reason="actual owned Linux flock/claim")
def test_one_shot_preserves_existing_ledger_and_runtime(physical_runtime: Any) -> None:
    root, query, assets, known, install = physical_runtime
    before = (root / accounting.LEDGER).read_bytes()
    result = native.run(query, setup, assets, known, b"# fixed synthetic source\n")
    assert result["entry_count"] == 4 and result["counter_before"] == result["counter_after"]
    assert result["candidate_file_contents_read"] is False
    assert result["physical_execution_qualified"] is False
    assert result["stage_files_created"] == 3
    host._validate_result(
        result,
        {
            "directory_targets": [str(install)],
            "tool_targets": [str(install / name) for name in ("ocean", "spectre", "virtuoso")],
            "manifest_sha256": result["manifest_sha256"],
            "collector_sha256": result["collector_sha256"],
            "environment_sha256": result["profile_sha256"],
            "pdk_sha256": result["pdk_sha256"],
        },
    )
    assert (root / accounting.LEDGER).read_bytes() == before
    with pytest.raises(FileExistsError):
        native.run(query, setup, assets, known, b"# fixed synthetic source\n")
    assert (root / accounting.LEDGER).read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="actual owned Linux drift/claim")
def test_metadata_drift_retains_failed_claim(
    physical_runtime: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, query, assets, known, install = physical_runtime
    original = native.same_listings

    def drift(listings: Any) -> None:
        (install / "ocean").chmod(0o600)
        original(listings)

    monkeypatch.setattr(native, "same_listings", drift)
    with pytest.raises(ValueError, match="metadata_drift"):
        native.run(query, setup, assets, known, b"# drift source\n")
    assert list((root / "physical-metadata-v1").glob("*/request.json"))
    assert not list((root / "physical-metadata-v1").glob("*/receipt.json"))
    with pytest.raises(FileExistsError):
        native.run(query, setup, assets, known, b"# drift source\n")
