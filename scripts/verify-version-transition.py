"""Isolated, offline-EDA published/candidate package transition verification.

Supply an independently hash-verified published wheel and its runtime lock, plus
the frozen candidate wheel and lock. No developer/real operator files are read.
Dependency downloads may occur; no SSH, EDA, native activation or real app runs.
All disposable evidence is retained, including on failure.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import sysconfig
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from email.parser import BytesParser
from pathlib import Path
from typing import Any

PUBLISHED_VERSION = "2.0.0"
PUBLISHED_WHEEL_SHA256 = "4633549b869ba8e6fc3b900454dbd96d96d51dd6e52d04bde3a78400d548203c"
PUBLISHED_LOCK_SHA256 = "272f9ba4528ee335b13bd838f582f141691b6a6c4afc8f4175ced14e5cc0831f"
OPERATION_ID = "8c3bb876-4c6a-4cc2-bf4a-0ec2977f7919"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wheel_version(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("one wheel metadata member required")
        metadata = BytesParser().parsebytes(archive.read(names[0]))
        if metadata["Name"] != "cadence-mcp-bridge" or not metadata["Version"]:
            raise ValueError("bridge wheel required")
        return str(metadata["Version"])


def snapshot(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError("disposable state links are forbidden")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")


@contextmanager
def ordinary_fixture_owner() -> Iterator[None]:
    """Use user ownership for this process's disposable Windows fixtures only.

    An elevated CI token can otherwise create administrator-owned files. This
    changes the process token's default object owner, never OS accounts, existing
    objects, ACLs or product guards; restore the token before leaving the probe.
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
        w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD),
    ]
    api.SetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    token = w.HANDLE()
    if not api.OpenProcessToken(kernel.GetCurrentProcess(), 0x88, ctypes.byref(token)):
        raise ValueError("cannot obtain fixture process token")

    def information(kind: int) -> Any:
        size = w.DWORD()
        api.GetTokenInformation(token, kind, None, 0, ctypes.byref(size))
        data = ctypes.create_string_buffer(size.value)
        if not api.GetTokenInformation(token, kind, data, size, ctypes.byref(size)):
            raise ValueError("cannot read fixture process token")
        return data

    previous = information(4)
    user = information(1)
    sid = ctypes.c_void_p.from_buffer(user)
    changed = False
    try:
        if not api.SetTokenInformation(token, 4, ctypes.byref(sid), ctypes.sizeof(sid)):
            raise ValueError("cannot set fixture object owner")
        changed = True
        yield
    finally:
        try:
            if changed and not api.SetTokenInformation(token, 4, previous, ctypes.sizeof(previous)):
                raise ValueError("cannot restore fixture object owner")
        finally:
            kernel.CloseHandle(token)


def clean_environment(workspace: Path) -> dict[str, str]:
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith("CADENCE_MCP_")
        and key.upper() not in {"PYTHONPATH", "PYTHONHOME", "PATH"}
    }
    # No external SSH/EDA executable can be located by the child bridge.
    env.update(PATH=str(workspace / "no-external-programs"), PYTHONUTF8="1")
    return env


def installed_files(wheel: Path) -> int:
    import cadence_mcp_bridge

    origin = Path(cadence_mcp_bridge.__file__).resolve()
    if not origin.is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("bridge must originate from the isolated environment")
    installed = Path(sysconfig.get_path("purelib"))
    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.startswith("cadence_mcp_bridge/")]
        if not names:
            raise ValueError("empty bridge wheel")
        for name in names:
            if (installed / name).read_bytes() != archive.read(name):
                raise ValueError("installed source differs from the selected wheel")
    return len(names)


