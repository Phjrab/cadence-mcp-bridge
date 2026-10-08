"""MCP SDK v2 adapter exposing only reviewed Cadence tools."""

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable
from typing import Annotated, Any, cast

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, InputRequiredResult, TextContent, Tool, ToolAnnotations
from pydantic import WithJsonSchema

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.actual_diagnostics import (
    ActualDiagnosticProfiles,
    ActualDiagnosticRequest,
    ActualDiagnosticResult,
    ActualDiagnosticStatus,
)
from cadence_mcp_bridge.amplifier_specifications import (
    AmplifierEvaluationQuery,
    AmplifierSpecificationCatalog,
    AmplifierSpecificationEvaluation,
    load_amplifier_specifications,
)
from cadence_mcp_bridge.amplifier_sweeps import (
    AmplifierPrepared,
    AmplifierQuery,
    AmplifierStatus,
    AmplifierSubmission,
    AmplifierSweepRequest,
    AmplifierSweepResult,
)
from cadence_mcp_bridge.analog_measurements import (
    AnalogDescription,
    AnalogList,
    AnalogQuery,
    AnalogResult,
    AnalogSelection,
)
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
from cadence_mcp_bridge.bandwidth_study import BandwidthStudyResult
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.design_sweep_service import (
    DesignSweepExecutionPlan,
    DesignSweepExecutionResult,
    DesignSweepQuery,
    DesignSweepSubmission,
)
from cadence_mcp_bridge.designs import (
    DesignDescription,
    DesignList,
    DesignRejected,
    LogicalId,
    load_design_registry,
)
from cadence_mcp_bridge.errors import BridgeError, ConfigurationError, InvalidInputError
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
from cadence_mcp_bridge.models import (
    CellList,
    CellViewInspection,
    ContractModel,
    ErrorResponse,
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
from cadence_mcp_bridge.offset_study import OffsetStudyResult
from cadence_mcp_bridge.pdk_adapters import (
    DesignPdkStatus,
    PdkDescription,
    PdkList,
    PdkRejected,
    load_pdk_registry,
)
from cadence_mcp_bridge.power_measurements import (
    PowerDescription,
    PowerQuery,
    PowerResult,
    PowerSelection,
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
)
from cadence_mcp_bridge.runtime_info import RuntimeInfo, RuntimeInfoV2
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.slew_study import SlewStudyResult
from cadence_mcp_bridge.specifications import (
    SpecificationDescription,
    SpecificationEvaluation,
    SpecificationList,
    SpecificationQuery,
    SpecificationSelection,
)
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.storage import (
    CleanupOutcome,
    CleanupPlan,
    CleanupRequest,
    StorageArtifact,
    StorageArtifactRequest,
    StoragePage,
    StoragePageRequest,
    StorageSelection,
    StorageSummary,
)
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
)
from cadence_mcp_bridge.write_models import (
    DesignWritePlan,
    DesignWriteValidationResult,
    WriteConfirmation,
)

_LOGGER = logging.getLogger(__name__)

NativeAnalysisInput = Annotated[
    str, WithJsonSchema({"type": "string", "enum": ["dc", "ac", "tran"]})
]

JobIdInput = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "format": "uuid",
            "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            "description": "Lowercase RFC 4122 UUID returned by cadence_submit_smoke.",
        }
    ),
]
LogStreamInput = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "enum": ["stdout", "stderr"],
            "description": "Allowlisted remote log stream.",
        }
    ),
]
LogLinesInput = Annotated[
    int,
    WithJsonSchema(
        {
            "type": "integer",
            "minimum": 1,
            "maximum": 200,
            "description": "Number of trailing lines to return.",
        }
    ),
]
DiscoveryIdentifierInput = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "pattern": "^[A-Za-z][A-Za-z0-9_#-]{0,63}$",
            "description": "Exact name from the reviewed read-only discovery allowlist.",
        }
    ),
]
ProfileIdInput = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "enum": [
                "fixture-rc-transient",
                "actual-differential-amplifier-tb2-transient",
            ],
            "description": "Exact profile identifier from cadence_list_profiles.",
        }
    ),
]
ProfileCornerInput = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "enum": ["nominal", "NN"],
            "description": "Exact corner allowed by the selected profile.",
        }
    ),
]
MeasurementContractIdInput = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "enum": ["adc-synthetic-v1"],
            "description": "Exact versioned measurement contract identifier.",
        }
    ),
]
ActualAnalysisInput = Annotated[
    str,
    WithJsonSchema(
        {"type": "string", "enum": ["dc", "ac"], "description": "Fixed work-copy analysis."}
    ),
]

_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
_SUBMIT = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)
_CANCEL = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)
_WRITE_VALIDATION = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=False,
)


def _call_result(result: ContractModel, *, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=result.model_dump_json(by_alias=True))],
        structured_content=result.model_dump(mode="json", by_alias=True),
        is_error=is_error,
    )


async def _stable_result[ResultT: ContractModel](
    operation: Awaitable[ResultT],
) -> CallToolResult:
    try:
        return _call_result(await operation)
    except BridgeError as exc:
        _LOGGER.warning("Cadence tool failed with code %s", exc.code.value)
        return _call_result(ErrorResponse(error=exc.to_envelope()), is_error=True)
    except Exception:
        _LOGGER.exception("Cadence tool failed unexpectedly")
        error = ErrorResponse(error=BridgeError("Internal server error").to_envelope())
        return _call_result(error, is_error=True)


