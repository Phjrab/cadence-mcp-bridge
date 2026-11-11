"""Read-only user adapters for registered CMOS TRAN delay results."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Annotated, Any, cast

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult

from cadence_mcp_bridge.cmos_delay_service import (
    CmosDelayResultQuery,
    CmosDelayService,
    RegisteredCmosDelayResult,
)
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import BridgeError, ConfigurationError, InvalidInputError
from cadence_mcp_bridge.models import ContractModel, ErrorResponse
from cadence_mcp_bridge.operator_operations import OperationRejected, bounded_document
from cadence_mcp_bridge.runtime_context import RuntimeRejected, select_context

DELAY_TOOL = "cadence_cmos_delay_result"


def create_cmos_delay_service(settings: BridgeConfig | None) -> CmosDelayService:
    """Select the existing operator registration; no caller backend or execution path."""
    if settings is None or settings.runtime_mode != "operator":
        raise ConfigurationError("CMOS delay requires an explicit operator context")
    try:
        context = select_context(settings)
    except RuntimeRejected:
        raise ConfigurationError("CMOS delay operator context rejected") from None
    if context is None:
        raise ConfigurationError("CMOS delay requires an explicit operator context")
    return CmosDelayService(context)


async def delay_result(
    settings: BridgeConfig | None, request: CmosDelayResultQuery,
) -> RegisteredCmosDelayResult:
    try:
        return await create_cmos_delay_service(settings).result(request)
    except OperationRejected as exc:
        reason = (exc.reason if re.fullmatch(r"[a-z][a-z0-9_]{0,95}", exc.reason)
                  else "cmos_delay_rejected")
        raise InvalidInputError("CMOS delay request rejected", details={"reason": reason}) from None


def register_cmos_delay_tool(server: MCPServer, settings: BridgeConfig | None) -> None:
    from cadence_mcp_bridge.server import _READ_ONLY, _stable_result

    @server.tool(
        name=DELAY_TOOL, annotations=_READ_ONLY, structured_output=True,
        description="Evaluate sampled CMOS delays from an already succeeded registered TRAN "
        "operation and exact plan hash, including separate registered supply voltage. "
        "No caller waveforms, simulation, extraction or reservation. Local estimates remain "
        "NOT_ATTESTED; logic/physical qualification NOT_ASSESSED, transient power unsupported.",
    )
    async def result(
        request: CmosDelayResultQuery,
    ) -> Annotated[CallToolResult, RegisteredCmosDelayResult]:
        model: RegisteredCmosDelayResult | None = None

        async def invoke() -> ContractModel:
            nonlocal model
            model = await delay_result(settings, request)
            return cast(ContractModel, model)

        response = await _stable_result(invoke())
        if not response.is_error and model is not None:
            # Preserve strict tuple types for SDK Python-mode output validation.
            response.structured_content = model.model_dump(mode="python", by_alias=True)
        return response


def add_cmos_delay_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    parser = subparsers.add_parser("cmos-delay", help="Read registered TRAN delay evidence.")
    actions = parser.add_subparsers(dest="delay_action", required=True)
    actions.add_parser("schema", help="Local query schema; no native configuration required.")
    result = actions.add_parser("result")
    result.add_argument("--request", type=Path, required=True)
    result.add_argument("--settings", type=Path)
    result.add_argument("--context")


def cmos_delay_cli(arguments: argparse.Namespace) -> int:
    try:
        if arguments.delay_action == "schema":
            print(json.dumps(CmosDelayResultQuery.model_json_schema()))
            return 0
        settings_args: dict[str, Any] = {"runtime_mode": "operator"}
        if arguments.settings is not None:
            settings_args["runtime_settings_path"] = arguments.settings
        if arguments.context is not None:
            settings_args["runtime_context_id"] = arguments.context
        request = CmosDelayResultQuery.model_validate_json(bounded_document(arguments.request))
        result = asyncio.run(delay_result(BridgeConfig(**settings_args), request))
    except BridgeError as exc:
        print(ErrorResponse(error=exc.to_envelope()).model_dump_json())
        return 1
    except (OSError, ValueError):
        error = InvalidInputError("Invalid CMOS delay query or operator configuration")
        print(ErrorResponse(error=error.to_envelope()).model_dump_json())
        return 1
    except Exception:
        internal = BridgeError("CMOS delay result unavailable; inspect retained operation")
        print(ErrorResponse(error=internal.to_envelope()).model_dump_json())
        return 1
    print(result.model_dump_json())
    return 0
