from __future__ import annotations

import inspect
import json
import subprocess
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

import pytest

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import (
    AuthenticationError,
    BackendUnavailableError,
    HostKeyError,
    InvalidInputError,
    OperationTimeoutError,
    RemoteFailureError,
)
from cadence_mcp_bridge.models import NoProfileVariables, RcTransientVariables
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

SSH_EXE = r"C:\Windows\System32\OpenSSH\ssh.exe"


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> OpenSshBackend:
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.shutil.which", lambda _: SSH_EXE)
    return OpenSshBackend(BridgeConfig())


def completed(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> Any:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


@pytest.mark.asyncio
async def test_health_uses_fixed_argv_without_a_shell(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "ssh": "ok",
        "remote_host": "cadence-host",
        "remote_user": "buet",
        "remote_root_accessible": True,
        "virtuoso": {"available": True, "version": "IC6.1.5"},
        "spectre": {"available": True, "version": "12.1"},
        "ocean": {"available": True},
        "license_env": {"CDS_LIC_FILE": "SET"},
        "runner_version": "0.2.0",
    }
    run = Mock(return_value=completed(json.dumps(payload).encode("ascii")))
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    report = await backend.health()

    assert report.runner_version == "0.2.0"
    argv = run.call_args.args[0]
    assert argv == [
        SSH_EXE,
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
        "cadence-vm",
        "/home/buet/cds_work/.cadence_mcp/bin/cadence-runner",
        "health",
    ]
    assert run.call_args.kwargs == {
        "shell": False,
        "capture_output": True,
        "check": False,
        "timeout": 120,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malicious",
    ["abc;rm -rf x", "../x", "$(id)", "`id`", "a\nb", "*", "--help"],
)
async def test_malicious_job_ids_are_rejected_before_subprocess(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch, malicious: str
) -> None:
    run = Mock()
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    with pytest.raises(InvalidInputError):
        await backend.status(cast(Any, malicious))

    run.assert_not_called()


@pytest.mark.asyncio
async def test_submit_smoke_maps_runner_status(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = uuid4()
    payload = {
        "job_id": str(job_id),
        "state": "queued",
        "profile": "spectre-smoke",
        "updated_at": "2026-08-28T00:00:00Z",
        "message": "job queued",
    }
    run = Mock(return_value=completed(json.dumps(payload).encode("ascii")))
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    status = await backend.submit_smoke(job_id)

    assert status.job_id == job_id
    assert status.submitted_at == status.updated_at
    assert run.call_args.args[0][-3:] == ["submit-smoke", str(job_id), "mcp"]


@pytest.mark.asyncio
async def test_result_maps_structured_summary_and_artifacts(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = uuid4()
    payload = {
        "job_id": str(job_id),
        "state": "succeeded",
        "exit_code": 0,
        "summary": {"text": "complete", "errors": 0, "warnings": 0, "notices": 1},
        "artifacts": [
            {
                "name": "smoke.log",
                "relative_path": "artifacts/smoke.log",
                "media_type": "text/plain",
                "size_bytes": 12,
            }
        ],
        "storage": {"contained": True, "directory_mode": "0700"},
    }
    monkeypatch.setattr(
        "cadence_mcp_bridge.ssh_backend.subprocess.run",
        Mock(return_value=completed(json.dumps(payload).encode("ascii"))),
    )

    result = await backend.result(job_id)

    assert result.summary.notices == 1
    assert result.artifacts[0].relative_path == "artifacts/smoke.log"
    assert result.storage is not None
    assert result.storage.directory_mode == "0700"


@pytest.mark.asyncio
async def test_log_tail_validates_stream_and_line_limit_before_subprocess(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Mock()
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    with pytest.raises(InvalidInputError):
        await backend.log_tail(uuid4(), cast(Any, "combined"), 10)
    with pytest.raises(InvalidInputError):
        await backend.log_tail(uuid4(), "stdout", 201)

    run.assert_not_called()


@pytest.mark.asyncio
async def test_discovery_commands_use_fixed_runner_argv(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = [
        {
            "libraries": [{"name": "MyFirstDesign", "allowed_cell_count": 1}],
            "allowlist_enforced": True,
            "proprietary_content_included": False,
        },
        {
            "library": "MyFirstDesign",
            "cells": ["NOT_gate"],
            "allowlist_enforced": True,
            "proprietary_content_included": False,
        },
        {
            "library": "MyFirstDesign",
            "cell": "NOT_gate",
            "view": "schematic",
            "exists": True,
            "kind": "cellview",
            "allowlist_enforced": True,
            "proprietary_content_included": False,
        },
    ]
    run = Mock(side_effect=[completed(json.dumps(item).encode("ascii")) for item in payloads])
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    await backend.list_libraries()
    await backend.list_cells("MyFirstDesign")
    await backend.inspect_cellview("MyFirstDesign", "NOT_gate", "schematic")

    assert run.call_args_list[0].args[0][-1:] == ["list-libraries"]
    assert run.call_args_list[1].args[0][-2:] == ["list-cells", "MyFirstDesign"]
    assert run.call_args_list[2].args[0][-4:] == [
        "inspect-cellview",
        "MyFirstDesign",
        "NOT_gate",
        "schematic",
    ]


@pytest.mark.asyncio
async def test_submit_profile_uses_fixed_safe_runner_arguments(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = uuid4()
    payload = {
        "job_id": str(job_id),
        "state": "queued",
        "profile": "fixture-rc-transient",
        "updated_at": "2026-08-28T00:00:00Z",
        "message": "profile job queued",
    }
    run = Mock(return_value=completed(json.dumps(payload).encode("ascii")))
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    status = await backend.submit_profile(
        job_id, "fixture-rc-transient", "nominal", RcTransientVariables()
    )

    assert status.profile == "fixture-rc-transient"
    assert run.call_args.args[0][-8:] == [
        "submit-profile",
        str(job_id),
        "fixture-rc-transient",
        "nominal",
        "1000",
        "9.9999999999999998e-13",
        "1.0000000000000001e-09",
        "mcp",
    ]


@pytest.mark.asyncio
async def test_submit_actual_profile_uses_no_path_or_variable_arguments(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = uuid4()
    payload = {
        "job_id": str(job_id),
        "state": "queued",
        "profile": "actual-differential-amplifier-tb2-transient",
        "updated_at": "2026-08-28T00:00:00Z",
        "message": "profile job queued",
    }
    run = Mock(return_value=completed(json.dumps(payload).encode("ascii")))
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    status = await backend.submit_profile(
        job_id,
        "actual-differential-amplifier-tb2-transient",
        "NN",
        NoProfileVariables(),
    )

    assert status.profile == "actual-differential-amplifier-tb2-transient"
    assert run.call_args.args[0][-5:] == [
        "submit-profile",
        str(job_id),
        "actual-differential-amplifier-tb2-transient",
        "NN",
        "mcp",
    ]


@pytest.mark.asyncio
async def test_design_write_plan_uses_no_caller_arguments(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "policy_version": 2,
        "plan_id": "mcp-cellview-property-v2",
        "plan_sha256": "a" * 64,
        "source": "MyDesignLib/Differential_Amplifier_TB2/schematic",
        "target": "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic",
        "backup": "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic",
        "preserved_target": "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic",
        "operation": "set_cellview_property",
        "property_name": "mcpMutationTest",
        "old_value": None,
        "proposed_value": "validated-v1",
        "affected_objects": 1,
        "original_library_mutations": 0,
        "destructive": False,
        "source_exists": True,
        "source_artifact_present": False,
        "target_exists": False,
        "backup_exists": False,
        "preserved_target_exists": True,
        "ready": True,
        "confirmation": "APPROVE_MCP_WRITE_VALIDATED_V2",
    }
    run = Mock(return_value=completed(json.dumps(payload).encode("ascii")))
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    plan = await backend.design_write_plan()

    assert plan.ready is True
    assert run.call_args.args[0][-1:] == ["design-write-plan"]


@pytest.mark.asyncio
async def test_design_write_validation_passes_only_uuid_confirmation_and_origin(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation_id = uuid4()
    payload = {
        "validation_id": str(validation_id),
        "plan_id": "mcp-cellview-property-v2",
        "plan_sha256": "a" * 64,
        "source": "MyDesignLib/Differential_Amplifier_TB2/schematic",
        "target": "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic",
        "backup": "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic",
        "preserved_target": "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic",
        "operation": "set_cellview_property",
        "property_name": "mcpMutationTest",
        "old_value": None,
        "proposed_value": "validated-v1",
        "affected_objects": 1,
        "original_library_mutations": 0,
        "destructive": False,
        "copy_verified": True,
        "dry_run_unchanged": True,
        "backup_verified": True,
        "apply_verified": True,
        "rollback_verified": True,
        "source_unchanged": True,
        "preserved_target_unchanged": True,
        "topology_unchanged": True,
        "baseline_fingerprint": "a" * 64,
        "rollback_fingerprint": "a" * 64,
        "audit_recorded": True,
        "sequence": [
            "source_verify",
            "copy",
            "baseline",
            "dry_run",
            "dry_run_unchanged",
            "backup",
            "apply",
            "verify_apply",
            "source_unchanged_before_rollback",
            "rollback",
            "verify_rollback",
            "source_unchanged",
            "complete",
        ],
    }
    run = Mock(return_value=completed(json.dumps(payload).encode("ascii")))
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    result = await backend.execute_design_write_validation(
        validation_id, "APPROVE_MCP_WRITE_VALIDATED_V2"
    )

    assert result.rollback_verified is True
    assert run.call_args.args[0][-4:] == [
        "design-write-validate",
        str(validation_id),
        "APPROVE_MCP_WRITE_VALIDATED_V2",
        "mcp",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("profile_id", ["../x", "x;id", "$(id)", "--help"])
async def test_malicious_profile_ids_are_rejected_before_subprocess(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch, profile_id: str
) -> None:
    run = Mock()
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    with pytest.raises(InvalidInputError):
        await backend.submit_profile(uuid4(), profile_id, "nominal", RcTransientVariables())

    run.assert_not_called()


@pytest.mark.asyncio
async def test_operation_timeout_is_distinct(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Mock(side_effect=subprocess.TimeoutExpired([SSH_EXE], 120))
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    with pytest.raises(OperationTimeoutError):
        await backend.health()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        (b"Host key verification failed.", HostKeyError),
        (b"Permission denied (publickey).", AuthenticationError),
        (b"Connection timed out", BackendUnavailableError),
        (b"runner exploded", RemoteFailureError),
    ],
)
async def test_nonzero_exit_maps_stable_error(
    backend: OpenSshBackend,
    monkeypatch: pytest.MonkeyPatch,
    stderr: bytes,
    expected: type[Exception],
) -> None:
    monkeypatch.setattr(
        "cadence_mcp_bridge.ssh_backend.subprocess.run",
        Mock(return_value=completed(stderr=stderr, returncode=255)),
    )

    with pytest.raises(expected):
        await backend.health()


@pytest.mark.asyncio
async def test_error_details_are_sanitized(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"
    stderr = f"failure {token} C:\\Users\\private-user\\key".encode()
    monkeypatch.setattr(
        "cadence_mcp_bridge.ssh_backend.subprocess.run",
        Mock(return_value=completed(stderr=stderr, returncode=70)),
    )

    with pytest.raises(RemoteFailureError) as captured:
        await backend.health()

    envelope = captured.value.to_envelope()
    assert token not in str(envelope.details)
    assert "private-user" not in str(envelope.details)


@pytest.mark.asyncio
async def test_output_byte_limit_is_enforced(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "cadence_mcp_bridge.ssh_backend.subprocess.run",
        Mock(return_value=completed(stdout=b"x" * 65_537)),
    )

    with pytest.raises(RemoteFailureError, match="byte limit"):
        await backend.health()


def test_backend_has_no_public_raw_command_method(backend: OpenSshBackend) -> None:
    public_methods = {name for name in dir(backend) if not name.startswith("_")}

    assert public_methods == {
        "cancel",
        "design_write_plan",
        "execute_design_write_validation",
        "health",
        "inspect_cellview",
        "list_cells",
        "list_libraries",
        "log_tail",
        "result",
        "status",
        "submit_profile",
        "submit_smoke",
    }
    assert "profile" not in inspect.signature(backend.submit_smoke).parameters


def test_missing_ssh_executable_is_backend_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.shutil.which", lambda _: None)

    with pytest.raises(BackendUnavailableError):
        OpenSshBackend(BridgeConfig())
