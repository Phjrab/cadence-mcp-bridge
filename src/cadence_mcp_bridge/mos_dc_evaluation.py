"""Bind a verified MOS edit to one registered fixed-DC operation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, NamedTuple

from pydantic import ConfigDict

from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.authenticated_provider import (
    NATIVE_RESULT_LIMIT,
    NativeResultPayload,
    verify_native_result,
)
from cadence_mcp_bridge.candidate_execution import (
    PmosDcOperation,
    _pinned_json,
    _width_report,
    _width_route,
)
from cadence_mcp_bridge.candidate_reports import CandidateMetric, candidate_metric_delta
from cadence_mcp_bridge.domain_provisioning import _closed_document
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import NativeOperationService, NativeOperationStatus
from cadence_mcp_bridge.operator_operations import DurableOperation, OperationPhase
from cadence_mcp_bridge.registered_mos_edit import RegisteredMosEditBinding
from cadence_mcp_bridge.registered_mos_sizing import (
    MosSizingPlan,
    RegisteredMosSizingResult,
)
from cadence_mcp_bridge.result_reports import ReportConditions, ResultReport, capture, make_report
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest


@dataclass(frozen=True)
class MosDcRoute:
    """Original operator-selected route and C1's separately pinned source export."""

    context: ExecutionContext
    operation: PmosDcOperation
    export: bytes
    export_sha256: str


@dataclass(frozen=True)
class MosDcEvidence:
    sizing_plan: MosSizingPlan
    edit_binding: RegisteredMosEditBinding
    edit_result: bytes
    edit_result_sha256: str
    baseline_input: bytes
    confirmed_input: bytes | None = None
    route: MosDcRoute | None = None


class MosDcEvaluation(VariableModel):
    edit: RegisteredMosSizingResult
    baseline_revision_sha256: Digest
    analysis_design_id: LogicalId | None = None
    analysis_id: LogicalId | None = None
    analysis_operation_id: OperationId | None = None
    analysis_plan_sha256: Digest | None = None
    source_export_sha256: Digest | None = None
    conditions: ReportConditions | None = None
    analysis_status: OperationPhase | Literal["NOT_RUN"] = "NOT_RUN"
    analysis_reason: str | None = None
    terminal_receipt_sha256: Digest | None = None
    report: ResultReport | None = None
    baseline_operation_id: OperationId | None = None
    baseline_report_sha256: Digest | None = None
    comparison_status: Literal[
        "NOT_EVALUATED", "BASELINE_UNAVAILABLE", "CONDITION_MISMATCH", "COMPARABLE"
    ] = "NOT_EVALUATED"
    metrics: tuple[CandidateMetric, ...] = ()


class _DcRegistration(NamedTuple):
    ade: AdeExecutionRegistration
    conditions: ReportConditions
    reader: GenericReaderRegistration
    semantics: tuple[object, ...]
    seed_ade_sha256: str