def create_state(root: Path) -> None:
    from cadence_mcp_bridge.analysis_store import AnalysisStore
    from cadence_mcp_bridge.operator_operations import OperationPlan, OperationProgress
    from cadence_mcp_bridge.sweeps import SweepStore

    root.mkdir(mode=0o700)
    frozen = OperationPlan.model_validate_json(json.dumps({
        "resource_domain_sha256": "a" * 64, "runner_sha256": "b" * 64,
        "ledger_ref": "synthetic-retained-ledger", "environment_sha256": "c" * 64,
        "design_sha256": "d" * 64, "pdk_sha256": "e" * 64, "grant_sha256": "f" * 64,
        "analysis": "dc", "request": {
            "schema_version": 1, "design_id": "synthetic-design", "analysis_id": "synthetic-dc",
            "values": [], "result_reservation_bytes": 1048576,
        },
    }))
    store = AnalysisStore(root / "analysis.sqlite3")
    if not store.admit_operation(OPERATION_ID, frozen):
        raise ValueError("fresh disposable admission failed")
    current = store.operation(OPERATION_ID)
    current = store.advance_operation(
        OPERATION_ID, current.progress, OperationProgress(phase="UNKNOWN_OUTCOME")
    )
    store.advance_operation(
        OPERATION_ID, current.progress,
        OperationProgress(phase="SUCCEEDED", remote_revision=1, provider_receipt_sha256="a" * 64),
    )
    SweepStore(root / "sweep.sqlite3")
    values = {
        "operation-plan.json": json.loads(frozen.model_dump_json()),
        "context.json": {"synthetic": True, "journal": "analysis.sqlite3", "context": "retained"},
        "grant.json": {"synthetic": True, "spent": True, "execution_authorized": False},
        "shared-ledger.json": {"synthetic": True, "attempts": 7, "reserved_bytes": 7340032},
        "result.json": {"synthetic": True, "operation_id": OPERATION_ID, "retained": True},
        "client.json": {"mcpServers": {
            "unrelated-user-server": {"command": "preserve-me", "args": ["--keep"]},
            "cadence": {"command": "python", "args": ["-m", "cadence_mcp_bridge", "serve"]},
        }},
        # An existing durable account-scoped marker must survive an older package
        # which has no physical metadata API. This is a synthetic claim, not a
        # new claim in the actual OS account home or permission to collect.
        "account-home/.cadence-mcp-physical-intents-v1/spent.private.json": {
            "schema_version": 1, "status": "ATTEMPT_SPENT_NO_RETRY",
            "identity_sha256": "a" * 64, "plan_sha256": "b" * 64,
            "request_sha256": "c" * 64,
        },
    }
    for name, value in values.items():
        target = root / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_json(target, value)


def state_replay(root: Path) -> None:
    from cadence_mcp_bridge.analysis_store import AnalysisStore
    from cadence_mcp_bridge.operator_operations import OperationPlan

    frozen = OperationPlan.model_validate_json((root / "operation-plan.json").read_bytes())
    store = AnalysisStore(root / "analysis.sqlite3")
    if store.operation(OPERATION_ID).progress.phase != "SUCCEEDED":
        raise ValueError("retained result state changed")
    if store.admit_operation(OPERATION_ID, frozen):
        raise ValueError("same-ID replay admitted duplicate work")


def account_claim(workspace: Path, state: Path, first: bool) -> None:
    """Run the installed2.1 durable API against a substituted disposable home.

    Only the OS-home lookup is substituted. Real owner/mode/namespace/fsync and
    exclusive-claim guards remain active. No real account-home path is accessed.
    """
    from cadence_mcp_bridge import physical_metadata as physical
    from cadence_mcp_bridge.environments import EnvironmentProfile

    profile = Path(physical.__file__).parent / "operator_starter/environment.json"
    environment = EnvironmentProfile.model_validate_json(profile.read_bytes())
    previous_home = physical._operator_home
    physical._operator_home = lambda: state / "account-home"
    try:
        if first:
            before = snapshot(state)
            physical._claim_intent(environment, "a" * 64, "b" * 64, "c" * 64)
            after = snapshot(state)
            if len(after) != len(before) + 1 or any(after.get(k) != v for k, v in before.items()):
                raise ValueError("explicit synthetic claim changed unrelated state")
            write_json(workspace / "preserved-with-claim.json", after)
        try:
            physical._claim_intent(environment, "a" * 64, "different-plan", "d" * 64)
        except FileExistsError:
            pass
        else:
            raise ValueError("installed durable intent admitted a duplicate claim")
    finally:
        physical._operator_home = previous_home


