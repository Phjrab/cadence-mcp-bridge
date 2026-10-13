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
from cadence_mcp_bridge.native_specifications import (
    NativeSpecificationQuery,
    NativeSpecificationResult,
    NativeSpecificationSupervisor,
)
from cadence_mcp_bridge.native_sweeps import (
    NativeSweepPlanned,
    NativeSweepQuery,
    NativeSweepRequest,
    NativeSweepResult,
    NativeSweepStatus,
    NativeSweepSubmission,
    NativeSweepSupervisor,
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

    sweeps = NativeSweepSupervisor(native)
    write = ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    )

    @server.tool(
        name="cadence_plan_native_sweep",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Plan up to16 explicit registered values on one qualified axis. "
        "Independent points use existing native authority/accounting. No dispatch.",
    )
    async def cadence_plan_native_sweep(
        request: NativeSweepRequest,
    ) -> Annotated[CallToolResult, NativeSweepPlanned]:
        return await _stable_result(sweeps.plan(request))

    @server.tool(
        name="cadence_submit_native_sweep",
        annotations=write,
        structured_output=True,
        description="Persist one immutable sweep and child UUIDs. No simulator dispatch. "
        "Same sweep-ID retries only observe the existing plan.",
    )
    async def cadence_submit_native_sweep(
        submission: NativeSweepSubmission,
    ) -> Annotated[CallToolResult, NativeSweepStatus]:
        return await _stable_result(sweeps.submit(submission))

    @server.tool(
        name="cadence_advance_native_sweep",
        annotations=write,
        structured_output=True,
        description="Admit at most one untouched point after preceding points succeed. "
        "Stops at unknown outcome/failure; existing UUID retries never resend.",
    )
    async def cadence_advance_native_sweep(
        request: NativeSweepQuery,
    ) -> Annotated[CallToolResult, NativeSweepStatus]:
        return await _stable_result(sweeps.advance(request))

    @server.tool(
        name="cadence_native_sweep_status",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Reconcile registered sweep points without starting new work.",
    )
    async def cadence_native_sweep_status(
        request: NativeSweepQuery,
    ) -> Annotated[CallToolResult, NativeSweepStatus]:
        return await _stable_result(sweeps.status(request))

    @server.tool(
        name="cadence_native_sweep_result",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Read bounded integrity-verified results from a completed sweep. "
        "No simulation/extraction retry, budget refund or raw file download.",
    )
    async def cadence_native_sweep_result(
        request: NativeSweepQuery,
    ) -> Annotated[CallToolResult, NativeSweepResult]:
        return await _stable_result(sweeps.result(request))

    specifications = NativeSpecificationSupervisor(native)

    @server.tool(
        name="cadence_evaluate_native_specification",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Evaluate an operator-registered target against exact native "
        "plan/reader conditions. Targetless is NOT_EVALUATED; failed jobs remain errors. "
        "No target selection, simulation or optimization.",
    )
    async def cadence_evaluate_native_specification(
        request: NativeSpecificationQuery,
    ) -> Annotated[CallToolResult, NativeSpecificationResult]:
        return await _stable_result(specifications.result(request))
