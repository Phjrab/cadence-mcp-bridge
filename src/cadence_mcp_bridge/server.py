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
)
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

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

    return server


def create_default_server() -> MCPServer:
    config = BridgeConfig()
    return create_server(CadenceService(OpenSshBackend(config)))


def run_stdio_server() -> None:
    """Run locally over stdio; all application logging is directed to stderr."""

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    create_default_server().run("stdio")