async def protocol(workspace: Path) -> dict[str, Any]:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-I", "-X", "utf8", "-m", "cadence_mcp_bridge", "serve-operator"],
        env=clean_environment(workspace), cwd=str(workspace),
    )
    async with Client(parameters) as client:
        tools = await client.list_tools()
        declarations = {
            tool.name: tool.model_dump(mode="json", by_alias=True) for tool in tools.tools
        }
        if len(declarations) != 85 or len(declarations) != len(tools.tools):
            raise ValueError("v2 public tool inventory changed")
        identity = client.server_info
        if identity is None or identity.version != wheel_version(workspace / "selected.whl"):
            raise ValueError("handshake server version changed")
        designs = await client.call_tool("cadence_list_designs")
        if designs.is_error or designs.structured_content is None or (
            designs.structured_content["designs"] != []
        ):
            raise ValueError("unconfigured server inherited a circuit")
        # Unconfigured operator mode creates no backend or SSH executable lookup.
        # Its runtime and remote routes must reject instead of selecting a legacy
        # reference or any real operator journal from the process environment.
        for name in ("cadence_runtime_info_v2", "cadence_health"):
            denied = await client.call_tool(name)
            if not denied.is_error or "SETUP_REQUIRED" not in str(denied.content):
                raise ValueError("unconfigured operator route did not remain blocked")
    return declarations


def probe(workspace: Path, wheel: Path, label: str) -> None:
    with ordinary_fixture_owner():
        installed_probe(workspace, wheel, label)


def installed_probe(workspace: Path, wheel: Path, label: str) -> None:
    import cadence_mcp_bridge

    version = wheel_version(wheel)
    if importlib.metadata.version("cadence-mcp-bridge") != version:
        raise ValueError("distribution version differs")
    if cadence_mcp_bridge.__version__ != version:
        raise ValueError("runtime version differs")
    matched = installed_files(wheel)
    state = workspace / "state"
    if not state.exists():
        if label != "published-before":
            raise ValueError("retained state is missing; never reinitialize after transition")
        create_state(state)
        write_json(workspace / "preserved.json", snapshot(state))
    extended = workspace / "preserved-with-claim.json"
    baseline = extended if extended.exists() else workspace / "preserved.json"
    expected = json.loads(baseline.read_bytes())
    if snapshot(state) != expected:
        raise ValueError("transition modified operator files before probe")
    state_replay(state)
    if version == "2.1.0":
        account_claim(workspace, state, first=not extended.exists())
        expected = json.loads(extended.read_bytes())
    # Wheel selection is a disposable probe input outside protected state.
    (workspace / "selected.whl").write_bytes(wheel.read_bytes())
    declarations = asyncio.run(protocol(workspace))
    write_json(workspace / (label + "-tools.json"), declarations)
    if snapshot(state) != expected:
        raise ValueError("probe modified retained operator state")
    result = run(
        [sys.executable, "-I", "-X", "utf8", "-m", "cadence_mcp_bridge", "--version"],
        workspace, label + "-cli-version", environment=clean_environment(workspace), timeout=30,
    )
    if result.stdout.decode("utf-8").strip() != version:
        raise ValueError("CLI version differs")
    write_json(workspace / (label + "-receipt.json"), {
        "status": "PASS", "version": version, "wheel_sha256": sha(wheel),
        "installed_package_files_equal": matched, "retained_state_files": len(expected),
        "duplicate_operation_admitted": False, "public_tools": len(declarations),
        "remote_contact": False, "native_runtime_activated": False,
        "protocol_mode": "UNCONFIGURED_OPERATOR_EMPTY_CATALOG_SETUP_REQUIRED",
        "scope": "ISOLATED_INSTALLED_SYNTHETIC_HOST_TRANSITION_NOT_VM_OR_APP",
        "account_claim_scope": (
            "INSTALLED_DURABLE_API_SYNTHETIC_HOME_DUPLICATE_DENIED"
            if version == "2.1.0" else "PRESERVED_MARKERS_NO_METADATA_API_IN_2_0"
        ),
    })


def _captured_bytes(value: bytes | str | None) -> bytes:
    return value.encode("utf-8") if isinstance(value, str) else value or b""


