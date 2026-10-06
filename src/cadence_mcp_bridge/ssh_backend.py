"""Allowlisted Windows OpenSSH transport for the fixed remote runner."""

from __future__ import annotations

import asyncio
import ctypes
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cadence_mcp_bridge.actual_diagnostics import (
    ActualDiagnosticRequest,
    ActualDiagnosticResult,
    ActualDiagnosticStatus,
)
from cadence_mcp_bridge.bandwidth_study import RefinementExtraction
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import (
    AuthenticationError,
    BackendUnavailableError,
    BridgeError,
    HostKeyError,
    InvalidInputError,
    OperationTimeoutError,
    RemoteFailureError,
)
from cadence_mcp_bridge.models import (
    ArtifactMetadata,
    CellList,
    CellViewInspection,
    HealthReport,
    JobLogTail,
    JobOrigin,
    JobResult,
    JobState,
    JobStatus,
    JobStorageMetadata,
    JobSummary,
    LibraryList,
    NoProfileVariables,
    ProfileVariables,
    RcTransientVariables,
    ResultLimitMetadata,
)
from cadence_mcp_bridge.native_diagnostics import (
    NativeDiagnosticRequest,
    NativeDiagnosticResult,
    NativeDiagnosticStatus,
)
from cadence_mcp_bridge.offset_study import OffsetExtraction
from cadence_mcp_bridge.power_measurements import REFERENCE_OPERATION, PowerExtraction
from cadence_mcp_bridge.profiles import ACTUAL_PROFILE_ID, FIXTURE_PROFILE_ID
from cadence_mcp_bridge.sanitization import sanitize_text
from cadence_mcp_bridge.slew_study import StepExtraction
from cadence_mcp_bridge.storage import CleanupOutcome, CleanupRequest, StorageSnapshot
from cadence_mcp_bridge.write_models import (
    DesignWritePlan,
    DesignWriteValidationResult,
    WriteConfirmation,
)


class _RunnerCommand(StrEnum):
    HEALTH = "health"
    SUBMIT_SMOKE = "submit-smoke"
    STATUS = "status"
    LOG_TAIL = "log-tail"
    RESULT = "result"
    CANCEL = "cancel"
    LIST_LIBRARIES = "list-libraries"
    LIST_CELLS = "list-cells"
    INSPECT_CELLVIEW = "inspect-cellview"
    SUBMIT_PROFILE = "submit-profile"
    DESIGN_WRITE_PLAN = "design-write-plan"
    DESIGN_WRITE_VALIDATE = "design-write-validate"


class _RunnerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _RunnerStatus(_RunnerModel):
    job_id: UUID
    state: JobState
    profile: str
    origin: JobOrigin = JobOrigin.MCP
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


class _RunnerStorage(_RunnerModel):
    contained: Literal[True]
    directory_mode: Literal["0700"]


class _RunnerLimits(_RunnerModel):
    response_limit_bytes: Literal[65_536]
    artifacts_total: int
    artifacts_returned: int
    artifacts_truncated: bool
    summary_original_chars: int
    summary_returned_chars: int
    summary_truncated: bool


class _RunnerResult(_RunnerModel):
    job_id: UUID
    state: JobState
    exit_code: int | None = None
    summary: _RunnerSummary
    artifacts: tuple[_RunnerArtifact, ...] = ()
    storage: _RunnerStorage | None = None
    origin: JobOrigin = JobOrigin.MCP
    limits: _RunnerLimits | None = None


