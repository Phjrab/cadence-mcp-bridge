"""Dedicated MCP profile for an operator-registered MOS update."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.candidate_cli import read_candidate_document
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import BridgeError, ConfigurationError
from cadence_mcp_bridge.mos_dc_operator import (
    MosDcCompareRequest,
    MosDcComparison,
    compare_registered_mos_dc,
)
from cadence_mcp_bridge.parameter_changes import ChangePlan
from cadence_mcp_bridge.registered_mos_edit import RegisteredMosEditResult, RegisteredMosEditService
from cadence_mcp_bridge.registered_mos_sizing import RegisteredMosSizingResult
from cadence_mcp_bridge.registered_mos_sizing_transport import (
    MosSizingApply,
    MosSizingCandidate,
    MosSizingLookup,
    MosSizingPreview,
    MosSizingRegistrationInfo,
    RegisteredMosSizing,
    selected_mos_sizing,
)
from cadence_mcp_bridge.registered_mos_transport import registered_mos_edit
from cadence_mcp_bridge.runtime_context import ExecutionContext, select_context
from cadence_mcp_bridge.variable_contracts import VariableModel

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_REJECTED = "registered_mos_edit_rejected"
_APPLY = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=True,
    open_world_hint=True,
)


class RegisteredMosPlan(VariableModel):
    identity: PmosDefaultChangeRequest
    plan: ChangePlan
    execution_authorized: Literal[False] = False


def _resolve(
    config: BridgeConfig,
) -> tuple[ExecutionContext, RegisteredMosEditService | RegisteredMosSizing]:
    context = select_context(config) if config.runtime_mode == "operator" else None
    if context is None:
        raise ConfigurationError("Registered MOS edit requires an operator context")
    sizing = selected_mos_sizing(context)
    return context, sizing if sizing is not None else registered_mos_edit(context)


def _plan(service: RegisteredMosEditService) -> RegisteredMosPlan:
    return RegisteredMosPlan(identity=service.identity, plan=service.plan)


def run_registered_mos_edit(arguments: argparse.Namespace) -> int:
    try:
        action = arguments.mos_edit_action
        raw = b""
        if action != "inspect-sizing":
            path, digest = arguments.request
            raw = read_candidate_document(Path(path), expected_sha256=digest)
        context, service = _resolve(
            BridgeConfig(
                runtime_mode="operator",
                runtime_settings_path=arguments.settings,
                runtime_context_id=arguments.context,
            )
        )
        result: VariableModel
        if isinstance(service, RegisteredMosSizing):
            if action == "inspect-sizing":
                result = service.inspect()
            elif action == "plan-sizing":
                result = service.plan(MosSizingCandidate.model_validate_json(raw))
            elif action == "apply-sizing":
                result = service.apply(MosSizingApply.model_validate_json(raw))
            elif action == "lookup-sizing":
                result = service.lookup(PmosDefaultChangeRequest.model_validate_json(raw))
            elif action == "compare-sizing":
                result = asyncio.run(
                    compare_registered_mos_dc(
                        context,
                        service,
                        MosDcCompareRequest.model_validate_json(raw),
                    )
                )
            else:
                raise ValueError("Sizing actions require their own typed request")
        else:
            request = PmosDefaultChangeRequest.model_validate_json(raw)
            if request != service.identity:
                raise ValueError("Registered MOS edit identity differs")
            if action == "plan":
                result = _plan(service)
            elif action == "lookup":
                result = service.lookup(request)
            elif action == "apply":
                result = service.apply(request)
            else:
                raise ValueError("The selected profile does not enroll W/L sizing")
    except (OSError, ValueError, BridgeError):
        print(json.dumps({"status": "REGISTERED_MOS_EDIT_REJECTED"}))
        return 2
    print(result.model_dump_json())
    return 0


def create_registered_mos_edit_server(config: BridgeConfig) -> MCPServer:
    try:
        context, registered = _resolve(config)
    except (OSError, ValueError, BridgeError):
        raise ConfigurationError("Registered MOS edit is unavailable") from None

    server = MCPServer(name="cadence-registered-mos-edit", version=__version__, log_level="WARNING")
    context_pin = context.context_sha256
    if isinstance(registered, RegisteredMosSizing):
        _register_sizing_tools(server, config, context_pin, registered.enrollment_sha256)
        return server

    identity = registered.identity

    def service_for(request: PmosDefaultChangeRequest) -> RegisteredMosEditService:
        selected, service = _resolve(config)
        if (
            isinstance(service, RegisteredMosSizing)
            or selected.context_sha256 != context_pin
            or request != identity
            or service.identity != identity
        ):
            raise ValueError("Registered MOS edit changed")
        return service

    @server.tool(annotations=_READ, structured_output=True)
    def cadence_plan_registered_mos_edit(
        request: PmosDefaultChangeRequest,
    ) -> RegisteredMosPlan:
        """Read the exact reviewed MOS change plan and its operation pins."""
        try:
            service = service_for(request)
            return _plan(service)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    @server.tool(annotations=_APPLY, structured_output=True)
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


def _register_sizing_tools(
    server: MCPServer, config: BridgeConfig, context_pin: str, enrollment_sha: str
) -> None:
    def resolved() -> tuple[ExecutionContext, RegisteredMosSizing]:
        selected, service = _resolve(config)
        if (
            selected.context_sha256 != context_pin
            or not isinstance(service, RegisteredMosSizing)
            or service.enrollment_sha256 != enrollment_sha
        ):
            raise ValueError("Registered MOS sizing enrollment changed")
        return selected, service

    def current() -> RegisteredMosSizing:
        return resolved()[1]

    @server.tool(annotations=_READ, structured_output=True)
    def cadence_inspect_registered_mos_sizing() -> MosSizingRegistrationInfo:
        """Read the pinned target, current dimensions and registered W/L admission."""
        try:
            return current().inspect()
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    @server.tool(annotations=_READ, structured_output=True)
    def cadence_plan_registered_mos_sizing(request: MosSizingCandidate) -> MosSizingPreview:
        """Validate and preview a new W/L candidate within the registered slot and bounds."""
        try:
            return current().plan(request)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    @server.tool(annotations=_APPLY, structured_output=True)
    def cadence_apply_registered_mos_sizing(request: MosSizingApply) -> RegisteredMosSizingResult:
        """Apply the exact previewed W/L plan or return the existing same-ID outcome."""
        try:
            return current().apply(request)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    @server.tool(annotations=_READ, structured_output=True)
    def cadence_lookup_registered_mos_sizing(request: PmosDefaultChangeRequest) -> MosSizingLookup:
        """Read a retained W/L edit outcome without dispatching a writer."""
        try:
            return current().lookup(request)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None

    @server.tool(
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
        structured_output=True,
    )
    async def cadence_compare_registered_mos_sizing(
        request: MosDcCompareRequest,
    ) -> MosDcComparison:
        """Compare retained fixed-DC measurements for up to three registered W/L edits."""
        try:
            context, service = resolved()
            return await compare_registered_mos_dc(context, service, request)
        except (OSError, ValueError, BridgeError):
            raise ToolError(_REJECTED) from None
