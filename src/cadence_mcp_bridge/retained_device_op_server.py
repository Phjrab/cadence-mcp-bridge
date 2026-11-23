"""Dedicated grantless MCP endpoint for retained DC and device OP evidence."""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.research_adapters import DeviceOpResult
from cadence_mcp_bridge.research_measurements import DeviceOpQuery
from cadence_mcp_bridge.retained_device_op import retained_device_op_result
from cadence_mcp_bridge.runtime_context import select_context


def create_retained_device_op_server(config: BridgeConfig) -> MCPServer:
    context = select_context(config) if config.runtime_mode == "operator" else None
    if context is None or (
        context.binding.native_provider_binding is not None
        or context.binding.operator_grant is not None
        or context.binding.device_op_catalog_path is None
        or context.binding.device_op_catalog_sha256 is None
    ):
        raise ConfigurationError("Retained device OP requires a grantless catalog context")

    server = MCPServer(name="cadence-retained-device-op", version=__version__, log_level="WARNING")

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
        structured_output=True,
        description="Read the registered retained DC report and device operating-point evidence.",
    )
    def cadence_research_device_op_result(request: DeviceOpQuery) -> DeviceOpResult:
        try:
            return retained_device_op_result(context, request)
        except (OSError, ValueError, ConfigurationError):
            raise ToolError("registered_research_device_op_unavailable") from None

    return server
