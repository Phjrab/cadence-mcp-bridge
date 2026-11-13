"""Link independently planned candidate analyses using their retained identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from math import isfinite
from typing import Annotated, Any, Literal, NamedTuple, Protocol, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge._native_rendering import effective_input, partition_input
from cadence_mcp_bridge.amplifier_specifications import AmplifierFactProvenance, provenance
from cadence_mcp_bridge.amplifier_sweeps import AmplifierSweepResult
from cadence_mcp_bridge.candidate_contracts import (
    CandidateBatchPlan,
    CandidateFixedEvidence,
    SuppliedValue,
)
from cadence_mcp_bridge.candidate_reports import (
    CandidateObservation,
    CandidateReportRow,
    CandidateStatus,
    compare_candidate_reports,
)
from cadence_mcp_bridge.designs import DesignMeasurementRegistry
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration, ModelInclude
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_runtime import KIND
from cadence_mcp_bridge.native_service import NativeOperationQuery
from cadence_mcp_bridge.operator_operations import (
    DurableOperation,
    ExplicitValue,
    OperationPhase,
    OperationPlan,
    OperationRejected,
)
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    ChangeReadback,
    ChangeValue,
    MosWidthTarget,
    _amp_pm0_options,
    project_netlist_change,
    verify_change_readback,
)
from cadence_mcp_bridge.power_measurements import require_same_resource_policy
from cadence_mcp_bridge.result_reports import ReportConditions, ReportMetric, ResultReport
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest


class CandidateAnalysisManifest(VariableModel):
    """A local index of existing batch plans for one fixed source and candidate set."""

    batches: Annotated[tuple[CandidateBatchPlan, ...], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def same_candidates(self) -> Self:
        first = self.batches[0]
        seen_ids: set[str] = set()
        seen_analyses: set[str] = set()
        for batch in self.batches:
            analysis = batch.plans[0].analysis
            ids = {batch.request.batch_id, *(c.operation_id for c in batch.request.candidates)}
            if analysis in seen_analyses or ids & seen_ids:
                raise ValueError("distinct analyses and operation identities required")
            seen_analyses.add(analysis)
            seen_ids.update(ids)
            if _source_identity(batch) != _source_identity(first):
                raise ValueError("candidate source, model or runtime binding differs")
            if _candidate_values(batch) != _candidate_values(first):
                raise ValueError("complete candidate inventories differ across analyses")
        return self

    @property
    def manifest_sha256(self) -> str:
        return canonical_digest(self)

    @property
    def expected_executions(self) -> int:
        return sum(batch.expected_executions for batch in self.batches)

    @property
    def result_reservation_bytes(self) -> int:
        return sum(batch.result_reservation_bytes for batch in self.batches)


def _source_identity(batch: CandidateBatchPlan) -> tuple[object, ...]:
    child = batch.plans[0]
    evidence = batch.request.fixed_evidence
    return (
        child.resource_domain_sha256,
        child.ledger_ref,
        child.runner_sha256,
        child.environment_sha256,
        child.design_sha256,
        child.pdk_sha256,
        child.grant_sha256,
        child.request.design_id,
        evidence.source_revision_sha256,
        evidence.testbench_revision_sha256,
        evidence.source_baseline_sha256,
        evidence.design_profile_sha256,
        evidence.conditions.source_tree_sha256,
        evidence.conditions.model_file_sha256,
        evidence.variable_bindings,
        batch.varied_variables,
        batch.request.baseline_candidate_id,
    )


def _candidate_values(
    batch: CandidateBatchPlan,
) -> tuple[tuple[str, tuple[ExplicitValue, ...]], ...]:
    return tuple(
        (candidate.candidate_id, child.request.values)
        for candidate, child in zip(batch.request.candidates, batch.plans, strict=True)
    )


def _runtime_routes(
    first: OperationPlan,
    runtime_manifest: bytes,
    runtime_registration: bytes,
) -> dict[tuple[str, str], dict[str, Any]]:
    try:
        _closed_document(runtime_manifest)
        _closed_document(runtime_registration)
        registration_sha = hashlib.sha256(runtime_registration).hexdigest()
        bundle = json.loads(runtime_manifest)
        registration = json.loads(runtime_registration)
        if (
            hashlib.sha256(runtime_manifest).hexdigest() != first.runner_sha256
            or bundle["schema_version"] != 3
            or bundle["kind"] != KIND
            or bundle["profile_sha256"] != first.environment_sha256
            or bundle["registration_sha256"] != registration_sha
            or bundle["files"]["registration.json"]
            != {
                "sha256": registration_sha,
                "bytes": len(runtime_registration),
            }
            or type(registration["schema_version"]) is not int
            or registration["schema_version"] != 1
            or (
                registration["environment_sha256"],
                registration["design_sha256"],
                registration["pdk_sha256"],
            )
            != (
                first.environment_sha256,
                first.design_sha256,
                first.pdk_sha256,
            )
        ):
            raise ValueError("runtime identity")
        routes = {(r["design_id"], r["analysis_id"]): r for r in registration["routes"]}
        if len(routes) != len(registration["routes"]):
            raise ValueError("duplicate runtime route")
    except (KeyError, TypeError, ValueError):
        raise OperationRejected("candidate_cross_analysis_runtime_binding_invalid") from None
    return routes


def validate_cross_analysis_conditions(
    manifest: CandidateAnalysisManifest,
    runtime_manifest: bytes,
    runtime_registration: bytes,
    *,
    analyses: frozenset[str],
) -> None:
    """Check shared circuit conditions against the existing hash-bound runtime assets."""
    manifest = CandidateAnalysisManifest.model_validate_json(manifest.model_dump_json())
    batches = {batch.plans[0].analysis: batch for batch in manifest.batches}
    if len(analyses) < 2 or analyses - batches.keys():
        raise OperationRejected("candidate_cross_analysis_inventory_invalid")
    routes = _runtime_routes(manifest.batches[0].plans[0], runtime_manifest, runtime_registration)

    static_conditions = set()
    source_models = set()
    for analysis, batch in batches.items():
        if analysis not in analyses:
            continue
        child = batch.plans[0]
        request = child.request
        fixed = batch.request.fixed_evidence
        conditions = fixed.conditions
        try:
            route = routes[request.design_id, request.analysis_id]
            ade = AdeExecutionRegistration.model_validate_json(_canonical(route["ade"]))
            reader = GenericReaderRegistration.model_validate_json(_canonical(route["reader"]))
            if (
                (ade.design_id, ade.analysis_id, ade.design_profile_sha256)
                != (request.design_id, request.analysis_id, fixed.design_profile_sha256)
                or (reader.design_id, reader.analysis_id, reader.measurement_id)
                != (request.design_id, request.analysis_id, fixed.measurement_id)
                or reader.ade_registration_sha256 != canonical_digest(ade)
                or canonical_digest(reader) != fixed.reader_registration_sha256
                or ade.inputs != conditions.analysis_inputs
                or ade.source_tree_sha256 != conditions.source_tree_sha256
                or ade.ade_state_tree_sha256 != conditions.ade_state_tree_sha256
                or ade.static_statements_sha256 != conditions.static_statements_sha256
                or tuple(model.file_sha256 for model in ade.model_includes)
                != conditions.model_file_sha256
                or reader.transfer != conditions.transfer
            ):
                raise ValueError("route conditions")
            static_conditions.add(ade.static_statements_sha256)
            source_models.add(
                _canonical(
                    [
                        route["source_cell"],
                        [model.model_dump(mode="json") for model in ade.model_includes],
                        route["model_files"],
                    ]
                )
            )
        except (KeyError, TypeError, ValueError):
            raise OperationRejected("candidate_cross_analysis_route_binding_invalid") from None
    if len(static_conditions) != 1:
        raise OperationRejected("candidate_cross_analysis_static_conditions_mismatch")
    if len(source_models) != 1:
        raise OperationRejected("candidate_cross_analysis_source_or_model_mismatch")


class CandidateRevision(VariableModel):
    """Logical V/A candidate revision over a retained source and testbench revision."""

    design_id: LogicalId
    source_revision_sha256: Digest
    testbench_revision_sha256: Digest
    source_baseline_sha256: Digest
    source_tree_sha256: Digest
    values: tuple[ExplicitValue, ...]
    evidence_status: Literal["PLANNED_SOURCE_REFERENCE"] = "PLANNED_SOURCE_REFERENCE"

    @property
    def revision_sha256(self) -> str:
        return canonical_digest(self)


class CandidateAnalysisResult(VariableModel):
    analysis: Literal["dc", "ac", "tran"]
    analysis_id: LogicalId
    operation_id: OperationId
    plan_sha256: Digest
    batch_plan_sha256: Digest
    planned_evidence: CandidateFixedEvidence
    requested_values: tuple[SuppliedValue, ...]
    status: CandidateStatus | Literal["NOT_OBSERVED"]
    reason: str | None
    row: CandidateReportRow | None


class CandidateRevisionResult(VariableModel):
    candidate_id: LogicalId
    label: str
    revision: CandidateRevision
    revision_sha256: Digest
    analyses: tuple[CandidateAnalysisResult, ...]
    verification_at_read: Literal["LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"] = (
        "LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"
    )


def collect_candidate_analyses(
    manifest: CandidateAnalysisManifest,
    expected_manifest_sha256: str,
    observations: dict[str, tuple[CandidateObservation, ...]],
) -> tuple[CandidateRevisionResult, ...]:
    """Join existing captures by batch and candidate ID without contacting a provider."""
    manifest = CandidateAnalysisManifest.model_validate_json(manifest.model_dump_json())
    if expected_manifest_sha256 != manifest.manifest_sha256:
        raise OperationRejected("candidate_analysis_manifest_digest_mismatch")
    if observations.keys() - {batch.request.batch_id for batch in manifest.batches}:
        raise OperationRejected("candidate_analysis_observation_batch_unknown")

    first = manifest.batches[0]
    evidence = first.request.fixed_evidence
    analyses: dict[str, list[CandidateAnalysisResult]] = {
        candidate.candidate_id: [] for candidate in first.request.candidates
    }
    for batch in manifest.batches:
        captures = observations.get(batch.request.batch_id, ())
        captured_ids = {capture.candidate_id for capture in captures}
        comparison = compare_candidate_reports(
            batch,
            batch.plan_sha256,
            captures,
        )
        for child, row in zip(batch.plans, comparison.rows, strict=True):
            captured = row.candidate_id in captured_ids
            analyses[row.candidate_id].append(
                CandidateAnalysisResult(
                    analysis=child.analysis,
                    analysis_id=child.request.analysis_id,
                    operation_id=row.operation_id,
                    plan_sha256=row.plan_sha256,
                    batch_plan_sha256=batch.plan_sha256,
                    planned_evidence=batch.request.fixed_evidence,
                    requested_values=row.requested_values,
                    status=row.status if captured else "NOT_OBSERVED",
                    reason=row.reason if captured else "retained_observation_not_supplied",
                    row=row if captured else None,
                )
            )

    results = []
    for candidate, child in zip(first.request.candidates, first.plans, strict=True):
        revision = CandidateRevision(
            design_id=child.request.design_id,
            source_revision_sha256=evidence.source_revision_sha256,
            testbench_revision_sha256=evidence.testbench_revision_sha256,
            source_baseline_sha256=evidence.source_baseline_sha256,
            source_tree_sha256=evidence.conditions.source_tree_sha256,
            values=child.request.values,
        )
        results.append(
            CandidateRevisionResult(
                candidate_id=candidate.candidate_id,
                label=candidate.label,
                revision=revision,
                revision_sha256=revision.revision_sha256,
                analyses=tuple(analyses[candidate.candidate_id]),
            )
        )
    return tuple(results)


@dataclass(frozen=True)
class PmosDcOperation:
    """One reviewed operation and the original registered assets for that plan."""

    query: NativeOperationQuery
    plan: OperationPlan
    runtime_manifest: bytes
    runtime_registration: bytes
    design_registry: bytes
    record: DurableOperation | None = None
    report: bytes | None = None
    expected_report_sha256: str | None = None
    expected_terminal_sha256: str | None = None


class PmosDefaultChangeRequest(VariableModel):
    operation_id: OperationId
    expected_plan_sha256: Digest
    expected_scope_sha256: Digest


class PmosDefaultChangeResult(VariableModel):
    operation_id: OperationId
    plan_sha256: Digest
    scope_sha256: Digest
    outcome: Literal["VERIFIED", "FAILED", "OUTCOME_UNKNOWN"]
    replayed: bool
    dispatched_this_call: bool | None
    candidate_revision: RevisionBinding
    observed_revision_sha256: Digest | None = None
    observed_testbench_revision_sha256: Digest | None = None
    source_preservation_sha256: Digest | None = None
    reopen_receipt_sha256: Digest | None = None
    netlist_receipt_sha256: Digest | None = None
    netlist_sha256: Digest | None = None
    reason: str | None = None
    new_simulations: Literal[0] = 0
    new_reservations: Literal[0] = 0

    @model_validator(mode="after")
    def retained_evidence(self) -> Self:
        if self.replayed and self.dispatched_this_call is not False:
            raise ValueError("retained lookup cannot dispatch")
        if self.dispatched_this_call is None and self.outcome != "OUTCOME_UNKNOWN":
            raise ValueError("uncertain dispatch requires an unknown outcome")
        reopen_evidence = (
            self.observed_revision_sha256,
            self.observed_testbench_revision_sha256,
            self.source_preservation_sha256,
            self.reopen_receipt_sha256,
        )
        reopened = all(value is not None for value in reopen_evidence)
        if (self.outcome == "VERIFIED" or self.reopen_receipt_sha256 is not None) and not reopened:
            raise ValueError("verified reopen requires observed revision and source preservation")
        if (self.netlist_receipt_sha256 is None) != (self.netlist_sha256 is None):
            raise ValueError("netlist evidence requires both receipt and artifact digests")
        if self.outcome == "VERIFIED" and self.netlist_receipt_sha256 is None:
            raise ValueError("verified change requires netlist evidence")
        if self.netlist_receipt_sha256 is not None and not reopened:
            raise ValueError("netlist evidence requires verified reopen evidence")
        return self

    def check_registered_scope(
        self,
        request: PmosDefaultChangeRequest,
        *,
        registered_plan: ChangePlan,
        registered_scope_sha256: str,
    ) -> None:
        """Check the result against independently resolved registration before returning it."""
        if (
            not isinstance(registered_plan.target, MosWidthTarget)
            or self.operation_id != request.operation_id
            or self.plan_sha256 != request.expected_plan_sha256
            or self.plan_sha256 != registered_plan.plan_sha256
            or self.scope_sha256 != request.expected_scope_sha256
            or self.scope_sha256 != registered_scope_sha256
            or self.candidate_revision != registered_plan.candidate_revision
        ):
            raise OperationRejected("pmos_default_change_identity_mismatch")


class PmosDefaultChangeService(Protocol):
    """C1 resolves registration, verifies receipts and checks scope before returning."""

    def apply(self, request: PmosDefaultChangeRequest) -> PmosDefaultChangeResult: ...


class PmosDcRow(VariableModel):
    revision: RevisionBinding
    revision_sha256: Digest
    testbench_revision_sha256: Digest
    requested_width: ChangeValue | None
    observed_width: ChangeValue
    effective_width: ChangeValue
    operation: NativeOperationQuery
    terminal_receipt_sha256: Digest | None
    status: OperationPhase | Literal["NOT_OBSERVED"]
    reason: str | None
    report: ResultReport | None


class PmosDcMetricPair(VariableModel):
    signal_id: Literal["cmos-vout", "supply-rail"]
    baseline: ReportMetric | None
    candidate: ReportMetric | None


class PmosDcPair(VariableModel):
    change_plan_sha256: Digest
    copy_receipt_sha256: Digest
    rows: tuple[PmosDcRow, PmosDcRow]
    metrics: tuple[PmosDcMetricPair, PmosDcMetricPair]
    verification: Literal["LOCAL_EVIDENCE_COMPARISON"] = "LOCAL_EVIDENCE_COMPARISON"
    goals: Literal["GOALS_NOT_PROVIDED"] = "GOALS_NOT_PROVIDED"
    execution_authorized: Literal[False] = False


class AmplifierWidthAnalysisBinding(VariableModel):
    """Independently verified legacy measurement and native child route bindings."""

    baseline_operation_id: str
    baseline_plan_sha256: Digest
    baseline_reader: GenericReaderRegistration
    model_includes: tuple[ModelInclude, ...]
    model_closure_sha256: Digest
    child_operation_id: OperationId | None = None
    child_plan_sha256: Digest | None = None

    @model_validator(mode="after")
    def child_identity_pair(self) -> Self:
        if (self.child_operation_id is None) != (self.child_plan_sha256 is None):
            raise ValueError("child operation and plan pins must be supplied together")
        return self


class AmplifierWidthBinding(VariableModel):
    change_plan_sha256: Digest
    readback_sha256: Digest
    baseline_revision_sha256: Digest
    baseline_testbench_revision_sha256: Digest
    child_revision_sha256: Digest
    child_testbench_revision_sha256: Digest
    child_source_tree_sha256: Digest
    child_ade_state_sha256: Digest
    dc: AmplifierWidthAnalysisBinding
    ac: AmplifierWidthAnalysisBinding


@dataclass(frozen=True)
class AmplifierWidthAnalysis:
    baseline: AmplifierSweepResult
    expected_baseline_sha256: str
    baseline_input: bytes
    child: PmosDcOperation | None = None
    child_input: bytes | None = None


class AmplifierWidthAnalysisPair(VariableModel):
    analysis: Literal["dc", "ac"]
    metric_id: Literal["dc-supply-power-grid-v2", "gain-10hz-grid-v1"]
    unit: Literal["W", "dB"]
    baseline: AmplifierFactProvenance
    baseline_value: float
    child_operation: NativeOperationQuery | None
    child_terminal_sha256: Digest | None
    child_status: OperationPhase | Literal["NOT_RUN"]
    child_report: ResultReport | None
    child_value: float | None
    reason: str | None
    dc_output_reason: Literal["baseline_output_scalars_not_retained"] | None = None


class AmplifierWidthPair(VariableModel):
    change_plan_sha256: Digest
    binding_sha256: Digest
    readback: ChangeReadback
    dc: AmplifierWidthAnalysisPair
    ac: AmplifierWidthAnalysisPair
    goals: Literal["GOALS_NOT_PROVIDED"] = "GOALS_NOT_PROVIDED"
    execution_authorized: Literal[False] = False


class _AmplifierCircuit(NamedTuple):
    parameters: dict[str, str]
    includes: list[tuple[str, str]]
    fixed_statements: list[str]
    pm0_options: dict[str, str]


def _pinned_json(raw: bytes, digest: str) -> Any:
    _closed_document(raw, max_bytes=1048576)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("evidence digest mismatch")
    return json.loads(raw)


def _reader_signals(reader: GenericReaderRegistration) -> tuple[object, ...]:
    return reader.nodes, reader.sources, reader.transfer


def _amp_child_metric(report: ResultReport, reader: GenericReaderRegistration) -> float | None:
    if report.plan.analysis == "ac":
        transfer = reader.transfer
        if transfer is None or transfer.negative_input is None or transfer.negative_output is None:
            raise ValueError("differential AC reader required")
        selectors = {node.logical_id: node.selector for node in reader.nodes}
        if tuple(
            selectors[node]
            for node in (
                transfer.positive_input,
                transfer.negative_input,
                transfer.positive_output,
                transfer.negative_output,
            )
        ) != ("/Vp", "/Vm", "/Vop", "/Vom"):
            raise ValueError("amplifier differential selectors differ")
        return next(
            (
                m.value
                for m in report.metrics
                if m.kind == "voltage_gain_db" and m.frequency_hz == 10 and m.signal_id is None
            ),
            None,
        )
    selectors = {node.logical_id: node.selector for node in reader.nodes}
    rails = {
        source.source_id: (
            source.current_selector,
            selectors.get(source.positive_node or ""),
            source.negative_node,
        )
        for source in reader.sources
        if source.role == "supply"
    }
    if rails != {"vdd": ("/VDD/PLUS", "/VDD", None), "vss": ("/VSS/PLUS", "/VSS", None)}:
        raise ValueError("amplifier rail inventory differs")
    values = {
        metric.signal_id: metric.value
        for metric in report.metrics
        if metric.kind == "delivered_power" and metric.source_role == "supply"
    }
    if values.keys() - rails.keys():
        raise ValueError("unregistered supply power")
    if values.keys() != rails.keys():
        return None
    total = sum(value for value in values.values() if value is not None)
    if not isfinite(total):
        raise ValueError("nonfinite amplifier power")
    return total


def _width_route(
    operation: PmosDcOperation,
    diagnostic: bytes,
    analysis_kind: Literal["dc", "ac"],
) -> tuple[dict[str, Any], ReportConditions, GenericReaderRegistration, tuple[object, ...]]:
    plan = OperationPlan.model_validate_json(operation.plan.model_dump_json())
    query = NativeOperationQuery.model_validate_json(operation.query.model_dump_json())
    if plan.plan_sha256 != query.expected_plan_sha256 or plan.analysis != analysis_kind:
        raise ValueError("analysis plan identity mismatch")
    design, analysis = plan.request.design_id, plan.request.analysis_id
    route = _runtime_routes(plan, operation.runtime_manifest, operation.runtime_registration)[
        design, analysis
    ]
    ade = AdeExecutionRegistration.model_validate_json(_canonical(route["ade"]))
    reader = GenericReaderRegistration.model_validate_json(_canonical(route["reader"]))
    registry = DesignMeasurementRegistry.model_validate_json(
        _canonical(_pinned_json(operation.design_registry, plan.design_sha256))
    )
    profile = registry.profile(design)
    variables = registry.variable_set(design)
    (contract,) = (item for item in registry.analyses_for(design) if item.analysis_id == analysis)
    (measurement,) = (
        item
        for item in registry.measurements_for(design)
        if item.analysis_id == analysis and item.measurement_id == reader.measurement_id
    )
    if (
        variables is None
        or route["analysis"] != analysis_kind
        or contract.analysis != analysis_kind
        or ade.inputs.analysis != analysis_kind
        or (ade.design_id, ade.analysis_id) != (design, analysis)
        or (reader.design_id, reader.analysis_id) != (design, analysis)
        or reader.ade_registration_sha256 != canonical_digest(ade)
        or reader.measurement_contract_sha256 != canonical_digest(measurement)
        or measurement.analysis_contract_sha256 != canonical_digest(contract)
        or ade.design_profile_sha256 != canonical_digest(profile)
        or ade.variable_set_sha256 != canonical_digest(variables)
        or route["profile"] != profile.model_dump(mode="json")
        or route["variables"] != [var.model_dump(mode="json") for var in variables.variables]
        or (reader.transfer is not None) != (analysis_kind == "ac")
    ):
        raise ValueError("DC route binding mismatch")
    supplied = {value.logical_id: value for value in plan.request.values}
    if supplied.keys() != {var.logical_id for var in variables.variables} or any(
        supplied[var.logical_id].unit != var.unit
        or var.check_number(supplied[var.logical_id].value) is not None
        for var in variables.variables
    ):
        raise ValueError("DC variable binding mismatch")
    effective_input(  # type: ignore[no-untyped-call]
        diagnostic,
        {var.cadence_binding: supplied[var.logical_id].value for var in variables.variables},
        [(model.path, model.section) for model in ade.model_includes],
        ade.inputs.model_dump(mode="json"),
        ade.static_statements_sha256,
    )
    conditions = ReportConditions(
        analysis_inputs=ade.inputs,
        source_tree_sha256=ade.source_tree_sha256,
        ade_state_tree_sha256=ade.ade_state_tree_sha256,
        static_statements_sha256=ade.static_statements_sha256,
        model_file_sha256=tuple(model.file_sha256 for model in ade.model_includes),
        transfer=reader.transfer,
    )
    (library,) = (item for item in route["libraries"] if item["name"] == profile.binding.library)
    if route["source_cell"] != library["path"] + "/" + profile.binding.cell:
        raise ValueError("DC source cell is outside its registered library binding")
    semantics = (
        plan.resource_domain_sha256,
        plan.ledger_ref,
        plan.environment_sha256,
        plan.pdk_sha256,
        plan.request.values,
        variables.variables,
        ade.inputs,
        ade.model_includes,
        route["model_files"],
        [item for item in route["libraries"] if item != library],
        profile.model_dump(exclude={"design_id": True, "binding": {"library"}}),
        reader.model_dump(
            exclude={
                "design_id",
                "analysis_id",
                "ade_registration_sha256",
                "measurement_contract_sha256",
            }
        ),
        measurement.model_dump(exclude={"design_id", "analysis_id", "analysis_contract_sha256"}),
        contract.model_dump(
            exclude={"design_id", "analysis_id", "design_profile_sha256", "variable_set_sha256"}
        ),
    )
    return route, conditions, reader, semantics


def _width_report(
    operation: PmosDcOperation,
    conditions: ReportConditions,
    reader: GenericReaderRegistration,
) -> tuple[OperationPhase | Literal["NOT_OBSERVED"], str | None, ResultReport | None]:
    status: OperationPhase | Literal["NOT_OBSERVED"] = "NOT_OBSERVED"
    record = None
    if operation.record is not None:
        record = DurableOperation.model_validate_json(operation.record.model_dump_json())
        if record.operation_id != operation.query.operation_id or record.plan != operation.plan:
            raise ValueError("retained operation identity differs")
        status = record.progress.phase
    terminal = operation.expected_terminal_sha256
    if terminal is not None and (
        record is None or record.progress.provider_receipt_sha256 != terminal
    ):
        raise ValueError("retained terminal receipt differs")
    if operation.report is None:
        return status, terminal, None
    if record is None or operation.expected_report_sha256 is None:
        raise ValueError("retained report requires a record and an independent pin")
    report = ResultReport.model_validate_json(
        _canonical(
            _pinned_json(
                operation.report,
                operation.expected_report_sha256,
            )
        )
    )
    if (
        status != "SUCCEEDED"
        or terminal is None
        or report.operation_id != operation.query.operation_id
        or report.plan != operation.plan
        or report.analysis_conditions != conditions
        or report.measurement_id != reader.measurement_id
        or report.reader_registration_sha256 != canonical_digest(reader)
    ):
        raise ValueError("retained report binding differs")
    return status, terminal, report


def _pmos_dc_report(
    operation: PmosDcOperation,
    conditions: ReportConditions,
    reader: GenericReaderRegistration,
) -> tuple[OperationPhase | Literal["NOT_OBSERVED"], str | None, ResultReport | None]:
    status, terminal, report = _width_report(operation, conditions, reader)
    if report is None:
        return status, terminal, report
    nodes = {node.logical_id for node in reader.nodes}
    sources = {source.source_id: source.role for source in reader.sources}
    voltages = {}
    for metric in report.metrics:
        if metric.sample_count is not None:
            raise ValueError("DC point metric cannot have a sample count")
        if metric.kind == "node_voltage" and metric.signal_id in nodes:
            voltages[metric.signal_id] = metric.value
        elif (
            metric.kind != "delivered_power"
            or metric.signal_id not in sources
            or metric.source_role != sources[metric.signal_id]
        ):
            raise ValueError("report metric differs from the registered reader")
    for signal, nominal in (("cmos-vin", 0.0), ("cmos-vdd", 1.0)):
        observed = voltages.get(signal)
        if observed is None or not nominal - 0.01 <= observed <= nominal + 0.01:
            raise ValueError("measured DC input or rail differs")
    return status, terminal, report


def _pmos_dc_metric_pair(
    signal_id: Literal["cmos-vout", "supply-rail"],
    baseline: ResultReport,
    candidate: ResultReport | None,
) -> PmosDcMetricPair:
    kind = "node_voltage" if signal_id == "cmos-vout" else "delivered_power"
    old = next((m for m in baseline.metrics if (m.kind, m.signal_id) == (kind, signal_id)), None)
    new = (
        None
        if candidate is None
        else next(
            (m for m in candidate.metrics if (m.kind, m.signal_id) == (kind, signal_id)),
            None,
        )
    )
    if (
        old is not None
        and new is not None
        and old.model_dump(exclude={"value"}) != (new.model_dump(exclude={"value"}))
    ):
        raise ValueError("DC metric definitions differ")
    return PmosDcMetricPair(signal_id=signal_id, baseline=old, candidate=new)


def associate_pmos_dc_pair(
    plan: ChangePlan,
    readback: ChangeReadback,
    *,
    expected_plan_sha256: str,
    baseline_input: bytes,
    candidate_input: bytes,
    copy_receipt: bytes,
    expected_copy_receipt_sha256: str,
    expected_copy_scope_sha256: str,
    expected_copy_id: str,
    expected_reopen_receipt_sha256: str,
    baseline: PmosDcOperation,
    candidate: PmosDcOperation,
) -> PmosDcPair:
    """Associate a reviewed width-only DC pair from pinned retained evidence.

    Expected pins must come from the reviewed C1/C4 packet. This local join
    does not authenticate imported bytes anew, authorize, or run an operation.
    """
    try:
        if not isinstance(plan.target, MosWidthTarget) or plan.plan_sha256 != expected_plan_sha256:
            raise ValueError("width change plan differs")
        checked = verify_change_readback(
            plan,
            baseline=readback.baseline,
            reopened=readback.reopened,
            netlist=readback.netlist,
        )
        old, reopened, netlist = checked.baseline, checked.reopened, checked.netlist
        if checked != readback or checked.status != "MATCHED" or not (old and reopened and netlist):
            raise ValueError("complete matched change readback required")
        projected = project_netlist_change(plan, baseline_input, candidate_input)
        if (
            projected.artifact_sha256 != netlist.artifact_sha256
            or projected.value.normalized != netlist.value.normalized
            or projected.derived != netlist.derived
        ):
            raise ValueError("candidate effective input differs from readback")
        _, old_conditions, old_reader, old_semantics = _width_route(baseline, baseline_input, "dc")
        route, new_conditions, new_reader, new_semantics = _width_route(
            candidate, candidate_input, "dc"
        )
        copy = _pinned_json(copy_receipt, expected_copy_receipt_sha256)
        if (
            copy["status"] != "OWNED_INPUT_COPY_VERIFIED"
            or copy["scope_sha256"] != expected_copy_scope_sha256
            or copy["copy_id"] != expected_copy_id
            or copy["source_revision_sha256"] != reopened.revision_sha256
            or copy["reopen_receipt_sha256"] != expected_reopen_receipt_sha256
            or copy["source_ade_sha256"] != old_conditions.ade_state_tree_sha256
            or (copy["source_cell"], copy["source_state"])
            != (route["source_cell"], route["source_state"])
            or (copy["source_cell_sha256"], copy["source_state_sha256"])
            != (new_conditions.source_tree_sha256, new_conditions.ade_state_tree_sha256)
            or {
                "name": route["profile"]["binding"]["library"],
                "path": copy["library_path"],
                "tree_sha256": copy["dependency_tree_sha256"],
            }
            not in route["libraries"]
        ):
            raise ValueError("external copy is not bound to the child route")
        if (
            old_semantics != new_semantics
            or baseline.query.operation_id == candidate.query.operation_id
            or candidate.query.operation_id == expected_copy_id
        ):
            raise ValueError("DC comparison conditions differ")
        old_status, old_terminal, old_report = _pmos_dc_report(baseline, old_conditions, old_reader)
        new_status, new_terminal, new_report = _pmos_dc_report(
            candidate, new_conditions, new_reader
        )
        if old_report is None:
            raise ValueError("baseline report required")
        vout = _pmos_dc_metric_pair("cmos-vout", old_report, new_report)
        power = _pmos_dc_metric_pair("supply-rail", old_report, new_report)
    except (KeyError, TypeError, ValueError):
        raise OperationRejected("candidate_pmos_dc_evidence_mismatch") from None
    reason = None
    if new_status == "NOT_OBSERVED":
        reason = "retained_operation_not_supplied"
    elif new_status != "SUCCEEDED":
        reason = "retained_operation_not_succeeded"
    elif new_report is None:
        reason = "retained_result_unavailable"
    return PmosDcPair(
        change_plan_sha256=plan.plan_sha256,
        copy_receipt_sha256=expected_copy_receipt_sha256,
        metrics=(vout, power),
        rows=(
            PmosDcRow(
                revision=old.revision,
                revision_sha256=old.revision_sha256,
                testbench_revision_sha256=old.testbench_revision_sha256,
                requested_width=None,
                observed_width=old.value,
                effective_width=plan.old,
                operation=baseline.query,
                terminal_receipt_sha256=old_terminal,
                status=old_status,
                reason=None,
                report=old_report,
            ),
            PmosDcRow(
                revision=reopened.revision,
                revision_sha256=reopened.revision_sha256,
                testbench_revision_sha256=reopened.testbench_revision_sha256,
                requested_width=plan.requested,
                observed_width=reopened.value,
                effective_width=netlist.value,
                operation=candidate.query,
                terminal_receipt_sha256=new_terminal,
                status=new_status,
                reason=reason,
                report=new_report,
            ),
        ),
    )


def _amp_width_analysis(
    analysis: Literal["dc", "ac"],
    evidence: AmplifierWidthAnalysis,
    binding: AmplifierWidthAnalysisBinding,
    revision: AmplifierWidthBinding,
    old_circuit: _AmplifierCircuit,
    child_circuit: _AmplifierCircuit,
) -> AmplifierWidthAnalysisPair:
    metric_id: Literal["dc-supply-power-grid-v2", "gain-10hz-grid-v1"] = (
        "dc-supply-power-grid-v2" if analysis == "dc" else "gain-10hz-grid-v1"
    )
    (metric,) = (
        m
        for m in evidence.baseline.measurements
        if m.requested_vbiasn_v == "0.32" and m.measurement_id == metric_id
    )
    if (
        str(metric.job_id) != binding.baseline_operation_id
        or evidence.baseline.engine.plan_hash != binding.baseline_plan_sha256
        or hashlib.sha256(evidence.baseline_input).hexdigest() != metric.input_sha256
    ):
        raise ValueError("original amplifier measurement identity differs")
    params, includes, analyses, static = partition_input(evidence.baseline_input)  # type: ignore[no-untyped-call]
    fixed, options = _amp_pm0_options(static, baseline=True)
    if (
        (params, includes, options)
        != (old_circuit.parameters, old_circuit.includes, old_circuit.pm0_options)
        or (analysis == "dc" and fixed != old_circuit.fixed_statements)
        or includes != [(model.path, model.section) for model in binding.model_includes]
        or len(analyses) != 1
        or analyses[0][0] != analysis
    ):
        raise ValueError("baseline measurement circuit differs from center")
    child = evidence.child
    terminal = report = value = None
    reason: str | None = "retained_operation_not_supplied"
    status: OperationPhase | Literal["NOT_RUN"] = "NOT_RUN"
    if child is not None:
        if (
            evidence.child_input is None
            or child.plan.plan_sha256 != binding.child_plan_sha256
            or child.query.operation_id != binding.child_operation_id
        ):
            raise ValueError("child operation requires registered effective input and plan")
        route, conditions, reader, _ = _width_route(child, evidence.child_input, analysis)
        new_params, new_includes, new_analyses, new_static = partition_input(evidence.child_input)  # type: ignore[no-untyped-call]
        new_fixed, new_options = _amp_pm0_options(new_static, baseline=False)
        if (
            (new_params, new_includes, new_options)
            != (child_circuit.parameters, child_circuit.includes, child_circuit.pm0_options)
            or new_fixed != fixed
            or new_analyses != analyses
            or AdeExecutionRegistration.model_validate_json(_canonical(route["ade"])).model_includes
            != binding.model_includes
            or hashlib.sha256(_canonical(route["model_files"])).hexdigest()
            != binding.model_closure_sha256
            or conditions.source_tree_sha256 != revision.child_source_tree_sha256
            or conditions.ade_state_tree_sha256 != revision.child_ade_state_sha256
            or _reader_signals(reader) != _reader_signals(binding.baseline_reader)
            or reader.measurement_id != binding.baseline_reader.measurement_id
            or reader.maximum_samples != binding.baseline_reader.maximum_samples
        ):
            raise ValueError("child amplifier circuit or measurement differs")
        phase, terminal, report = _width_report(child, conditions, reader)
        if phase != "NOT_OBSERVED":
            status = phase
            reason = (
                "retained_result_unavailable"
                if phase == "SUCCEEDED"
                else "retained_operation_not_succeeded"
            )
        if report is not None:
            if report.execution_input_sha256 != hashlib.sha256(evidence.child_input).hexdigest():
                raise ValueError("child report effective input differs")
            value = _amp_child_metric(report, reader)
            reason = "registered_measurement_unavailable" if value is None else None
    elif evidence.child_input is not None:
        raise ValueError("unbound child input")
    return AmplifierWidthAnalysisPair(
        analysis=analysis,
        metric_id=metric_id,
        unit=metric.unit,
        baseline=provenance(metric, binding.baseline_plan_sha256),
        baseline_value=metric.value,
        child_operation=None if child is None else child.query,
        child_terminal_sha256=terminal,
        child_status=status,
        child_report=report,
        child_value=value,
        reason=reason,
        dc_output_reason="baseline_output_scalars_not_retained" if analysis == "dc" else None,
    )


def associate_amplifier_width_pair(
    plan: ChangePlan,
    readback: ChangeReadback,
    *,
    expected_plan_sha256: str,
    baseline_input: bytes,
    candidate_input: bytes,
    registration_evidence: bytes,
    expected_registration_sha256: str,
    dc: AmplifierWidthAnalysis,
    ac: AmplifierWidthAnalysis,
) -> AmplifierWidthPair:
    """Join a qualified PM0 child to the retained 0.320 V DC and AC measurements.

    The registration pin must come from C1/C4's independent verification of
    source lineage, model closure and original measurement reader semantics.
    A local comparison of these retained records conveys no execution authority.
    """
    from cadence_mcp_bridge.amplifier_candidate_selection import _checked_source

    try:
        binding = AmplifierWidthBinding.model_validate_json(
            _canonical(_pinned_json(registration_evidence, expected_registration_sha256))
        )
        checked = verify_change_readback(
            plan, baseline=readback.baseline, reopened=readback.reopened, netlist=readback.netlist
        )
        old, reopened, netlist = checked.baseline, checked.reopened, checked.netlist
        if (
            not isinstance(plan.target, MosWidthTarget)
            or plan.target.instance.instance_path != "PM0"
            or plan.plan_sha256 != expected_plan_sha256
            or binding.change_plan_sha256 != expected_plan_sha256
            or binding.readback_sha256 != canonical_digest(readback)
            or checked != readback
            or checked.status != "MATCHED"
            or old is None
            or reopened is None
            or netlist is None
        ):
            raise ValueError("complete PM0 change readback required")
        projection = project_netlist_change(plan, baseline_input, candidate_input)
        if (
            (binding.baseline_revision_sha256, binding.baseline_testbench_revision_sha256)
            != (old.revision_sha256, old.testbench_revision_sha256)
            or (binding.child_revision_sha256, binding.child_testbench_revision_sha256)
            != (reopened.revision_sha256, reopened.testbench_revision_sha256)
            or reopened.testbench_revision_sha256 == old.testbench_revision_sha256
            or projection.artifact_sha256 != netlist.artifact_sha256
            or projection.value.normalized != netlist.value.normalized
            or projection.derived != netlist.derived
            or (
                binding.dc.child_plan_sha256 is not None
                and binding.dc.child_plan_sha256 == binding.ac.child_plan_sha256
            )
            or binding.dc.model_closure_sha256 != binding.ac.model_closure_sha256
            or binding.dc.model_includes != binding.ac.model_includes
            or (
                dc.child is not None
                and ac.child is not None
                and (
                    dc.child.query.operation_id == ac.child.query.operation_id
                    or dc.child.plan.resource_domain_sha256 != ac.child.plan.resource_domain_sha256
                    or dc.child.plan.ledger_ref != ac.child.plan.ledger_ref
                )
            )
        ):
            raise ValueError("PM0 child evidence binding differs")
        dc_source = _checked_source(
            dc.baseline, dc.expected_baseline_sha256, "dc-supply-power-grid-v2"
        )
        ac_source = _checked_source(ac.baseline, ac.expected_baseline_sha256, "gain-10hz-grid-v1")
        require_same_resource_policy(
            tuple(
                m.counter for source in (dc_source, ac_source) for m in source.source.measurements
            )
        )
        old_params, old_includes, old_analyses, old_static = partition_input(baseline_input)  # type: ignore[no-untyped-call]
        new_params, new_includes, _, new_static = partition_input(candidate_input)  # type: ignore[no-untyped-call]
        if (
            old_params.get("VBIASN") != "0.32"
            or old_params.get("VBIASP") != "0.702"
            or len(old_analyses) != 1
            or old_analyses[0][0] != "dc"
        ):
            raise ValueError("center amplifier DC operating point required")
        if partition_input(dc.baseline_input)[2] != old_analyses:  # type: ignore[no-untyped-call]
            raise ValueError("center DC analysis differs")
        old_circuit = _AmplifierCircuit(
            old_params, old_includes, *_amp_pm0_options(old_static, baseline=True)
        )
        child_circuit = _AmplifierCircuit(
            new_params, new_includes, *_amp_pm0_options(new_static, baseline=False)
        )
        dc_pair = _amp_width_analysis("dc", dc, binding.dc, binding, old_circuit, child_circuit)
        ac_pair = _amp_width_analysis("ac", ac, binding.ac, binding, old_circuit, child_circuit)
    except (KeyError, TypeError, ValueError):
        raise OperationRejected("candidate_amplifier_width_evidence_mismatch") from None
    return AmplifierWidthPair(
        change_plan_sha256=expected_plan_sha256,
        binding_sha256=expected_registration_sha256,
        readback=checked,
        dc=dc_pair,
        ac=ac_pair,
    )