def run(
    command: list[str], workspace: Path, label: str, *,
    environment: dict[str, str] | None = None, timeout: float = 600,
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            command, cwd=workspace, env=environment, capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        (workspace / (label + ".stdout.log")).write_bytes(_captured_bytes(error.stdout))
        (workspace / (label + ".stderr.log")).write_bytes(_captured_bytes(error.stderr))
        write_json(workspace / (label + ".timeout.json"), {
            "status": "TIMEOUT", "timeout_seconds": timeout,
            "partial_output_preserved": True,
        })
        raise ValueError("transition step timed out; retained logs: " + label) from None
    (workspace / (label + ".stdout.log")).write_bytes(result.stdout)
    (workspace / (label + ".stderr.log")).write_bytes(result.stderr)
    if result.returncode:
        raise ValueError("transition step failed; retained logs: " + label)
    return result


def verify(args: argparse.Namespace) -> None:
    published = args.published_wheel.resolve(strict=True)
    candidate = args.candidate_wheel.resolve(strict=True)
    old_lock = args.published_lock.resolve(strict=True)
    new_lock = args.candidate_lock.resolve(strict=True)
    if sha(published) != PUBLISHED_WHEEL_SHA256 or sha(old_lock) != PUBLISHED_LOCK_SHA256:
        raise ValueError("published v2.0.0 wheel/lock identity differs")
    if wheel_version(published) != PUBLISHED_VERSION or wheel_version(candidate) != "2.1.0":
        raise ValueError("this verifier requires exact published2.0.0 and candidate2.1.0")
    inputs = {path: sha(path) for path in (published, candidate, old_lock, new_lock)}
    workspace = args.workspace.absolute()
    workspace.mkdir(mode=0o700, parents=False, exist_ok=False)
    (workspace / "no-external-programs").mkdir(mode=0o700)
    interpreter = workspace / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run([sys.executable, "-I", "-m", "venv", "--copies", str(workspace / "venv")],
        workspace, "create-venv")
    transitions = (
        ("published-before", published, old_lock), ("candidate-upgrade", candidate, new_lock),
        ("published-rollback", published, old_lock), ("candidate-restored", candidate, new_lock),
    )
    for label, wheel, lock in transitions:
        if any(sha(path) != digest for path, digest in inputs.items()):
            raise ValueError("a frozen transition input changed")
        run([args.uv, "pip", "sync", "--python", str(interpreter), "--require-hashes",
             "--link-mode", "copy", str(lock)], workspace, label + "-dependencies")
        run([args.uv, "pip", "install", "--python", str(interpreter), "--no-deps",
             "--link-mode", "copy", str(wheel)], workspace, label + "-wheel")
        run([str(interpreter), "-I", "-X", "utf8", str(Path(__file__).resolve()),
             "--probe", "--workspace", str(workspace), "--candidate-wheel", str(wheel),
             "--label", label], workspace, label + "-probe")
        if any(sha(path) != digest for path, digest in inputs.items()):
            raise ValueError("a frozen transition input changed")
    catalogs = [json.loads((workspace / (label + "-tools.json")).read_bytes())
                for label, _, _ in transitions]
    if any(catalog != catalogs[0] for catalog in catalogs[1:]):
        raise ValueError("published/candidate full v2 declarations differ")
    write_json(workspace / "transition-receipt.json", {
        "status": "PASS", "versions": ["2.0.0", "2.1.0", "2.0.0", "2.1.0"],
        "published_wheel_sha256": sha(published), "candidate_wheel_sha256": sha(candidate),
        "published_lock_sha256": sha(old_lock), "candidate_lock_sha256": sha(new_lock),
        "full_public_declarations_equal": 85,
        "protocol_mode": "UNCONFIGURED_OPERATOR_EMPTY_CATALOG_SETUP_REQUIRED",
        "retained_state_files": len(snapshot(workspace / "state")),
        "dependencies": "EACH_VERSION_HASH_LOCKED_SYNC_NOT_LATEST_RESOLUTION",
        "remote_contact": False, "new_simulations": 0, "new_reservations": 0,
        "native_activation": "NOT_PERFORMED_HOST_PACKAGE_TRANSITION_ONLY",
        "scope": "SYNTHETIC_HOST_INSTALL_NOT_ACTUAL_CLIENT_OR_VM_UPGRADE",
        "account_claim_scope": (
            "INSTALLED_DURABLE_API_SYNTHETIC_HOME_DOWNGRADE_UPGRADE_DUPLICATE_DENIED"
        ),
    })
    print(json.dumps({"status": "PASS", "receipt": str(workspace / "transition-receipt.json")}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published-wheel", type=Path)
    parser.add_argument("--candidate-wheel", type=Path, required=True)
    parser.add_argument("--published-lock", type=Path)
    parser.add_argument("--candidate-lock", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--label", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        probe(args.workspace, args.candidate_wheel, args.label)
    else:
        if not all((args.published_wheel, args.published_lock, args.candidate_lock)):
            parser.error("published wheel and both hash-locked runtime files are required")
        verify(args)


if __name__ == "__main__":
    main()
