"""MCP SDK v2 adapter exposing only reviewed Cadence tools."""

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import WithJsonSchema

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import BridgeError
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
    AdeProfileIntrospection,
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
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.write_models import (
    DesignWritePlan,
    DesignWriteValidationResult,
    WriteConfirmation,
)

_LOGGER = logging.getLogger(__name__)

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
AdeProfileIdInput = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "enum": ["actual-differential-amplifier-tb2-transient"],
            "description": "The sole reviewed actual ADE L profile identifier.",
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


def create_server(service: CadenceService) -> MCPServer:
    """Build an MCP server around an injected service for production or tests."""

    server = MCPServer(
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
        name="cadence_inspect_ade_profile",
        description=(
            "Inspect the one reviewed ADE L state with fixed read-only OA and metadata probes; "
            "return no paths, raw state, netlist, model, OCEAN, or SKILL content."
        ),
        annotations=_READ_ONLY,
        structured_output=True,
    )
    async def cadence_inspect_ade_profile(
        profile_id: AdeProfileIdInput,
    ) -> Annotated[CallToolResult, AdeProfileIntrospection]:
        return await _stable_result(service.inspect_ade_profile(profile_id))

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

    return server


def create_default_server() -> MCPServer:
    config = BridgeConfig()
    return create_server(CadenceService(OpenSshBackend(config)))


def run_stdio_server() -> None:
    """Run locally over stdio; all application logging is directed to stderr."""

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    create_default_server().run("stdio")
