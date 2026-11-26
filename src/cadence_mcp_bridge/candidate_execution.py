"""Link independently planned candidate analyses using their retained identities."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from math import isfinite
from typing import Annotated, Any, Literal, NamedTuple, Protocol, Self, TypedDict

from pydantic import Field, model_validator

from cadence_mcp_bridge._native_rendering import effective_input, partition_input
from cadence_mcp_bridge.amplifier_specifications import AmplifierFactProvenance, provenance
from cadence_mcp_bridge.amplifier_sweeps import AmplifierSweepResult
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.authenticated_provider import (
    NATIVE_RESULT_LIMIT,
    NativeResultPayload,
    verify_native_result,
)
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
from cadence_mcp_bridge.environments import EnvironmentProfile
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration, ModelInclude
from cadence_mcp_bridge.generic_measurements import (
    GenericReaderRegistration,
    _ac_axis,
    _matches_ac_axis,
    _sample_indices,
    bind_reader,
)
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
    AdeTarget,
    ChangePlan,
    ChangeReadback,
    ChangeValue,
    DerivedValue,
    MosWidthTarget,
    Readback,
    _amp_pm0_options,
    partition_amplifier_input,
    project_netlist_change,
    verify_change_readback,
)
from cadence_mcp_bridge.power_measurements import require_same_resource_policy
from cadence_mcp_bridge.result_reports import (
    ReportConditions,
    ReportMetric,
    ResultReport,
    make_report,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    VariableContract,
    VariableModel,
    canonical_digest,
)


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
    environment_profile: bytes | None = None


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


class AmplifierBaselineIncludeAlias(VariableModel):
    """Receipt references independently authenticated for one archived AMP input."""

    baseline_input_sha256: Digest
    archived_path_sha256: Digest
    canonical_include: ModelInclude
    historical_model_closure_sha256: Digest
    historical_equivalence_receipt_sha256: Digest


class AmplifierWidthAnalysisBinding(VariableModel):
    """Independently verified legacy measurement and native child route bindings."""

    baseline_operation_id: str
    baseline_plan_sha256: Digest
    baseline_reader: GenericReaderRegistration
    model_includes: tuple[ModelInclude, ...]
    model_closure_sha256: Digest
    baseline_include_alias: AmplifierBaselineIncludeAlias | None = None
    child_operation_id: OperationId | None = None
    child_plan_sha256: Digest | None = None
    child_input_sha256: Digest | None = None

    @model_validator(mode="after")
    def child_identity_pair(self) -> Self:
        pins = (self.child_operation_id, self.child_plan_sha256, self.child_input_sha256)
        if any(pin is None for pin in pins) and any(pin is not None for pin in pins):
            raise ValueError("child operation, plan and input pins must be supplied together")
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
    child_status: OperationPhase | Literal["NOT_RUN", "NOT_OBSERVED"]
    child_report: ResultReport | None
    child_value: float | None
    reason: str | None
    model_comparison: Literal["MATCHED", "NOT_EVALUATED"] = "MATCHED"
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


_AMP_DC_OUTPUT_DIRECTIVE_SHA256 = "a9ca38379d1571bcd44fe8525109abeceea855e2784c0dc93c6c3384f0447fbd"


_AMP_ARCHIVED_INCLUDE_PATH_SHA256 = (
    "b628372fdce9ae6af7a2a6e3fc6fb4091e2c8a0b5c605d1432ba3152bd0cd47e"
)
_AMP_CANONICAL_INCLUDE_PATH_SHA256 = (
    "6d4ec0a3bfc8d8e3742a09c5ff7f817ff5c11c5d4f33187b3a6e8e1ba6c4e8f7"
)


def _amp_model_comparison(
    includes: list[tuple[str, str]],
    binding: AmplifierWidthAnalysisBinding,
    baseline_input_sha256: str,
) -> Literal["MATCHED", "NOT_EVALUATED"]:
    registered = [(model.path, model.section) for model in binding.model_includes]
    evidence = binding.baseline_include_alias
    if includes == registered and evidence is None:
        return "MATCHED"
    ((archived_path, section),) = includes
    (canonical,) = binding.model_includes
    if (
        hashlib.sha256(archived_path.encode("ascii")).hexdigest()
        != _AMP_ARCHIVED_INCLUDE_PATH_SHA256
        or hashlib.sha256(canonical.path.encode("ascii")).hexdigest()
        != _AMP_CANONICAL_INCLUDE_PATH_SHA256
        or section != "NN"
        or canonical.section != section
    ):
        raise ValueError("amplifier model include differs")
    if evidence is None:
        return "NOT_EVALUATED"
    if (
        evidence.baseline_input_sha256 != baseline_input_sha256
        or evidence.archived_path_sha256 != _AMP_ARCHIVED_INCLUDE_PATH_SHA256
        or evidence.canonical_include != canonical
        or evidence.historical_model_closure_sha256 != binding.model_closure_sha256
        or evidence.historical_equivalence_receipt_sha256
        in (baseline_input_sha256, canonical.file_sha256, binding.model_closure_sha256)
    ):
        raise ValueError("amplifier archived model evidence differs")
    return "MATCHED"


def _amplifier_cross_analysis_body(statements: list[str]) -> list[str]:
    # The original center DC alone emits this exact operating-point output directive.
    indexes = [
        index
        for index, statement in enumerate(statements)
        if hashlib.sha256(statement.encode("ascii")).hexdigest() == _AMP_DC_OUTPUT_DIRECTIVE_SHA256
    ]
    if not indexes:
        return statements
    (index,) = indexes
    return statements[:index] + statements[index + 1 :]


def _pinned_json(raw: bytes, digest: str) -> Any:
    _closed_document(raw, max_bytes=NATIVE_RESULT_LIMIT)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("evidence digest mismatch")
    return json.loads(raw)


def _reader_signals(reader: GenericReaderRegistration) -> tuple[object, ...]:
    return reader.nodes, reader.sources, reader.transfer


def _amp_child_metric(
    report: ResultReport,
    reader: GenericReaderRegistration,
    *,
    physical_sources: tuple[str, str] = ("VDD", "VSS"),
) -> float | None:
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
    vdd, vss = physical_sources
    if rails != {"vdd": (f"/{vdd}/PLUS", "/VDD", None), "vss": (f"/{vss}/PLUS", "/VSS", None)}:
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
    diagnostic: bytes | None,
    analysis_kind: Literal["dc", "ac"],
    *,
    varied_id: str | None = None,
    exported_technology: dict[str, str] | None = None,
    export_comparison: bool = False,
    storage_successor_verified: bool = False,
    owned_copy: _FreshAmplifierCopyRoute | None = None,
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
    if diagnostic is not None:
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
    profile_fields = profile.model_dump(exclude={"design_id": True, "binding": {"library"}})
    if export_comparison:
        profile_fields["binding"]["ade"].pop("state")
    libraries = [item for item in route["libraries"] if item not in (library, exported_technology)]
    if owned_copy is not None:
        libraries = _fresh_amplifier_copy_route(
            owned_copy, operation, route, library, libraries, profile_fields, analysis_kind
        )
    semantics = (
        plan.resource_domain_sha256,
        plan.ledger_ref,
        None if export_comparison or storage_successor_verified else plan.environment_sha256,
        plan.pdk_sha256,
        tuple(value for value in plan.request.values if value.logical_id != varied_id),
        tuple(variable for variable in variables.variables if variable.logical_id != varied_id),
        ade.inputs,
        ade.model_includes,
        route["model_files"],
        libraries,
        profile_fields,
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
    params, includes, analyses, static = partition_amplifier_input(
        evidence.baseline_input, expected_sha256=metric.input_sha256
    )
    fixed, options = _amp_pm0_options(static, baseline=True)
    if (
        (params, includes, options)
        != (old_circuit.parameters, old_circuit.includes, old_circuit.pm0_options)
        or fixed
        != (
            old_circuit.fixed_statements
            if analysis == "dc"
            else _amplifier_cross_analysis_body(old_circuit.fixed_statements)
        )
        or len(analyses) != 1
        or analyses[0][0] != analysis
    ):
        raise ValueError("baseline measurement circuit differs from center")
    model_comparison = _amp_model_comparison(includes, binding, metric.input_sha256)
    child = evidence.child
    terminal = report = value = None
    reason: str | None = "retained_operation_not_supplied"
    status: OperationPhase | Literal["NOT_RUN", "NOT_OBSERVED"] = "NOT_RUN"
    if child is not None:
        if (
            evidence.child_input is None
            or child.plan.plan_sha256 != binding.child_plan_sha256
            or child.query.operation_id != binding.child_operation_id
        ):
            raise ValueError("child operation requires registered effective input and plan")
        route, conditions, reader, _ = _width_route(child, evidence.child_input, analysis)
        if binding.child_input_sha256 is None:
            raise ValueError("child operation requires pinned effective input")
        new_params, new_includes, new_analyses, new_static = partition_amplifier_input(
            evidence.child_input, expected_sha256=binding.child_input_sha256
        )
        new_fixed, new_options = _amp_pm0_options(new_static, baseline=False)
        if (
            (new_params, new_options) != (child_circuit.parameters, child_circuit.pm0_options)
            or new_includes != [(model.path, model.section) for model in binding.model_includes]
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
        status, terminal, report = _width_report(child, conditions, reader)
        if status != "NOT_OBSERVED":
            reason = (
                "retained_result_unavailable"
                if status == "SUCCEEDED"
                else "retained_operation_not_succeeded"
            )
        if report is not None:
            if report.execution_input_sha256 != hashlib.sha256(evidence.child_input).hexdigest():
                raise ValueError("child report effective input differs")
            if model_comparison == "MATCHED":
                value = _amp_child_metric(report, reader)
                reason = "registered_measurement_unavailable" if value is None else None
            else:
                reason = "historical_model_equivalence_unavailable"
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
        model_comparison=model_comparison,
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
        dc_alias, ac_alias = binding.dc.baseline_include_alias, binding.ac.baseline_include_alias
        if (
            dc_alias is not None
            and ac_alias is not None
            and dc_alias.historical_equivalence_receipt_sha256
            == ac_alias.historical_equivalence_receipt_sha256
        ):
            raise ValueError("distinct archived DC and AC model receipts required")
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
        old_params, old_includes, old_analyses, old_static = partition_amplifier_input(
            baseline_input, expected_sha256=plan.baseline.netlist_sha256
        )
        new_params, new_includes, _, new_static = partition_amplifier_input(
            candidate_input, expected_sha256=netlist.artifact_sha256
        )
        if (
            old_params.get("VBIASN") != "0.32"
            or old_params.get("VBIASP") != "0.702"
            or len(old_analyses) != 1
            or old_analyses[0][0] != "dc"
        ):
            raise ValueError("center amplifier DC operating point required")
        if dc.baseline_input != baseline_input:
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


class FreshAmplifierOperationBinding(VariableModel):
    operation_id: OperationId
    plan_sha256: Digest
    input_sha256: Digest | None


class FreshAmplifierRevisionBinding(VariableModel):
    revision_sha256: Digest
    testbench_revision_sha256: Digest
    source_tree_sha256: Digest
    ade_state_sha256: Digest
    dc: FreshAmplifierOperationBinding | None = None
    ac: FreshAmplifierOperationBinding | None = None


class FreshAmplifierWidthBinding(VariableModel):
    change_plan_sha256: Digest
    readback_sha256: Digest
    canonical_model_include: ModelInclude
    diagnostic_model_closure_sha256: Digest
    diagnostic_model_receipt_sha256: Digest
    baseline: FreshAmplifierRevisionBinding
    candidate: FreshAmplifierRevisionBinding


@dataclass(frozen=True)
class VerifiedAmplifierCopyChangeEvidence:
    """Host-pinned outputs of the stock fixed writer and its same-ID lookup."""

    original: bytes
    original_sha256: Digest
    replay: bytes
    replay_sha256: Digest
    receipt: bytes
    receipt_sha256: Digest


class _ReadbackConditions(TypedDict):
    plan_sha256: Digest
    target_sha256: Digest
    fixed_conditions_sha256: Digest


def project_verified_amplifier_copy_change(
    plan: ChangePlan,
    request: PmosDefaultChangeRequest,
    evidence: VerifiedAmplifierCopyChangeEvidence,
    *,
    baseline_input: bytes,
    candidate_input: bytes,
) -> ChangeReadback:
    """Bind the stock VERIFIED change to a comparison without admitting analysis."""
    from cadence_mcp_bridge.amplifier_pm0_default import _pm0_frame
    from cadence_mcp_bridge.amplifier_pm0_service import _Receipt

    try:
        original = PmosDefaultChangeResult.model_validate_json(
            _canonical(_pinned_json(evidence.original, evidence.original_sha256))
        )
        replay = PmosDefaultChangeResult.model_validate_json(
            _canonical(_pinned_json(evidence.replay, evidence.replay_sha256))
        )
        for writer in (original, replay):
            writer.check_registered_scope(
                request, registered_plan=plan, registered_scope_sha256=request.expected_scope_sha256
            )
        receipt = _Receipt.model_validate_json(
            _canonical(_pinned_json(evidence.receipt, evidence.receipt_sha256))
        )
        view = receipt.saved_view_tree_sha256
        frame, reopened_properties = _pm0_frame(baseline=False)
        if (
            not isinstance(plan.target, MosWidthTarget)
            or plan.target.instance.instance_path != "PM0"
            or original.outcome != "VERIFIED"
            or original.replayed
            or original.dispatched_this_call is not True
            or replay
            != original.model_copy(update={"replayed": True, "dispatched_this_call": False})
            or (receipt.operation_id, receipt.plan_sha256, receipt.scope_sha256)
            != (original.operation_id, original.plan_sha256, original.scope_sha256)
            or view != receipt.reopened_view_tree_sha256
            or view != receipt.netlisted_view_tree_sha256
            or view != original.observed_revision_sha256
            or view != original.observed_testbench_revision_sha256
            or view == receipt.owned_before_view_tree_sha256
            or receipt.source_preservation_sha256 != original.source_preservation_sha256
            or receipt.reopen_receipt_sha256 != original.reopen_receipt_sha256
            or receipt.netlist_receipt_sha256 != original.netlist_receipt_sha256
            or receipt.netlist_sha256 != original.netlist_sha256
            or list(receipt.reopen_frame) != frame
        ):
            raise ValueError("verified fixed writer evidence differs")
        projection = project_netlist_change(plan, baseline_input, candidate_input)
        if projection.artifact_sha256 != receipt.netlist_sha256:
            raise ValueError("verified fixed writer netlist differs")
        reference = plan.baseline
        _, _, _, baseline_statements = partition_amplifier_input(
            baseline_input, expected_sha256=reference.netlist_sha256
        )
        _, baseline_properties = _amp_pm0_options(baseline_statements, baseline=True)
        # Spectre emits the fixed single-finger width as w, not the OA fw field.
        baseline_properties["fw"] = baseline_properties["w"].strip("()")
        names = tuple(change.before.property_name for change in plan.allowed_derived)
        common = _ReadbackConditions(
            plan_sha256=plan.plan_sha256,
            target_sha256=canonical_digest(plan.target),
            fixed_conditions_sha256=reference.fixed_conditions_sha256,
        )
        baseline = Readback(
            **common,
            stage="baseline",
            revision=reference.revision,
            revision_sha256=reference.revision_sha256,
            testbench_revision_sha256=reference.testbench_revision_sha256,
            artifact_sha256=reference.netlist_sha256,
            value=plan.old,
            derived=tuple(
                DerivedValue(property_name=name, value=baseline_properties[name]) for name in names
            ),
            mos_fingers=1,
            mos_multiplicity=1,
        )
        reopened = Readback(
            **common,
            stage="reopened",
            revision=plan.candidate_revision,
            revision_sha256=view,
            testbench_revision_sha256=view,
            artifact_sha256=receipt.reopen_receipt_sha256,
            value=plan.expected,
            derived=tuple(
                DerivedValue(property_name=name, value=reopened_properties[name]) for name in names
            ),
            mos_fingers=1,
            mos_multiplicity=1,
        )
        netlist = Readback(
            **common,
            stage="netlist",
            revision=plan.candidate_revision,
            revision_sha256=view,
            testbench_revision_sha256=view,
            artifact_sha256=projection.artifact_sha256,
            value=projection.value,
            derived=projection.derived,
        )
        result = verify_change_readback(plan, baseline=baseline, reopened=reopened, netlist=netlist)
        if result.status != "MATCHED":
            raise ValueError("verified fixed writer projections do not match")
        return result
    except (KeyError, TypeError, ValueError):
        raise OperationRejected("verified_amplifier_copy_change_evidence_mismatch") from None


@dataclass(frozen=True)
class AmplifierRetainedPolicyStep:
    """An independently pinned applied policy record and its host receipt."""

    apply_receipt: bytes
    apply_receipt_sha256: Digest
    policy_record: bytes
    policy_record_sha256: Digest


@dataclass(frozen=True)
class FreshAmplifierStorageSuccessorEvidence:
    """Raw profiles and independently pinned native storage migration artifacts."""

    baseline_profile: bytes
    candidate_profile: bytes
    v7_apply_receipt: bytes
    successor_apply_receipt: bytes
    successor_apply_receipt_sha256: Digest
    successor_policy_record: bytes
    successor_policy_record_sha256: Digest
    policy_steps: tuple[AmplifierRetainedPolicyStep, ...] = ()


@dataclass(frozen=True)
class FreshAmplifierOwnedCopyEvidence:
    """Local receipt bytes for the explicitly mapped ADE state and technology library."""

    baseline_ade_state: str
    candidate_ade_state: str
    copy_receipt: bytes
    copy_receipt_sha256: Digest
    preservation_receipt: bytes
    technology_receipt: bytes
    technology_receipt_sha256: Digest
    registration_receipt: bytes
    registration_receipt_sha256: Digest


@dataclass(frozen=True)
class Amplifier5656AcSuccessorEvidence:
    scope: bytes
    dc_context: ExecutionContext


@dataclass(frozen=True)
class SavedAmplifier5656Evidence:
    """Original saved writer and the exact C1 export and compiled-revision pins."""

    writer_request: bytes
    writer_request_sha256: Digest
    writer: VerifiedAmplifierCopyChangeEvidence
    preflight: bytes
    export_receipt: bytes
    export_receipt_sha256: Digest
    export_custody: bytes
    export_custody_sha256: Digest
    runtime_manifest_sha256: Digest
    runtime_registration_sha256: Digest
    dc_native_result: bytes | None = None
    ac_native_result: bytes | None = None
    export_dependency_observation: bytes | None = None
    ac_successor: Amplifier5656AcSuccessorEvidence | None = None


@dataclass(frozen=True)
class _FreshAmplifierCopyRoute:
    ade_state: str
    baseline_ade_state: str
    technology: dict[str, str]
    export: dict[str, Any] | None = None
    registration: dict[str, Any] | None = None
    saved_source: SavedAmplifier5656Evidence | None = None
    registered_library_tree_sha256: Digest | None = None


def _fresh_amplifier_owned_copy(
    evidence: FreshAmplifierOwnedCopyEvidence,
    binding: FreshAmplifierWidthBinding,
    diagnostic_sha256: Digest,
) -> tuple[_FreshAmplifierCopyRoute, _FreshAmplifierCopyRoute]:
    export = _pinned_json(evidence.copy_receipt, evidence.copy_receipt_sha256)
    preserved = _pinned_json(evidence.preservation_receipt, binding.diagnostic_model_receipt_sha256)
    technology = _pinned_json(evidence.technology_receipt, evidence.technology_receipt_sha256)
    registration = _pinned_json(evidence.registration_receipt, evidence.registration_receipt_sha256)
    if (
        not evidence.baseline_ade_state
        or not evidence.candidate_ade_state
        or evidence.baseline_ade_state == evidence.candidate_ade_state
        or export["status"] != "4497_INPUTS_EXPORTED"
        or any(
            type(export[key]) is not int or export[key] != 0
            for key in ("ocean_calls", "reservations", "simulations")
        )
        or export["original_state_sha256"] != binding.baseline.ade_state_sha256
        or export["source_state_sha256"] != binding.candidate.ade_state_sha256
        or export["source_cell_sha256"] != binding.candidate.source_tree_sha256
        or preserved["status"] != "RECONCILED_READ_ONLY"
        or preserved["phase"] != "child-netlist"
        or preserved["input_sha256"] != diagnostic_sha256
        or preserved["before"] != preserved["after"]
        or preserved["after"]["view_tree"] != binding.candidate.revision_sha256
        or preserved["after"]["view_tree"] != binding.candidate.testbench_revision_sha256
        or preserved["after"]["view_content"] != export["view_content_sha256"]
        or preserved["after"]["library_tree"] != export["original_library_sha256"]
        or any(
            type(preserved[key]) is not int or preserved[key] != 0
            for key in ("reservations", "simulations")
        )
        or technology["status"] != "FIXED_TECH_DEPENDENCY_SNAPSHOT_OBSERVED"
        or technology["technology"] != "cdsDefTechLib"
        or any(
            type(technology[key]) is not int or technology[key] != 0
            for key in (
                "config_content_reads",
                "ocean_calls",
                "reservations",
                "simulations",
                "writes",
            )
        )
        or registration["status"] != "LOCAL_COMPILER_ONLY"
        or registration["execution_authorized"] is not False
        or registration["source_revision"] != preserved["after"]["revision"]
        or registration["export_proof_sha256"] != evidence.copy_receipt_sha256
        or registration["netlist_proof_sha256"] != binding.diagnostic_model_receipt_sha256
    ):
        raise ValueError("fresh amplifier owned-copy receipts differ")
    dependency = {
        "name": technology["technology"],
        "path": technology["technology_path"],
        "tree_sha256": technology["technology_tree_sha256"],
    }
    center = _FreshAmplifierCopyRoute(
        evidence.baseline_ade_state, evidence.baseline_ade_state, dependency
    )
    child = _FreshAmplifierCopyRoute(
        evidence.candidate_ade_state, evidence.baseline_ade_state, dependency, export, registration
    )
    return center, child


def _fresh_amplifier_copy_route(
    proof: _FreshAmplifierCopyRoute,
    operation: PmosDcOperation,
    route: dict[str, Any],
    library: dict[str, Any],
    libraries: list[dict[str, Any]],
    profile: dict[str, Any],
    mode: Literal["dc", "ac"],
) -> list[dict[str, Any]]:
    ade = profile["binding"]["ade"]
    if ade["state"] != proof.ade_state:
        raise ValueError("fresh amplifier ADE state differs from the recorded mapping")
    technology = [item for item in libraries if item["name"] == proof.technology["name"]]
    export, registration = proof.export, proof.registration
    if proof.saved_source is not None:
        saved = proof.saved_source
        plan = operation.plan
        if (
            export is None
            or len(technology) != 1
            or technology[0]["tree_sha256"] != proof.technology["tree_sha256"]
            or hashlib.sha256(_canonical(technology[0])).hexdigest() != _AMP_5656_TECHNOLOGY_SHA256
            or route["source_cell"] != export["library"] + "/Differential_Amplifier_TB2"
            or route["source_state"] != export["ade"]
            or library["path"] != export["library"]
            or library["tree_sha256"] != proof.registered_library_tree_sha256
            or (plan.request.design_id, plan.request.analysis_id)
            != (_AMP_5656_DESIGN, f"matched-{mode}")
            or plan.runner_sha256 != saved.runtime_manifest_sha256
            or hashlib.sha256(operation.runtime_registration).hexdigest()
            != saved.runtime_registration_sha256
        ):
            raise ValueError("5656 registered export differs from executed route")
        return [item for item in libraries if item != technology[0]]
    if export is None or registration is None:
        if technology:
            raise ValueError("fresh amplifier Center already registers the added technology")
        return libraries
    plan = operation.plan
    compiled = operation.runtime_registration
    if (
        technology != [proof.technology]
        or route["source_cell"] != export["source_cell"]
        or route["source_state"] != export["source_state"]
        or library["path"] != export["library"]
        or library["tree_sha256"] != export["library_sha256"]
        or registration["successor"] != plan.runner_sha256
        or registration["profile_sha256"] != plan.environment_sha256
        or registration["design_sha256"] != plan.design_sha256
        or registration["design_id"] != plan.request.design_id
        or registration["compiled_file_inventory"]["registration.json"]
        != {"bytes": len(compiled), "sha256": hashlib.sha256(compiled).hexdigest()}
        or registration["controls_only"][mode]["static"] != route["ade"]["static_statements_sha256"]
    ):
        raise ValueError("fresh amplifier owned-copy registration differs")
    ade["state"] = proof.baseline_ade_state
    return [item for item in libraries if item != proof.technology]


_AMP_CENTER_STORAGE_BYTES = 17_179_869_184
_AMP_CENTER_PROFILE_SHA256 = "6e1485b39561d0cd3edcaef89908af13d4fca56f25b442c305ed71ba5aec2b82"
_AMP_V7_APPLY_SHA256 = "ec19cdc22084c5ad99b73ac056ec0020772b77eb9f8290cd8044e794b7241458"
_AMP_V7_DOMAIN_ANCHOR_SHA256 = "cfd037cd4db24359614baa9f5e465bd24176f34151ee252e462016cdd2a6ef36"
_AMP_4497_STORAGE_BYTES = 17_632_854_016
_AMP_4497_STORAGE_POLICY_SHA256 = "939d57d3f038c90d3b3401315c15f8a76fb2c3c6b96410b4dfcf2db5b67c9ad5"
_AMP_4497_STORAGE_BASELINE = {
    "campaign_id": "AUTO-PHASE-01",
    "count": 140,
    "result_reserved_bytes": 17_331_912_704,
}
_AMP_5656_PREFLIGHT_SHA256 = "367a0dc7172680179a0a4f736bcb9402e1f81c77707d4ec1bfd1fb29402cd9e9"
_AMP_5656_CLOSURE_SHA256 = "382c63b2bb6b444336801b21ac1667c36f681d706de52d871ba062706c6e7fd7"
_AMP_5656_TECHNOLOGY_SHA256 = "363f7658940faded59bbddc3b0ef266c0995eb19e1e15e26568788fc09ad2561"
_AMP_5656_WRITER = "5656c6fb-287c-41a6-b891-057f4ef4e0b2"
_AMP_5656_EXPORT = "1221e5d5-0e11-4bc9-a0bf-592278573f7a"
_AMP_5656_DEPENDENCY_OBSERVATION_SHA256 = (
    "59d926ffa9721c4780e3c5c6e6e164d8867f70a6f2fa6515277b63c733f99b2f"
)
_AMP_5656_R2_SETTINGS_SHA256 = "08921dbdf92862b22b62842984459b79d739552ceab1f8d2312379208d655939"
_AMP_5656_R2_CONTEXT_SHA256 = "3e373473f8445335c8437aa00e8b20317c3385a5e894dae668b0c6c0bebf3b7b"
_AMP_5656_R3_CONTEXT_SHA256 = "d289b4fbba81e700c2486dfdbcf48dbd2942e9a513767b6b674df0b58ccfe6ca"
_AMP_5656_R3_SCOPE_SHA256 = "0a56fbe11267c0f11d25bdf81405e7f3394c9ad767a1dc07e2101cd1a1eaf3f1"
_AMP_5656_R3_RENEWED_CONTEXT_SHA256 = (
    "282163bfde8f3a89e2b6943607bc232ec0530a0b4478a3c61425e41f7b2adc54"
)
_AMP_5656_R3_RENEWED_SCOPE_SHA256 = (
    "f6d89e437ab453b8cf02da9c399cbe03b60a4e56b00dfc2e52e3f1226720516f"
)
_AMP_5656_FAILED_DC_ID = "97e9eef0-b49a-4113-9ebf-8ddcbd09438a"
_AMP_5656_FAILED_DC_PLAN = "4919b38c8e78fd7241541f0a3e4ee87c4440f7acf7ae87d4e270ee1b5cd4a991"
_AMP_5656_REVISION = "amp-pm0-user-mcp-1123-r1"
_AMP_5656_DESIGN = "amp-pm0-auto120-5656"
_AMP_5656_PRIOR_RECORDS = (
    "b1133fb68b9fbe9a384294c5ae5862264d1766b60a9b9e479e9b5e325e002016",
    "c32b0ff1bcc611cb5c6b3a4c10c053989f638c9ec31aeade9e7a12807c39f090",
)
_AMP_5656_CENTER_PINS = {
    "dc": (
        "a9a9d30d-b707-4f14-a5af-3470391282ba",
        "1197a69afea69704f1da27bf1da8a4dd54f2c5a348f8263f29208467ad5cb6c7",
        "e3a90d9c947e81d497b8c1fe973b0794d00cbaeef7b19bd031714b808bd984d8",
        "d41f8f2951ac8f0513ea52d59d29340c1ec6484b53074eda0777b4aaf74512ef",
        "ff29308606f87f12abeb4fd759bd0ad88dd2b3c6ecd427dd5aeb038d548daccf",
    ),
    "ac": (
        "69c5f785-1539-4939-a18d-a1e3850e25f3",
        "9f74f7b87b508489f97ce032dd29fb92e7416396fbf009f3821c48f1ec0c44f5",
        "a50cd9548615d41cdf5bf5c24f1e654f9075b39ea73afe6e42b41ec8720f5c11",
        "381871f210a04f8e2c34515b5ee321fb3b0e543a6e596c6aa216e6fca3cdf608",
        "018eb36c36113cd145181fd53ba6710bbeec1b96ffe34314f08b9f09303c12f7",
    ),
}
_AMP_5656_POLICY_STEPS = (
    (
        9,
        17_767_071_744,
        142,
        17_600_348_160,
        "4325facb94d3d26982950ebecfa22eb2594270de1cd7168a923d0cf27553ad19",
    ),
    (
        10,
        18_169_724_928,
        143,
        17_734_565_888,
        "f2f546514a2b2986de399a22f4c18cf05600c4391473ff0fb5a4d481e696da66",
    ),
)


def _fresh_amplifier_saved_source(
    evidence: SavedAmplifier5656Evidence,
    binding: FreshAmplifierWidthBinding,
    plan: ChangePlan,
    readback: ChangeReadback,
    baseline_input: bytes,
    candidate_input: bytes,
) -> tuple[_FreshAmplifierCopyRoute, _FreshAmplifierCopyRoute]:
    if (
        binding.diagnostic_model_receipt_sha256 != _AMP_5656_PREFLIGHT_SHA256
        or binding.diagnostic_model_closure_sha256 != _AMP_5656_CLOSURE_SHA256
    ):
        raise ValueError("5656 diagnostic model evidence differs")
    observed = _pinned_json(evidence.preflight, _AMP_5656_PREFLIGHT_SHA256)
    source = observed["source"]
    request = PmosDefaultChangeRequest.model_validate_json(
        _canonical(_pinned_json(evidence.writer_request, evidence.writer_request_sha256))
    )
    export = _pinned_json(evidence.export_receipt, evidence.export_receipt_sha256)
    custody = _pinned_json(evidence.export_custody, evidence.export_custody_sha256)
    copy = export["copy"]
    parent = observed["candidate_external_parent"]
    charged_bytes = export["charged_bytes_before_receipt"]
    if (
        request.operation_id != _AMP_5656_WRITER
        or evidence.writer.receipt_sha256 != source["durable_receipt_sha256"]
        or source["view_tree"] != binding.candidate.revision_sha256
        or source["view_tree"] != binding.candidate.testbench_revision_sha256
        or source["input_sha256"] != hashlib.sha256(candidate_input).hexdigest()
        or observed["status"] != "RESEARCH_1124_LIVE_READ_ONLY"
        or observed["candidate_parent_absent"] is not True
        or project_verified_amplifier_copy_change(
            plan,
            request,
            evidence.writer,
            baseline_input=baseline_input,
            candidate_input=candidate_input,
        )
        != readback
        or export["status"] != "AMP_5656_OWNED_EXPORT_VERIFIED"
        or export["operation"] != _AMP_5656_EXPORT
        or export["originals_preserved"] is not True
        or export["executed"] is not True
        or export["replayed"] is not False
        or type(charged_bytes) is not int
        or not 0 < charged_bytes <= 3 * 1024**2 - 16384
        or not re.fullmatch(r"[0-9a-f]{64}", export["scope"])
        or any(
            type(export[key]) is not int or export[key] != 0
            for key in ("ocean", "spectre", "reservations")
        )
        or export["exact_saved_input_sha256"] != source["input_sha256"]
        or copy["library"] != parent + "/" + source["library"].rsplit("/", 1)[-1]
        or copy["ade"] != parent + "/Candidate5656_ADE"
        or copy["library_content"] != source["library_content"]
        or copy["view_content"] != source["view_content"]
        or copy["cell_tree"] != binding.candidate.source_tree_sha256
        or copy["ade_tree"] != binding.candidate.ade_state_sha256
        or binding.baseline.source_tree_sha256 != observed["protected"]["archive_cell_tree_sha256"]
        or binding.baseline.ade_state_sha256 != observed["protected"]["archive_state_tree_sha256"]
        or _canonical(custody)
        != _canonical(
            {
                "status": "RESEARCH_1124_INPUTS_EXPORTED",
                "preflight_sha256": _AMP_5656_PREFLIGHT_SHA256,
                "saved_view_tree_sha256": source["view_tree"],
                "saved_view_content_sha256": source["view_content"],
                "copied_view_content_sha256": copy["view_content"],
                "source_library_content_sha256": source["library_content"],
                "copied_library_content_sha256": copy["library_content"],
                "source_cell": copy["library"] + "/Differential_Amplifier_TB2",
                "source_cell_sha256": copy["cell_tree"],
                "source_state": copy["ade"],
                "source_state_sha256": copy["ade_tree"],
                "ocean_calls": 0,
                "simulations": 0,
                "reservations": 0,
                "raw_receipt_sha256": evidence.export_receipt_sha256,
                "scope_sha256": export["scope"],
            }
        )
    ):
        raise ValueError("5656 saved writer or export evidence differs")
    technology = {
        "name": "cdsDefTechLib",
        "tree_sha256": observed["protected"]["technology_tree_sha256"],
    }
    registered_tree = _5656_export_library_tree(evidence.export_dependency_observation, copy)
    return (
        _FreshAmplifierCopyRoute("state1", "state1", technology),
        _FreshAmplifierCopyRoute(
            "state1",
            "state1",
            technology,
            export=copy,
            saved_source=evidence,
            registered_library_tree_sha256=registered_tree,
        ),
    )


def _5656_export_library_tree(raw: bytes | None, exported: dict[str, Any]) -> str:
    strict = exported["library_tree"]
    if not isinstance(strict, str) or re.fullmatch(r"[0-9a-f]{64}", strict) is None:
        raise ValueError("5656 original export library digest invalid")
    if raw is None:
        return strict
    observed = _pinned_json(raw, _AMP_5656_DEPENDENCY_OBSERVATION_SHA256)
    dependency = observed["dependency_tree_sha256"]
    mismatches = [row for row in observed["libraries"] if row["matches"] is not True]
    observation_scope = {
        **{key: observed[key] for key in ("operation_id", "plan_sha256", "counter")},
        **{
            key: exported[key]
            for key in (
                "library",
                "library_tree",
                "library_content",
                "cell_tree",
                "ade",
                "ade_tree",
            )
        },
    }
    if (
        observed["status"] != "EXPORT_DEPENDENCY_PIN_VERIFIED"
        or observed["scope_sha256"] != hashlib.sha256(_canonical(observation_scope)).hexdigest()
        or observed["strict_tree_sha256"] != strict
        or observed["content_sha256"] != exported["library_content"]
        or not isinstance(dependency, str)
        or dependency == strict
        or re.fullmatch(r"[0-9a-f]{64}", dependency) is None
        or observed["native_job_exists"] is not False
        or any(
            type(observed[key]) is not int or observed[key] != 0
            for key in ("ocean_calls", "simulations", "reservations", "vm_writes")
        )
        or _canonical(mismatches)
        != _canonical(
            [
                {
                    "name": exported["library"].rsplit("/", 1)[-1],
                    "registered_tree_sha256": strict,
                    "observed_tree_sha256": dependency,
                    "matches": False,
                }
            ]
        )
    ):
        raise ValueError("5656 export dependency observation differs")
    return dependency


def _fresh_amplifier_storage_successor(
    evidence: FreshAmplifierStorageSuccessorEvidence,
    baseline: OperationPlan,
    candidate: OperationPlan,
    *,
    saved_source: bool = False,
) -> None:
    end = _AMP_5656_POLICY_STEPS[-1][1] if saved_source else _AMP_4497_STORAGE_BYTES
    old = _pinned_json(evidence.baseline_profile, baseline.environment_sha256)
    new = _pinned_json(evidence.candidate_profile, candidate.environment_sha256)
    EnvironmentProfile.model_validate_json(_canonical(old))
    EnvironmentProfile.model_validate_json(_canonical(new))
    old_ceiling = old["limits"].pop("result_reserved_bytes")
    new_ceiling = new["limits"].pop("result_reserved_bytes")
    if (
        baseline.environment_sha256 != _AMP_CENTER_PROFILE_SHA256
        or _canonical(old) != _canonical(new)
        or (old_ceiling, new_ceiling) != (_AMP_CENTER_STORAGE_BYTES, end)
        or old["limits"]["spectre_attempts"] != 500
        or len(evidence.policy_steps) != (2 if saved_source else 0)
        or (
            saved_source
            and (
                evidence.successor_policy_record_sha256,
                evidence.policy_steps[0].policy_record_sha256,
            )
            != _AMP_5656_PRIOR_RECORDS
        )
    ):
        raise ValueError("fresh amplifier profiles differ outside the approved storage ceiling")

    v7 = _pinned_json(evidence.v7_apply_receipt, _AMP_V7_APPLY_SHA256)
    v8 = AmplifierRetainedPolicyStep(
        evidence.successor_apply_receipt,
        evidence.successor_apply_receipt_sha256,
        evidence.successor_policy_record,
        evidence.successor_policy_record_sha256,
    )
    steps = [
        (
            8,
            _AMP_4497_STORAGE_BYTES,
            _AMP_4497_STORAGE_BASELINE,
            _AMP_4497_STORAGE_POLICY_SHA256,
            v8,
        )
    ]
    for (version, ceiling, count, reserved, policy), step in zip(
        _AMP_5656_POLICY_STEPS, evidence.policy_steps, strict=saved_source
    ):
        steps.append(
            (
                version,
                ceiling,
                dict(campaign_id="AUTO-PHASE-01", count=count, result_reserved_bytes=reserved),
                policy,
                step,
            )
        )
    prior = v7["policy_receipt_sha256"]
    root_sha = hashlib.sha256(old["paths"]["managed_root"].encode()).hexdigest()
    for version, ceiling, ledger, policy, step in steps:
        _check_amplifier_policy_step(
            step,
            v7,
            version=version,
            ceiling=ceiling,
            ledger=ledger,
            policy=policy,
            prior=prior,
            root_sha=root_sha,
            domain=baseline.resource_domain_sha256,
        )
        prior = step.policy_record_sha256


def _check_amplifier_policy_step(
    step: AmplifierRetainedPolicyStep,
    v7: dict[str, Any],
    *,
    version: int,
    ceiling: int,
    ledger: dict[str, Any],
    policy: str,
    prior: str,
    root_sha: str,
    domain: str,
) -> None:
    applied = _pinned_json(step.apply_receipt, step.apply_receipt_sha256)
    record = _pinned_json(step.policy_record, step.policy_record_sha256)
    if (
        not isinstance(applied, dict)
        or set(applied) != set(v7)
        or applied["status"] != f"RETAINED_RESULT_LIMIT_V{version}_APPLIED_NO_LEDGER_CHANGE"
        or type(applied["created"]) is not bool
        or any(
            applied[key] is not False
            for key in ("execution_authorized", "ledger_modified", "ledger_initialized")
        )
        or type(applied["reservation_cost"]) is not int
        or applied["reservation_cost"] != 0
        or type(applied["result_ceiling_bytes"]) is not int
        or applied["result_ceiling_bytes"] != ceiling
        or applied["policy_receipt_sha256"] != step.policy_record_sha256
        or not isinstance(record, dict)
        or set(record)
        != {
            "schema_version",
            "kind",
            "root_sha256",
            "resource_domain_sha256",
            "identity_manifest_sha256",
            "prior_receipt_sha256",
            "policy_sha256",
            "baseline",
            "plan_sha256",
            "operator_authority",
        }
        or step.policy_record != _canonical(record)
        or type(record["schema_version"]) is not int
        or record["schema_version"] != version
        or record["kind"] != f"EXPLICIT_RETAINED_RESULT_LIMIT_V{version}"
        or record["prior_receipt_sha256"] != prior
        or record["resource_domain_sha256"] != domain
        or record["root_sha256"] != root_sha
        or record["plan_sha256"] != applied["plan_sha256"]
        or record["policy_sha256"] != applied["policy_sha256"]
        or record["policy_sha256"] != policy
        or _canonical(record["baseline"]) != _canonical(ledger)
        or not isinstance(record["operator_authority"], str)
        or not 1 <= len(record["operator_authority"]) <= 512
        or any(ord(char) < 32 for char in record["operator_authority"])
        or not re.fullmatch(r"[0-9a-f]{64}", applied["ledger_sha256"])
        or not re.fullmatch(r"[0-9a-f]{64}", record["plan_sha256"])
        or record["identity_manifest_sha256"] != _AMP_V7_DOMAIN_ANCHOR_SHA256
    ):
        raise ValueError("fresh amplifier retained storage successor receipt differs")


def associate_persisted_amplifier_bias(
    saved_width: FreshAmplifierRevisionBinding,
    plan: ChangePlan,
    readback: ChangeReadback,
    *,
    expected_plan_sha256: Digest,
    expected_readback_sha256: Digest,
    baseline_input: bytes | None = None,
    candidate_input: bytes | None = None,
) -> ChangeReadback:
    """Bind independently captured ADE and Netlist observations to the saved width.

    The caller authenticates the native observations before pinning their typed
    readback. Their association does not change any retained operation's ADE state.
    """
    try:
        checked = verify_change_readback(
            plan, baseline=readback.baseline, reopened=readback.reopened, netlist=readback.netlist
        )
        if (
            plan.plan_sha256 != expected_plan_sha256
            or canonical_digest(readback) != expected_readback_sha256
            or not isinstance(plan.target, AdeTarget)
            or plan.target.schematic_revision_sha256 != saved_width.revision_sha256
            or (plan.target.binding.logical_id, plan.target.binding.cadence_binding)
            != ("vbiasn", "VBIASN")
            or plan.baseline.testbench_revision_sha256 != saved_width.testbench_revision_sha256
            or plan.baseline.revision_sha256 != saved_width.ade_state_sha256
            or plan.old.normalized != ("0.32", "V")
            or plan.requested.normalized != ("0.321", "V")
            or plan.expected.normalized != ("0.321", "V")
            or checked != readback
        ):
            raise ValueError("persisted Bias plan or readback differs from the saved width")
        if checked.status == "MATCHED":
            if baseline_input is None or candidate_input is None or checked.netlist is None:
                raise ValueError("matched persisted Bias requires both observed Netlists")
            projection = project_netlist_change(plan, baseline_input, candidate_input)
            if (
                projection.artifact_sha256 != checked.netlist.artifact_sha256
                or projection.value.normalized != checked.netlist.value.normalized
                or projection.derived != checked.netlist.derived
            ):
                raise ValueError("persisted Bias Netlist differs from readback")
            parameters, _, _, _ = partition_input(baseline_input)  # type: ignore[no-untyped-call]
            if parameters.get("VBIASP") != "0.702":
                raise ValueError("persisted Bias fixed VBIASP differs")
    except (TypeError, ValueError):
        raise OperationRejected("candidate_persisted_amplifier_bias_evidence_mismatch") from None
    return checked


@dataclass(frozen=True)
class FreshAmplifierOperation:
    operation: PmosDcOperation
    effective_input: bytes | None


@dataclass(frozen=True)
class FreshAmplifierWidthAnalysis:
    baseline: FreshAmplifierOperation | None = None
    candidate: FreshAmplifierOperation | None = None


class FreshAmplifierMeasurement(VariableModel):
    operation: NativeOperationQuery | None
    terminal_sha256: Digest | None
    status: OperationPhase | Literal["NOT_RUN", "NOT_OBSERVED"]
    report: ResultReport | None
    value: float | None
    reason: str | None


class FreshAmplifierAnalysisPair(VariableModel):
    analysis: Literal["dc", "ac"]
    metric_id: Literal["dc-supply-power-grid-v2", "gain-10hz-grid-v1"]
    unit: Literal["W", "dB"]
    baseline: FreshAmplifierMeasurement
    candidate: FreshAmplifierMeasurement


class FreshAmplifierWidthPair(VariableModel):
    change_plan_sha256: Digest
    binding_sha256: Digest
    readback: ChangeReadback
    dc: FreshAmplifierAnalysisPair
    ac: FreshAmplifierAnalysisPair
    goals: Literal["GOALS_NOT_PROVIDED"] = "GOALS_NOT_PROVIDED"
    selected_candidate_id: Literal[None] = None
    execution_authorized: Literal[False] = False


def _fresh_amplifier_reader(
    mode: Literal["dc", "ac"], reader: GenericReaderRegistration, static: list[str]
) -> None:
    selectors = {node.logical_id: node.selector for node in reader.nodes}
    if mode == "dc":
        top_level = {}
        in_subcircuit = False
        for line in static:
            name = line.split()[0]
            if line.startswith(("subckt ", "inline subckt ")):
                in_subcircuit = True
            elif name == "ends":
                in_subcircuit = False
            elif not in_subcircuit and name in ("V0", "V5"):
                if name in top_level:
                    raise ValueError("ambiguous fresh amplifier supply instance")
                top_level[name] = line
        for source_id, instance, node in (("vdd", "V0", "VDD"), ("vss", "V5", "VSS")):
            line = top_level[instance]
            (source,) = (s for s in reader.sources if s.source_id == source_id)
            if (
                re.match(rf"{instance} \({node} 0\) vsource(?: |$)", line) is None
                or source.role != "supply"
                or source.current_selector != f"/{instance}/PLUS"
                or selectors.get(source.positive_node or "") != f"/{node}"
                or source.negative_node is not None
            ):
                raise ValueError("fresh amplifier supply orientation differs")
        if {s.source_id for s in reader.sources if s.role == "supply"} != {"vdd", "vss"}:
            raise ValueError("fresh amplifier supply inventory differs")
        return
    transfer = reader.transfer
    if (
        transfer is None
        or tuple(
            selectors.get(signal or "")
            for signal in (
                transfer.positive_input,
                transfer.negative_input,
                transfer.positive_output,
                transfer.negative_output,
            )
        )
        != ("/Vp", "/Vm", "/Vop", "/Vom")
        or "10" not in transfer.gain_frequencies_hz
    ):
        raise ValueError("fresh amplifier differential measurement differs")


def _fresh_amplifier_metric(
    report: ResultReport, reader: GenericReaderRegistration, ade: AdeExecutionRegistration
) -> float | None:
    if ade.inputs.analysis == "ac":
        axes = tuple(float(format(axis, ".16g")) for axis in _ac_axis(ade.inputs))
        (index,) = _sample_indices(("10",), axes)
        gains = [
            metric
            for metric in report.metrics
            if metric.kind == "voltage_gain_db"
            and metric.frequency_hz is not None
            and _matches_ac_axis(metric.frequency_hz, axes, index)
        ]
        if not gains:
            return None
        (gain,) = gains
        if gain.signal_id is not None or gain.sample_count is not None:
            raise ValueError("fresh amplifier gain is not a point measurement")
        return gain.value

    sources = {source.source_id: source.role for source in reader.sources}
    seen = set()
    for metric in report.metrics:
        if metric.sample_count is not None:
            raise ValueError("fresh amplifier DC report contains a sampled metric")
        if metric.kind == "delivered_power":
            if metric.signal_id not in sources or metric.source_role != sources[metric.signal_id]:
                raise ValueError("fresh amplifier DC power is not registered")
            if metric.signal_id in seen:
                raise ValueError("duplicate fresh amplifier DC power")
            seen.add(metric.signal_id)
    return _amp_child_metric(report, reader, physical_sources=("V0", "V5"))


def _fresh_amplifier_measurement(
    mode: Literal["dc", "ac"],
    operation: PmosDcOperation,
    conditions: ReportConditions,
    reader: GenericReaderRegistration,
    ade: AdeExecutionRegistration,
    static: list[str],
    input_sha256: str,
) -> FreshAmplifierMeasurement:
    _fresh_amplifier_reader(mode, reader, static)
    status, terminal, report = _width_report(operation, conditions, reader)
    value = None
    reason: str | None = {
        "NOT_OBSERVED": "retained_record_unavailable",
        "SUCCEEDED": "retained_result_unavailable",
    }.get(status, "retained_operation_not_succeeded")
    if report is not None:
        if report.execution_input_sha256 != input_sha256:
            raise ValueError("fresh amplifier report input differs")
        value = _fresh_amplifier_metric(report, reader, ade)
        reason = "registered_measurement_unavailable" if value is None else None
    return FreshAmplifierMeasurement(
        operation=operation.query,
        terminal_sha256=terminal,
        status=status,
        report=report,
        value=value,
        reason=reason,
    )


@dataclass(frozen=True)
class PersistedBiasExportEvidence:
    """Independently pinned export and policy evidence for one retained comparison."""

    readback: ChangeReadback
    export: bytes
    export_sha256: Digest
    policy_receipt: bytes
    policy_receipt_sha256: Digest
    baseline_profile: bytes
    candidate_profile: bytes
    reopened_receipt: bytes
    persistence_baseline: FreshAmplifierRevisionBinding
    plan: ChangePlan
    plan_sha256: Digest
    readback_sha256: Digest
    baseline_input: bytes
    candidate_input: bytes
    baseline_receipt: bytes


def _persisted_bias_export(
    evidence: PersistedBiasExportEvidence,
    saved_width: FreshAmplifierRevisionBinding,
    baseline: OperationPlan,
    candidate: OperationPlan,
    mode: Literal["dc", "ac"],
) -> dict[str, Any]:
    export = _pinned_json(evidence.export, evidence.export_sha256)
    policy = _pinned_json(evidence.policy_receipt, evidence.policy_receipt_sha256)
    old_profile = _pinned_json(evidence.baseline_profile, baseline.environment_sha256)
    new_profile = _pinned_json(evidence.candidate_profile, candidate.environment_sha256)
    old_ceiling = old_profile["limits"].pop("result_reserved_bytes")
    new_ceiling = new_profile["limits"].pop("result_reserved_bytes")
    persistence_baseline = evidence.persistence_baseline
    if (
        persistence_baseline.revision_sha256 != saved_width.revision_sha256
        or persistence_baseline.testbench_revision_sha256 != saved_width.testbench_revision_sha256
        or persistence_baseline.source_tree_sha256 != saved_width.source_tree_sha256
        or persistence_baseline.ade_state_sha256 == saved_width.ade_state_sha256
    ):
        raise ValueError("persisted Bias baseline differs from the retained physical source")
    readback = associate_persisted_amplifier_bias(
        persistence_baseline,
        evidence.plan,
        evidence.readback,
        expected_plan_sha256=evidence.plan_sha256,
        expected_readback_sha256=evidence.readback_sha256,
        baseline_input=evidence.baseline_input,
        candidate_input=evidence.candidate_input,
    )
    if (
        readback.status != "MATCHED"
        or readback.baseline is None
        or readback.reopened is None
        or readback.reopened.value.normalized != ("0.321", "V")
        or readback.reopened.schematic_revision_sha256 != saved_width.revision_sha256
        or readback.reopened.testbench_revision_sha256 != saved_width.testbench_revision_sha256
        or export["status"] != "CANDIDATE321_EXTERNAL_INPUTS_VERIFIED"
        or export["physical_oa_sha256"] != saved_width.revision_sha256
        or export["source_owned_state_tree_sha256"] != readback.reopened.revision_sha256
        or export["state_tree_sha256"] == export["source_owned_state_tree_sha256"]
        or any(export[key] != 0 for key in ("route_changes", "simulations", "reservations"))
        or old_profile != new_profile
        or (old_ceiling, new_ceiling) != (17179869184, 17381195776)
        or policy["status"] != "RETAINED_RESULT_LIMIT_V7_APPLIED_NO_LEDGER_CHANGE"
        or policy["result_ceiling_bytes"] != new_ceiling
        or policy["ledger_modified"] is not False
    ):
        raise ValueError("persisted Bias export or policy successor differs")
    for raw in (evidence.baseline_input, evidence.candidate_input):
        _, _, analyses, _ = partition_input(raw)  # type: ignore[no-untyped-call]
        if len(analyses) != 1 or analyses[0][0] != mode:
            raise ValueError("persisted Bias Netlist analysis differs")
    center = _pinned_json(evidence.baseline_receipt, readback.baseline.artifact_sha256)
    reopened = _pinned_json(evidence.reopened_receipt, readback.reopened.artifact_sha256)
    if (
        center["phase"] != "center-reopen"
        or center["center_ade_tree_sha256"] != persistence_baseline.ade_state_sha256
        or center["physical_oa_sha256"] != saved_width.revision_sha256
        or 'C1_AMP_ADE_VAR|LOADED|"VBIASN"|"0.32"' not in center["rows"]
        or 'C1_AMP_ADE_VAR|LOADED|"VBIASP"|"0.702"' not in center["rows"]
        or reopened["phase"] != "bias-reopen"
        or reopened["candidate_ade_tree_sha256"] != readback.reopened.revision_sha256
        or reopened["candidate_ade_content_sha256"] != export["state_content_sha256"]
        or reopened["physical_oa_sha256"] != saved_width.revision_sha256
        or 'C1_AMP_ADE_VAR|LOADED|"VBIASN"|"0.321"' not in reopened["rows"]
        or 'C1_AMP_ADE_VAR|LOADED|"VBIASP"|"0.702"' not in reopened["rows"]
    ):
        raise ValueError("persisted Bias reopened content differs from the exported copy")
    return export  # type: ignore[no-any-return]


def associate_saved_width_bias_analysis(
    mode: Literal["dc", "ac"],
    baseline: FreshAmplifierOperation,
    candidate: FreshAmplifierOperation,
    *,
    saved_width: FreshAmplifierRevisionBinding,
    baseline_input_sha256: Digest,
    candidate_input_sha256: Digest,
    candidate_query: NativeOperationQuery,
    requested_bias: ChangeValue,
    export_evidence: PersistedBiasExportEvidence | None = None,
) -> FreshAmplifierAnalysisPair:
    """Compare an existing saved-width center to one separately registered bias point.

    The caller supplies independently pinned execution inputs and an authenticated
    saved-width binding. Each operation retains its own original runtime and grant.
    """
    try:
        center = baseline.operation
        changed = candidate.operation
        center_pin = saved_width.dc if mode == "dc" else saved_width.ac
        if (
            center_pin is None
            or (center.query.operation_id, center.query.expected_plan_sha256, baseline_input_sha256)
            != (center_pin.operation_id, center_pin.plan_sha256, center_pin.input_sha256)
            or center.query.operation_id == changed.query.operation_id
            or changed.query
            != NativeOperationQuery.model_validate_json(candidate_query.model_dump_json())
            or requested_bias.normalized[1] != "V"
        ):
            raise ValueError("saved-width bias operation identity differs")

        export = (
            None
            if export_evidence is None
            else _persisted_bias_export(
                export_evidence, saved_width, center.plan, changed.plan, mode
            )
        )
        measurements = []
        fixed_conditions = []
        for side, pin, bias, is_candidate in (
            (baseline, baseline_input_sha256, "0.32", False),
            (candidate, candidate_input_sha256, requested_bias.normalized[0], True),
        ):
            operation, raw = side.operation, side.effective_input
            if raw is None or hashlib.sha256(raw).hexdigest() != pin:
                raise ValueError("saved-width bias input digest differs")
            technology = None
            side_export = export if is_candidate else None
            if side_export is not None:
                technology = {
                    "name": "cdsDefTechLib",
                    "path": side_export["technology_path"],
                    "tree_sha256": side_export["technology_tree_sha256"],
                }
            if export is None:
                route, conditions, reader, semantics = _width_route(
                    operation, raw, mode, varied_id="vbiasn"
                )
            else:
                route, conditions, reader, semantics = _width_route(
                    operation,
                    raw,
                    mode,
                    varied_id="vbiasn",
                    exported_technology=technology,
                    export_comparison=True,
                )
            source_tree = saved_width.source_tree_sha256
            ade_tree = saved_width.ade_state_sha256
            if (
                export is not None
                and not is_candidate
                and route["profile"]["binding"]["ade"]["state"] != "state1"
            ):
                raise ValueError("retained center ADE selector differs")
            if side_export is not None:
                source_tree = side_export["source_cell_tree_sha256"]
                ade_tree = side_export["state_tree_sha256"]
                source_library = side_export["source_library_path"]
                expected_library = {
                    "name": source_library.rsplit("/", 1)[-1],
                    "path": source_library,
                    "tree_sha256": side_export["source_library_tree_sha256"],
                }
                if (
                    requested_bias.normalized != ("0.321", "V")
                    or route["source_cell"] != side_export["source_cell_path"]
                    or route["source_state"] != side_export["state_path"]
                    or route["profile"]["binding"]["ade"]["state"] != "Candidate321"
                    or route["libraries"].count(expected_library) != 1
                    or route["libraries"].count(technology) != 1
                ):
                    raise ValueError("persisted Bias registered copy differs from the export")
            (variable,) = (
                VariableContract.model_validate(row)
                for row in route["variables"]
                if row["logical_id"] == "vbiasn"
            )
            (value,) = (v for v in operation.plan.request.values if v.logical_id == "vbiasn")
            if (
                (variable.cadence_binding, variable.unit, value.unit, value.value)
                != ("VBIASN", "V", "V", bias)
                or conditions.source_tree_sha256 != source_tree
                or conditions.ade_state_tree_sha256 != ade_tree
                or variable.mutation_policy != "fixed"
                or variable.fixed_value != bias
            ):
                raise ValueError("saved-width bias is outside the registered revision or variable")
            parameters, includes, analyses, static = partition_input(raw)  # type: ignore[no-untyped-call]
            if parameters.pop("VBIASN") != bias:
                raise ValueError("saved-width bias input value differs")
            ade = AdeExecutionRegistration.model_validate_json(_canonical(route["ade"]))
            measurements.append(
                _fresh_amplifier_measurement(mode, operation, conditions, reader, ade, static, pin)
            )
            fixed_conditions.append(
                (
                    conditions
                    if export is None
                    else conditions.model_dump(
                        exclude={"source_tree_sha256", "ade_state_tree_sha256"}
                    ),
                    semantics,
                    (route["source_cell"], route["libraries"]) if export is None else None,
                    parameters,
                    includes,
                    analyses,
                    static,
                )
            )

        if requested_bias.normalized[0] == "0.32" or fixed_conditions[0] != fixed_conditions[1]:
            raise ValueError("saved-width bias fixed conditions differ")
    except (KeyError, TypeError, ValueError, OperationRejected):
        raise OperationRejected("candidate_saved_width_bias_evidence_mismatch") from None
    return FreshAmplifierAnalysisPair(
        analysis=mode,
        metric_id="dc-supply-power-grid-v2" if mode == "dc" else "gain-10hz-grid-v1",
        unit="W" if mode == "dc" else "dB",
        baseline=measurements[0],
        candidate=measurements[1],
    )


def _fresh_amplifier_row(
    mode: Literal["dc", "ac"],
    evidence: FreshAmplifierOperation | None,
    revision: FreshAmplifierRevisionBinding,
    binding: FreshAmplifierWidthBinding,
    diagnostic: _AmplifierCircuit,
    diagnostic_dc: tuple[str, str],
    *,
    baseline: bool,
    storage_successor_verified: bool = False,
    owned_copy: _FreshAmplifierCopyRoute | None = None,
    trusted_context: ExecutionContext | None = None,
    allow_missing_execution: bool = False,
) -> tuple[FreshAmplifierMeasurement, tuple[object, ...] | None]:
    identity = revision.dc if mode == "dc" else revision.ac
    if evidence is None and identity is None:
        return FreshAmplifierMeasurement(
            operation=None,
            terminal_sha256=None,
            status="NOT_RUN",
            report=None,
            value=None,
            reason="retained_operation_not_supplied",
        ), None
    if evidence is None or identity is None:
        raise ValueError("fresh amplifier operation and registration must occur together")
    operation, raw = evidence.operation, evidence.effective_input
    if (operation.query.operation_id, operation.query.expected_plan_sha256) != (
        identity.operation_id,
        identity.plan_sha256,
    ):
        raise ValueError("fresh amplifier operation differs from registration")
    if raw is None or identity.input_sha256 is None:
        if not allow_missing_execution or raw is not None or identity.input_sha256 is not None:
            raise ValueError("fresh amplifier executed input evidence is incomplete")
    else:
        params, includes, analyses, static = partition_amplifier_input(
            raw, expected_sha256=identity.input_sha256
        )
        fixed, options = _amp_pm0_options(static, baseline=baseline)
        if (
            params != diagnostic.parameters
            or includes
            != [(binding.canonical_model_include.path, binding.canonical_model_include.section)]
            or fixed
            != (
                diagnostic.fixed_statements
                if mode == "dc"
                else _amplifier_cross_analysis_body(diagnostic.fixed_statements)
            )
            or options != diagnostic.pm0_options
            or len(analyses) != 1
            or analyses[0][0] != mode
            or (mode == "dc" and analyses[0] != diagnostic_dc)
        ):
            raise ValueError("fresh amplifier input differs from qualified circuit")
    model = binding.canonical_model_include
    route, conditions, reader, semantics = _width_route(
        operation,
        raw,
        mode,
        storage_successor_verified=storage_successor_verified,
        owned_copy=owned_copy,
    )
    ade = AdeExecutionRegistration.model_validate_json(_canonical(route["ade"]))
    if (
        conditions.source_tree_sha256 != revision.source_tree_sha256
        or conditions.ade_state_tree_sha256 != revision.ade_state_sha256
        or ade.model_includes != (model,)
        or hashlib.sha256(_canonical(route["model_files"])).hexdigest()
        != binding.diagnostic_model_closure_sha256
    ):
        raise ValueError("fresh amplifier route differs from registered revision or model closure")
    source = None if owned_copy is None else owned_copy.saved_source
    native_result = None
    if source is not None:
        native_result = source.dc_native_result if mode == "dc" else source.ac_native_result
    if raw is None:
        if trusted_context is None or native_result is not None or operation.report is not None:
            raise ValueError("unmeasured 5656 row has measurement evidence or no context")
        bind_reader(trusted_context, operation.plan, ade, reader)
        original = _read_5656_original(trusted_context, operation.query.operation_id)
        status, terminal, _ = _width_report(operation, conditions, reader)
        if (
            original != operation.record
            or status == "SUCCEEDED"
            or (original is not None and terminal != original.progress.provider_receipt_sha256)
        ):
            raise ValueError("unmeasured 5656 row differs from the original journal")
        return FreshAmplifierMeasurement(
            operation=operation.query,
            terminal_sha256=terminal,
            status="NOT_RUN" if original is None else status,
            report=None,
            value=None,
            reason="retained_execution_input_unavailable",
        ), (*semantics, None)
    assert identity.input_sha256 is not None
    measurement = _fresh_amplifier_measurement(
        mode, operation, conditions, reader, ade, static, identity.input_sha256
    )
    if source is not None:
        _check_5656_native_result(
            trusted_context,
            operation,
            native_result,
            measurement.report,
            identity.input_sha256,
            ade,
            reader,
        )
    return measurement, (*semantics, analyses[0])


def _read_5656_original(context: ExecutionContext, operation_id: str) -> DurableOperation | None:
    store = AnalysisStore(context.binding.analysis_journal)
    try:
        with store.connection(create=False, read_only=True) as connection:
            return store._read_operation(connection, operation_id)
    except InvalidInputError:
        return None
    except ConfigurationError as exc:
        raise ValueError("5656 trusted operation journal unavailable") from exc


def _check_5656_native_result(
    context: ExecutionContext | None,
    operation: PmosDcOperation,
    raw: bytes | None,
    report: ResultReport | None,
    input_sha256: str,
    ade: AdeExecutionRegistration,
    reader: GenericReaderRegistration,
) -> None:
    if raw is None and report is None:
        return
    if context is None or raw is None or report is None or operation.record is None:
        raise ValueError("5656 report requires the original native payload and trusted context")
    trusted = _read_5656_original(context, operation.query.operation_id)
    if trusted is None or trusted != operation.record or trusted.progress.phase != "SUCCEEDED":
        raise ValueError("5656 terminal differs from the trusted operation journal")

    _closed_document(raw, max_bytes=1048576)
    data = NativeResultPayload.model_validate_json(raw)
    data.observation.check(trusted)
    if (
        data.observation.progress != trusted.progress
        or data.receipt.native_input_sha256 != input_sha256
        or data.ade != ade
        or data.reader != reader
    ):
        raise ValueError("5656 original reader result does not match the execution")
    _, projected = verify_native_result(
        context, trusted.plan, trusted.operation_id, data, include_report_conditions=True
    )
    expected = make_report(trusted, projected)
    if report != expected.model_copy(update={"captured_at_utc": report.captured_at_utc}):
        raise ValueError("5656 report does not match the native reader frame")


def _check_5656_ac_successor(
    source: SavedAmplifier5656Evidence,
    context: ExecutionContext | None,
    dc: FreshAmplifierOperation | None,
    ac: FreshAmplifierOperation | None,
) -> ExecutionContext:
    successor = source.ac_successor
    if successor is None or context is None or dc is None or ac is None:
        raise ValueError("5656 successor requires both original operations and contexts")
    scope_sha256 = {
        _AMP_5656_R3_CONTEXT_SHA256: _AMP_5656_R3_SCOPE_SHA256,
        _AMP_5656_R3_RENEWED_CONTEXT_SHA256: _AMP_5656_R3_RENEWED_SCOPE_SHA256,
    }.get(context.context_sha256)
    if scope_sha256 is None:
        raise ValueError("5656 successor AC context is not enrolled")
    scope = _pinned_json(successor.scope, scope_sha256)
    prior = successor.dc_context
    failed, selected = dc.operation, ac.operation
    if (
        prior.context_sha256 != _AMP_5656_R2_CONTEXT_SHA256
        or prior.binding.analysis_journal != context.binding.analysis_journal
        or prior.binding.runner_sha256 != scope["previous_runtime"]
        or context.binding.runner_sha256 != source.runtime_manifest_sha256
        or source.runtime_manifest_sha256 != scope["successor"]
        or source.runtime_registration_sha256 != scope["compiled_registration_sha256"]
        or failed.query.operation_id != _AMP_5656_FAILED_DC_ID
        or failed.plan.plan_sha256 != _AMP_5656_FAILED_DC_PLAN
        or failed.expected_terminal_sha256 != scope["dc_terminal"]
        or failed.record is None
        or failed.record.progress.phase != "FAILED"
        or dc.effective_input is not None
        or (selected.query.operation_id, selected.plan.plan_sha256)
        != (scope["operation_id"], scope["plan_sha256"])
    ):
        raise ValueError("5656 successor does not bind the R2 failed DC and R3 AC")
    if selected.record is not None and selected.record.progress.phase == "SUCCEEDED":
        if ac.effective_input is None or selected.report is None or source.ac_native_result is None:
            raise ValueError("successful 5656 AC requires its original input and result")
    elif ac.effective_input is not None:
        raise ValueError("unmeasured 5656 AC cannot use an executed input")
    return prior


def associate_fresh_amplifier_width_pair(
    plan: ChangePlan,
    readback: ChangeReadback,
    *,
    expected_plan_sha256: str,
    baseline_input: bytes,
    candidate_input: bytes,
    registration_evidence: bytes,
    expected_registration_sha256: str,
    dc: FreshAmplifierWidthAnalysis,
    ac: FreshAmplifierWidthAnalysis,
    policy_successor: FreshAmplifierStorageSuccessorEvidence | None = None,
    owned_copy: FreshAmplifierOwnedCopyEvidence | None = None,
    saved_source: SavedAmplifier5656Evidence | None = None,
    trusted_context: ExecutionContext | None = None,
) -> FreshAmplifierWidthPair:
    """Compare four retained native operations with independently authenticated bindings.

    The model receipt must attest current diagnostic-to-canonical resolution and
    the entire graph. No historical measurement or model equivalence is inferred.
    The 4497 and 5656 sources require their own copy and policy evidence. Each
    operation is validated under its original profile and measurement contract.
    """
    try:
        binding = FreshAmplifierWidthBinding.model_validate_json(
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
            or old.testbench_revision_sha256 == reopened.testbench_revision_sha256
            or binding.baseline.source_tree_sha256 == binding.candidate.source_tree_sha256
            or (saved_source is not None and (owned_copy is not None or policy_successor is None))
            or (reopened.revision.revision_id == _AMP_5656_REVISION) != (saved_source is not None)
        ):
            raise ValueError("complete PM0 change and distinct revision evidence required")
        projection = project_netlist_change(plan, baseline_input, candidate_input)
        if (
            projection.artifact_sha256 != netlist.artifact_sha256
            or projection.value.normalized != netlist.value.normalized
            or projection.derived != netlist.derived
        ):
            raise ValueError("fresh amplifier diagnostic differs from verified readback")
        circuits = []
        controls = []
        model = binding.canonical_model_include
        for raw, observed, revision in (
            (baseline_input, old, binding.baseline),
            (candidate_input, netlist, binding.candidate),
        ):
            if (observed.revision_sha256, observed.testbench_revision_sha256) != (
                revision.revision_sha256,
                revision.testbench_revision_sha256,
            ):
                raise ValueError("fresh amplifier physical revision differs")
            pin = plan.baseline.netlist_sha256 if observed is old else observed.artifact_sha256
            params, includes, analyses, static = partition_amplifier_input(raw, expected_sha256=pin)
            (control,) = analyses
            ((path, section),) = includes
            if (
                control[0] != "dc"
                or section != model.section
                or section != "NN"
                or (
                    path != model.path
                    and (
                        hashlib.sha256(path.encode("ascii")).hexdigest()
                        != _AMP_ARCHIVED_INCLUDE_PATH_SHA256
                        or hashlib.sha256(model.path.encode("ascii")).hexdigest()
                        != _AMP_CANONICAL_INCLUDE_PATH_SHA256
                    )
                )
            ):
                raise ValueError("fresh amplifier diagnostic route differs")
            circuits.append(
                _AmplifierCircuit(
                    params, includes, *_amp_pm0_options(static, baseline=observed is old)
                )
            )
            controls.append(control)

        baseline_ops = [side.operation for side in (dc.baseline, ac.baseline) if side is not None]
        candidate_ops = [
            side.operation for side in (dc.candidate, ac.candidate) if side is not None
        ]
        operations = baseline_ops + candidate_ops
        if (
            len({op.query.operation_id for op in operations}) != len(operations)
            or (
                saved_source is None
                and any(op.plan.request.design_id == _AMP_5656_DESIGN for op in operations)
            )
            or len(
                {
                    (
                        op.plan.resource_domain_sha256,
                        op.plan.ledger_ref,
                        op.plan.pdk_sha256,
                    )
                    for op in operations
                }
            )
            > 1
        ):
            raise ValueError("fresh amplifier operation or resource identity differs")
        baseline_profiles = {op.plan.environment_sha256 for op in baseline_ops}
        candidate_profiles = {op.plan.environment_sha256 for op in candidate_ops}
        if policy_successor is None:
            if len(baseline_profiles | candidate_profiles) > 1:
                raise ValueError("fresh amplifier operation profiles differ")
        else:
            child_revision = (
                _AMP_5656_REVISION if saved_source is not None else "amp-pm0-auto-4497-r1"
            )
            if (
                len(baseline_profiles) != 1
                or len(candidate_profiles) != 1
                or baseline_profiles == candidate_profiles
                or old.revision.revision_id != "reference-amplifier-bias-grid-v1"
                or reopened.revision.revision_id != child_revision
            ):
                raise ValueError("fresh amplifier storage successor is outside its comparison")
            _fresh_amplifier_storage_successor(
                policy_successor,
                baseline_ops[0].plan,
                candidate_ops[0].plan,
                saved_source=saved_source is not None,
            )
        center_copy = child_copy = dc_copy = None
        dc_context = None
        if owned_copy is not None:
            if policy_successor is None or len(baseline_ops) != 2 or len(candidate_ops) != 2:
                raise ValueError("fresh amplifier copy comparison requires all four operations")
            center_copy, child_copy = _fresh_amplifier_owned_copy(
                owned_copy, binding, netlist.artifact_sha256
            )
        if saved_source is not None:
            if len(baseline_ops) != 2 or len(candidate_ops) != 2:
                raise ValueError("5656 comparison requires all four retained operations")
            for mode, op, center_pin in (
                ("dc", baseline_ops[0], binding.baseline.dc),
                ("ac", baseline_ops[1], binding.baseline.ac),
            ):
                if (
                    center_pin is None
                    or (
                        center_pin.operation_id,
                        center_pin.plan_sha256,
                        center_pin.input_sha256,
                        op.expected_terminal_sha256,
                        op.expected_report_sha256,
                    )
                    != _AMP_5656_CENTER_PINS[mode]
                ):
                    raise ValueError("5656 Center operation pin differs")
            center_copy, child_copy = _fresh_amplifier_saved_source(
                saved_source, binding, plan, readback, baseline_input, candidate_input
            )
            if saved_source.ac_successor is not None:
                dc_context = _check_5656_ac_successor(
                    saved_source, trusted_context, dc.candidate, ac.candidate
                )
                dc_copy = replace(
                    child_copy,
                    saved_source=replace(
                        saved_source, runtime_manifest_sha256=dc_context.binding.runner_sha256
                    ),
                )
        rows = []
        analysis_pairs: tuple[tuple[Literal["dc", "ac"], FreshAmplifierWidthAnalysis], ...] = (
            ("dc", dc),
            ("ac", ac),
        )
        for mode, pair in analysis_pairs:
            baseline_row, old_semantics = _fresh_amplifier_row(
                mode,
                pair.baseline,
                binding.baseline,
                binding,
                circuits[0],
                controls[0],
                baseline=True,
                storage_successor_verified=policy_successor is not None,
                owned_copy=center_copy,
            )
            child_row, child_semantics = _fresh_amplifier_row(
                mode,
                pair.candidate,
                binding.candidate,
                binding,
                circuits[1],
                controls[1],
                baseline=False,
                storage_successor_verified=policy_successor is not None,
                owned_copy=(dc_copy or child_copy) if mode == "dc" else child_copy,
                trusted_context=(dc_context or trusted_context)
                if mode == "dc"
                else trusted_context,
                allow_missing_execution=dc_context is not None,
            )
            # An absent executed input leaves the registered controls comparable.
            if (
                old_semantics is not None
                and child_semantics is not None
                and child_semantics[-1] is None
            ):
                old_semantics, child_semantics = old_semantics[:-1], child_semantics[:-1]
            if (
                old_semantics is not None
                and child_semantics is not None
                and old_semantics != child_semantics
            ):
                raise ValueError("fresh amplifier analysis conditions differ")
            rows.append(
                FreshAmplifierAnalysisPair(
                    analysis=mode,
                    metric_id="dc-supply-power-grid-v2" if mode == "dc" else "gain-10hz-grid-v1",
                    unit="W" if mode == "dc" else "dB",
                    baseline=baseline_row,
                    candidate=child_row,
                )
            )
    except (KeyError, TypeError, ValueError):
        raise OperationRejected("candidate_fresh_amplifier_width_evidence_mismatch") from None
    return FreshAmplifierWidthPair(
        change_plan_sha256=expected_plan_sha256,
        binding_sha256=expected_registration_sha256,
        readback=checked,
        dc=rows[0],
        ac=rows[1],
    )