class _MosDcExport(VariableModel):
    """Required lineage fields from an independently pinned C1 export receipt."""

    model_config = ConfigDict(extra="ignore")
    status: Literal["OWNED_INPUT_COPY_VERIFIED"]
    edit_operation_id: OperationId
    edit_scope_sha256: Digest
    owned_copy_operation_id: OperationId
    source_preservation_sha256: Digest
    source_revision_sha256: Digest
    testbench_revision_sha256: Digest
    reopen_receipt_sha256: Digest
    netlist_receipt_sha256: Digest
    netlist_sha256: Digest
    source_cell: str
    source_state: str
    source_cell_sha256: Digest
    source_state_sha256: Digest
    library_path: str
    dependency_tree_sha256: Digest
    source_ade_sha256: Digest


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _edit(evidence: MosDcEvidence) -> RegisteredMosSizingResult:
    _pinned_json(evidence.edit_result, evidence.edit_result_sha256)
    edit = RegisteredMosSizingResult.model_validate_json(evidence.edit_result)
    change, binding, observed = evidence.sizing_plan, evidence.edit_binding, edit.readback
    if (
        edit.replayed != (edit.outcome != "NOT_FOUND")
        or edit.dispatched_this_call is not False
        or change.plan_sha256 != binding.plan_sha256
        or change.route_sha256 != binding.route_sha256
        or edit.candidate_revision != change.candidate_revision
        or edit.requested != change.requested
        or edit.expected != change.expected
        or (
            edit.identity.operation_id,
            edit.identity.expected_plan_sha256,
            edit.identity.expected_scope_sha256,
        )
        != (binding.operation_id, binding.plan_sha256, binding.scope_sha256)
        or _sha(evidence.baseline_input) != change.baseline.netlist_sha256
    ):
        raise ValueError("MOS candidate does not bind the pinned edit and baseline")
    if edit.outcome != "VERIFIED":
        if (
            evidence.route
            or evidence.confirmed_input is not None
            or observed is not None
            or edit.observed is not None
            or edit.effective_input is not None
            or edit.effective_mos_options is not None
        ):
            raise ValueError("unverified MOS edit cannot bind analysis")
        return edit
    diagnostic = evidence.confirmed_input
    if (
        observed is None
        or diagnostic is None
        or edit.effective_input is None
        or edit.effective_mos_options is None
        or edit.observed != change.expected
        or (observed.operation_id, observed.plan_sha256, observed.scope_sha256)
        != (binding.operation_id, binding.plan_sha256, binding.scope_sha256)
        or observed.source_preservation_sha256 != binding.source_preservation_sha256
        or observed.saved.revision_sha256 != observed.reopened.revision_sha256
        or observed.saved.testbench_revision_sha256 != observed.reopened.testbench_revision_sha256
        or (observed.reopened.revision_sha256, observed.reopened.testbench_revision_sha256)
        != (observed.netlisted_revision_sha256, observed.netlisted_testbench_revision_sha256)
        or observed.netlisted_revision_sha256 == change.baseline.revision_sha256
        or not 0 < len(diagnostic) <= 32768
        or observed.netlist_sha256 != _sha(diagnostic)
        or edit.effective_input.artifact_sha256 != observed.netlist_sha256
    ):
        raise ValueError("independent MOS input does not match the reopened revision")
    return edit


def _registered(
    evidence: MosDcEvidence,
    edit: RegisteredMosSizingResult,
    source: MosDcRoute,
) -> _DcRegistration:
    operation, context = source.operation, source.context
    plan, binding, observed = operation.plan, context.binding, edit.readback
    if observed is None or (
        plan.resource_domain_sha256,
        plan.runner_sha256,
        plan.ledger_ref,
        plan.environment_sha256,
        plan.design_sha256,
        plan.pdk_sha256,
    ) != (
        context.resource_domain_sha256,
        binding.runner_sha256,
        binding.ledger_ref,
        binding.environment_sha256,
        binding.design_sha256,
        binding.pdk_sha256,
    ):
        raise ValueError("DC operation does not use the selected context")
    if operation.query.operation_id in (
        edit.identity.operation_id,
        evidence.edit_binding.owned_copy_operation_id,
    ):
        raise ValueError("edit, copy and DC operation require separate IDs")

    route, conditions, reader, semantics = _width_route(operation, evidence.confirmed_input, "dc")
    export = _MosDcExport.model_validate(_pinned_json(source.export, source.export_sha256))
    if (
        export.edit_operation_id != observed.operation_id
        or export.edit_scope_sha256 != observed.scope_sha256
        or export.owned_copy_operation_id != evidence.edit_binding.owned_copy_operation_id
        or export.source_preservation_sha256 != observed.source_preservation_sha256
        or export.source_revision_sha256 != observed.netlisted_revision_sha256
        or export.testbench_revision_sha256 != observed.netlisted_testbench_revision_sha256
        or export.reopen_receipt_sha256 != observed.reopened.receipt_sha256
        or export.netlist_receipt_sha256 != observed.netlist_receipt_sha256
        or export.netlist_sha256 != observed.netlist_sha256
        or (export.source_cell, export.source_state)
        != (route["source_cell"], route["source_state"])
        or (export.source_cell_sha256, export.source_state_sha256)
        != (conditions.source_tree_sha256, conditions.ade_state_tree_sha256)
        or {
            "name": route["profile"]["binding"]["library"],
            "path": export.library_path,
            "tree_sha256": export.dependency_tree_sha256,
        }
        not in route["libraries"]
    ):
        raise ValueError("DC registration is not bound to the original MOS export")
    return _DcRegistration(
        AdeExecutionRegistration.model_validate(route["ade"], strict=False),
        conditions,
        reader,
        semantics,
        export.source_ade_sha256,
    )


