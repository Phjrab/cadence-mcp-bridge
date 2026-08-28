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
    assert run.call_args.args[0][-2:] == ["submit-smoke", str(job_id)]


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
    }
    monkeypatch.setattr(
        "cadence_mcp_bridge.ssh_backend.subprocess.run",
        Mock(return_value=completed(json.dumps(payload).encode("ascii"))),
    )

    result = await backend.result(job_id)

    assert result.summary.notices == 1
    assert result.artifacts[0].relative_path == "artifacts/smoke.log"


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
    token = "ghp_abcdefghijklmnopqrstuvwxyz123456"
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

    assert public_methods == {"cancel", "health", "log_tail", "result", "status", "submit_smoke"}
    assert "profile" not in inspect.signature(backend.submit_smoke).parameters


def test_missing_ssh_executable_is_backend_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.shutil.which", lambda _: None)

    with pytest.raises(BackendUnavailableError):
        OpenSshBackend(BridgeConfig())
