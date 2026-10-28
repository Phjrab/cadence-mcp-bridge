"""One-request local UI backend; no public MCP tools or implicit remote actions."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.onboarding import export_context_client_config, export_starter
from cadence_mcp_bridge.operator_setup import _check, _export_runtime, setup_guide
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.windows_host.configuration import (
    SetupRejected,
    apply,
    codex_config,
    digest,
    ordinary,
    parse,
    preview,
    remove_managed,
    snapshot,
)

NO_EXECUTION = {
    "new_simulations": 0,
    "new_reservations": 0,
    "execution_authorized": False,
    "remote_contact": False,
}


def data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        raise SetupRejected("local_app_data_required")
    root = Path(base) / "CadenceMCPBridge" / "UserData"
    for p in (root, *root.parents):
        if p.is_symlink() or p.is_junction():
            raise SetupRejected("linked_data_root_rejected")
    return root


def state_read(root: Path) -> dict[str, Any]:
    raw = snapshot(root / "setup.json")
    return {} if raw is None else dict(json.loads(raw))


def state_write(root: Path, data: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    destination = ordinary(root / "setup.json")
    fd, name = tempfile.mkstemp(prefix="setup-", suffix=".json", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, destination)
    finally:
        Path(name).unlink(missing_ok=True)


def ssh_executable() -> Path | None:
    # Use only the Windows optional-feature installation, never a CWD/PATH shim.
    system = os.environ.get("SYSTEMROOT")
    if not system or not Path(system).is_absolute():
        return None
    path = Path(system) / "System32" / "OpenSSH" / "ssh.exe"
    return path if path.is_file() else None


def host_status(root: Path) -> dict[str, Any]:
    from cadence_mcp_bridge.windows_host.uninstall import owned_receipts

    saved = state_read(root)
    # Reconcile durable pre-change intent after a process interrupted between
    # config replacement and setup.json publication. No change is replayed.
    receipts = owned_receipts(root, Path(sys.executable).parent.parent / "CadenceMCPBridge.exe")
    saved["receipts"] = [str(path) for path in receipts]
    return {
        **NO_EXECUTION,
        "status": "HOST_INSTALLED",
        "version": __version__,
        "python": platform.python_version(),
        "architecture": "x64" if struct.calcsize("P") == 8 else "unsupported",
        "python_executable": sys.executable,
        "isolated": bool(sys.flags.isolated),
        "codex_config": str(codex_config()),
        "saved_setup": saved,
        "ssh_available": ssh_executable() is not None,
        "ssh_install_help": "Windows 설정 > 시스템 > 선택적 기능 > OpenSSH Client. "
        "없으면 VM 연결은 대기 상태이며 관리자/사용자가 설치해야 합니다.",
        "stages": {
            "HOST_INSTALLED": True,
            "CLIENT_CONFIGURED": "NOT_CHECKED",
            "VM_CONNECTED": "NOT_CHECKED",
            "PREFLIGHT_PASSED": "NOT_CHECKED",
            "CIRCUIT_REGISTERED": "NOT_CHECKED",
            "EXECUTION_AUTHORIZED": "NOT_CHECKED",
        },
    }


def connection_draft(request: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key in ("alias", "host", "user"):
        value = request.get(key, "")
        if (
            not isinstance(value, str)
            or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,252}", value) is None
        ):
            raise SetupRejected("connection_field_invalid_" + key)
        result[key] = value
    identity = request.get("identity", "")
    if identity:
        ordinary(Path(identity))
        if not Path(identity).is_file():
            raise SetupRejected("identity_file_missing")
    result["identity"] = identity
    result["authentication"] = "existing_key_or_agent"
    return result


def connect(request: dict[str, Any]) -> dict[str, Any]:
    """Explicit ordinary-user connectivity check. No keys/passwords saved or returned."""
    if request.get("consent") is not True:
        raise SetupRejected("explicit_connection_consent_required")
    draft = connection_draft(request)
    ssh = ssh_executable()
    if ssh is None:
        raise SetupRejected("openssh_client_missing")
    # Alias is user-selected, but hostname/user are fixed from the same displayed
    # draft. Disable proxy/local commands and forwarding from ambient SSH config.
    args = [
        str(ssh),
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "ProxyCommand=none",
        "-o",
        "ProxyJump=none",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "HostName=" + draft["host"],
        "-o",
        "User=" + draft["user"],
    ]
    if draft["identity"]:
        args.extend(["-o", "IdentitiesOnly=yes", "-i", draft["identity"]])
    args.extend([draft["alias"], "/usr/bin/printf CADENCE_BRIDGE_CONNECTION_OK"])
    try:
        code, stdout, stderr = run_fixed(
            args, b"", OpenSshBackend._ssh_environment(), timeout=15, limit=8192
        )
    except (OSError, ValueError, TimeoutError, subprocess.SubprocessError):
        return {
            **NO_EXECUTION,
            "remote_contact": True,
            "status": "CONNECTION_FAILED_OR_UNKNOWN",
            "retry_performed": False,
            "remote_termination_guaranteed": False,
        }
    if code == 0 and stdout == b"CADENCE_BRIDGE_CONNECTION_OK":
        return {
            **NO_EXECUTION,
            "remote_contact": True,
            "status": "VM_CONNECTED",
            "preflight_passed": False,
            "circuit_registered": False,
        }
    stderr = stderr.lower()
    reason = "connection_failed"
    if b"host key" in stderr or b"host identification" in stderr:
        reason = "host_key_unverified_or_mismatch"
    elif b"permission denied" in stderr:
        reason = "key_or_agent_authentication_failed"
    return {
        **NO_EXECUTION,
        "remote_contact": True,
        "status": "BLOCKED",
        "reason": reason,
        "guidance": "호스트 키는 VM 콘솔 등 독립 경로에서 확인하세요. 비밀번호는 저장하지 "
        "않습니다. 기존 OpenSSH key/agent와 별칭 설정을 확인하세요.",
    }


def runtime_import(root: Path, settings: Path, context: str) -> dict[str, Any]:
    ordinary(settings)
    contexts = load_runtime(settings)
    choices = [c.binding.context_id for c in contexts]
    if not context:
        return {**NO_EXECUTION, "status": "CONTEXT_SELECTION_REQUIRED", "contexts": choices}
    report = _check(
        argparse.Namespace(
            profile=None,
            design_registry=None,
            pdk_registry=None,
            settings=settings,
            context=context,
        )
    )
    state = state_read(root)
    state.update(settings=str(settings), context=context, mode="existing")
    state_write(root, state)
    return {
        **NO_EXECUTION,
        **report,
        "contexts": choices,
        "original_paths_preserved": True,
        "journal_created": False,
        "execution_status": "NOT_ASSESSED",
    }


def runtime_create(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Use the existing exporter; compute pins, never invent observed inputs/grants."""
    if request.get("consent") is not True:
        raise SetupRejected("explicit_local_export_consent_required")
    fields = (
        "profile",
        "design_registry",
        "pdk_registry",
        "resource_state_root",
        "journal",
        "sweep_journal",
        "output",
    )
    values: dict[str, Any] = {key: Path(request[key]) for key in fields}
    for key in ("context", "authority_ref", "ledger_ref"):
        values[key] = request[key]
    runner = snapshot(Path(request["runner_file"]))
    if not runner:
        raise SetupRejected("reviewed_runner_file_required")
    values["runner_sha256"] = digest(runner)
    for key in ("native_provider_binding", "operator_grant", "native_specifications"):
        selected = request.get(key)
        values[key] = None if not selected else ordinary(Path(selected))
        pin_name = "native_provider_sha256" if key == "native_provider_binding" else key + "_sha256"
        raw = None if not selected else snapshot(values[key])
        if selected and raw is None:
            raise SetupRejected("selected_binding_missing")
        values[pin_name] = None if raw is None else digest(raw)
    report = _export_runtime(argparse.Namespace(**values))
    runtime_import(root, values["output"], values["context"])
    return {
        **NO_EXECUTION,
        **report,
        "journal_created": False,
        "next": "로컬 runtime 파일을 만들었습니다. 기존 장부 참조를 유지하고 "
        "VM preflight·회로 등록·실행 승인을 별도로 확인하세요.",
    }


