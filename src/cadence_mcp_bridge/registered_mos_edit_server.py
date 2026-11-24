"""Dedicated MCP profile for an operator-registered MOS update."""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import BridgeError, ConfigurationError
from cadence_mcp_bridge.parameter_changes import ChangePlan
from cadence_mcp_bridge.registered_mos_edit import RegisteredMosEditResult, RegisteredMosEditService
from cadence_mcp_bridge.registered_mos_transport import registered_mos_edit
from cadence_mcp_bridge.runtime_context import select_context
from cadence_mcp_bridge.variable_contracts import VariableModel

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_REJECTED = "registered_mos_edit_rejected"


class RegisteredMosPlan(VariableModel):
    identity: PmosDefaultChangeRequest
    plan: ChangePlan
    execution_authorized: Literal[False] = False


def create_registered_mos_edit_server(config: BridgeConfig) -> MCPServer:
    def resolve() -> tuple[str, RegisteredMosEditService]:
        context = select_context(config) if config.runtime_mode == "operator" else None
        if context is None:
            raise ConfigurationError("Registered MOS edit requires an operator context")
        return context.context_sha256, registered_mos_edit(context)

    try:
        context_pin, registered = resolve()
    except (OSError, ValueError, BridgeError):
        raise ConfigurationError("Registered MOS edit is unavailable") from None

    identity = registered.identity
    server = MCPServer(name="cadence-registered-mos-edit", version=__version__, log_level="WARNING")

    def service_for(request: PmosDefaultChangeRequest) -> RegisteredMosEditService:
        current_pin, service = resolve()
        if current_pin != context_pin or request != identity or service.identity != identity:
            raise ValueError("Registered MOS edit changed")
        return service

    @server.tool(annotations=_READ, structured_output=True)
    def cadence_plan_registered_mos_edit(
        request: PmosDefaultChangeRequest,
    ) -> RegisteredMosPlan:
        """Read the exact reviewed MOS change plan and its operation pins."""
        try:
            service = service_for(request)
            return RegisteredMosPlan(identity=service.identity, plan=service.plan)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
            open_world_hint=True,
        ),
        structured_output=True,
    )
    def cadence_apply_registered_mos_edit(
        request: PmosDefaultChangeRequest,
    ) -> RegisteredMosEditResult:
        """Apply the registered change or replay the retained outcome for the same identity."""
        try:
            return service_for(request).apply(request)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    @server.tool(annotations=_READ, structured_output=True)
    def cadence_lookup_registered_mos_edit(
        request: PmosDefaultChangeRequest,
    ) -> RegisteredMosEditResult:
        """Read retained MOS edit evidence without dispatching a writer."""
        try:
            return service_for(request).lookup(request)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    return server