class DesignContractServer(MCPServer):
    """Close new design inputs using public SDK hooks; preserve legacy schemas."""

    async def list_tools(self) -> list[Tool]:
        tools = await super().list_tools()
        for tool in tools:
            if tool.name in {
                "cadence_amplifier_specification_catalog",
                "cadence_evaluate_amplifier_specifications",
                "cadence_prepare_amplifier_sweep",
                "cadence_submit_amplifier_sweep",
                "cadence_amplifier_sweep_status",
                "cadence_amplifier_sweep_result",
                "cadence_cancel_amplifier_sweep",
                "cadence_measurement_catalog",
                "cadence_evaluate_specification_v2",
                "cadence_runtime_info_v2",
                "cadence_runtime_info",
                "cadence_describe_power_measurement",
                "cadence_power_measurement_result",
                "cadence_bandwidth_study_result",
                "cadence_slew_study_result",
                "cadence_offset_study_result",
                "cadence_list_specifications",
                "cadence_describe_specification",
                "cadence_evaluate_specification",
                "cadence_list_analog_measurements",
                "cadence_describe_analog_measurement",
                "cadence_analog_measurement_result",
                "cadence_storage_summary",
                "cadence_list_storage_artifacts",
                "cadence_describe_storage_artifact",
                "cadence_plan_storage_cleanup",
                "cadence_execute_storage_cleanup",
                "cadence_list_designs",
                "cadence_list_pdk_adapters",
                "cadence_describe_pdk_adapter",
                "cadence_design_pdk_status",
                "cadence_describe_design",
                "cadence_list_design_variables",
                "cadence_check_variable_values",
                "cadence_list_analyses",
                "cadence_plan_operation",
                "cadence_submit_operation",
                "cadence_operation_status",
                "cadence_operation_result",
                "cadence_cancel_pending_operation",
                "cadence_plan_analysis",
                "cadence_submit_analysis",
                "cadence_analysis_status",
                "cadence_analysis_result",
                "cadence_cancel_analysis",
                "cadence_list_measurements",
                "cadence_describe_measurement",
                "cadence_measurement_result",
                "cadence_describe_design_sweep",
                "cadence_plan_design_sweep",
                "cadence_prepare_design_sweep",
                "cadence_submit_design_sweep",
                "cadence_design_sweep_status",
                "cadence_design_sweep_result",
                "cadence_cancel_design_sweep",
            }:
                tool.input_schema = {**tool.input_schema, "additionalProperties": False}
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Context[Any, Any] | None = None,
    ) -> CallToolResult | InputRequiredResult:
        if name in {"cadence_runtime_info", "cadence_runtime_info_v2"} and arguments:
            raise ToolError("Runtime information accepts no arguments")
        if (
            name
            in {
                "cadence_list_designs",
                "cadence_list_pdk_adapters",
                "cadence_storage_summary",
            }
            and arguments
        ):
            raise ToolError("Design listing accepts no arguments")
        if name in {
            "cadence_describe_design",
            "cadence_list_design_variables",
            "cadence_list_analyses",
            "cadence_design_pdk_status",
            "cadence_list_measurements",
            "cadence_list_analog_measurements",
            "cadence_list_specifications",
            "cadence_measurement_catalog",
            "cadence_amplifier_specification_catalog",
        } and (set(arguments) != {"design_id"} or type(arguments["design_id"]) is not str):
            raise ToolError("Design description accepts only one string design_id")
        if name == "cadence_describe_pdk_adapter" and (
            set(arguments) != {"adapter_id"} or type(arguments["adapter_id"]) is not str
        ):
            raise ToolError("PDK description accepts only one string adapter_id")
        if name == "cadence_check_variable_values" and (
            set(arguments) != {"request"} or type(arguments["request"]) is not dict
        ):
            raise ToolError("Variable checking accepts only one request object")
        argument = {
            "cadence_evaluate_amplifier_specifications": "request",
            "cadence_prepare_amplifier_sweep": "request",
            "cadence_submit_amplifier_sweep": "submission",
            "cadence_amplifier_sweep_status": "request",
            "cadence_amplifier_sweep_result": "request",
            "cadence_cancel_amplifier_sweep": "request",
            "cadence_evaluate_specification_v2": "request",
            "cadence_describe_power_measurement": "request",
            "cadence_power_measurement_result": "request",
            "cadence_bandwidth_study_result": "request",
            "cadence_slew_study_result": "request",
            "cadence_offset_study_result": "request",
            "cadence_describe_specification": "request",
            "cadence_evaluate_specification": "request",
            "cadence_describe_analog_measurement": "request",
            "cadence_analog_measurement_result": "request",
            "cadence_list_storage_artifacts": "request",
            "cadence_describe_storage_artifact": "request",
            "cadence_plan_storage_cleanup": "request",
            "cadence_execute_storage_cleanup": "request",
            "cadence_plan_operation": "request",
            "cadence_submit_operation": "submission",
            "cadence_operation_status": "request",
            "cadence_operation_result": "request",
            "cadence_cancel_pending_operation": "request",
            "cadence_plan_analysis": "request",
            "cadence_submit_analysis": "submission",
            "cadence_analysis_status": "request",
            "cadence_analysis_result": "request",
            "cadence_cancel_analysis": "request",
            "cadence_describe_measurement": "request",
            "cadence_measurement_result": "request",
            "cadence_describe_design_sweep": "request",
            "cadence_plan_design_sweep": "request",
            "cadence_prepare_design_sweep": "request",
            "cadence_submit_design_sweep": "submission",
            "cadence_design_sweep_status": "request",
            "cadence_design_sweep_result": "request",
            "cadence_cancel_design_sweep": "request",
        }.get(name)
        if argument is not None and (
            set(arguments) != {argument} or type(arguments[argument]) is not dict
        ):
            raise ToolError("Analysis tools accept only their registered request object")
        return await super().call_tool(name, arguments, context)