def client_entry(root: Path, settings: Path, context: str, launcher: Path) -> dict[str, Any]:
    ordinary(launcher)
    if not launcher.is_file() or launcher.name != "CadenceMCPBridge.exe":
        raise SetupRejected("installed_launcher_required")
    marker = snapshot(launcher.parent / "INSTALLATION.json")
    if marker is None or json.loads(marker) != {"version": __version__, "kind": "per-user"}:
        raise SetupRejected("installed_location_required_not_build_folder")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="client-preview-", dir=root) as folder:
        output = Path(folder) / "fragment.toml"
        export_context_client_config(settings, context, output, format="codex")
        # A preview must survive JSON persistence/restart without TOML trivia
        # changing its after hash. Retain semantic settings as plain JSON types.
        entry: dict[str, Any] = json.loads(
            json.dumps(parse(output.read_bytes())["mcp_servers"]["cadence-mcp-bridge"])
        )
    entry["command"] = str(launcher)
    entry["args"] = ["serve-operator"]
    return entry


def dispatch(
    request: dict[str, Any], *, root: Path | None = None, launcher: Path | None = None
) -> dict[str, Any]:
    root = data_root() if root is None else root
    launcher = (
        Path(sys.executable).parent.parent / "CadenceMCPBridge.exe"
        if launcher is None
        else launcher
    )
    action = request.get("action")
    if action == "status":
        return host_status(root)
    if action == "guide":
        mode = request.get("mode")
        if mode not in ("fresh", "existing", "program-only"):
            raise SetupRejected("setup_mode_invalid")
        state = state_read(root)
        state["mode"] = mode
        state_write(root, state)
        return {
            **NO_EXECUTION,
            "status": "HOST_INSTALLED",
            "mode": mode,
            "guide": setup_guide("existing" if mode == "program-only" else mode),
            "next": "새 설정은 연결 정보 저장 → 본인 환경/회로/PDK 등록 → runtime 선택 순서입니다. "
            "기존 VM 이력은 새 장부로 대체하지 않습니다.",
        }
    if action == "save-connection":
        draft = connection_draft(request)
        state = state_read(root)
        state["connection"] = draft
        state_write(root, state)
        return {
            **NO_EXECUTION,
            "status": "CONNECTION_DRAFT_SAVED",
            "ssh_configuration_applied": False,
            "host_key_verified": False,
        }
    if action == "connect":
        return connect(request)
    if action == "starter":
        result = export_starter(Path(request["output"]))
        return {**NO_EXECUTION, **result, "examples_only": True, "production_ready": False}
    if action == "runtime":
        return runtime_import(root, Path(request["settings"]), request.get("context", ""))
    if action == "create-runtime":
        return runtime_create(root, request)
    if action == "preview":
        entry = client_entry(root, Path(request["settings"]), request["context"], launcher)
        plan = preview(
            codex_config(),
            request["name"],
            entry,
            replace=request.get("replace") is True,
            project=Path(request["project"]) if request.get("project") else None,
        )
        state = state_read(root)
        state["pending_config"] = plan
        state_write(root, state)
        return {**NO_EXECUTION, "status": "PREVIEW_REQUIRES_CONFIRMATION", **plan}
    if action == "apply":
        if request.get("consent") is not True:
            raise SetupRejected("explicit_config_consent_required")
        state = state_read(root)
        plan = state.get("pending_config", {})
        if not plan:
            raise SetupRejected("preview_required")
        if request.get("after") != plan["after"] or Path(plan["path"]) != codex_config():
            raise SetupRejected("preview_changed")
        history = root / "config-history"
        history.mkdir(parents=True, exist_ok=True)
        # A missing Codex installation is allowed; the explicit local config
        # apply may create its selected home, not mark the app itself as connected.
        codex_config().parent.mkdir(parents=True, exist_ok=True)
        result = apply(plan, history)
        if "receipt" in result:
            state.setdefault("receipts", []).append(result["receipt"])
        state.pop("pending_config", None)
        state_write(root, state)
        return {**NO_EXECUTION, **result}
    if action == "remove":
        if request.get("consent") is not True:
            raise SetupRejected("explicit_removal_consent_required")
        state = state_read(root)
        receipt = request["receipt"]
        from cadence_mcp_bridge.windows_host.uninstall import owned_receipts

        if receipt not in state.get("receipts", []) and Path(receipt) not in owned_receipts(
            root, launcher
        ):
            raise SetupRejected("unmanaged_receipt")
        return {**NO_EXECUTION, **remove_managed(Path(receipt), root / "config-history")}
    raise SetupRejected("unknown_setup_action")


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise SetupRejected("request_too_large")
        result = dispatch(json.loads(raw))
    except (OSError, ValueError, KeyError, TypeError) as error:
        # No raw exception text, SSH output, config contents or credential data.
        reason = str(error) if isinstance(error, SetupRejected) else "setup_input_or_file_invalid"
        guidance = {
            "preview_changed": "설정 미리보기를 새로 만들고 표시된 변경을 다시 확인하세요.",
            "configuration_changed_preview_again": "다른 앱이 설정을 변경했습니다. 덮어쓰지 "
            "않았습니다. 미리보기를 다시 실행하세요.",
            "name_conflict_choose_update_another_name_or_cancel": "같은 MCP 이름이 있습니다. "
            "업데이트를 선택하거나 다른 이름을 입력하세요.",
            "installed_location_required_not_build_folder": "설치 EXE로 설치한 도우미를 여세요. "
            "빌드/임시 경로를 Codex에 등록하지 않습니다.",
            "setup_input_or_file_invalid": "선택한 파일이 존재하고 본인 runtime인지 확인하세요. "
            "context ID는 먼저 빈 칸으로 확인해 목록에서 선택할 수 있습니다.",
            "openssh_client_missing": "Windows 선택적 기능에서 OpenSSH Client를 설치한 뒤 "
            "연결 확인을 실행하세요. 프로그램 설치는 완료됐습니다.",
            "configuration_busy": "다른 설정 저장 작업이 진행 중입니다. 완료 후 다시 확인하세요. "
            "중단된 프로세스의 잠금은 Windows가 자동 해제합니다.",
        }.get(reason, "입력과 파일 권한을 확인하세요. 기존 설정·journal은 보존했습니다.")
        result = {
            **NO_EXECUTION,
            "status": "BLOCKED",
            "reason": reason,
            "guidance": guidance,
        }
    print(json.dumps(result, ensure_ascii=True))
    return 1 if result.get("status") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