async def submit_mos_dc(
    evidence: MosDcEvidence,
    service: NativeOperationService,
) -> NativeOperationStatus:
    """Advance one verified point through the stock approved plan and same-ID lifecycle."""
    edit = _edit(evidence)
    source = evidence.route
    if source is None or service.context != source.context:
        raise ValueError("selected DC registration required")
    _registered(evidence, edit, source)
    operation = source.operation
    return await service.observe(operation.query, submission=operation.plan.request)


def _record(source: MosDcRoute) -> DurableOperation | None:
    store = AnalysisStore(source.context.binding.analysis_journal)
    try:
        with store.connection(create=False, read_only=True) as connection:
            return store._read_operation(connection, source.operation.query.operation_id)
    except InvalidInputError:
        return None


def _state(
    evidence: MosDcEvidence,
) -> tuple[MosDcEvaluation, _DcRegistration | None, DurableOperation | None]:
    edit = _edit(evidence)
    row = MosDcEvaluation(
        edit=edit,
        baseline_revision_sha256=evidence.sizing_plan.baseline.revision_sha256,
        analysis_reason="verified_edit_required"
        if edit.outcome != "VERIFIED"
        else "registered_dc_required",
    )
    source = evidence.route
    if source is None:
        return row, None, None
    operation = source.operation
    binding = _registered(evidence, edit, source)
    record = _record(source)
    if record is not None and record.plan != operation.plan:
        raise ValueError("journaled DC plan differs from approved candidate plan")
    phase = "NOT_RUN" if record is None else record.progress.phase
    row = row.model_copy(
        update={
            "analysis_design_id": operation.plan.request.design_id,
            "analysis_id": operation.plan.request.analysis_id,
            "analysis_operation_id": operation.query.operation_id,
            "analysis_plan_sha256": operation.plan.plan_sha256,
            "source_export_sha256": source.export_sha256,
            "conditions": binding.conditions,
            "analysis_status": phase,
            "analysis_reason": (
                "operation_not_admitted"
                if record is None
                else "original_result_unavailable"
                if phase == "SUCCEEDED"
                else "operation_not_succeeded"
            ),
            "terminal_receipt_sha256": None
            if record is None
            or phase not in ("SUCCEEDED", "FAILED", "EXTRACTION_FAILED", "CANCELLED")
            else record.progress.provider_receipt_sha256,
        }
    )
    return row, binding, record


def read_mos_dc(
    evidence: MosDcEvidence,
    *,
    executed_input: bytes | None = None,
    native_result: bytes | None = None,
    baseline: PmosDcOperation | None = None,
    baseline_executed_input: bytes | None = None,
) -> MosDcEvaluation:
    """Verify a retained local capture without an analysis or extraction call."""
    row, binding, record = _state(evidence)
    if executed_input is None and native_result is None:
        return row
    source = evidence.route
    if (
        record is None
        or row.analysis_status != "SUCCEEDED"
        or executed_input is None
        or native_result is None
        or source is None
        or binding is None
    ):
        raise ValueError("successful DC requires the original result and executed input")
    _width_route(source.operation, executed_input, "dc")
    _closed_document(native_result, max_bytes=NATIVE_RESULT_LIMIT)
    payload = NativeResultPayload.model_validate_json(native_result)
    if (
        payload.observation.progress != record.progress
        or payload.receipt.native_input_sha256 != _sha(executed_input)
        or payload.ade != binding.ade
        or payload.reader != binding.reader
    ):
        raise ValueError("DC result is not bound to the original effective input and terminal")
    _, result = verify_native_result(
        source.context, record.plan, record.operation_id, payload, include_report_conditions=True
    )
    return _comparison(
        row, make_report(record, result), binding, evidence, baseline, baseline_executed_input
    )


async def capture_mos_dc(
    evidence: MosDcEvidence,
    service: NativeOperationService,
    *,
    baseline: PmosDcOperation | None = None,
) -> MosDcEvaluation:
    """Use the existing authenticated result-only action for an admitted success."""
    row, binding, record = _state(evidence)
    if record is None or row.analysis_status != "SUCCEEDED":
        return row
    source = evidence.route
    if source is None or binding is None or service.context != source.context:
        raise ValueError("selected DC result context differs")
    # The native worker verifies the retained input bytes, frame, reader script
    # and PSF against the original journal. capture does not reconcile or extract.
    report = await capture(service, record.operation_id, record.plan.plan_sha256)
    return _comparison(row, report, binding, evidence, baseline, None)


