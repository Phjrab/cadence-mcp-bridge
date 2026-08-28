"""Allowlisted Windows OpenSSH transport for the fixed remote runner."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import (
    AuthenticationError,
    BackendUnavailableError,
    HostKeyError,
    InvalidInputError,
    OperationTimeoutError,
    RemoteFailureError,
)
from cadence_mcp_bridge.models import (
    ArtifactMetadata,
    HealthReport,
    JobResult,
    JobState,
    JobStatus,
    JobSummary,
)
from cadence_mcp_bridge.sanitization import sanitize_text


class _RunnerCommand(StrEnum):
    HEALTH = "health"
    SUBMIT_SMOKE = "submit-smoke"
    STATUS = "status"
    LOG_TAIL = "log-tail"
    RESULT = "result"
    CANCEL = "cancel"


class _RunnerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _RunnerStatus(_RunnerModel):
    job_id: UUID
    state: JobState
    profile: str
    updated_at: datetime
    message: str | None = None


class _RunnerArtifact(_RunnerModel):
    name: str
    relative_path: str
    media_type: str
    size_bytes: int


class _RunnerSummary(_RunnerModel):
    text: str
    errors: int
    warnings: int
    notices: int


class _RunnerResult(_RunnerModel):
    job_id: UUID
    state: JobState
    exit_code: int | None = None
    summary: _RunnerSummary
    artifacts: tuple[_RunnerArtifact, ...] = ()


_ModelT = TypeVar("_ModelT", bound=BaseModel)


class OpenSshBackend:
    """Typed facade over the runner; deliberately exposes no raw command method."""

    _SERVER_ALIVE_INTERVAL_SECONDS = 15
    _SERVER_ALIVE_COUNT_MAX = 2

    def __init__(self, config: BridgeConfig) -> None:
        self._config = config
        executable = shutil.which("ssh.exe")
        if executable is None:
            raise BackendUnavailableError("Windows OpenSSH ssh.exe is unavailable")
        self._ssh_executable = executable

    async def health(self) -> HealthReport:
        payload = await self._invoke_json(_RunnerCommand.HEALTH)
        return self._validate(HealthReport, payload)

    async def submit_smoke(self, job_id: UUID) -> JobStatus:
        safe_job_id = self._job_id(job_id)
        payload = await self._invoke_json(_RunnerCommand.SUBMIT_SMOKE, safe_job_id)
        status = self._validate(_RunnerStatus, payload)
        return self._status(status, submitted=True)

    async def status(self, job_id: UUID) -> JobStatus:
        payload = await self._invoke_json(_RunnerCommand.STATUS, self._job_id(job_id))
        return self._status(self._validate(_RunnerStatus, payload))

    async def log_tail(
        self,
        job_id: UUID,
        stream: Literal["stdout", "stderr"],
        lines: Annotated[int, Field(ge=1, le=200)] = 100,
    ) -> str:
        safe_job_id = self._job_id(job_id)
        if stream not in ("stdout", "stderr"):
            raise InvalidInputError("log stream must be stdout or stderr")
        if isinstance(lines, bool) or not isinstance(lines, int) or not 1 <= lines <= 200:
            raise InvalidInputError("log line count must be between 1 and 200")
        return await asyncio.to_thread(
            self._invoke,
            _RunnerCommand.LOG_TAIL,
            safe_job_id,
            stream,
            str(lines),
        )

    async def result(self, job_id: UUID) -> JobResult:
        payload = await self._invoke_json(_RunnerCommand.RESULT, self._job_id(job_id))
        result = self._validate(_RunnerResult, payload)
        return JobResult(
            job_id=result.job_id,
            state=result.state,
            exit_code=result.exit_code,
            summary=JobSummary(
                text=result.summary.text,
                errors=result.summary.errors,
                warnings=result.summary.warnings,
                notices=result.summary.notices,
            ),
            artifacts=tuple(
                ArtifactMetadata(
                    name=artifact.name,
                    relative_path=artifact.relative_path,
                    media_type=artifact.media_type,
                    size_bytes=artifact.size_bytes,
                )
                for artifact in result.artifacts
            ),
        )

    async def cancel(self, job_id: UUID) -> JobStatus:
        payload = await self._invoke_json(_RunnerCommand.CANCEL, self._job_id(job_id))
        return self._status(self._validate(_RunnerStatus, payload))

    async def _invoke_json(self, command: _RunnerCommand, *arguments: str) -> dict[str, Any]:
        output = await asyncio.to_thread(self._invoke, command, *arguments)
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RemoteFailureError("Remote runner returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RemoteFailureError("Remote runner returned an invalid payload")
        return payload

    def _invoke(self, command: _RunnerCommand, *arguments: str) -> str:
        argv = [
            self._ssh_executable,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"ConnectTimeout={self._config.connect_timeout_seconds}",
            "-o",
            f"ServerAliveInterval={self._SERVER_ALIVE_INTERVAL_SECONDS}",
            "-o",
            f"ServerAliveCountMax={self._SERVER_ALIVE_COUNT_MAX}",
            self._config.ssh_alias,
            self._config.runner_path,
            command.value,
            *arguments,
        ]
        try:
            completed = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                check=False,
                timeout=self._config.operation_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise OperationTimeoutError("Remote operation timed out") from exc
        except OSError as exc:
            raise BackendUnavailableError("Windows OpenSSH could not be started") from exc

        self._check_output_size(completed.stdout, "stdout")
        self._check_output_size(completed.stderr, "stderr")
        stdout = self._decode(completed.stdout)
        stderr = self._decode(completed.stderr)
        if completed.returncode != 0:
            self._raise_remote_error(completed.returncode, stderr)
        return stdout

    def _check_output_size(self, output: bytes, stream: str) -> None:
        if len(output) > self._config.max_output_bytes:
            raise RemoteFailureError(
                "Remote output exceeded the configured byte limit",
                details={"stream": stream, "limit": self._config.max_output_bytes},
            )

    @staticmethod
    def _decode(output: bytes) -> str:
        try:
            return output.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise RemoteFailureError("Remote runner returned non-UTF-8 output") from exc

    @staticmethod
    def _job_id(job_id: UUID) -> str:
        if not isinstance(job_id, UUID):
            raise InvalidInputError("job_id must be a UUID")
        return str(job_id)

    @staticmethod
    def _validate(model: type[_ModelT], payload: dict[str, Any]) -> _ModelT:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise RemoteFailureError("Remote runner returned an invalid payload") from exc

    @staticmethod
    def _status(status: _RunnerStatus, *, submitted: bool = False) -> JobStatus:
        return JobStatus(
            job_id=status.job_id,
            state=status.state,
            profile=status.profile,
            submitted_at=status.updated_at if submitted else None,
            updated_at=status.updated_at,
            message=status.message,
        )

    @staticmethod
    def _raise_remote_error(returncode: int, stderr: str) -> None:
        lowered = stderr.lower()
        details = {
            "exit_code": returncode,
            "stderr": sanitize_text(stderr, max_length=1_024),
        }
        if "host key verification failed" in lowered or "identification has changed" in lowered:
            raise HostKeyError("SSH host key verification failed", details=details)
        if "permission denied" in lowered or "authentication failed" in lowered:
            raise AuthenticationError("SSH authentication failed", details=details)
        if any(
            marker in lowered
            for marker in (
                "connection refused",
                "connection timed out",
                "could not resolve hostname",
                "network is unreachable",
                "no route to host",
            )
        ):
            raise BackendUnavailableError("SSH backend is unavailable", details=details)
        if returncode == 64:
            raise InvalidInputError("Remote runner rejected the request", details=details)
        raise RemoteFailureError("Remote runner failed", details=details)
