"""Compare explicit user goals over already validated candidate measurements."""

from __future__ import annotations

import csv
import hashlib
import io
import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from cadence_mcp_bridge.candidate_execution import (
    CandidateAnalysisManifest,
    CandidateRevisionResult,
    collect_candidate_analyses,
    validate_cross_analysis_conditions,
)
from cadence_mcp_bridge.candidate_reports import (
    CSV_LIMIT,
    CandidateComparison,
    CandidateObservation,
    CandidateReportRow,
    DeltaReason,
    _safe_cell,
    candidate_metric_delta,
    validate_candidate_comparison,
)
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.result_reports import DEFINITIONS, MetricKind
from cadence_mcp_bridge.specifications import Comparison, compare_numeric_target
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)

MeasurementUnit = Literal["V", "A", "W", "V/V", "dB", "deg", "Hz", "s"]
MeasurementValue = Annotated[float, Field(allow_inf_nan=False)]
Direction = Literal["minimize", "maximize"]
MeasureKind = MetricKind | Literal["supply_power"]
GoalStatus = Literal["PASS", "FAIL", "AVAILABLE", "CONDITION_MISMATCH", "MISSING_MEASUREMENT"]
SelectionStatus = Literal[
    "GOALS_NOT_PROVIDED", "NO_ELIGIBLE_CANDIDATE", "SELECTED", "MULTIPLE_ELIGIBLE_CANDIDATES"
]
DecisionStatus = Literal["NOT_EVALUATED", "INELIGIBLE", "SELECTED", "ON_FRONTIER", "DOMINATED"]

UNITS: dict[MeasureKind, MeasurementUnit] = {
    "node_voltage": "V",
    "delivered_power": "W",
    "supply_power": "W",
    "voltage_gain": "V/V",
    "voltage_gain_db": "dB",
    "voltage_phase": "deg",
    "minimum": "V",
    "maximum": "V",
    "first": "V",
    "last": "V",
    "time_weighted_mean": "V",
}
AC_METRICS = ("voltage_gain", "voltage_gain_db", "voltage_phase")
DC_METRICS = ("node_voltage", "delivered_power", "supply_power")
SUPPLY_POWER_DEFINITION = "Sum of signed delivered DC power (-V*I) over the specified supply rails."


class CandidateMeasurement(VariableModel):
    metric_id: LogicalId
    kind: MeasureKind
    signal_id: LogicalId | None = None
    frequency_hz: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = None
    source_role: Literal["supply", "bias", "stimulus"] | None = None
    supply_source_ids: Annotated[tuple[LogicalId, ...], Field(max_length=16)] = ()

    @model_validator(mode="after")
    def selector(self) -> Self:
        is_ac = self.kind in AC_METRICS
        is_sum = self.kind == "supply_power"
        if is_ac != (self.frequency_hz is not None):
            raise ValueError("AC gain and phase require an exact retained frequency")
        if (not is_ac and not is_sum) != (self.signal_id is not None):
            raise ValueError("a single DC source or node or TRAN signal is required")
        if (self.kind == "delivered_power") != (self.source_role is not None):
            raise ValueError("per-source power requires its registered source role")
        if is_sum != bool(self.supply_source_ids) or (
            len(set(self.supply_source_ids)) != len(self.supply_source_ids)
        ):
            raise ValueError("supply power requires distinct explicit supply IDs")
        return self

    @property
    def analysis(self) -> Literal["ac", "dc", "tran"]:
        if self.kind in AC_METRICS:
            return "ac"
        return "dc" if self.kind in DC_METRICS else "tran"

    @property
    def definition(self) -> str:
        if self.kind == "supply_power":
            return SUPPLY_POWER_DEFINITION
        return DEFINITIONS[self.kind]

    @property
    def unit(self) -> MeasurementUnit:
        return UNITS[self.kind]


class CandidateLimit(VariableModel):
    comparison: Comparison
    target: NumberText
    upper_target: NumberText | None = None

    @field_validator("target", "upper_target", mode="before")
    @classmethod
    def decimal_target(cls, value: str | None) -> str | None:
        return None if value is None else number_text(value)

    @model_validator(mode="after")
    def ordered_range(self) -> Self:
        if self.comparison == "range":
            if self.upper_target is None or Decimal(self.target) > Decimal(self.upper_target):
                raise ValueError("range requires ordered lower and upper targets")
        elif self.upper_target is not None:
            raise ValueError("upper target requires a range comparison")
        return self


