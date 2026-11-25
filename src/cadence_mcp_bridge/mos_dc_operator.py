"""Read operator-enrolled W/L evaluations through the original MOS and DC records."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.candidate_execution import PmosDcOperation, PmosDefaultChangeRequest
from cadence_mcp_bridge.mos_dc_evaluation import (
    MosDcEvaluation,
    MosDcEvidence,
    MosDcRoute,
    capture_mos_dc,
    mos_dc_batch_cost,
    read_mos_dc,
)
from cadence_mcp_bridge.native_service import NativeOperationQuery, NativeOperationService
from cadence_mcp_bridge.operator_operations import OperationPhase, OperationPlan, OperationRejected
from cadence_mcp_bridge.pmos_default_service import _read
from cadence_mcp_bridge.registered_mos_sizing import RegisteredMosSizingResult
from cadence_mcp_bridge.registered_mos_sizing_transport import RegisteredMosSizing
from cadence_mcp_bridge.runtime_context import (
    ExecutionContext,
    read_pmos_default_change_binding,
    validate_runtime_document,
)
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel


class MosDcCompareRequest(VariableModel):
    edits: Annotated[tuple[PmosDefaultChangeRequest, ...], Field(min_length=1, max_length=3)]

    @field_validator("edits", mode="before")
    @classmethod
    def json_array(cls, value: Any) -> Any:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def distinct_edits(self) -> Self:
        if len({edit.operation_id for edit in self.edits}) != len(self.edits):
            raise ValueError("MOS evaluation requires distinct edit IDs")
        return self


class MosDcStatus(VariableModel):
    identity: PmosDefaultChangeRequest
    edit_outcome: Literal["NOT_FOUND", "OUTCOME_UNKNOWN", "VERIFIED"]
    analysis_status: OperationPhase | Literal["NOT_RUN"] = "NOT_RUN"
    reason: str | None = None
    edit_result: RegisteredMosSizingResult | None = None
    evaluation: MosDcEvaluation | None = None


class MosDcComparison(VariableModel):
    rows: tuple[MosDcStatus, ...]


class _Artifact(VariableModel):
    path: Path
    sha256: Digest

    def read(self, limit: int) -> bytes:
        if not self.path.is_absolute():
            raise ValueError("operator evidence requires an absolute path")
        return _read(self.path, limit, self.sha256)


class _ContextRef(VariableModel):
    settings: _Artifact
    context_id: LogicalId
    context_sha256: Digest

    def resolve(self, selected: ExecutionContext) -> ExecutionContext:
        context = next(
            (
                item
                for item in validate_runtime_document(self.settings.path, self.settings.read(65536))
                if item.binding.context_id == self.context_id
            ),
            None,
        )
        if (
            context is None
            or context.context_sha256 != self.context_sha256
            or context.resource_domain_sha256 != selected.resource_domain_sha256
            or context.binding.ledger_ref != selected.binding.ledger_ref
        ):
            raise ValueError("MOS evaluation analysis context does not match enrollment")
        return context


class _Analysis(VariableModel):
    context: _ContextRef | None = None
    query: NativeOperationQuery
    plan: OperationPlan
    runtime_manifest: _Artifact
    runtime_registration: _Artifact

    def load(self, selected: ExecutionContext) -> tuple[ExecutionContext, PmosDcOperation]:
        context = selected if self.context is None else self.context.resolve(selected)
        plan, binding = self.plan, context.binding
        if (
            plan.analysis != "dc"
            or plan.plan_sha256 != self.query.expected_plan_sha256
            or (
                plan.resource_domain_sha256,
                plan.runner_sha256,
                plan.ledger_ref,
                plan.environment_sha256,
                plan.design_sha256,
                plan.pdk_sha256,
            )
            != (
                context.resource_domain_sha256,
                binding.runner_sha256,
                binding.ledger_ref,
                binding.environment_sha256,
                binding.design_sha256,
                binding.pdk_sha256,
            )
        ):
            raise ValueError("MOS evaluation operation does not match its selected DC context")
        return context, PmosDcOperation(
            self.query,
            plan,
            self.runtime_manifest.read(32768),
            self.runtime_registration.read(262144),
            _Artifact(path=binding.design_registry, sha256=plan.design_sha256).read(65536),
        )


class _Candidate(VariableModel):
    edit: PmosDefaultChangeRequest
    analysis: _Analysis
    source_export: _Artifact


class _Baseline(VariableModel):
    analysis: _Analysis
    report: _Artifact
    terminal_sha256: Digest

    def load(self, selected: ExecutionContext) -> PmosDcOperation:
        context, operation = self.analysis.load(selected)
        store = AnalysisStore(context.binding.analysis_journal)
        with store.connection(create=False, read_only=True) as connection:
            record = store._read_operation(connection, operation.query.operation_id)
        return replace(
            operation,
            record=record,
            report=self.report.read(524288),
            expected_report_sha256=self.report.sha256,
            expected_terminal_sha256=self.terminal_sha256,
        )


class _Enrollment(VariableModel):
    schema_version: Literal[1]
    owner: Literal["C0"]
    context_id: LogicalId
    resource_domain_sha256: Digest
    sizing_enrollment_sha256: Digest
    candidates: Annotated[tuple[_Candidate, ...], Field(min_length=1, max_length=3)]
    baseline: _Baseline | None = None

    @model_validator(mode="after")
    def distinct_operations(self) -> Self:
        ids = [
            id_
            for point in self.candidates
            for id_ in (
                point.edit.operation_id,
                point.analysis.query.operation_id,
            )
        ]
        if self.baseline is not None:
            ids.append(self.baseline.analysis.query.operation_id)
        if len(set(ids)) != len(ids):
            raise ValueError("MOS evaluation edit and analysis IDs must be independent")
        return self


def _enrollment(context: ExecutionContext, sizing: RegisteredMosSizing) -> _Enrollment | None:
    path = context.binding.mos_dc_evaluation_binding
    pin = context.binding.mos_dc_evaluation_sha256
    if path is None and pin is None:
        return None
    if path is None or pin is None:
        raise ValueError("MOS evaluation requires its exact enrollment")
    enrolled = _Enrollment.model_validate_json(read_pmos_default_change_binding(path, pin))
    if (
        enrolled.context_id != context.binding.context_id
        or enrolled.resource_domain_sha256 != context.resource_domain_sha256
        or enrolled.sizing_enrollment_sha256 != sizing.enrollment_sha256
        or not {item.edit.operation_id for item in enrolled.candidates}.issubset(
            sizing.inspect().operation_ids
        )
    ):
        raise ValueError("MOS evaluation enrollment does not bind the selected sizing context")
    return enrolled


async def compare_registered_mos_dc(
    context: ExecutionContext,
    sizing: RegisteredMosSizing,
    request: MosDcCompareRequest,
) -> MosDcComparison:
    """Join sealed evidence only. Submission still uses the normal operator tools."""
    request = MosDcCompareRequest.model_validate_json(request.model_dump_json())
    enrolled = _enrollment(context, sizing)
    routes = (
        {} if enrolled is None else {item.edit.operation_id: item for item in enrolled.candidates}
    )
    edits = []
    evidence: dict[str, MosDcEvidence] = {}
    for identity in request.edits:
        candidate = routes.get(identity.operation_id)
        if candidate is not None and candidate.edit != identity:
            raise ValueError("requested edit does not match the enrolled evaluation")
        lookup, retained = sizing.lookup_evidence(identity)
        edits.append(lookup)
        if lookup.result is None or retained is None:
            continue
        route = None
        if candidate is not None:
            native, operation = candidate.analysis.load(context)
            route = MosDcRoute(
                native,
                operation,
                candidate.source_export.read(32768),
                candidate.source_export.sha256,
            )
        raw = lookup.result.model_dump_json().encode()
        evidence[identity.operation_id] = MosDcEvidence(
            retained.plan,
            retained.binding,
            raw,
            sha256(raw).hexdigest(),
            retained.baseline_input,
            retained.confirmed_input,
            route,
        )
    if evidence:
        mos_dc_batch_cost(tuple(evidence.values()))
    baseline = None
    rows = []
    for edit in edits:
        point = evidence.get(edit.identity.operation_id)
        if point is None:
            rows.append(
                MosDcStatus(
                    identity=edit.identity,
                    edit_outcome=edit.outcome,
                    reason="verified_edit_required",
                    edit_result=edit.result,
                )
            )
            continue
        evaluation = read_mos_dc(point)
        if evaluation.analysis_status == "SUCCEEDED" and point.route is not None:
            if baseline is None and enrolled is not None and enrolled.baseline is not None:
                baseline = enrolled.baseline.load(context)
            try:
                evaluation = await capture_mos_dc(
                    point,
                    NativeOperationService(point.route.context),
                    baseline=baseline,
                )
            except OperationRejected as error:
                if error.reason != "native_provider_transport_unknown":
                    raise
        rows.append(
            MosDcStatus(
                identity=edit.identity,
                edit_outcome=edit.outcome,
                analysis_status=evaluation.analysis_status,
                reason=evaluation.analysis_reason,
                evaluation=evaluation,
            )
        )
    return MosDcComparison(rows=tuple(rows))
