"""Application service boundary, independent from SSH and MCP transports."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, TypeVar, cast
from uuid import RFC_4122, UUID, uuid4

from cadence_mcp_bridge.discovery import validate_cell, validate_library, validate_view
from cadence_mcp_bridge.errors import (
    BackendUnavailableError,
    BridgeError,
    InvalidInputError,
    OperationTimeoutError,
    RemoteFailureError,
)
from cadence_mcp_bridge.measurement_models import (
    AdcMeasurementContract,
    CornerComparison,
    CornerComparisonRequest,
    DcPowerRequest,
    FftMeasurementRequest,
    FftMetrics,
    LinearityMetrics,
    LinearityRequest,
    MonteCarloRequest,
    MonteCarloSummary,
    OffsetRequest,
    ScalarMetric,
    SettlingMetric,
    SettlingRequest,
)
from cadence_mcp_bridge.measurements import (
    compare_corner_results,
    get_measurement_contract,
    measure_dc_power,
    measure_fft_metrics,
    measure_linearity,
    measure_offset,
    measure_settling,
    summarize_monte_carlo,
)
from cadence_mcp_bridge.models import (
    AdeProfileIntrospection,
    CellList,
    CellViewInspection,
    HealthReport,
    JobLogTail,
    JobResult,
    JobStatus,
    LibraryList,
    ProfileList,
    ProfileVariables,
    SimulationProfile,
)
from cadence_mcp_bridge.profiles import (
    ACTUAL_PROFILE_ID,
    get_profile,
    list_profiles,
    validate_corner,
    validate_variables,
)
from cadence_mcp_bridge.write_models import (
    DesignWritePlan,
    DesignWriteValidationResult,
    WriteConfirmation,
)


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

    async def list_libraries(self) -> LibraryList: ...

    async def list_cells(self, library: str) -> CellList: ...

    async def inspect_cellview(self, library: str, cell: str, view: str) -> CellViewInspection: ...

    async def inspect_ade_profile(self, profile_id: str) -> AdeProfileIntrospection: ...

    async def submit_profile(
        self,
        job_id: UUID,
        profile_id: str,
        corner: str,
        variables: ProfileVariables,
    ) -> JobStatus: ...

    async def design_write_plan(self) -> DesignWritePlan: ...

    async def execute_design_write_validation(
        self, validation_id: UUID, confirmation: WriteConfirmation
    ) -> DesignWriteValidationResult: ...


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

    async def get_measurement_contract(self, contract_id: str) -> AdcMeasurementContract:
        return get_measurement_contract(contract_id)

    async def measure_dc_power(self, request: DcPowerRequest) -> ScalarMetric:
        return measure_dc_power(request)

    async def measure_offset(self, request: OffsetRequest) -> ScalarMetric:
        return measure_offset(request)

    async def measure_settling(self, request: SettlingRequest) -> SettlingMetric:
        return measure_settling(request)

    async def measure_fft_metrics(self, request: FftMeasurementRequest) -> FftMetrics:
        return measure_fft_metrics(request)

    async def measure_linearity(self, request: LinearityRequest) -> LinearityMetrics:
        return measure_linearity(request)

    async def compare_corner_results(
        self, request: CornerComparisonRequest
    ) -> CornerComparison:
        return compare_corner_results(request)

    async def summarize_monte_carlo(
        self, request: MonteCarloRequest
    ) -> MonteCarloSummary:
        return summarize_monte_carlo(request)

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

    async def list_libraries(self) -> LibraryList:
        return await self._call(self._backend.list_libraries)

    async def list_cells(self, library: str) -> CellList:
        safe_library = validate_library(library)
        result = await self._call(lambda: self._backend.list_cells(safe_library))
        if result.library != safe_library:
            raise RemoteFailureError("Remote runner returned mismatched library metadata")
        return result

    async def inspect_cellview(self, library: str, cell: str, view: str) -> CellViewInspection:
        safe_library = validate_library(library)
        safe_cell = validate_cell(safe_library, cell)
        safe_view = validate_view(safe_library, safe_cell, view)
        result = await self._call(
            lambda: self._backend.inspect_cellview(safe_library, safe_cell, safe_view)
        )
        if (result.library, result.cell, result.view) != (
            safe_library,
            safe_cell,
            safe_view,
        ):
            raise RemoteFailureError("Remote runner returned mismatched cellview metadata")
        return result

    async def inspect_ade_profile(self, profile_id: str) -> AdeProfileIntrospection:
        if profile_id != ACTUAL_PROFILE_ID:
            raise InvalidInputError("profile is outside the ADE introspection allowlist")
        result = await self._call(lambda: self._backend.inspect_ade_profile(profile_id))
        if result.profile_id != profile_id:
            raise RemoteFailureError("Remote runner returned mismatched ADE profile metadata")
        return result

    async def list_profiles(self) -> ProfileList:
        return list_profiles()

    async def get_profile(self, profile_id: str) -> SimulationProfile:
        return get_profile(profile_id)

    async def submit_profile(
        self, profile_id: str, corner: str, variables: ProfileVariables
    ) -> JobStatus:
        profile = get_profile(profile_id)
        safe_corner = validate_corner(profile, corner)
        safe_variables = validate_variables(profile, variables)
        job_id = uuid4()
        status = await self._call(
            lambda: self._backend.submit_profile(
                job_id, profile.profile_id, safe_corner, safe_variables
            )
        )
        if status.job_id != job_id or status.profile != profile.profile_id:
            raise RemoteFailureError("Remote runner returned mismatched profile job metadata")
        self._owned_job_ids.add(job_id)
        return status

    async def design_write_plan(self) -> DesignWritePlan:
        return await self._call(self._backend.design_write_plan)

    async def execute_design_write_validation(
        self, confirmation: WriteConfirmation
    ) -> DesignWriteValidationResult:
        validation_id = uuid4()
        result = await self._call(
            lambda: self._backend.execute_design_write_validation(validation_id, confirmation)
        )
        if result.validation_id != validation_id:
            raise RemoteFailureError("Remote runner returned a mismatched validation_id")
        return result

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