def create_server(service: CadenceService) -> MCPServer:
    """Build an MCP server around an injected service for production or tests."""

    server = DesignContractServer(
        name="cadence-mcp-bridge",
        title="Cadence MCP Bridge",
        description="Restricted stdio bridge to the fixed Cadence runner.",
        instructions=(
            "Use only the reviewed allowlisted tools. Discovery returns names and existence "
            "metadata only; no raw command or proprietary file-content interface exists."
        ),
        version=__version__,
        log_level="WARNING",
    )

    @server.tool(
        name="cadence_runtime_info",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Inspect the running bridge version, loaded design/PDK catalog versions, "
        "counts and semantic hashes, and default/operator journal selection. Local only; "
        "no paths, contents, remote contact or writes. Does not assess journal health, "
        "environment qualification or execution authority. Takes no arguments.",
    )
    async def cadence_runtime_info() -> Annotated[CallToolResult, RuntimeInfo]:
        return await _stable_result(service.runtime_info())

    @server.tool(
        name="cadence_storage_summary",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Inspect only registered reference result roots. Returns bounded totals, "
        "coverage, protected/replay/evidence classes, disk floor and cumulative reservations. "
        "No raw contents/paths or automatic deletion; partial totals are lower bounds.",
    )
    async def cadence_storage_summary() -> Annotated[CallToolResult, StorageSummary]:
        return await _stable_result(service.storage_summary())

    @server.tool(
        name="cadence_list_storage_artifacts",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Page at most 20 opaque artifacts from an inspected snapshot. Snapshot drift "
        "fails closed. Age and extracted measurements do not grant deletion permission.",
    )
    async def cadence_list_storage_artifacts(
        request: StoragePageRequest,
    ) -> Annotated[CallToolResult, StoragePage]:
        return await _stable_result(service.list_storage_artifacts(request))

    @server.tool(
        name="cadence_describe_storage_artifact",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Describe one opaque registered artifact at the exact snapshot, including "
        "dependencies, classification and deletion reason. No filesystem path/content inputs.",
    )
    async def cadence_describe_storage_artifact(
        request: StorageArtifactRequest,
    ) -> Annotated[CallToolResult, StorageArtifact]:
        return await _stable_result(service.describe_storage_artifact(request))

    @server.tool(
        name="cadence_plan_storage_cleanup",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Plan at most 16 exact inspected artifact IDs. Returns stable hash, qualified "
        "candidates and protected exclusions without deleting. Report the plan for user selection.",
    )
    async def cadence_plan_storage_cleanup(
        request: StorageSelection,
    ) -> Annotated[CallToolResult, CleanupPlan]:
        return await _stable_result(service.plan_storage_cleanup(request))

    @server.tool(
        name="cadence_execute_storage_cleanup",
        annotations=_CANCEL,
        structured_output=True,
        description="Dry-run by default. Execute only exact selected IDs from a hash-bound plan "
        "when an independent operator approval records explicit user selection for this UUID. "
        "Rechecks fingerprints/dependencies under EDA lock; protected/history/replay data cannot "
        "be deleted. Retry the same operation UUID; UNKNOWN never authorizes a blind retry. "
        "Only reviewed isolated intermediate leaves qualify; reservations never refund.",
    )
    async def cadence_execute_storage_cleanup(
        request: CleanupRequest,
    ) -> Annotated[CallToolResult, CleanupOutcome]:
        return await _stable_result(service.execute_storage_cleanup(request))

    @server.tool(
        name="cadence_describe_design_sweep",
        annotations=_READ_ONLY,
        description="Describe a registered design/analysis/variable and same-analysis measurement "
        "IDs for local 1D sweep planning. Returns contract hash, fixed-value requirements and "
        "blockers; no execution, defaults, range qualification or transport.",
        structured_output=True,
    )
    async def cadence_describe_design_sweep(
        request: DesignSweepSelection,
    ) -> Annotated[CallToolResult, DesignSweepDescription]:
        return await _stable_result(service.describe_design_sweep(request))

    @server.tool(
        name="cadence_plan_design_sweep",
        annotations=_READ_ONLY,
        description="Plan at most 16 registered 1D points using the described contract hash, "
        "decimal strings/units and every non-axis fixed value. Use explicit values or exact "
        "linear start/stop/step. Reports numeric denials; all points NOT_RUN, no simulation, "
        "reservation or durable admission. Parameterized execution is unqualified.",
        structured_output=True,
    )
    async def cadence_plan_design_sweep(
        request: DesignSweepRequest,
    ) -> Annotated[CallToolResult, DesignSweepPlan]:
        return await _stable_result(service.plan_design_sweep(request))

    @server.tool(
        name="cadence_prepare_design_sweep",
        annotations=_READ_ONLY,
        description="Bind a registered 1D request to the existing sweep engine. Use described "
        "contract hash, exact decimal values/units and all fixed values. Only the registry-v5 "
        "compiled RC fixture has a parameterized route; real-design ranges remain unqualified. "
        "Returns execution plan hash and blockers without reserving or executing.",
        structured_output=True,
    )
    async def cadence_prepare_design_sweep(
        request: DesignSweepRequest,
    ) -> Annotated[CallToolResult, DesignSweepExecutionPlan]:
        return await _stable_result(service.prepare_design_sweep(request))

    @server.tool(
        name="cadence_submit_design_sweep",
        annotations=_SUBMIT,
        description="Submit/resume a prepared registered RC fixture sweep with the exact plan "
        "hash and stable experiment UUID. Reuse that UUID on retry/restart; changed contracts "
        "are denied. Uses existing shared EDA lock, cumulative Spectre/result budget and disk "
        "guards. No real-design bias sweep or analog specification claim.",
        structured_output=True,
    )
    async def cadence_submit_design_sweep(
        submission: DesignSweepSubmission,
    ) -> Annotated[CallToolResult, DesignSweepExecutionResult]:
        return await _stable_result(service.submit_design_sweep(submission))

    @server.tool(
        name="cadence_design_sweep_status",
        annotations=_READ_ONLY,
        description="Read locally journaled status of an admitted design ID/sweep UUID; no replay.",
        structured_output=True,
    )
    async def cadence_design_sweep_status(
        request: DesignSweepQuery,
    ) -> Annotated[CallToolResult, DesignSweepExecutionResult]:
        return await _stable_result(service.design_sweep_status(request))

    @server.tool(
        name="cadence_design_sweep_result",
        annotations=_READ_ONLY,
        description="Read bounded admitted sweep points, exact effective inputs and completion "
        "measurement. NOT_RUN/UNKNOWN never imply success; spec_evaluation stays not_evaluated.",
        structured_output=True,
    )
    async def cadence_design_sweep_result(
        request: DesignSweepQuery,
    ) -> Annotated[CallToolResult, DesignSweepExecutionResult]:
        return await _stable_result(service.design_sweep_result(request))

    @server.tool(
        name="cadence_cancel_design_sweep",
        annotations=_CANCEL,
        description="Cancel only recorded children of an admitted design ID/sweep UUID. "
        "Uncertain sends/cancellation stay UNKNOWN; no unrelated process is signaled.",
        structured_output=True,
    )
    async def cadence_cancel_design_sweep(
        request: DesignSweepQuery,
    ) -> Annotated[CallToolResult, DesignSweepExecutionResult]:
        return await _stable_result(service.cancel_design_sweep(request))

    @server.tool(
        name="cadence_runtime_info_v2",
        annotations=_READ_ONLY,
        description="Observe loaded local catalog versions (including v8), semantic hashes and "
        "journal selection. No paths, health assessment, remote contact or execution authority.",
        structured_output=True,
    )
    async def cadence_runtime_info_v2() -> Annotated[CallToolResult, RuntimeInfoV2]:
        return await _stable_result(service.runtime_info_v2())

    @server.tool(
        name="cadence_measurement_catalog",
        annotations=_READ_ONLY,
        description="Discover at most six registered analog definitions, one separate signed "
        "DC power reader and 32 versioned operator specifications for a registered design. "
        "Each reader has its own definition and contract hash; use its named result tool. "
        "Includes complete goal descriptions for v2 evaluation. Eligibility does not establish "
        "artifact availability or qualification. No registration, targets or simulation grant.",
        structured_output=True,
    )
    async def cadence_measurement_catalog(
        design_id: LogicalId,
    ) -> Annotated[CallToolResult, MeasurementCatalog]:
        return await _stable_result(service.measurement_catalog(design_id))

    @server.tool(
        name="cadence_evaluate_specification_v2",
        annotations=_READ_ONLY,
        description="Evaluate one described operator specification by exact contract hash "
        "and optional admitted UUID4. Routes legacy goals to the original engine and v2 "
        "power goals to the existing signed-current reader. No target: NOT_EVALUATED without "
        "source read; only qualified facts with exact conditions yield PASS/FAIL. Source errors "
        "remain errors. No caller facts, formulas, paths, targets or simulation.",
        structured_output=True,
    )
    async def cadence_evaluate_specification_v2(
        request: SpecificationQuery,
    ) -> Annotated[CallToolResult, SpecificationEvaluationV2]:
        return await _stable_result(service.evaluate_specification_v2(request))

    @server.tool(
        name="cadence_list_specifications",
        annotations=_READ_ONLY,
        description="List up to 32 operator-owned specifications for one registered design. "
        "Registry v7 is required; empty targets stay not_evaluated. No simulation or registration.",
        structured_output=True,
    )
    async def cadence_list_specifications(
        design_id: LogicalId,
    ) -> Annotated[CallToolResult, SpecificationList]:
        return await _stable_result(service.list_specifications(design_id))

    @server.tool(
        name="cadence_describe_specification",
        annotations=_READ_ONLY,
        description="Describe an operator-registered target, exact unit, measurement-definition "
        "hash and conditions; obtain its contract hash before evaluation. No caller target.",
        structured_output=True,
    )
    async def cadence_describe_specification(
        request: SpecificationSelection,
    ) -> Annotated[CallToolResult, SpecificationDescription]:
        return await _stable_result(service.describe_specification(request))

    @server.tool(
        name="cadence_evaluate_specification",
        annotations=_READ_ONLY,
        description="Evaluate one registered specification using its described contract hash "
        "and an optional admitted completed UUID4. Missing target: NOT_EVALUATED; missing selected "
        "operation: MISSING_MEASUREMENT; partial/unqualified measurement: UNQUALIFIED; differing "
        "conditions: CONDITION_MISMATCH. PASS/FAIL applies only to this exact operation. "
        "Invalid/failed source requests are errors, not FAIL. "
        "No caller facts, simulation or search.",
        structured_output=True,
    )
    async def cadence_evaluate_specification(
        request: SpecificationQuery,
    ) -> Annotated[CallToolResult, SpecificationEvaluation]:
        return await _stable_result(service.evaluate_specification(request))

    @server.tool(
        name="cadence_list_analog_measurements",
        annotations=_READ_ONLY,
        description="List operator-registered analog definitions, source IDs, contract hashes "
        "and missing scientific qualification. Registry v6 is required; no simulation grant.",
        structured_output=True,
    )
    async def cadence_list_analog_measurements(
        design_id: LogicalId,
    ) -> Annotated[CallToolResult, AnalogList]:
        return await _stable_result(service.list_analog_measurements(design_id))

    @server.tool(
        name="cadence_describe_analog_measurement",
        annotations=_READ_ONLY,
        description="Describe one registered analog metric and exact method, unit, source "
        "and qualification requirements. No caller formula, frequency, path or registration.",
        structured_output=True,
    )
    async def cadence_describe_analog_measurement(
        request: AnalogSelection,
    ) -> Annotated[CallToolResult, AnalogDescription]:
        return await _stable_result(service.describe_analog_measurement(request))

    @server.tool(
        name="cadence_analog_measurement_result",
        annotations=_READ_ONLY,
        description="Derive a registered analog metric from an admitted completed UUID4 using "
        "the described contract hash. Gain is at 10 Hz; bandwidth is a bracketed sampled-reference "
        "estimate. Missing qualification yields UNQUALIFIED, never a fabricated value. "
        "No simulation, PSF extraction or specification evaluation.",
        structured_output=True,
    )
    async def cadence_analog_measurement_result(
        request: AnalogQuery,
    ) -> Annotated[CallToolResult, AnalogResult]:
        return await _stable_result(service.analog_measurement_result(request))

    @server.tool(
        name="cadence_bandwidth_study_result",
        annotations=_READ_ONLY,
        description="Read the fixed two-grid bandwidth study for the preserved admitted native AC "
        "operation using registered bandwidth IDs and its original analog contract hash. "
        "Reports sampled 10 Hz reference flatness, first -3.0 dB crossing brackets and empirical "
        "grid convergence. Remains PARTIALLY_QUALIFIED without an absolute error bound. "
        "No simulation, caller frequency/grid/path/expression, raw vectors or target evaluation.",
        structured_output=True,
    )
    async def cadence_bandwidth_study_result(
        request: AnalogQuery,
    ) -> Annotated[CallToolResult, BandwidthStudyResult]:
        return await _stable_result(service.bandwidth_study_result(request))

    @server.tool(
        name="cadence_offset_study_result",
        annotations=_READ_ONLY,
        description="Read fixed nominal open-loop input-nulling diagnostics using the "
        "registered offset contract hash and preserved admitted DC operation. Applied Vp−Vm "
        "at Vop−Vom=0; five fixed scalar receipts, local bracket and refinement diagnostics. "
        "Numerical residual is consistent with zero, not physical precision. Generic offset "
        "remains UNQUALIFIED. No simulation, caller path/range/expression or goal evaluation.",
        structured_output=True,
    )
    async def cadence_offset_study_result(
        request: AnalogQuery,
    ) -> Annotated[CallToolResult, OffsetStudyResult]:
        return await _stable_result(service.offset_study_result(request))

    @server.tool(
        name="cadence_slew_study_result",
        annotations=_READ_ONLY,
        description="Read fixed reference open-loop differential step diagnostics using the "
        "registered slew contract hash and preserved admitted TRAN operation. Reports signed "
        "20--80% rise/fall secants, timestep and faster-edge agreement, nonlinear transition "
        "and saturated endpoints. Conventional slew remains UNQUALIFIED. No simulation, "
        "caller path/signal/stimulus/expression, raw vectors or specification evaluation.",
        structured_output=True,
    )
    async def cadence_slew_study_result(
        request: AnalogQuery,
    ) -> Annotated[CallToolResult, SlewStudyResult]:
        return await _stable_result(service.slew_study_result(request))

    @server.tool(
        name="cadence_describe_power_measurement",
        annotations=_READ_ONLY,
        description="Describe the separate dc-supply-power-v1 reader for a registered power "
        "metric and its unique qualified native DC source (registry v6/v7). Supply-rail power "
        "excludes bias/input sources, which are reported separately. Returns the required "
        "contract hash; no artifact availability check, extraction or simulation permission.",
        structured_output=True,
    )
    async def cadence_describe_power_measurement(
        request: PowerSelection,
    ) -> Annotated[CallToolResult, PowerDescription]:
        return await _stable_result(service.describe_power_measurement(request))

    @server.tool(
        name="cadence_power_measurement_result",
        annotations=_READ_ONLY,
        description="Read operator-extracted signed currents for the preserved admitted native "
        "DC operation using the described power contract hash and registered power metric ID. "
        "Reports W as sum(-V*I) for VDD/VSS, separate bias/input contributions, six-source "
        "inventory and provenance. Only the reviewed reference extraction exists; other "
        "operations fail closed. No new extraction, simulation, paths, formulas or target PASS.",
        structured_output=True,
    )
    async def cadence_power_measurement_result(
        request: PowerQuery,
    ) -> Annotated[CallToolResult, PowerResult]:
        return await _stable_result(service.power_measurement_result(request))

    @server.tool(
        name="cadence_list_measurements",
        annotations=_READ_ONLY,
        description="List registered bounded measurement definitions locally for a design ID. "
        "Reading requires an admitted completed analysis; no simulation or specification grant.",
        structured_output=True,
    )
    async def cadence_list_measurements(
        design_id: LogicalId,
    ) -> Annotated[CallToolResult, MeasurementList]:
        return await _stable_result(service.list_measurements(design_id))

    @server.tool(
        name="cadence_describe_measurement",
        annotations=_READ_ONLY,
        description="Describe a registered design/measurement ID and its contract hash, fixed "
        "units/method and read eligibility. No private bindings, registration or execution.",
        structured_output=True,
    )
    async def cadence_describe_measurement(
        request: MeasurementSelection,
    ) -> Annotated[CallToolResult, MeasurementDescription]:
        return await _stable_result(service.describe_measurement(request))

    @server.tool(
        name="cadence_measurement_result",
        annotations=_READ_ONLY,
        description="Read a bounded registered measurement from an admitted completed UUID4. "
        "Use the described contract hash; reuse validated scalar/spectrum/transient data and "
        "provenance. Never submit or extract anew. spec_evaluation remains not_evaluated.",
        structured_output=True,
    )
    async def cadence_measurement_result(
        request: MeasurementQuery,
    ) -> Annotated[CallToolResult, MeasurementResult]:
        return await _stable_result(service.measurement_result(request))

    @server.tool(
        name="cadence_list_pdk_adapters",
        annotations=_READ_ONLY,
        description="List registered logical PDK capabilities locally; no execution grant.",
        structured_output=True,
    )
    async def cadence_list_pdk_adapters() -> Annotated[CallToolResult, PdkList]:
        return await _stable_result(service.list_pdk_adapters())

    @server.tool(
        name="cadence_describe_pdk_adapter",
        annotations=_READ_ONLY,
        description="Inspect a registered PDK ID without physical bindings or model data.",
        structured_output=True,
    )
    async def cadence_describe_pdk_adapter(
        adapter_id: LogicalId,
    ) -> Annotated[CallToolResult, PdkDescription]:
        return await _stable_result(service.describe_pdk_adapter(adapter_id))

    @server.tool(
        name="cadence_design_pdk_status",
        annotations=_READ_ONLY,
        description="Resolve a registered design's PDK and environment compatibility locally. "
        "Fixed native compatibility is not generic qualification or execution authority.",
        structured_output=True,
    )
    async def cadence_design_pdk_status(
        design_id: LogicalId,
    ) -> Annotated[CallToolResult, DesignPdkStatus]:
        return await _stable_result(service.design_pdk_status(design_id))

    @server.tool(
        name="cadence_list_designs",
        description=(
            "List locally registered design descriptions. Registration grants no execution."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_list_designs() -> Annotated[CallToolResult, DesignList]:
        return await _stable_result(service.list_designs())

    @server.tool(
        name="cadence_describe_design",
        description=(
            "Describe the logical allowlists of one registered design ID without source bindings. "
            "Environment, PDK, variable ranges and generic execution remain unqualified."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_describe_design(
        design_id: LogicalId,
    ) -> Annotated[CallToolResult, DesignDescription]:
        return await _stable_result(service.describe_design(design_id))

    @server.tool(
        name="cadence_list_design_variables",
        description="Inspect registered logical numeric contracts locally; no private bindings.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_list_design_variables(
        design_id: LogicalId,
    ) -> Annotated[CallToolResult, VariableList]:
        return await _stable_result(service.list_design_variables(design_id))

    @server.tool(
        name="cadence_check_variable_values",
        description="Check explicit decimal text and units locally. Never execute, mutate or "
        "fill defaults; numeric admissibility grants no electrical or execution qualification.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_check_variable_values(
        request: VariableValuesRequest,
    ) -> Annotated[CallToolResult, VariableValuesResult]:
        return await _stable_result(service.check_variable_values(request))

    @server.tool(
        name="cadence_list_analyses",
        description="List registered analysis contracts and "
        "local dispatch eligibility. Fixed compatibility is not generic environment qualification.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_list_analyses(
        design_id: LogicalId,
    ) -> Annotated[CallToolResult, AnalysisList]:
        return await _stable_result(service.list_analyses(design_id))

    @server.tool(
        name="cadence_plan_analysis",
        description="Hash a registered fixed analysis locally. "
        "Planning does not reserve resources or grant runtime authority.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_plan_analysis(
        request: AnalysisSelection,
    ) -> Annotated[CallToolResult, AnalysisPlan]:
        return await _stable_result(service.plan_analysis(request))

    @server.tool(
        name="cadence_submit_analysis",
        description="Admit one UUID4 under its exact current "
        "plan hash and dispatch the compiled adapter. Retry the same ID: lookup only; never "
        "blindly resend. Native guards and cumulative budgets remain required.",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def cadence_submit_analysis(
        submission: AnalysisSubmission,
    ) -> Annotated[CallToolResult, AnalysisStatus]:
        return await _stable_result(service.submit_analysis(submission))

    @server.tool(
        name="cadence_analysis_status",
        description="Read an admitted operation's native "
        "state using its registered design, analysis and durable identity.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_analysis_status(
        request: AnalysisJobQuery,
    ) -> Annotated[CallToolResult, AnalysisStatus]:
        return await _stable_result(service.analysis_status(request))

    @server.tool(
        name="cadence_analysis_result",
        description="Read a bounded admitted native result "
        "and provenance. Specification evaluation remains not_evaluated.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_analysis_result(
        request: AnalysisJobQuery,
    ) -> Annotated[CallToolResult, AnalysisResult]:
        return await _stable_result(service.analysis_result(request))

    @server.tool(
        name="cadence_cancel_analysis",
        description="Inspect cancellation capability for an "
        "admitted operation. Native active cancellation is unsupported; terminal jobs are "
        "no-ops. No process is signalled and cancellation is never claimed.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_cancel_analysis(
        request: AnalysisJobQuery,
    ) -> Annotated[CallToolResult, AnalysisCancellation]:
        return await _stable_result(service.cancel_analysis(request))

    @server.tool(
        name="cadence_health",
        description=(
            "Read the fixed Cadence runner and tool availability without exposing license values."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_health() -> Annotated[CallToolResult, HealthReport]:
        return await _stable_result(service.health())

    @server.tool(
        name="cadence_submit_smoke",
        description=(
            "Submit the built-in Spectre smoke profile as a new remote job and return immediately."
        ),
        annotations=_SUBMIT,
        structured_output=True,
    )
    async def cadence_submit_smoke() -> Annotated[CallToolResult, JobStatus]:
        return await _stable_result(service.submit_smoke())

    @server.tool(
        name="cadence_job_status",
        description="Read status for one validated lowercase UUID job identifier.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_job_status(job_id: JobIdInput) -> Annotated[CallToolResult, JobStatus]:
        return await _stable_result(service.job_status(job_id))

    @server.tool(
        name="cadence_job_log_tail",
        description="Read at most 200 lines from the bounded stdout or stderr log of one job.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_job_log_tail(
        job_id: JobIdInput,
        stream: LogStreamInput,
        lines: LogLinesInput = 100,
    ) -> Annotated[CallToolResult, JobLogTail]:
        return await _stable_result(service.job_log_tail(job_id, stream, lines))

    @server.tool(
        name="cadence_job_result",
        description="Read the structured result and artifact metadata for one completed job.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_job_result(job_id: JobIdInput) -> Annotated[CallToolResult, JobResult]:
        return await _stable_result(service.job_result(job_id))

    @server.tool(
        name="cadence_cancel_job",
        description="Cancel only a job submitted by this MCP server process; this is destructive.",
        annotations=_CANCEL,
        structured_output=True,
    )
    async def cadence_cancel_job(job_id: JobIdInput) -> Annotated[CallToolResult, JobStatus]:
        return await _stable_result(service.cancel_job(job_id))

    @server.tool(
        name="cadence_list_libraries",
        description=(
            "List only reviewed project libraries and allowed-cell counts; exclude paths and "
            "proprietary file content."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_list_libraries() -> Annotated[CallToolResult, LibraryList]:
        return await _stable_result(service.list_libraries())

    @server.tool(
        name="cadence_list_cells",
        description=(
            "List only allowlisted cell names in one reviewed project library; exclude paths "
            "and proprietary file content."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_list_cells(
        library: DiscoveryIdentifierInput,
    ) -> Annotated[CallToolResult, CellList]:
        return await _stable_result(service.list_cells(library))

    @server.tool(
        name="cadence_inspect_cellview",
        description=(
            "Check existence of one allowlisted project cellview and return metadata only; "
            "never return cellview content."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_inspect_cellview(
        library: DiscoveryIdentifierInput,
        cell: DiscoveryIdentifierInput,
        view: DiscoveryIdentifierInput,
    ) -> Annotated[CallToolResult, CellViewInspection]:
        return await _stable_result(service.inspect_cellview(library, cell, view))

    @server.tool(
        name="cadence_list_profiles",
        description=(
            "List reviewed simulation profiles and their fixed analyses, corners, and outputs."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_list_profiles() -> Annotated[CallToolResult, ProfileList]:
        return await _stable_result(service.list_profiles())

    @server.tool(
        name="cadence_get_profile",
        description="Read one reviewed profile schema, variable units/ranges, and timeout.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_get_profile(
        profile_id: ProfileIdInput,
    ) -> Annotated[CallToolResult, SimulationProfile]:
        return await _stable_result(service.get_profile(profile_id))

    @server.tool(
        name="cadence_submit_profile",
        description=(
            "Submit one reviewed simulation profile with its exact variable contract; no raw "
            "netlist, OCEAN, SKILL, path, analysis, or output input is accepted."
        ),
        annotations=_SUBMIT,
        structured_output=True,
    )
    async def cadence_submit_profile(
        profile_id: ProfileIdInput,
        corner: ProfileCornerInput,
        variables: ProfileVariables,
    ) -> Annotated[CallToolResult, JobStatus]:
        return await _stable_result(service.submit_profile(profile_id, corner, variables))

    @server.tool(
        name="cadence_get_measurement_contract",
        description=(
            "Read the complete versioned synthetic ADC measurement definitions and formulas."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_get_measurement_contract(
        contract_id: MeasurementContractIdInput,
    ) -> Annotated[CallToolResult, AdcMeasurementContract]:
        return await _stable_result(service.get_measurement_contract(contract_id))

    @server.tool(
        name="cadence_measure_dc_power",
        description="Calculate mean DC supply power under one explicit measurement contract.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_measure_dc_power(
        request: DcPowerRequest,
    ) -> Annotated[CallToolResult, ScalarMetric]:
        return await _stable_result(service.measure_dc_power(request))

    @server.tool(
        name="cadence_measure_offset",
        description="Calculate mean voltage offset against the contract's fixed reference.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_measure_offset(
        request: OffsetRequest,
    ) -> Annotated[CallToolResult, ScalarMetric]:
        return await _stable_result(service.measure_offset(request))

    @server.tool(
        name="cadence_measure_settling",
        description="Calculate strict stay-within-band settling time from bounded samples.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_measure_settling(
        request: SettlingRequest,
    ) -> Annotated[CallToolResult, SettlingMetric]:
        return await _stable_result(service.measure_settling(request))

    @server.tool(
        name="cadence_measure_fft_metrics",
        description="Calculate contract-fixed SNR, SNDR, THD, and ENOB from 1024 samples.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_measure_fft_metrics(
        request: FftMeasurementRequest,
    ) -> Annotated[CallToolResult, FftMetrics]:
        return await _stable_result(service.measure_fft_metrics(request))

    @server.tool(
        name="cadence_measure_linearity",
        description="Calculate endpoint DNL and INL for the fixed three-bit synthetic contract.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_measure_linearity(
        request: LinearityRequest,
    ) -> Annotated[CallToolResult, LinearityMetrics]:
        return await _stable_result(service.measure_linearity(request))

    @server.tool(
        name="cadence_compare_corner_results",
        description="Compare exact NN, FF, and SS metric values against the NN reference.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_compare_corner_results(
        request: CornerComparisonRequest,
    ) -> Annotated[CallToolResult, CornerComparison]:
        return await _stable_result(service.compare_corner_results(request))

    @server.tool(
        name="cadence_summarize_monte_carlo",
        description="Calculate bounded deterministic Monte Carlo summary statistics.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_summarize_monte_carlo(
        request: MonteCarloRequest,
    ) -> Annotated[CallToolResult, MonteCarloSummary]:
        return await _stable_result(service.summarize_monte_carlo(request))

    @server.tool(
        name="cadence_design_write_plan",
        description=(
            "Read the one fixed copy-based property mutation plan and current target readiness; "
            "this performs no OA database write."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_design_write_plan() -> Annotated[CallToolResult, DesignWritePlan]:
        return await _stable_result(service.design_write_plan())

    @server.tool(
        name="cadence_list_native_diagnostics",
        description="List fixed native ADE DC/AC/trap TRAN settings and provenance contract.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_list_native_diagnostics() -> Annotated[
        CallToolResult, NativeDiagnosticProfiles
    ]:
        return await _stable_result(service.list_native_diagnostics())

    @server.tool(
        name="cadence_submit_native_diagnostic",
        description="Submit native ADE netlist, Spectre and PSF extraction. Reuse operation_id on "
        "retry; existing IDs never execute again. Fixed candidate only; cumulative limits apply.",
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def cadence_submit_native_diagnostic(
        request: NativeDiagnosticRequest,
    ) -> Annotated[CallToolResult, NativeDiagnosticStatus]:
        return await _stable_result(service.submit_native_diagnostic(request))

    @server.tool(
        name="cadence_native_diagnostic_status",
        description="Read native netlisting, simulation and extraction state by request ID.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_native_diagnostic_status(
        job_id: JobIdInput, analysis: NativeAnalysisInput
    ) -> Annotated[CallToolResult, NativeDiagnosticStatus]:
        return await _stable_result(service.native_diagnostic_status(job_id, analysis))

    @server.tool(
        name="cadence_native_diagnostic_result",
        description="Read native DC scalars, AC spectrum or bounded TRAN summary and provenance.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_native_diagnostic_result(
        job_id: JobIdInput, analysis: NativeAnalysisInput
    ) -> Annotated[CallToolResult, NativeDiagnosticResult]:
        return await _stable_result(service.native_diagnostic_result(job_id, analysis))

    @server.tool(
        name="cadence_list_actual_diagnostics",
        description="List the closed DC/AC diagnostic contract for the pinned work copy.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_list_actual_diagnostics() -> Annotated[
        CallToolResult, ActualDiagnosticProfiles
    ]:
        return await _stable_result(service.list_actual_diagnostics())

    @server.tool(
        name="cadence_submit_actual_diagnostic",
        description="Submit a fixed candidate DC or AC diagnostic under cumulative limits.",
        annotations=_SUBMIT,
        structured_output=True,
    )
    async def cadence_submit_actual_diagnostic(
        request: ActualDiagnosticRequest,
    ) -> Annotated[CallToolResult, ActualDiagnosticStatus]:
        return await _stable_result(service.submit_actual_diagnostic(request))

    @server.tool(
        name="cadence_actual_diagnostic_status",
        description="Read simulation and extraction state for one fixed work-copy diagnostic.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_actual_diagnostic_status(
        job_id: JobIdInput,
        analysis: ActualAnalysisInput,
    ) -> Annotated[CallToolResult, ActualDiagnosticStatus]:
        return await _stable_result(service.actual_diagnostic_status(job_id, analysis))

    @server.tool(
        name="cadence_actual_diagnostic_result",
        description="Read bounded scalar or spectrum measurements and provenance.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_actual_diagnostic_result(
        job_id: JobIdInput,
        analysis: ActualAnalysisInput,
    ) -> Annotated[CallToolResult, ActualDiagnosticResult]:
        return await _stable_result(service.actual_diagnostic_result(job_id, analysis))

    @server.tool(
        name="cadence_plan_sweep",
        description="Validate and hash one bounded variable sweep of a reviewed profile.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_plan_sweep(request: SweepRequest) -> Annotated[CallToolResult, SweepPlan]:
        return await _stable_result(service.plan_sweep(request))

    @server.tool(
        name="cadence_submit_sweep",
        description=(
            "Start or resume the same experiment key; each point has a deterministic child job."
        ),
        annotations=_SUBMIT,
        structured_output=True,
    )
    async def cadence_submit_sweep(
        submission: SweepSubmission,
    ) -> Annotated[CallToolResult, SweepStatus]:
        return await _stable_result(service.submit_sweep(submission))

    @server.tool(
        name="cadence_sweep_status",
        description="Read every point's durable state, including failures and unknown outcomes.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_sweep_status(sweep_id: JobIdInput) -> Annotated[CallToolResult, SweepStatus]:
        return await _stable_result(service.sweep_status(sweep_id))

    @server.tool(
        name="cadence_sweep_result",
        description="Read the bounded aggregate with per-point conditions and provenance.",
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_sweep_result(sweep_id: JobIdInput) -> Annotated[CallToolResult, SweepResult]:
        return await _stable_result(service.sweep_result(sweep_id))

    @server.tool(
        name="cadence_cancel_sweep",
        description="Cancel only child jobs recorded as owned by the requested sweep.",
        annotations=_CANCEL,
        structured_output=True,
    )
    async def cadence_cancel_sweep(sweep_id: JobIdInput) -> Annotated[CallToolResult, SweepStatus]:
        return await _stable_result(service.cancel_sweep(sweep_id))

    @server.tool(
        name="cadence_execute_design_write_validation",
        description=(
            "Execute the approved one-time copy, dry-run, backup, fixed property apply, exact "
            "verification, and rollback sequence. Requires the exact reviewed confirmation and "
            "is destructive/state-changing."
        ),
        annotations=_WRITE_VALIDATION,
        structured_output=True,
    )
    async def cadence_execute_design_write_validation(
        confirmation: WriteConfirmation,
    ) -> Annotated[CallToolResult, DesignWriteValidationResult]:
        return await _stable_result(service.execute_design_write_validation(confirmation))

    @server.tool(
        name="cadence_prepare_amplifier_sweep",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Prepare a compiled 1D finite reference amplifier grid with registered "
        "variable/analysis/measurement/definition hashes. Requires the reviewed operator numeric "
        "registry. Local only; no reservation, range expansion or source change.",
    )
    async def cadence_prepare_amplifier_sweep(
        request: AmplifierSweepRequest,
    ) -> Annotated[CallToolResult, AmplifierPrepared]:
        return await _stable_result(service.prepare_amplifier_sweep(request))

    @server.tool(
        name="cadence_submit_amplifier_sweep",
        annotations=_SUBMIT,
        structured_output=True,
        description="Submit/resume the exact prepared finite 1D amplifier grid using the existing "
        "durable sweep engine and shared EDA/resource guards. "
        "Same experiment UUID is lookup/resume; "
        "uncertain children never resubmit. No script/path/netlist or optimization input.",
    )
    async def cadence_submit_amplifier_sweep(
        submission: AmplifierSubmission,
    ) -> Annotated[CallToolResult, AmplifierStatus]:
        return await _stable_result(service.submit_amplifier_sweep(submission))

    @server.tool(
        name="cadence_amplifier_sweep_status",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Read the registered amplifier sweep journal and deterministic point states.",
    )
    async def cadence_amplifier_sweep_status(
        request: AmplifierQuery,
    ) -> Annotated[CallToolResult, AmplifierStatus]:
        return await _stable_result(service.amplifier_sweep_status(request))

    @server.tool(
        name="cadence_amplifier_sweep_result",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Read bounded qualified per-point10Hz differential gain or signed DC supply "
        "power with effective conditions and provenance. No raw PSF or target PASS/FAIL.",
    )
    async def cadence_amplifier_sweep_result(
        request: AmplifierQuery,
    ) -> Annotated[CallToolResult, AmplifierSweepResult]:
        return await _stable_result(service.amplifier_sweep_result(request))

    @server.tool(
        name="cadence_cancel_amplifier_sweep",
        annotations=_CANCEL,
        structured_output=True,
        description="Durably cancel unstarted amplifier sweep points only. Active simulator "
        "continues; no process termination or active cancellation qualification.",
    )
    async def cadence_cancel_amplifier_sweep(
        request: AmplifierQuery,
    ) -> Annotated[CallToolResult, AmplifierStatus]:
        return await _stable_result(service.cancel_amplifier_sweep(request))

    @server.tool(
        name="cadence_amplifier_specification_catalog",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Inspect at most16 operator-owned version3 gain/power goals and the target "
        "catalog digest. Empty by default; no target registration or simulation from MCP.",
    )
    async def cadence_amplifier_specification_catalog(
        design_id: LogicalId,
    ) -> Annotated[CallToolResult, AmplifierSpecificationCatalog]:
        return await _stable_result(service.amplifier_specification_catalog(design_id))

    @server.tool(
        name="cadence_evaluate_amplifier_specifications",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Evaluate registered goals against exact admitted amplifier sweep point "
        "facts using source/catalog digests and the existing comparator. Absent goal remains "
        "NOT_EVALUATED. Exact conditions only; "
        "no caller target/value/path/script or new execution.",
    )
    async def cadence_evaluate_amplifier_specifications(
        request: AmplifierEvaluationQuery,
    ) -> Annotated[CallToolResult, AmplifierSpecificationEvaluation]:
        return await _stable_result(service.evaluate_amplifier_specifications(request))

    from cadence_mcp_bridge.runtime_context import OperatorService

    if isinstance(service, OperatorService) and service.native_operations is not None:
        native = service.native_operations

        from cadence_mcp_bridge.native_server import register_native_tools

        register_native_tools(server, native)

    return server


def create_default_server(*, operator_mode: bool = False) -> MCPServer:
    config = (
        BridgeConfig(runtime_mode="operator")
        if operator_mode
        else BridgeConfig(
            runtime_mode="legacy_reference", runtime_settings_path=None, runtime_context_id=None
        )
    )
    if config.runtime_mode == "operator":
        from cadence_mcp_bridge.runtime_context import create_operator_service

        return create_server(cast(CadenceService, create_operator_service(config)))
    designs = None
    pdks = None
    amplifier_specs = None
    if config.amplifier_specification_registry_path is not None:
        try:
            amplifier_specs = load_amplifier_specifications(
                config.amplifier_specification_registry_path
            )
        except InvalidInputError:
            raise ConfigurationError("Configured amplifier target registry is invalid") from None
    if config.pdk_registry_path is not None:
        try:
            pdks, _ = load_pdk_registry(config.pdk_registry_path)
        except PdkRejected:
            raise ConfigurationError("Configured PDK registry is invalid") from None
    if config.design_registry_path is not None:
        try:
            designs, _ = load_design_registry(config.design_registry_path)
        except DesignRejected:
            raise ConfigurationError("Configured design registry is invalid") from None
    return create_server(
        CadenceService(
            OpenSshBackend(config),
            designs,
            analysis_journal=config.analysis_journal_path,
            sweep_journal=config.sweep_journal_path,
            pdks=pdks,
            amplifier_specifications=amplifier_specs,
        )
    )


def run_stdio_server(*, operator_mode: bool = False) -> None:
    """Run locally over stdio; all application logging is directed to stderr."""

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    create_default_server(operator_mode=operator_mode).run("stdio")