class _RunnerLogTail(_RunnerModel):
    job_id: UUID
    stream: Literal["stdout", "stderr"]
    lines_requested: int
    text: str
    limit_bytes: Literal[65_536]
    original_bytes: int | None
    returned_bytes: int
    truncated: bool


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

    async def storage_snapshot(self) -> StorageSnapshot:
        output = await self._storage_request("inventory", {})
        return self._validate(StorageSnapshot, json.loads(output))

    async def storage_cleanup(self, request: CleanupRequest) -> CleanupOutcome:
        output = await self._storage_request("cleanup", request.model_dump(mode="json"))
        return self._validate(CleanupOutcome, json.loads(output))

    async def _storage_request(
        self, action: Literal["inventory", "cleanup"], request: dict[str, Any]
    ) -> str:
        if self._config.remote_root != "/home/buet/cds_work/.cadence_mcp":
            raise InvalidInputError("storage requires the reviewed managed root")
        raw = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "ascii"
        )
        if len(raw) > 8192:
            raise InvalidInputError("storage request bound exceeded")
        runner = self._config.remote_root + "/phase-campaign/storage-mgmt-v6/run.sh"
        return await asyncio.to_thread(self._invoke_at_path, runner, action, raw.hex())

    async def health(self) -> HealthReport:
        payload = await self._invoke_json(_RunnerCommand.HEALTH)
        return self._validate(HealthReport, payload)

    async def submit_smoke(self, job_id: UUID) -> JobStatus:
        safe_job_id = self._job_id(job_id)
        payload = await self._invoke_json(_RunnerCommand.SUBMIT_SMOKE, safe_job_id, "mcp")
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
    ) -> JobLogTail:
        safe_job_id = self._job_id(job_id)
        if stream not in ("stdout", "stderr"):
            raise InvalidInputError("log stream must be stdout or stderr")
        if isinstance(lines, bool) or not isinstance(lines, int) or not 1 <= lines <= 200:
            raise InvalidInputError("log line count must be between 1 and 200")
        payload = await self._invoke_json(_RunnerCommand.LOG_TAIL, safe_job_id, stream, str(lines))
        remote = self._validate(_RunnerLogTail, payload)
        if remote.job_id != job_id or remote.stream != stream or remote.lines_requested != lines:
            raise RemoteFailureError("Remote runner returned mismatched log metadata")
        safe_text = sanitize_text(remote.text, max_length=65_536)
        return JobLogTail(
            job_id=remote.job_id,
            stream=remote.stream,
            lines_requested=remote.lines_requested,
            text=safe_text,
            limit_bytes=remote.limit_bytes,
            original_bytes=remote.original_bytes,
            returned_bytes=len(safe_text.encode("utf-8")),
            truncated=remote.truncated,
            redacted=safe_text != remote.text,
        )

    async def result(self, job_id: UUID) -> JobResult:
        payload = await self._invoke_json(_RunnerCommand.RESULT, self._job_id(job_id))
        result = self._validate(_RunnerResult, payload)
        return JobResult(
            job_id=result.job_id,
            state=result.state,
            exit_code=result.exit_code,
            summary=JobSummary(
                text=sanitize_text(result.summary.text, max_length=512),
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
            storage=(
                JobStorageMetadata(
                    contained=result.storage.contained,
                    directory_mode=result.storage.directory_mode,
                )
                if result.storage is not None
                else None
            ),
            origin=result.origin,
            limits=(
                ResultLimitMetadata.model_validate(result.limits.model_dump())
                if result.limits is not None
                else ResultLimitMetadata(
                    artifacts_total=len(result.artifacts),
                    artifacts_returned=len(result.artifacts),
                    summary_original_chars=len(result.summary.text),
                    summary_returned_chars=len(result.summary.text),
                )
            ),
        )

    async def cancel(self, job_id: UUID) -> JobStatus:
        payload = await self._invoke_json(_RunnerCommand.CANCEL, self._job_id(job_id))
        return self._status(self._validate(_RunnerStatus, payload))

    async def list_libraries(self) -> LibraryList:
        payload = await self._invoke_json(_RunnerCommand.LIST_LIBRARIES)
        return self._validate(LibraryList, payload)

    async def list_cells(self, library: str) -> CellList:
        payload = await self._invoke_json(_RunnerCommand.LIST_CELLS, library)
        return self._validate(CellList, payload)

    async def inspect_cellview(self, library: str, cell: str, view: str) -> CellViewInspection:
        payload = await self._invoke_json(_RunnerCommand.INSPECT_CELLVIEW, library, cell, view)
        return self._validate(CellViewInspection, payload)

    async def submit_profile(
        self,
        job_id: UUID,
        profile_id: str,
        corner: str,
        variables: ProfileVariables,
    ) -> JobStatus:
        arguments = [
            self._job_id(job_id),
            self._safe_token(profile_id, "profile"),
            self._safe_token(corner, "corner"),
        ]
        if profile_id == FIXTURE_PROFILE_ID and isinstance(variables, RcTransientVariables):
            arguments.extend(
                (
                    self._number(variables.resistance_ohm),
                    self._number(variables.capacitance_f),
                    self._number(variables.stop_time_s),
                )
            )
        elif profile_id == ACTUAL_PROFILE_ID and isinstance(variables, NoProfileVariables):
            pass
        else:
            raise InvalidInputError("profile variables do not match the reviewed profile")
        arguments.append("mcp")
        payload = await self._invoke_json(_RunnerCommand.SUBMIT_PROFILE, *arguments)
        return self._status(self._validate(_RunnerStatus, payload), submitted=True)

    async def design_write_plan(self) -> DesignWritePlan:
        payload = await self._invoke_json(_RunnerCommand.DESIGN_WRITE_PLAN)
        return self._validate(DesignWritePlan, payload)

    async def execute_design_write_validation(
        self,
        validation_id: UUID,
        confirmation: WriteConfirmation,
    ) -> DesignWriteValidationResult:
        payload = await self._invoke_json(
            _RunnerCommand.DESIGN_WRITE_VALIDATE,
            self._job_id(validation_id),
            confirmation,
            "mcp",
        )
        result = self._validate(DesignWriteValidationResult, payload)
        if result.validation_id != validation_id:
            raise RemoteFailureError("Remote runner returned a mismatched validation_id")
        return result

    async def submit_actual_diagnostic(
        self, job_id: UUID, request: ActualDiagnosticRequest
    ) -> ActualDiagnosticStatus:
        return self._validate(
            ActualDiagnosticStatus,
            await self._invoke_diagnostic_json("submit", job_id, request.analysis),
        )

    async def reserve_sweep_attempt(self, job_id: UUID) -> None:
        result = await self._invoke_sweep_budget("reserve", job_id)
        if result != {"reserved": True}:
            raise RemoteFailureError("Sweep budget reservation was not confirmed")

    async def lookup_sweep_reservation(self, job_id: UUID) -> bool:
        result = await self._invoke_sweep_budget("lookup", job_id)
        if result not in ({"reserved": True}, {"reserved": False}):
            raise RemoteFailureError("Sweep budget lookup returned invalid data")
        return bool(result["reserved"])

    async def effective_sweep_values(self, job_id: UUID) -> dict[str, str]:
        result = await self._invoke_sweep_budget("effective", job_id)
        variables = result.get("variables")
        expected = {"resistance_ohm": "ohm", "capacitance_f": "F", "stop_time_s": "s"}
        if not isinstance(variables, dict) or set(variables) != set(expected):
            raise RemoteFailureError("Effective fixture variables missing")
        values: dict[str, str] = {}
        for name, unit in expected.items():
            item = variables[name]
            if (
                not isinstance(item, dict)
                or item.get("unit") != unit
                or not isinstance(item.get("value"), str)
            ):
                raise RemoteFailureError("Effective fixture variable invalid")
            values[name] = item["value"]
        return values

    async def _invoke_sweep_budget(
        self, action: Literal["reserve", "lookup", "effective"], job_id: UUID
    ) -> dict[str, Any]:
        if self._config.remote_root != "/home/buet/cds_work/.cadence_mcp":
            raise InvalidInputError("sweep budget requires the reviewed managed root")
        runner = f"{self._config.remote_root}/phase-campaign/sweep-mcp-v2/run.sh"
        output = await asyncio.to_thread(self._invoke_at_path, runner, action, self._job_id(job_id))
        try:
            value = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RemoteFailureError("Sweep budget returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise RemoteFailureError("Sweep budget returned invalid data")
        return value

    async def actual_diagnostic_status(
        self, job_id: UUID, analysis: Literal["dc", "ac"]
    ) -> ActualDiagnosticStatus:
        return self._validate(
            ActualDiagnosticStatus,
            await self._invoke_diagnostic_json("status", job_id, analysis),
        )

    async def actual_diagnostic_result(
        self, job_id: UUID, analysis: Literal["dc", "ac"]
    ) -> ActualDiagnosticResult:
        return self._validate(
            ActualDiagnosticResult,
            await self._invoke_diagnostic_json("result", job_id, analysis),
        )

    async def _invoke_diagnostic_json(
        self,
        action: Literal["submit", "status", "result"],
        job_id: UUID,
        analysis: Literal["dc", "ac"],
    ) -> dict[str, Any]:
        if action not in ("submit", "status", "result") or analysis not in ("dc", "ac"):
            raise InvalidInputError("unsupported actual diagnostic operation")
        if self._config.remote_root != "/home/buet/cds_work/.cadence_mcp":
            raise InvalidInputError("actual diagnostics require the reviewed managed root")
        runner = f"{self._config.remote_root}/phase-campaign/sim-mcp-v2/run.sh"
        output = await asyncio.to_thread(
            self._invoke_at_path, runner, action, self._job_id(job_id), analysis
        )
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RemoteFailureError("Remote diagnostic returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RemoteFailureError("Remote diagnostic returned an invalid payload")
        return payload

    async def submit_native_diagnostic(
        self, request: NativeDiagnosticRequest
    ) -> NativeDiagnosticStatus:
        return self._validate(
            NativeDiagnosticStatus,
            await self._invoke_native_json("submit", UUID(request.operation_id), request.analysis),
        )

    async def native_diagnostic_status(self, job_id: UUID, analysis: str) -> NativeDiagnosticStatus:
        return self._validate(
            NativeDiagnosticStatus, await self._invoke_native_json("status", job_id, analysis)
        )

    async def native_diagnostic_result(self, job_id: UUID, analysis: str) -> NativeDiagnosticResult:
        return self._validate(
            NativeDiagnosticResult, await self._invoke_native_json("result", job_id, analysis)
        )

    async def _invoke_native_json(self, action: str, job_id: UUID, analysis: str) -> dict[str, Any]:
        if action not in ("submit", "status", "result") or analysis not in ("dc", "ac", "tran"):
            raise InvalidInputError("unsupported native diagnostic operation")
        if self._config.remote_root != "/home/buet/cds_work/.cadence_mcp":
            raise InvalidInputError("native diagnostics require the reviewed managed root")
        runner = f"{self._config.remote_root}/phase-campaign/native-mcp-v3/run.sh"
        output = await asyncio.to_thread(
            self._invoke_at_path, runner, action, self._job_id(job_id), analysis
        )
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RemoteFailureError("Remote native diagnostic returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RemoteFailureError("Remote native diagnostic returned invalid data")
        return payload

    async def power_extraction_result(self, operation_id: str) -> PowerExtraction:
        if (operation_id != REFERENCE_OPERATION
                or self._config.remote_root != "/home/buet/cds_work/.cadence_mcp"):
            raise InvalidInputError("No reviewed power extraction for this operation or root")
        runner = self._config.remote_root + "/phase-campaign/analog-power-v2/run.sh"
        try:
            output = await asyncio.to_thread(self._invoke_at_path, runner, "result")
        except BridgeError as exc:
            # Preserve the stable transport category, never send private helper
            # traceback/path/license output through this measurement interface.
            raise type(exc)("Power extraction result could not be read safely") from None
        try:
            return PowerExtraction.model_validate_json(output)
        except ValueError:
            raise RemoteFailureError("Remote power extraction failed closed validation") from None

    async def bandwidth_refinement_result(self, operation_id: str) -> RefinementExtraction:
        from cadence_mcp_bridge.bandwidth_study import REFERENCE_OPERATION as BANDWIDTH_OPERATION

        if (operation_id != BANDWIDTH_OPERATION
                or self._config.remote_root != "/home/buet/cds_work/.cadence_mcp"):
            raise InvalidInputError("No reviewed bandwidth study for this operation or root")
        runner = self._config.remote_root + "/phase-campaign/bandwidth-qual-v1/run.sh"
        try:
            output = await asyncio.to_thread(self._invoke_at_path, runner, "result")
        except BridgeError as exc:
            raise type(exc)("Bandwidth study could not be read safely") from None
        try:
            return RefinementExtraction.model_validate_json(output)
        except ValueError:
            raise RemoteFailureError("Remote bandwidth study failed closed validation") from None

    async def offset_study_result(self, operation_id: str) -> OffsetExtraction:
        from cadence_mcp_bridge.offset_study import REFERENCE_OPERATION as OFFSET_OPERATION

        if (
            operation_id != OFFSET_OPERATION
            or self._config.remote_root != "/home/buet/cds_work/.cadence_mcp"
        ):
            raise InvalidInputError("No reviewed offset study for this operation or root")
        runner = self._config.remote_root + "/phase-campaign/offset-read-v1/run.sh"
        try:
            output = await asyncio.to_thread(self._invoke_at_path, runner, "result")
        except BridgeError as exc:
            raise type(exc)("Offset study could not be read safely") from None
        try:
            return OffsetExtraction.model_validate_json(output)
        except ValueError:
            raise RemoteFailureError("Offset study failed closed validation") from None

    async def slew_step_result(self, operation_id: str) -> StepExtraction:
        from cadence_mcp_bridge.slew_study import REFERENCE_OPERATION as STEP_OPERATION

        if (
            operation_id != STEP_OPERATION
            or self._config.remote_root != "/home/buet/cds_work/.cadence_mcp"
        ):
            raise InvalidInputError("No reviewed step study for this operation or root")
        runner = self._config.remote_root + "/phase-campaign/slew-read-v2/run.sh"
        try:
            output = await asyncio.to_thread(self._invoke_at_path, runner, "result")
        except BridgeError as exc:
            raise type(exc)("Step study could not be read safely") from None
        try:
            return StepExtraction.model_validate_json(output)
        except ValueError:
            raise RemoteFailureError("Step study failed closed validation") from None

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
        return self._invoke_at_path(self._config.runner_path, command.value, *arguments)

    def _invoke_at_path(self, runner_path: str, command: str, *arguments: str) -> str:
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
            runner_path,
            command,
            *arguments,
        ]
        try:
            completed = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                env=self._ssh_environment(),
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

    @staticmethod
    def _ssh_environment() -> dict[str, str]:
        """Restore the Windows known folder omitted by MCP's stdio environment.

        Windows OpenSSH requires PROGRAMDATA even with BatchMode enabled. Obtain
        it from the OS when absent; never infer a drive or loosen SSH checks.
        """
        environment = dict(os.environ)
        if sys.platform == "win32" and not any(
            key.upper() == "PROGRAMDATA" and value for key, value in environment.items()
        ):
            folder = ctypes.create_unicode_buffer(260)
            resolve = ctypes.windll.shell32.SHGetFolderPathW
            resolve.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_wchar_p,
            ]
            resolve.restype = ctypes.c_long
            if resolve(None, 0x23, None, 0, folder) != 0 or not folder.value:
                raise BackendUnavailableError("Windows common application folder unavailable")
            environment["PROGRAMDATA"] = folder.value
        return environment

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
    def _safe_token(value: str, label: str) -> str:
        if (
            not isinstance(value, str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value) is None
        ):
            raise InvalidInputError(f"{label} must be a reviewed identifier")
        return value

    @staticmethod
    def _number(value: float) -> str:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise InvalidInputError("profile variable must be a finite number")
        return format(value, ".17g")

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
            origin=status.origin,
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
