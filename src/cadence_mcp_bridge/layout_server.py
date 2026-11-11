"""Typed layout tools with lazy, explicitly configured native execution."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, cast

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ToolAnnotations
from pydantic import BaseModel, BeforeValidator

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.layout_engine import LayoutRejected
from cadence_mcp_bridge.layout_models import (
    LayoutApplyRequest,
    LayoutDiffRequest,
    LayoutForkRequest,
    LayoutInspectRequest,
    LayoutPlan,
    LayoutPlanRequest,
    LayoutResult,
    LayoutSelectRequest,
    LayoutSnapshot,
)
from cadence_mcp_bridge.layout_service import LayoutService
from cadence_mcp_bridge.models import ContractModel

LAYOUT_ACTIONS = ("inspect", "fork", "plan", "apply", "diff", "select")
LAYOUT_TOOLS = frozenset("cadence_layout_" + action for action in LAYOUT_ACTIONS)


def _json_request[ModelT: BaseModel](model: type[ModelT]) -> Callable[[Any], ModelT]:
    def parse(value: Any) -> ModelT:
        if isinstance(value, model):
            return value
        if type(value) is not dict:
            raise ValueError("layout_request_object_required")
        # Strict tuple models accept JSON arrays in JSON mode. Preserve all scalar
        # validation instead of using strict=False on the SDK's Python dictionary.
        return model.model_validate_json(json.dumps(value, allow_nan=False))

    return parse


InspectInput = Annotated[LayoutInspectRequest, BeforeValidator(_json_request(LayoutInspectRequest))]
ForkInput = Annotated[LayoutForkRequest, BeforeValidator(_json_request(LayoutForkRequest))]
PlanInput = Annotated[LayoutPlanRequest, BeforeValidator(_json_request(LayoutPlanRequest))]
ApplyInput = Annotated[LayoutApplyRequest, BeforeValidator(_json_request(LayoutApplyRequest))]
DiffInput = Annotated[LayoutDiffRequest, BeforeValidator(_json_request(LayoutDiffRequest))]
SelectInput = Annotated[LayoutSelectRequest, BeforeValidator(_json_request(LayoutSelectRequest))]


async def _checked[ResultT: BaseModel](operation: Awaitable[ResultT]) -> ResultT:
    try:
        return await operation
    except LayoutRejected as exc:
        reason = (
            exc.reason if re.fullmatch(r"[a-z][a-z0-9_]{0,95}", exc.reason) else "layout_rejected"
        )
        raise InvalidInputError("Layout request rejected", details={"reason": reason}) from None


async def _layout_result(operation: Awaitable[BaseModel]) -> CallToolResult:
    from cadence_mcp_bridge.server import _stable_result

    model: BaseModel | None = None

    async def invoke() -> ContractModel:
        nonlocal model
        model = await operation
        return cast(ContractModel, model)

    response = await _stable_result(invoke())
    if not response.is_error and model is not None:
        # SDK validates structured output in Python mode before encoding the wire.
        # Retain strict tuples here; JSON serialization still emits normal arrays.
        response.structured_content = model.model_dump(mode="python", by_alias=True)
    return response


class LazyLayoutService:
    """Discovery never loads a provider or contacts the VM."""

    def __init__(self, settings: BridgeConfig | None) -> None:
        self.settings = settings
        self._service: LayoutService | None = None

    def get(self) -> LayoutService:
        if (
            self.settings is None
            or self.settings.runtime_mode != "operator"
            or self.settings.runtime_settings_path is None
            or self.settings.runtime_context_id is None
        ):
            raise ConfigurationError(
                "Layout requires an explicitly configured development context",
                details={"reason": "layout_development_context_required"},
            )
        if self._service is None:
            from cadence_mcp_bridge.layout_native import create_layout_service

            self._service = create_layout_service(self.settings)
        return self._service

    async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot:
        return await _checked(self.get().inspect(request))

    async def fork(self, request: LayoutForkRequest) -> LayoutResult:
        return await _checked(self.get().fork(request))

    async def plan(self, request: LayoutPlanRequest) -> LayoutPlan:
        return await _checked(self.get().plan(request))

    async def apply(self, request: LayoutApplyRequest) -> LayoutResult:
        return await _checked(self.get().apply(request))

    async def diff(self, request: LayoutDiffRequest) -> LayoutResult:
        return await _checked(self.get().diff(request))

    async def select(self, request: LayoutSelectRequest) -> LayoutResult:
        return await _checked(self.get().select(request))


def register_layout_tools(server: MCPServer, settings: BridgeConfig | None) -> None:
    from cadence_mcp_bridge.server import _READ_ONLY

    layout = LazyLayoutService(settings)
    write = ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
    )

    @server.tool(
        name="cadence_layout_inspect", annotations=_READ_ONLY, structured_output=True,
        description="Inspect one registered layout revision, objects and observed DBU/grid/LPP. "
        "Requires a configured development context; no caller paths or commands.",
    )
    async def inspect(request: InspectInput) -> Annotated[CallToolResult, LayoutSnapshot]:
        return await _layout_result(layout.inspect(request))

    @server.tool(
        name="cadence_layout_fork", annotations=write, structured_output=True,
        description="Fork a registered source into an exclusive owned working revision. "
        "Original remains protected; operation identity prevents duplicate copies.",
    )
    async def fork(request: ForkInput) -> Annotated[CallToolResult, LayoutResult]:
        return await _layout_result(layout.fork(request))

    @server.tool(
        name="cadence_layout_plan", annotations=_READ_ONLY, structured_output=True,
        description="Validate typed move/add_rect/add_pin edits against an observed revision. "
        "Absolute orient edits require a qualified route. "
        "Returns exact plan hash and predicted diff; planning performs no layout write.",
    )
    async def plan(request: PlanInput) -> Annotated[CallToolResult, LayoutPlan]:
        return await _layout_result(layout.plan(request))

    @server.tool(
        name="cadence_layout_apply", annotations=write, structured_output=True,
        description="Apply the exact hashed plan within configured owned-revision authority. "
        "Retains uncertain outcomes; identical operation retries never resend a write. "
        "Save/reopen verification is separate from DRC/LVS/PEX qualification.",
    )
    async def apply(request: ApplyInput) -> Annotated[CallToolResult, LayoutResult]:
        return await _layout_result(layout.apply(request))

    @server.tool(
        name="cadence_layout_diff", annotations=_READ_ONLY, structured_output=True,
        description="Read retained layout changes and save/reopen/source-preservation evidence "
        "against an exact previous revision; no new apply or physical verification.",
    )
    async def diff(request: DiffInput) -> Annotated[CallToolResult, LayoutResult]:
        return await _layout_result(layout.diff(request))

    @server.tool(
        name="cadence_layout_select", annotations=write, structured_output=True,
        description="Select a preserved layout revision by exact baseline hash. "
        "Preserves subsequent revisions and partial results; never overwrites the original.",
    )
    async def select(request: SelectInput) -> Annotated[CallToolResult, LayoutResult]:
        return await _layout_result(layout.select(request))
