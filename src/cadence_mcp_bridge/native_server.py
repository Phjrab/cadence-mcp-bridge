"""Conditional fixed-operation tools for an explicitly configured operator service."""

import json
from collections.abc import Awaitable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, ToolAnnotations
from pydantic import ValidationInfo, field_validator

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
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    ChangeReadback,
    Readback,
    verify_change_readback,
)
from cadence_mcp_bridge.research_adapters import (
    RegisteredMosChangeRequest,
    ResearchAcGainRequest,
    ResearchAcGainResult,
    ResearchCircuitRequest,
    ResearchCircuitValidation,
    ResearchMosBlockEvidenceRequest,
    ResearchMosBlockPreparation,
    ResearchMosBlockRequest,
    ResearchMosBlockVerification,
    ResearchMosPlan,
    ResearchPowerResult,
    ResearchSupplyPowerRequest,
    ResearchTransientRequest,
    ResearchTransientResult,
    RetainedResearchResult,
    ac_gain_result,
    compare_mos_block,
    plan_mos,
    prepare_mos_block,
    supply_power_result,
    transient_result,
    validate_circuit,
)
from cadence_mcp_bridge.server import _READ_ONLY, _stable_result
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel


class ChangeReadbackRequest(VariableModel):
    plan: ChangePlan
    expected_plan_sha256: Digest
    baseline: Readback | None = None
    reopened: Readback | None = None
    netlist: Readback | None = None

    @field_validator("plan", "baseline", "reopened", "netlist", mode="before")
    @classmethod
    def validate_wire_json(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, dict):
            return value
        model = ChangePlan if info.field_name == "plan" else Readback
        # Decode JSON arrays without loosening the strict model fields.
        return model.model_validate_json(json.dumps(value, allow_nan=False))


async def _research_result[ResultT: RetainedResearchResult](
    operation: Awaitable[ResultT],
) -> ResultT:
    from cadence_mcp_bridge.errors import BridgeError

    try:
        return await operation
    except (BridgeError, OSError, ValueError, KeyError, TypeError) as exc:
        raise ToolError("registered_research_result_unavailable") from exc


def register_native_tools(server: MCPServer, native: NativeOperationService) -> None:
    from cadence_mcp_bridge.errors import BridgeError
    from cadence_mcp_bridge.result_reports import capture, job_page, report_view

    @server.resource(
        "cadence://operations", mime_type="application/json",
        description="First page of retained native job identities; local journal only.",
    )
    def operations() -> dict[str, Any]:
        try:
            return job_page(native.context)
        except (OSError, ValueError, BridgeError):
            return {"status": "BLOCKED", "reason": "result_catalog_unavailable"}

    @server.resource("cadence://operations/page/{offset}", mime_type="application/json")
    def operations_page(offset: str) -> dict[str, Any]:
        try:
            return job_page(native.context, int(offset))
        except (OSError, ValueError, BridgeError):
            return {"status": "BLOCKED", "reason": "result_catalog_unavailable"}

    @server.resource(
        "cadence://operation/{operation_id}/{plan_sha256}/report", mime_type="application/json",
        description="Report an already succeeded retained job through verified result lookup. "
        "Never reconcile, simulate, reserve or rerun extraction; use existing status if stale.",
    )
    async def operation_report(operation_id: str, plan_sha256: str) -> dict[str, Any]:
        try:
            return {
                **report_view(await capture(native, operation_id, plan_sha256)),
                "remote_contact": True,
            }
        except (OSError, ValueError, BridgeError, KeyError, TypeError):
            return {"status": "BLOCKED", "reason": "result_report_unavailable"}

    @server.tool(
        name="cadence_verify_change_readback",
        annotations=_READ_ONLY,
        structured_output=True,
        description="Compare typed parameter-change observations and an exact plan hash. "
        "Local evidence comparison only; artifact provenance requires independent verification.",
    )
    def cadence_verify_change_readback(request: ChangeReadbackRequest) -> ChangeReadback:
        if request.plan.plan_sha256 != request.expected_plan_sha256:
            raise ToolError("change_plan_digest_mismatch")
        return verify_change_readback(
            request.plan,
            baseline=request.baseline,
            reopened=request.reopened,
            netlist=request.netlist,
        )

    @server.tool(
        annotations=_READ_ONLY,
        structured_output=True,
        description="Validate an explicit circuit definition and compute its canonical digest. "
        "Local only; unresolved inputs are retained and no native circuit is generated.",
    )
    def cadence_validate_research_circuit(
        request: ResearchCircuitRequest,
    ) -> ResearchCircuitValidation:
        return validate_circuit(request)

    @server.tool(
        annotations=_READ_ONLY,
        structured_output=True,
        description="Prepare a bounded DUT hierarchy from a pinned circuit definition and "
        "logical library name. Local declaration only; grants no generation authority.",
    )
    def cadence_plan_research_mos_block(
        request: ResearchMosBlockRequest,
    ) -> ResearchMosBlockPreparation:
        try:
            return prepare_mos_block(request)
        except ValueError as exc:
            raise ToolError("research_mos_block_plan_rejected") from exc

    @server.tool(
        annotations=_READ_ONLY,
        structured_output=True,
        description="Compare typed reopen and Spectre projections against an exact MOS-block "
        "plan and artifact pins. Native artifact provenance requires independent verification.",
    )
    def cadence_verify_research_mos_block(
        request: ResearchMosBlockEvidenceRequest,
    ) -> ResearchMosBlockVerification:
        try:
            return compare_mos_block(request)
        except ValueError as exc:
            raise ToolError("research_mos_block_evidence_rejected") from exc

    @server.tool(
        annotations=_READ_ONLY,
        structured_output=True,
        description="Plan one finite MOS property change from supplied qualification evidence. "
        "Local only; creates no native authority or artifact provenance.",
    )
    def cadence_plan_registered_mos_change(request: RegisteredMosChangeRequest) -> ResearchMosPlan:
        try:
            return plan_mos(request)
        except ValueError as exc:
            raise ToolError("registered_mos_change_rejected") from exc

    @server.tool(
        annotations=_READ_ONLY,
        structured_output=True,
        description="Measure a bounded saved waveform window from a retained registered TRAN "
        "operation. No simulation or extraction replay; TRAN supply power is unavailable.",
    )
    async def cadence_research_transient_result(
        request: ResearchTransientRequest,
    ) -> ResearchTransientResult:
        return await _research_result(transient_result(native, request))

    @server.tool(
        annotations=_READ_ONLY,
        structured_output=True,
        description="Read exact complex reference gain and sampled downward unity crossing "
        "from a retained registered AC operation. Requests no new extraction or simulation.",
    )
    async def cadence_research_ac_gain_result(
        request: ResearchAcGainRequest,
    ) -> ResearchAcGainResult:
        return await _research_result(ac_gain_result(native, request))

    @server.tool(
        annotations=_READ_ONLY,
        structured_output=True,
        description="Read signed static delivered supply power for registered supplies of "
        "an exact retained DC operation. Requests no new extraction or simulation.",
    )
    async def cadence_research_supply_power_result(
        request: ResearchSupplyPowerRequest,
    ) -> ResearchPowerResult:
        return await _research_result(supply_power_result(native, request))

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
