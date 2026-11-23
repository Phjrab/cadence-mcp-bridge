"""Dedicated MCP profile for the single registered amplifier PM0 apply service."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.amplifier_pm0_default import RegisteredAmplifierPm0DefaultChange
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest, PmosDefaultChangeResult
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.pmos_default_service import registered_pmos_default_change
from cadence_mcp_bridge.runtime_context import select_context


def create_fixed_amp_pm0_server(config: BridgeConfig) -> MCPServer:
    def resolve() -> tuple[str, RegisteredAmplifierPm0DefaultChange]:
        if config.runtime_mode != "operator":
            raise ConfigurationError("Fixed AMP PM0 requires operator mode")
        context = select_context(config)
        if context is None:
            raise ConfigurationError("Fixed AMP PM0 requires an operator context")
        service = registered_pmos_default_change(context)
        if not isinstance(service, RegisteredAmplifierPm0DefaultChange):
            raise ConfigurationError("Fixed AMP PM0 requires the AMP registration")
        return context.context_sha256, service

    try:
        context_sha256, _ = resolve()
    except (OSError, ValueError, ConfigurationError):
        raise ConfigurationError("Fixed AMP PM0 is not registered") from None
    server = MCPServer(name="cadence-amp-fixed-pm0", version=__version__, log_level="WARNING")

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, open_world_hint=True,
        ),
        structured_output=True,
        description="Apply or replay the one host-registered PM0 operation by exact ID, plan "
        "and scope pins. Check replayed and dispatched_this_call for the result of this call.",
    )
    def cadence_apply_fixed_amp_pm0(request: PmosDefaultChangeRequest) -> PmosDefaultChangeResult:
        try:
            current_sha256, service = resolve()
            if current_sha256 != context_sha256:
                raise ConfigurationError("Fixed AMP PM0 context changed")
            return service.apply(request)
        except (OSError, ValueError, ConfigurationError):
            raise ToolError("registered_fixed_amp_pm0_rejected") from None

    return server
