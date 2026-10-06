"""Application service boundary, independent from SSH and MCP transports."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal, Protocol, TypeVar, cast
from uuid import RFC_4122, UUID, uuid4

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.actual_diagnostics import (
    COPY_SHA256,
    NETLIST_SHA256,
    PROFILE_AC,
    PROFILE_DC,
    SOURCE_SHA256,
    ActualDiagnosticProfiles,
    ActualDiagnosticRequest,
    ActualDiagnosticResult,
    ActualDiagnosticStatus,
)
from cadence_mcp_bridge.amplifier_sweeps import (
    AmplifierChild,
    AmplifierPrepared,
    AmplifierQuery,
    AmplifierStatus,
    AmplifierSubmission,
    AmplifierSupervisor,
    AmplifierSweepRequest,
    AmplifierSweepResult,
    AmplifierTransport,
    Mode,
)
from cadence_mcp_bridge.analog_measurements import (
    AnalogDescription,
    AnalogList,
    AnalogQuery,
    AnalogResult,
    AnalogSelection,
)
from cadence_mcp_bridge.analog_service import AnalogSupervisor
from cadence_mcp_bridge.analyses import (
    AnalysisCancellation,
    AnalysisJobQuery,
    AnalysisList,
    AnalysisPlan,
    AnalysisResult,
    AnalysisSelection,
    AnalysisStatus,
    AnalysisSubmission,
)
from cadence_mcp_bridge.analysis_service import AnalysisSupervisor
from cadence_mcp_bridge.bandwidth_service import BandwidthBackend, BandwidthSupervisor
from cadence_mcp_bridge.bandwidth_study import BandwidthStudyResult
from cadence_mcp_bridge.design_sweep_service import (
    DesignSweepExecutionPlan,
    DesignSweepExecutionResult,
    DesignSweepQuery,
    DesignSweepSubmission,
    DesignSweepSupervisor,
)
from cadence_mcp_bridge.designs import (
    DesignDescription,
    DesignList,
    RegistryBase,
    reference_measurement_registry,
)
from cadence_mcp_bridge.discovery import validate_cell, validate_library, validate_view
from cadence_mcp_bridge.errors import (
    BackendUnavailableError,
    BridgeError,
    InvalidInputError,
    OperationTimeoutError,
    RemoteFailureError,
)
from cadence_mcp_bridge.measurement_binding_service import MeasurementBindingSupervisor
from cadence_mcp_bridge.measurement_bindings import MeasurementCatalog, SpecificationEvaluationV2
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
from cadence_mcp_bridge.measurement_service import MeasurementSupervisor
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
from cadence_mcp_bridge.native_diagnostics import (
    NativeDiagnosticProfiles,
    NativeDiagnosticRequest,
    NativeDiagnosticResult,
    NativeDiagnosticStatus,
)
from cadence_mcp_bridge.offset_service import OffsetBackend, OffsetSupervisor
from cadence_mcp_bridge.offset_study import OffsetStudyResult
from cadence_mcp_bridge.pdk_adapters import DesignPdkStatus, PdkDescription, PdkList, PdkRegistry
from cadence_mcp_bridge.pdk_reference import reference_pdk_registry
from cadence_mcp_bridge.power_measurements import (
    PowerDescription,
    PowerQuery,
    PowerResult,
    PowerSelection,
)
from cadence_mcp_bridge.power_service import PowerBackend, PowerSupervisor
from cadence_mcp_bridge.profiles import (
    get_profile,
    list_profiles,
    validate_corner,
    validate_variables,
)
from cadence_mcp_bridge.registered_measurements import (
    MeasurementDescription,
    MeasurementList,
    MeasurementQuery,
    MeasurementResult,
    MeasurementSelection,
)
from cadence_mcp_bridge.registered_sweeps import (
    DesignSweepDescription,
    DesignSweepPlan,
    DesignSweepRequest,
    DesignSweepSelection,
    RegisteredSweepPlanner,
)
from cadence_mcp_bridge.runtime_info import (
    JournalSelection,
    LoadedCatalogV2,
    RuntimeInfo,
    RuntimeInfoV2,
)
from cadence_mcp_bridge.slew_service import SlewBackend, SlewSupervisor
from cadence_mcp_bridge.slew_study import SlewStudyResult
from cadence_mcp_bridge.specification_service import SpecificationSupervisor
from cadence_mcp_bridge.specifications import (
    SpecificationDescription,
    SpecificationEvaluation,
    SpecificationList,
    SpecificationQuery,
    SpecificationSelection,
)
from cadence_mcp_bridge.storage import (
    CleanupOutcome,
    CleanupPlan,
    CleanupRequest,
    StorageArtifact,
    StorageArtifactRequest,
    StorageBackend,
    StoragePage,
    StoragePageRequest,
    StorageSelection,
    StorageSummary,
    StorageSupervisor,
)
from cadence_mcp_bridge.sweep_service import SweepBackend, SweepSupervisor
from cadence_mcp_bridge.sweeps import (
    SweepPlan,
    SweepRequest,
    SweepResult,
    SweepStatus,
    SweepSubmission,
)
from cadence_mcp_bridge.variable_contracts import (
    VariableList,
    VariableValuesRequest,
    VariableValuesResult,
    canonical_digest,
)
from cadence_mcp_bridge.write_models import (
    DesignWritePlan,
    DesignWriteValidationResult,
    WriteConfirmation,
)


class CadenceBackend(Protocol):
    async def amplifier_reserve(
        self, child: UUID, mode: Mode, value: str, plan_hash: str
    ) -> None: ...
    async def amplifier_lookup_reservation(self, child: UUID) -> bool: ...
    async def amplifier_submit(self, child: UUID) -> JobStatus: ...
    async def amplifier_status(self, child: UUID) -> JobStatus: ...
    async def amplifier_result(self, child: UUID) -> AmplifierChild: ...
    async def amplifier_effective_values(self, child: UUID) -> dict[str, str]: ...
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

    async def submit_actual_diagnostic(
        self, job_id: UUID, request: ActualDiagnosticRequest
    ) -> ActualDiagnosticStatus: ...

    async def reserve_sweep_attempt(self, job_id: UUID) -> None: ...

    async def lookup_sweep_reservation(self, job_id: UUID) -> bool: ...

    async def effective_sweep_values(self, job_id: UUID) -> dict[str, str]: ...

    async def actual_diagnostic_status(
        self, job_id: UUID, analysis: Literal["dc", "ac"]
    ) -> ActualDiagnosticStatus: ...

    async def actual_diagnostic_result(
        self, job_id: UUID, analysis: Literal["dc", "ac"]
    ) -> ActualDiagnosticResult: ...


class NativeBackend(Protocol):
    async def submit_native_diagnostic(
        self, request: NativeDiagnosticRequest
    ) -> NativeDiagnosticStatus: ...

    async def native_diagnostic_status(
        self, job_id: UUID, analysis: str
    ) -> NativeDiagnosticStatus: ...

    async def native_diagnostic_result(
        self, job_id: UUID, analysis: str
    ) -> NativeDiagnosticResult: ...


_ResultT = TypeVar("_ResultT")


class CadenceService:
    def __init__(
        self,
        backend: CadenceBackend,
        designs: RegistryBase | None = None,
        *,
        analysis_journal: Path | None = None,
        sweep_journal: Path | None = None,
        pdks: PdkRegistry | None = None,
    ) -> None:
        self._backend = backend
        self._storage = StorageSupervisor(cast(StorageBackend, backend))
        self._designs = reference_measurement_registry() if designs is None else designs
        self._owned_job_ids: set[UUID] = set()
        self._pdks = reference_pdk_registry() if pdks is None else pdks
        self._runtime_info = RuntimeInfoV2(
            bridge_version=__version__,
            designs=LoadedCatalogV2(
                source="builtin_reference" if designs is None else "operator_supplied",
                schema_version=self._designs.schema_version,
                entry_count=len(self._designs.designs),
                semantic_sha256=canonical_digest(self._designs),
            ),
            pdks=LoadedCatalogV2(
                source="builtin_reference" if pdks is None else "operator_supplied",
                schema_version=self._pdks.schema_version,
                entry_count=len(self._pdks.adapters),
                semantic_sha256=canonical_digest(self._pdks),
            ),
            journals=JournalSelection(
                analysis="platform_default" if analysis_journal is None else "operator_supplied",
                sweep="package_relative_default" if sweep_journal is None else "operator_supplied",
            ),
        )
        self._analyses = AnalysisSupervisor(self, self._designs, analysis_journal, self._pdks)
        self._registered_measurements = MeasurementSupervisor(self._designs, self._analyses)
        self._analog_measurements = AnalogSupervisor(self._designs, self._registered_measurements)
        self._power = PowerSupervisor(self._analog_measurements, cast(PowerBackend, backend))
        self._bandwidth = BandwidthSupervisor(
            self._analog_measurements, cast(BandwidthBackend, backend)
        )
        self._offset = OffsetSupervisor(self._analog_measurements, cast(OffsetBackend, backend))
        self._slew = SlewSupervisor(self._analog_measurements, cast(SlewBackend, backend))
        self._specifications = SpecificationSupervisor(self._designs, self._analog_measurements)
        self._measurement_bindings = MeasurementBindingSupervisor(
            self._designs, self._analog_measurements, self._power, self._specifications
        )
        self._registered_sweeps = RegisteredSweepPlanner(
            self._designs, self._analyses, self._registered_measurements
        )

        self._sweeps = SweepSupervisor(
            cast(SweepBackend, backend),
            sweep_journal
            if sweep_journal is not None
            else Path(__file__).resolve().parents[2] / ".codex" / "sweeps-v1.sqlite3",
        )
        self._design_sweep_lifecycle = DesignSweepSupervisor(
            self._registered_sweeps,
            self._sweeps,
            self._pdks,
        )
        self._amplifier_sweeps = AmplifierSupervisor(
            self._designs, self._pdks, cast(AmplifierTransport, backend), self._sweeps.store.path
        )

    async def prepare_amplifier_sweep(self, request: AmplifierSweepRequest) -> AmplifierPrepared:
        return self._amplifier_sweeps.prepare(request)

    async def submit_amplifier_sweep(self, request: AmplifierSubmission) -> AmplifierStatus:
        return await self._amplifier_sweeps.submit(request)

    async def amplifier_sweep_status(self, request: AmplifierQuery) -> AmplifierStatus:
        return await self._amplifier_sweeps.status(request)

    async def amplifier_sweep_result(self, request: AmplifierQuery) -> AmplifierSweepResult:
        return await self._amplifier_sweeps.result(request)

    async def cancel_amplifier_sweep(self, request: AmplifierQuery) -> AmplifierStatus:
        return await self._amplifier_sweeps.cancel(request)

    async def runtime_info(self) -> RuntimeInfo:
        if self._runtime_info.designs.schema_version > 7:
            raise InvalidInputError("Registry v8 requires cadence_runtime_info_v2")
        return RuntimeInfo.model_validate({**self._runtime_info.model_dump(), "schema_version": 1})

    async def runtime_info_v2(self) -> RuntimeInfoV2:
        return self._runtime_info

    async def measurement_catalog(self, design_id: str) -> MeasurementCatalog:
        return self._measurement_bindings.catalog(design_id)

    async def evaluate_specification_v2(
        self, request: SpecificationQuery
    ) -> SpecificationEvaluationV2:
        return await self._measurement_bindings.result(request)

    async def storage_summary(self) -> StorageSummary:
        return await self._storage.summary()

    async def list_storage_artifacts(self, request: StoragePageRequest) -> StoragePage:
        return await self._storage.page(request)

    async def describe_storage_artifact(self, request: StorageArtifactRequest) -> StorageArtifact:
        return await self._storage.describe(request)

    async def plan_storage_cleanup(self, request: StorageSelection) -> CleanupPlan:
        return await self._storage.plan(request)

    async def execute_storage_cleanup(self, request: CleanupRequest) -> CleanupOutcome:
        return await self._storage.execute(request)

    async def list_designs(self) -> DesignList:
        return self._designs.listing()

    async def list_pdk_adapters(self) -> PdkList:
        return self._pdks.listing()

    async def describe_pdk_adapter(self, adapter_id: str) -> PdkDescription:
        return self._pdks.describe(adapter_id)

    async def design_pdk_status(self, design_id: str) -> DesignPdkStatus:
        profile = self._designs.profile(design_id)
        return self._pdks.resolve(design_id, profile.pdk_adapter_id, profile.environment_id)

    async def describe_design(self, design_id: str) -> DesignDescription:
        return self._designs.describe(design_id)

    async def list_design_variables(self, design_id: str) -> VariableList:
        return self._designs.variables(design_id)

    async def check_variable_values(self, request: VariableValuesRequest) -> VariableValuesResult:
        return self._designs.check_variables(request)

    async def list_analyses(self, design_id: str) -> AnalysisList:
        return self._analyses.listing(design_id)

    async def plan_analysis(self, request: AnalysisSelection) -> AnalysisPlan:
        return self._analyses.plan(request)

    async def list_measurements(self, design_id: str) -> MeasurementList:
        return self._registered_measurements.listing(design_id)

    async def describe_measurement(self, request: MeasurementSelection) -> MeasurementDescription:
        return self._registered_measurements.describe(request)

    async def measurement_result(self, request: MeasurementQuery) -> MeasurementResult:
        return await self._registered_measurements.result(request)

    async def list_analog_measurements(self, design_id: str) -> AnalogList:
        return self._analog_measurements.listing(design_id)

    async def list_specifications(self, design_id: str) -> SpecificationList:
        return self._specifications.listing(design_id)

    async def describe_specification(
        self, request: SpecificationSelection
    ) -> SpecificationDescription:
        return self._specifications.describe(request)

    async def evaluate_specification(self, request: SpecificationQuery) -> SpecificationEvaluation:
        return await self._specifications.result(request)

    async def describe_analog_measurement(self, request: AnalogSelection) -> AnalogDescription:
        return self._analog_measurements.describe(request)

    async def analog_measurement_result(self, request: AnalogQuery) -> AnalogResult:
        return await self._analog_measurements.result(request)

    async def bandwidth_study_result(self, request: AnalogQuery) -> BandwidthStudyResult:
        return await self._bandwidth.result(request)

    async def offset_study_result(self, request: AnalogQuery) -> OffsetStudyResult:
        return await self._offset.result(request)

    async def slew_study_result(self, request: AnalogQuery) -> SlewStudyResult:
        return await self._slew.result(request)

    async def describe_power_measurement(self, request: PowerSelection) -> PowerDescription:
        return self._power.describe(request)

    async def power_measurement_result(self, request: PowerQuery) -> PowerResult:
        return await self._power.result(request)

    async def submit_analysis(self, submission: AnalysisSubmission) -> AnalysisStatus:
        return await self._analyses.submit(submission)

    async def analysis_status(self, request: AnalysisJobQuery) -> AnalysisStatus:
        return await self._analyses.status(request)

    async def analysis_result(self, request: AnalysisJobQuery) -> AnalysisResult:
        return await self._analyses.result(request)

    async def cancel_analysis(self, request: AnalysisJobQuery) -> AnalysisCancellation:
        return await self._analyses.cancel(request)

    async def plan_sweep(self, request: SweepRequest) -> SweepPlan:
        return await self._sweeps.plan(request)

    async def describe_design_sweep(self, request: DesignSweepSelection) -> DesignSweepDescription:
        return self._registered_sweeps.describe(request)

    async def plan_design_sweep(self, request: DesignSweepRequest) -> DesignSweepPlan:
        return self._registered_sweeps.plan(request)

    async def prepare_design_sweep(self, request: DesignSweepRequest) -> DesignSweepExecutionPlan:
        return self._design_sweep_lifecycle.prepare(request)

    async def submit_design_sweep(
        self, submission: DesignSweepSubmission
    ) -> DesignSweepExecutionResult:
        return await self._design_sweep_lifecycle.submit(submission)

    async def design_sweep_status(self, request: DesignSweepQuery) -> DesignSweepExecutionResult:
        return await self._design_sweep_lifecycle.status(request)

    async def design_sweep_result(self, request: DesignSweepQuery) -> DesignSweepExecutionResult:
        return await self._design_sweep_lifecycle.result(request)

    async def cancel_design_sweep(self, request: DesignSweepQuery) -> DesignSweepExecutionResult:
        return await self._design_sweep_lifecycle.cancel(request)

    async def submit_sweep(self, submission: SweepSubmission) -> SweepStatus:
        return await self._sweeps.submit(submission)

    async def sweep_status(self, sweep_id: str) -> SweepStatus:
        return await self._sweeps.status(self._parse_job_id(sweep_id))

    async def sweep_result(self, sweep_id: str) -> SweepResult:
        return await self._sweeps.result(self._parse_job_id(sweep_id))

    async def cancel_sweep(self, sweep_id: str) -> SweepStatus:
        return await self._sweeps.cancel(self._parse_job_id(sweep_id))

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

    async def list_actual_diagnostics(self) -> ActualDiagnosticProfiles:
        return ActualDiagnosticProfiles()

    async def submit_actual_diagnostic(
        self, request: ActualDiagnosticRequest
    ) -> ActualDiagnosticStatus:
        job_id = uuid4()
        try:
            status = await self._call(
                lambda: self._backend.submit_actual_diagnostic(job_id, request)
            )
        except OperationTimeoutError as timeout:
            try:
                status = await self._call(
                    lambda: self._backend.actual_diagnostic_status(job_id, request.analysis)
                )
            except BridgeError as recovery_error:
                raise timeout from recovery_error
        expected_profile = PROFILE_DC if request.analysis == "dc" else PROFILE_AC
        if status.job_id != job_id or status.profile_id != expected_profile:
            raise RemoteFailureError("Remote diagnostic returned mismatched job metadata")
        return status

    async def actual_diagnostic_status(self, job_id: str, analysis: str) -> ActualDiagnosticStatus:
        parsed, safe_analysis = self._diagnostic_key(job_id, analysis)
        status = await self._call(
            lambda: self._backend.actual_diagnostic_status(parsed, safe_analysis)
        )
        if status.job_id != parsed or status.profile_id != self._diagnostic_profile(safe_analysis):
            raise RemoteFailureError("Remote diagnostic status identity mismatch")
        return status

    async def actual_diagnostic_result(self, job_id: str, analysis: str) -> ActualDiagnosticResult:
        parsed, safe_analysis = self._diagnostic_key(job_id, analysis)
        result = await self._call(
            lambda: self._backend.actual_diagnostic_result(parsed, safe_analysis)
        )
        if result.job_id != parsed or result.profile_id != self._diagnostic_profile(safe_analysis):
            raise RemoteFailureError("Remote diagnostic result identity mismatch")
        if (
            result.source_sha256 != SOURCE_SHA256
            or result.copy_sha256 != COPY_SHA256
            or result.netlist_sha256 != NETLIST_SHA256
        ):
            raise RemoteFailureError("Remote diagnostic revision mismatch")
        return result

    @staticmethod
    def _diagnostic_profile(analysis: Literal["dc", "ac"]) -> str:
        return PROFILE_DC if analysis == "dc" else PROFILE_AC

    @staticmethod
    def _diagnostic_key(job_id: str, analysis: str) -> tuple[UUID, Literal["dc", "ac"]]:
        parsed = CadenceService._parse_job_id(job_id)
        if analysis not in ("dc", "ac"):
            raise InvalidInputError("analysis must be dc or ac")
        return parsed, cast(Literal["dc", "ac"], analysis)

    async def list_native_diagnostics(self) -> NativeDiagnosticProfiles:
        return NativeDiagnosticProfiles()

    async def submit_native_diagnostic(
        self, request: NativeDiagnosticRequest
    ) -> NativeDiagnosticStatus:
        parsed = self._parse_job_id(request.operation_id)
        try:
            status = await self._call(
                lambda: cast(NativeBackend, self._backend).submit_native_diagnostic(request)
            )
        except OperationTimeoutError as timeout:
            try:
                status = await self._call(
                    lambda: cast(NativeBackend, self._backend).native_diagnostic_status(
                        parsed, request.analysis
                    )
                )
            except BridgeError as recovery_error:
                raise timeout from recovery_error
        if status.job_id != parsed or status.analysis != request.analysis:
            raise RemoteFailureError("Remote native submission identity mismatch")
        return status

    @staticmethod
    def _native_key(job_id: str, analysis: str) -> UUID:
        parsed = CadenceService._parse_job_id(job_id)
        if analysis not in ("dc", "ac", "tran"):
            raise InvalidInputError("native analysis must be dc, ac or tran")
        return parsed

    async def native_diagnostic_status(self, job_id: str, analysis: str) -> NativeDiagnosticStatus:
        parsed = self._native_key(job_id, analysis)
        status = await self._call(
            lambda: cast(NativeBackend, self._backend).native_diagnostic_status(parsed, analysis)
        )
        if status.job_id != parsed or status.analysis != analysis:
            raise RemoteFailureError("Remote native status identity mismatch")
        return status

    async def native_diagnostic_result(self, job_id: str, analysis: str) -> NativeDiagnosticResult:
        parsed = self._native_key(job_id, analysis)
        result = await self._call(
            lambda: cast(NativeBackend, self._backend).native_diagnostic_result(parsed, analysis)
        )
        if result.job_id != parsed or result.analysis != analysis:
            raise RemoteFailureError("Remote native result identity mismatch")
        return result

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

    async def compare_corner_results(self, request: CornerComparisonRequest) -> CornerComparison:
        return compare_corner_results(request)

    async def summarize_monte_carlo(self, request: MonteCarloRequest) -> MonteCarloSummary:
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
