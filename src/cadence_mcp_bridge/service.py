"""Application service boundary, independent from SSH and MCP transports."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, TypeVar, cast
from uuid import RFC_4122, UUID, uuid4

from cadence_mcp_bridge.errors import (
    BackendUnavailableError,
    BridgeError,
    InvalidInputError,
    OperationTimeoutError,
    RemoteFailureError,
)
from cadence_mcp_bridge.models import HealthReport, JobLogTail, JobResult, JobStatus


class CadenceBackend(Protocol):
    async def health(self) -> HealthReport: ...

    async def submit_smoke(self, job_id: UUID) -> JobStatus: ...

    async def status(self, job_id: UUID) -> JobStatus: ...

    async def log_tail(
        self,
        job_id: UUID,
        stream: Literal["stdout", "stderr"],
        lines: int = 100,
    ) -> JobLogTail: ...

    async def result(self, job_id: UUID) -> JobResult: ...

    async def cancel(self, job_id: UUID) -> JobStatus: ...


_ResultT = TypeVar("_ResultT")


class CadenceService:
    def __init__(self, backend: CadenceBackend) -> None:
        self._backend = backend
        self._owned_job_ids: set[UUID] = set()

    async def health(self) -> HealthReport:
        return await self._call(self._backend.health)

    async def submit_smoke(self) -> JobStatus:
        job_id = uuid4()
        try:
            status = await self._call(lambda: self._backend.submit_smoke(job_id))
        except OperationTimeoutError as timeout:
            # The remote create may have succeeded before SSH timed out. Reuse the
            # original idempotency key and recover only that exact job.
            try:
                status = await self._call(lambda: self._backend.status(job_id))
            except BridgeError as recovery_error:
                raise timeout from recovery_error
        if status.job_id != job_id:
            raise RemoteFailureError("Remote runner returned a mismatched job_id")
        self._owned_job_ids.add(job_id)
        return status

    async def job_status(self, job_id: str) -> JobStatus:
        parsed = self._parse_job_id(job_id)
        return await self._call(lambda: self._backend.status(parsed))

    async def job_log_tail(self, job_id: str, stream: str, lines: int) -> JobLogTail:
        parsed = self._parse_job_id(job_id)
        if stream not in ("stdout", "stderr"):
            raise InvalidInputError("stream must be stdout or stderr")
        if isinstance(lines, bool) or not isinstance(lines, int) or not 1 <= lines <= 200:
            raise InvalidInputError("lines must be between 1 and 200")
        safe_stream = cast(Literal["stdout", "stderr"], stream)
        result = await self._call(lambda: self._backend.log_tail(parsed, safe_stream, lines))
        if (
            result.job_id != parsed
            or result.stream != safe_stream
            or result.lines_requested != lines
        ):
            raise RemoteFailureError("Remote runner returned mismatched log metadata")
        return result

    async def job_result(self, job_id: str) -> JobResult:
        parsed = self._parse_job_id(job_id)
        return await self._call(lambda: self._backend.result(parsed))

    async def cancel_job(self, job_id: str) -> JobStatus:
        parsed = self._parse_job_id(job_id)
        if parsed not in self._owned_job_ids:
            raise InvalidInputError("job_id is not owned by this MCP server process")
        return await self._call(lambda: self._backend.cancel(parsed))

    @staticmethod
    def _parse_job_id(job_id: str) -> UUID:
        if not isinstance(job_id, str):
            raise InvalidInputError("job_id must be a UUID string")
        try:
            parsed = UUID(job_id)
        except ValueError as exc:
            raise InvalidInputError("job_id must be a lowercase RFC 4122 UUID") from exc
        if (
            str(parsed) != job_id
            or parsed.variant != RFC_4122
            or parsed.version not in (1, 2, 3, 4, 5)
        ):
            raise InvalidInputError("job_id must be a lowercase RFC 4122 UUID")
        return parsed

    @staticmethod
    async def _call(operation: Callable[[], Awaitable[_ResultT]]) -> _ResultT:
        try:
            return await operation()
        except BridgeError:
            raise
        except Exception as exc:
            raise BackendUnavailableError("Cadence backend is unavailable") from exc
