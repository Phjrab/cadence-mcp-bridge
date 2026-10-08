"""Conditional fixed-operation tools for an explicitly configured operator service."""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from cadence_mcp_bridge.native_service import (
    NativeOperationPlan,
    NativeOperationQuery,
    NativeOperationRequest,
    NativeOperationResult,
    NativeOperationService,
    NativeOperationStatus,
    NativeOperationSubmission,
)
from cadence_mcp_bridge.server import _READ_ONLY, _stable_result


def register_native_tools(server: MCPServer, native: NativeOperationService) -> None:
    @server.tool(
        name="cadence_plan_operation",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Plan explicit registered numeric values under the operator grant. "
        "Local only; no reservation or permission is created.",
    )
    async def cadence_plan_operation(
        request: NativeOperationRequest,
    ) -> Annotated[CallToolResult, NativeOperationPlan]:
        return await _stable_result(native.plan(request))

    @server.tool(
        name="cadence_submit_operation",
        structured_output=True,
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        description="Submit one registered DC/AC/TRAN operation under confirmed operator scope "
        "and existing shared accounting. Same UUID retries only look up; never resend.",
    )
    async def cadence_submit_operation(
        submission: NativeOperationSubmission,
    ) -> Annotated[CallToolResult, NativeOperationStatus]:
        return await _stable_result(native.observe(submission, submission.request))

    @server.tool(
        name="cadence_operation_status",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Reconcile one admitted UUID and exact plan hash without dispatch or spend.",
    )
    async def cadence_operation_status(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, NativeOperationStatus]:
        return await _stable_result(native.observe(request))

    @server.tool(
        name="cadence_operation_result",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Retrieve registered bounded measurements with terminal receipt, input, "
        "reader, frame and PSF integrity checks. Never reruns simulation or extraction.",
    )
    async def cadence_operation_result(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, NativeOperationResult]:
        return await _stable_result(native.result(request))

    @server.tool(
        name="cadence_cancel_pending_operation",
        structured_output=True,
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        description="Cancel only a verified pending or absent-intent operation with a durable "
        "remote tombstone. No active termination or reservation refund.",
    )
    async def cadence_cancel_pending_operation(
        request: NativeOperationQuery,
    ) -> Annotated[CallToolResult, NativeOperationStatus]:
        return await _stable_result(native.observe(request, cancel=True))