class CandidateGoal(VariableModel):
    metric_id: LogicalId
    unit: MeasurementUnit
    required: CandidateLimit | None = None
    objective: Direction | None = None

    @model_validator(mode="after")
    def explicit_goal(self) -> Self:
        if self.required is None and self.objective is None:
            raise ValueError("goal requires a limit or an objective")
        return self


class CandidateSelectionRequest(VariableModel):
    measurements: Annotated[tuple[CandidateMeasurement, ...], Field(min_length=1, max_length=32)]
    goals: Annotated[tuple[CandidateGoal, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def goal_bindings(self) -> Self:
        units = {item.metric_id: item.unit for item in self.measurements}
        if len(units) != len(self.measurements):
            raise ValueError("measurement IDs must be unique")
        if len({goal.metric_id for goal in self.goals}) != len(self.goals) or any(
            units.get(goal.metric_id) != goal.unit for goal in self.goals
        ):
            raise ValueError("each goal must identify one measured quantity with its exact unit")
        return self


class GoalAssessment(VariableModel):
    goal: CandidateGoal
    value: MeasurementValue | None
    status: GoalStatus
    reason: str


class CandidateDecision(VariableModel):
    candidate_id: LogicalId
    goals: tuple[GoalAssessment, ...]
    status: DecisionStatus
    reason: str
    dominated_by: tuple[LogicalId, ...] = ()


class SelectionMetric(VariableModel):
    measurement: CandidateMeasurement
    definition: str
    unit: MeasurementUnit
    value: MeasurementValue | None
    reason: str | None
    baseline_value: MeasurementValue | None
    absolute_change: MeasurementValue | None
    relative_change: MeasurementValue | None
    delta_reason: DeltaReason


class CandidateSelectionRow(CandidateDecision):
    metrics: tuple[SelectionMetric, ...]


class CandidateSelection(VariableModel):
    comparison: CandidateComparison | None = None
    comparison_sha256: Digest | None = None
    manifest_sha256: Digest | None = None
    candidates: tuple[CandidateRevisionResult, ...] = ()
    baseline_candidate_id: LogicalId
    request: CandidateSelectionRequest
    status: SelectionStatus
    selected_candidate_id: LogicalId | None
    rows: tuple[CandidateSelectionRow, ...]
    cross_analysis_proof_sha256: tuple[Digest, Digest] | None = None
    cross_analysis_blocking_reason: str | None = None
    scope: Literal["EXPLICIT_EVALUATED_CANDIDATES_ONLY"] = "EXPLICIT_EVALUATED_CANDIDATES_ONLY"
    layout_handoff: Literal["NONE_SELECTED", "EFFECTIVE_VALUES_AND_LAYOUT_BINDING_UNVERIFIED"]

    @property
    def selection_sha256(self) -> str:
        return canonical_digest(self)


def _measure(
    row: CandidateReportRow,
    spec: CandidateMeasurement,
    common_conditions: str | None,
) -> tuple[float | None, str | None]:
    if row.status != "SUCCEEDED":
        return None, "condition_mismatch" if row.status == "CONDITION_MISMATCH" else (
            row.reason or row.status.lower()
        )
    if common_conditions is None:
        return None, "common_conditions_unverified"
    if row.conditions_sha256 != common_conditions:
        return None, "condition_mismatch"
    if row.source_report is None or row.source_report.plan.analysis != spec.analysis:
        return None, "analysis_not_supplied"
    metrics = tuple(item.metric for item in row.metrics)
    if spec.kind == "supply_power":
        rails = [
            item
            for item in metrics
            if item.kind == "delivered_power"
            and item.source_role == "supply"
            and item.signal_id in spec.supply_source_ids
        ]
        if len(rails) != len(spec.supply_source_ids) or {
            item.signal_id for item in rails if item.value is not None
        } != set(spec.supply_source_ids):
            return None, "required_supply_source_unavailable"
        try:
            total = math.fsum(item.value for item in rails if item.value is not None)
        except OverflowError:
            return None, "nonfinite_supply_power"
        return (total, None) if math.isfinite(total) else (None, "nonfinite_supply_power")
    matches = tuple(
        item
        for item in metrics
        if (item.kind, item.signal_id, item.frequency_hz, item.source_role)
        == (
            spec.kind,
            spec.signal_id,
            spec.frequency_hz,
            spec.source_role,
        )
    )
    if not matches:
        return None, "required_metric_not_retained"
    if len(matches) != 1:
        return None, "ambiguous_retained_metric_definition"
    value = matches[0].value
    return value, "undefined_retained_metric" if value is None else None


def _assess(
    goal: CandidateGoal,
    value: float | None,
    reason: str | None,
) -> GoalAssessment:
    if value is None:
        return GoalAssessment(
            goal=goal,
            value=None,
            status=(
                "CONDITION_MISMATCH"
                if reason
                in (
                    "condition_mismatch",
                    "common_conditions_unverified",
                    "cross_analysis_conditions_unverified",
                )
                else "MISSING_MEASUREMENT"
            ),
            reason=reason or "measurement_unavailable",
        )
    limit = goal.required
    if limit is None:
        return GoalAssessment(goal=goal, value=value, status="AVAILABLE", reason="objective_only")
    status = compare_numeric_target(
        limit.comparison,
        Decimal(str(value)),
        limit.target,
        limit.upper_target,
    )
    return GoalAssessment(
        goal=goal,
        value=value,
        status=status,
        reason="target_met" if status == "PASS" else "target_not_met",
    )


def _dominates(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return all(a >= b for a, b in zip(left, right, strict=True)) and left != right


def _select(
    measurements: Mapping[str, Mapping[str, tuple[float | None, str | None]]],
    goals: tuple[CandidateGoal, ...],
) -> tuple[SelectionStatus, tuple[CandidateDecision, ...]]:
    assessments: dict[str, tuple[GoalAssessment, ...]] = {}
    eligible: dict[str, tuple[float, ...]] = {}
    for candidate_id, values in measurements.items():
        evaluated = tuple(_assess(goal, *values[goal.metric_id]) for goal in goals)
        assessments[candidate_id] = evaluated
        if goals and all(item.status in ("PASS", "AVAILABLE") for item in evaluated):
            eligible[candidate_id] = tuple(
                -item.value if item.goal.objective == "minimize" else item.value
                for item in evaluated
                if item.goal.objective is not None and item.value is not None
            )

    dominated = {
        candidate_id: tuple(
            other_id for other_id, other in eligible.items() if _dominates(other, vector)
        )
        for candidate_id, vector in eligible.items()
    }
    frontier = tuple(candidate_id for candidate_id, by in dominated.items() if not by)
    status: SelectionStatus
    if not goals:
        status = "GOALS_NOT_PROVIDED"
    elif not frontier:
        status = "NO_ELIGIBLE_CANDIDATE"
    elif len(frontier) == 1:
        status = "SELECTED"
    else:
        status = "MULTIPLE_ELIGIBLE_CANDIDATES"

    rows = []
    for candidate_id, evaluated in assessments.items():
        by = dominated.get(candidate_id, ())
        decision: DecisionStatus
        if not goals:
            decision, reason = "NOT_EVALUATED", "provide_explicit_limits_or_objectives"
        elif candidate_id not in eligible:
            decision, reason = "INELIGIBLE", "review_failed_or_unavailable_goals"
        elif by:
            decision, reason = "DOMINATED", "dominated_on_explicit_objectives"
        elif len(frontier) == 1:
            decision, reason = "SELECTED", "only_nondominated_eligible_evaluated_candidate"
        else:
            decision, reason = "ON_FRONTIER", "tie_or_tradeoff_requires_user_priority"
        rows.append(
            CandidateDecision(
                candidate_id=candidate_id,
                goals=evaluated,
                status=decision,
                reason=reason,
                dominated_by=by,
            )
        )
    return status, tuple(rows)


def select_candidates(
    comparison: CandidateComparison,
    expected_comparison_sha256: str,
    request: CandidateSelectionRequest,
) -> CandidateSelection:
    """Use exact retained candidate evidence and explicit user goals, entirely locally."""
    TypeAdapter(Digest).validate_python(expected_comparison_sha256)
    comparison = validate_candidate_comparison(comparison)
    if canonical_digest(comparison) != expected_comparison_sha256:
        raise OperationRejected("candidate_selection_comparison_digest_mismatch")
    request = CandidateSelectionRequest.model_validate_json(request.model_dump_json())
    measurements = {
        row.candidate_id: {
            spec.metric_id: _measure(row, spec, comparison.common_conditions_sha256)
            for spec in request.measurements
        }
        for row in comparison.rows
    }
    return _selection(
        measurements,
        comparison.baseline_candidate_id,
        request,
        comparison=comparison,
        comparison_sha256=expected_comparison_sha256,
    )


def select_candidate_analyses(
    manifest: CandidateAnalysisManifest,
    expected_manifest_sha256: str,
    observations: dict[str, tuple[CandidateObservation, ...]],
    request: CandidateSelectionRequest,
    *,
    runtime_manifest: bytes | None = None,
    runtime_registration: bytes | None = None,
) -> CandidateSelection:
    """Evaluate multiple analyses from C7's bound plans and captures."""
    candidates = collect_candidate_analyses(manifest, expected_manifest_sha256, observations)
    baseline_id = manifest.batches[0].request.baseline_candidate_id
    baseline = next(candidate for candidate in candidates if candidate.candidate_id == baseline_id)
    common = {
        analysis.analysis: analysis.row.conditions_sha256
        for analysis in baseline.analyses
        if analysis.status == "SUCCEEDED" and analysis.row
    }
    request = CandidateSelectionRequest.model_validate_json(request.model_dump_json())
    goal_ids = {goal.metric_id for goal in request.goals}
    goal_analyses = frozenset(
        spec.analysis for spec in request.measurements if spec.metric_id in goal_ids
    )
    proof = None
    blocking_reason = None
    if len(goal_analyses) > 1:
        if runtime_manifest is None or runtime_registration is None:
            blocking_reason = "candidate_cross_analysis_runtime_evidence_missing"
        else:
            try:
                validate_cross_analysis_conditions(
                    manifest,
                    runtime_manifest,
                    runtime_registration,
                    analyses=goal_analyses,
                )
            except OperationRejected as rejected:
                blocking_reason = rejected.reason
            else:
                proof = (
                    hashlib.sha256(runtime_manifest).hexdigest(),
                    hashlib.sha256(runtime_registration).hexdigest(),
                )
    measurements: dict[str, dict[str, tuple[float | None, str | None]]] = {}
    for candidate in candidates:
        analyses = {result.analysis: result for result in candidate.analyses}
        values: dict[str, tuple[float | None, str | None]] = {}
        for spec in request.measurements:
            analysis = analyses.get(spec.analysis)
            if analysis is None:
                values[spec.metric_id] = (None, "analysis_not_supplied")
            elif analysis.row is None:
                values[spec.metric_id] = (None, "retained_observation_not_supplied")
            else:
                values[spec.metric_id] = _measure(analysis.row, spec, common.get(spec.analysis))
        measurements[candidate.candidate_id] = values
    return _selection(
        measurements,
        baseline_id,
        request,
        manifest_sha256=expected_manifest_sha256,
        candidates=candidates,
        cross_analysis_proof_sha256=proof,
        cross_analysis_blocking_reason=blocking_reason,
    )


def _selection(
    measurements: Mapping[str, Mapping[str, tuple[float | None, str | None]]],
    baseline_id: str,
    request: CandidateSelectionRequest,
    *,
    comparison: CandidateComparison | None = None,
    comparison_sha256: str | None = None,
    manifest_sha256: str | None = None,
    candidates: tuple[CandidateRevisionResult, ...] = (),
    cross_analysis_proof_sha256: tuple[str, str] | None = None,
    cross_analysis_blocking_reason: str | None = None,
) -> CandidateSelection:
    goal_values = measurements
    if cross_analysis_blocking_reason is not None:
        goal_values = {
            candidate: {
                metric_id: (None, reason or "cross_analysis_conditions_unverified")
                for metric_id, (_, reason) in values.items()
            }
            for candidate, values in measurements.items()
        }
    status, decisions = _select(goal_values, request.goals)
    baseline = measurements[baseline_id]
    rows = []
    for decision in decisions:
        metrics = []
        for spec in request.measurements:
            value, reason = measurements[decision.candidate_id][spec.metric_id]
            baseline_value, _ = baseline[spec.metric_id]
            absolute, relative, delta_reason = candidate_metric_delta(
                value,
                baseline_value,
                baseline_present=baseline_value is not None,
            )
            metrics.append(
                SelectionMetric(
                    measurement=spec,
                    definition=spec.definition,
                    unit=spec.unit,
                    value=value,
                    reason=reason,
                    baseline_value=baseline_value,
                    absolute_change=absolute,
                    relative_change=relative,
                    delta_reason=delta_reason,
                )
            )
        rows.append(
            CandidateSelectionRow(
                candidate_id=decision.candidate_id,
                goals=decision.goals,
                status=decision.status,
                reason=decision.reason,
                dominated_by=decision.dominated_by,
                metrics=tuple(metrics),
            )
        )
    selected = next((item.candidate_id for item in rows if item.status == "SELECTED"), None)
    return CandidateSelection(
        comparison=comparison,
        comparison_sha256=comparison_sha256,
        manifest_sha256=manifest_sha256,
        candidates=candidates,
        baseline_candidate_id=baseline_id,
        request=request,
        status=status,
        selected_candidate_id=selected,
        rows=tuple(rows),
        cross_analysis_proof_sha256=cross_analysis_proof_sha256,
        cross_analysis_blocking_reason=cross_analysis_blocking_reason,
        layout_handoff=(
            "EFFECTIVE_VALUES_AND_LAYOUT_BINDING_UNVERIFIED" if selected else "NONE_SELECTED"
        ),
    )


def render_candidate_selection_csv(selection: CandidateSelection) -> bytes:
    """Render an in-process selection. Recompute from the retained inputs for later export."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        (
            "source_sha256",
            "baseline_candidate_id",
            "candidate_id",
            "label",
            "source_revision_sha256",
            "candidate_revision_sha256",
            "analysis",
            "operation_id",
            "plan_sha256",
            "analysis_status",
            "analysis_reason",
            "requested_values_json",
            "effective_values_json",
            "effective_values_verification",
            "frame_sha256",
            "execution_input_sha256",
            "extraction_receipt_sha256",
            "reader_registration_sha256",
            "conditions_sha256",
            "metric_id",
            "measurement_json",
            "definition",
            "unit",
            "value",
            "measurement_reason",
            "baseline_value",
            "absolute_change",
            "relative_change",
            "delta_reason",
            "goal_json",
            "goal_status",
            "goal_reason",
            "selection_status",
            "decision",
            "decision_reason",
            "dominated_by",
            "layout_handoff",
            "cross_analysis_runtime_manifest_sha256",
            "cross_analysis_runtime_registration_sha256",
            "cross_analysis_blocking_reason",
        )
    )
    comparison = selection.comparison
    singles = {} if comparison is None else {row.candidate_id: row for row in comparison.rows}
    linked = {candidate.candidate_id: candidate for candidate in selection.candidates}
    for row in selection.rows:
        candidate = linked.get(row.candidate_id)
        analyses = {} if candidate is None else {item.analysis: item for item in candidate.analyses}
        single = singles.get(row.candidate_id)
        source_revision = None if candidate is None else candidate.revision.source_revision_sha256
        if comparison is not None:
            source_revision = comparison.plan.request.fixed_evidence.source_revision_sha256
        goals = {item.goal.metric_id: item for item in row.goals}
        for metric in row.metrics:
            analysis = analyses.get(metric.measurement.analysis)
            original = single if analysis is None else analysis.row
            if (
                comparison is not None
                and metric.measurement.analysis != comparison.plan.plans[0].analysis
            ):
                original = None
            report = None if original is None else original.source_report
            goal = goals.get(metric.measurement.metric_id)
            provenance = original or analysis
            requested = provenance or single or (candidate.analyses[0] if candidate else None)
            writer.writerow(
                tuple(
                    _safe_cell(value)
                    for value in (
                        selection.comparison_sha256 or selection.manifest_sha256,
                        selection.baseline_candidate_id,
                        row.candidate_id,
                        candidate.label if candidate else singles[row.candidate_id].label,
                        source_revision,
                        candidate.revision_sha256 if candidate else None,
                        metric.measurement.analysis,
                        provenance.operation_id if provenance else None,
                        provenance.plan_sha256 if provenance else None,
                        provenance.status if provenance else "NOT_SUPPLIED",
                        provenance.reason if provenance else "analysis_not_supplied",
                        "["
                        + ",".join(v.model_dump_json() for v in requested.requested_values)
                        + "]"
                        if requested
                        else None,
                        None,  # The retained scalar contract has no verified effective values.
                        original.effective_values_verification if original else None,
                        report.frame_sha256 if report else None,
                        report.execution_input_sha256 if report else None,
                        report.extraction_receipt_sha256 if report else None,
                        report.reader_registration_sha256 if report else None,
                        original.conditions_sha256 if original else None,
                        metric.measurement.metric_id,
                        metric.measurement.model_dump_json(),
                        metric.definition,
                        metric.unit,
                        metric.value,
                        metric.reason,
                        metric.baseline_value,
                        metric.absolute_change,
                        metric.relative_change,
                        metric.delta_reason,
                        goal.goal.model_dump_json() if goal else None,
                        goal.status if goal else None,
                        goal.reason if goal else None,
                        selection.status,
                        row.status,
                        row.reason,
                        ",".join(row.dominated_by),
                        selection.layout_handoff if row.status == "SELECTED" else "NONE_SELECTED",
                        *(selection.cross_analysis_proof_sha256 or (None, None)),
                        selection.cross_analysis_blocking_reason,
                    )
                )
            )
            if stream.tell() > CSV_LIMIT:
                raise OperationRejected("candidate_csv_capacity_exceeded")
    raw = stream.getvalue().encode("utf-8-sig")
    if len(raw) > CSV_LIMIT:
        raise OperationRejected("candidate_csv_capacity_exceeded")
    return raw