def _comparison(
    row: MosDcEvaluation,
    report: ResultReport,
    binding: _DcRegistration,
    evidence: MosDcEvidence,
    baseline: PmosDcOperation | None,
    baseline_executed_input: bytes | None,
) -> MosDcEvaluation:
    if (
        report.operation_id != row.analysis_operation_id
        or report.plan.plan_sha256 != row.analysis_plan_sha256
        or report.analysis_conditions != binding.conditions
        or report.measurement_id != binding.reader.measurement_id
        or report.reader_registration_sha256 != canonical_digest(binding.reader)
    ):
        raise ValueError("DC report does not match the original candidate registration")
    reference = None
    comparison = "BASELINE_UNAVAILABLE"
    if baseline is not None:
        if baseline.query.operation_id in (
            report.operation_id,
            row.edit.identity.operation_id,
            evidence.edit_binding.owned_copy_operation_id,
        ):
            raise ValueError("baseline operation is not independent")
        _, old_conditions, old_reader, old_semantics = _width_route(
            baseline, evidence.baseline_input, "dc"
        )
        _, _, old_report = _width_report(baseline, old_conditions, old_reader)
        if (
            old_semantics != binding.semantics
            or old_conditions.ade_state_tree_sha256 != binding.seed_ade_sha256
        ):
            comparison = "CONDITION_MISMATCH"
        elif old_report is not None:
            # The pinned original report and diagnostic agree on the independently
            # registered DC projection. The two raw files may differ in comments.
            if baseline_executed_input is not None:
                if old_report.execution_input_sha256 != _sha(baseline_executed_input):
                    raise ValueError("baseline report does not bind the supplied executed input")
                _width_route(baseline, baseline_executed_input, "dc")
            reference = old_report
            comparison = "COMPARABLE"
    old_metrics = (
        {}
        if reference is None
        else {
            metric.model_dump_json(exclude={"value"}): metric.value for metric in reference.metrics
        }
    )
    metrics = []
    for metric in report.metrics:
        key = metric.model_dump_json(exclude={"value"})
        old = old_metrics.get(key)
        absolute, relative, reason = candidate_metric_delta(
            metric.value,
            old,
            baseline_present=key in old_metrics,
        )
        metrics.append(
            CandidateMetric(
                metric=metric,
                baseline_value=old,
                absolute_change=absolute,
                relative_change=relative,
                delta_reason=reason,
            )
        )
    return row.model_copy(
        update={
            "analysis_reason": None,
            "comparison_status": comparison,
            "report": report,
            "baseline_operation_id": None if reference is None else reference.operation_id,
            "baseline_report_sha256": None
            if reference is None or baseline is None
            else baseline.expected_report_sha256,
            "metrics": tuple(metrics),
        }
    )


def validate_mos_dc_batch(
    candidates: tuple[MosDcEvidence, ...],
    *,
    max_attempts: int,
    max_reservation_bytes: int,
) -> int:
    """Check the explicit set and declared cost before any individual submission."""
    if not 1 <= len(candidates) <= 3:
        raise ValueError("one to three explicit MOS candidates required")
    baselines = set()
    revision_ids = set()
    physical_revisions = set()
    input_hashes = set()
    operation_ids: list[str] = []
    reserved_bytes = attempts = 0
    for candidate in candidates:
        edit = _edit(candidate)
        baselines.add(candidate.sizing_plan.baseline.model_dump_json())
        revision_ids.add(edit.candidate_revision.revision_id)
        operation_ids.extend(
            (edit.identity.operation_id, candidate.edit_binding.owned_copy_operation_id)
        )
        if edit.readback is not None:
            revision = edit.readback.netlisted_revision_sha256
            if revision in physical_revisions:
                raise ValueError("two MOS candidates claim the same physical revision")
            physical_revisions.add(revision)
            digest = edit.readback.netlist_sha256
            if digest in input_hashes:
                raise ValueError("two MOS candidates claim the same verified input")
            input_hashes.add(digest)
        if candidate.route is not None:
            _registered(candidate, edit, candidate.route)
            operation = candidate.route.operation
            operation_ids.append(operation.query.operation_id)
            reserved_bytes += operation.plan.request.result_reservation_bytes
            attempts += operation.plan.attempt_cost
    if (
        len(baselines) != 1
        or len(revision_ids) != len(candidates)
        or (len(set(operation_ids)) != len(operation_ids))
    ):
        raise ValueError("MOS candidates require one baseline and distinct identities")
    if attempts > max_attempts or reserved_bytes > max_reservation_bytes:
        raise ValueError("MOS candidates exceed the declared analysis budget")
    return reserved_bytes
