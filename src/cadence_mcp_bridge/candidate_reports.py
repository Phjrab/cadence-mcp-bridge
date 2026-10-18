"""Compare manifest-bound retained scalar reports without execution or remote reads.

This is separate from same-input result_reports.compare. Imported reports and
operator evidence receive content checks only, never a fresh remote attestation.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import unicodedata
from typing import Annotated, Any, Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from cadence_mcp_bridge.candidate_contracts import CandidateBatchPlan, SuppliedValue
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.operator_operations import (
    DurableOperation,
    ExplicitValue,
    OperationRejected,
)
from cadence_mcp_bridge.result_reports import DEFINITIONS, ReportMetric, ResultReport
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel

CSV_LIMIT = 1048576

CandidateStatus = Literal[
    "NOT_RUN",
    "ADMITTED",
    "UNKNOWN_OUTCOME",
    "RESERVED",
    "DISPATCHED",
    "RUNNING",
    "EXTRACTING",
    "SUCCEEDED",
    "FAILED",
    "EXTRACTION_FAILED",
    "CANCELLED",
    "RESULT_UNAVAILABLE",
    "CONDITION_MISMATCH",
]
DeltaReason = Literal[
    "available",
    "baseline_unavailable",
    "measurement_unavailable",
    "zero_baseline",
    "nonfinite_difference",
]


class CandidateObservation(VariableModel):
    candidate_id: LogicalId
    record: DurableOperation | None = None
    report: ResultReport | None = None
    unavailable_reason: Literal["retained_report_read_failed"] | None = None

    @model_validator(mode="after")
    def source_pair(self) -> Self:
        if self.report is not None and (
            self.record is None
            or self.record.progress.phase != "SUCCEEDED"
            or self.record.operation_id != self.report.operation_id
            or self.record.plan != self.report.plan
        ):
            raise ValueError("retained report requires its exact succeeded operation")
        if self.unavailable_reason is not None and (
            self.report is not None
            or self.record is None
            or self.record.progress.phase != "SUCCEEDED"
        ):
            raise ValueError(
                "unavailable report reason requires a succeeded record without a report"
            )
        return self


class CandidateMetric(VariableModel):
    metric: ReportMetric
    baseline_value: float | None
    absolute_change: float | None
    relative_change: float | None
    delta_reason: DeltaReason

    @model_validator(mode="after")
    def finite(self) -> Self:
        if any(
            value is not None and not math.isfinite(value)
            for value in (
                self.baseline_value,
                self.absolute_change,
                self.relative_change,
            )
        ):
            raise ValueError("finite candidate differences required")
        return self


class CandidateReportRow(VariableModel):
    candidate_id: LogicalId
    label: Annotated[str, Field(min_length=1, max_length=128)]
    operation_id: OperationId
    plan_sha256: Digest
    status: CandidateStatus
    reason: str | None
    requested_values: Annotated[tuple[SuppliedValue, ...], Field(min_length=1, max_length=32)]
    canonical_requested_values: Annotated[
        tuple[ExplicitValue, ...], Field(min_length=1, max_length=32)
    ]
    record: DurableOperation | None
    source_report: ResultReport | None
    conditions_sha256: Digest | None
    metrics: Annotated[tuple[CandidateMetric, ...], Field(max_length=256)]
    effective_values: Literal[None] = None
    effective_values_verification: Literal["NOT_PRESENT_IN_RETAINED_SCALAR_REPORT"] = (
        "NOT_PRESENT_IN_RETAINED_SCALAR_REPORT"
    )


class CandidateComparison(VariableModel):
    schema_version: Literal[1] = 1
    plan: CandidateBatchPlan
    plan_sha256: Digest
    baseline_candidate_id: LogicalId
    common_conditions_sha256: Digest | None
    rows: Annotated[tuple[CandidateReportRow, ...], Field(min_length=2, max_length=16)]
    verification_at_read: Literal["LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"] = (
        "LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"
    )
    new_simulations: Literal[0] = 0
    new_reservations: Literal[0] = 0
    remote_contact: Literal[False] = False
    native_candidate_qualification: Literal["NOT_ESTABLISHED_BY_LOCAL_COMPARISON"] = (
        "NOT_ESTABLISHED_BY_LOCAL_COMPARISON"
    )
    waveform_export: Literal["UNSUPPORTED_RETAINED_SCALARS_ONLY"] = (
        "UNSUPPORTED_RETAINED_SCALARS_ONLY"
    )
    relative_change_definition: Literal["(value-baseline_value)/abs(baseline_value)"] = (
        "(value-baseline_value)/abs(baseline_value)"
    )

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_schema(cls, value: int) -> int:
        if type(value) is not int:
            raise ValueError("integer version required")
        return value

    @model_validator(mode="after")
    def manifest_rows(self) -> Self:
        if (
            self.plan_sha256 != self.plan.plan_sha256
            or (self.baseline_candidate_id != self.plan.request.baseline_candidate_id)
            or len(self.rows) != len(self.plan.plans)
        ):
            raise ValueError("candidate comparison manifest differs")
        for candidate, plan, row in zip(
            self.plan.request.candidates,
            self.plan.plans,
            self.rows,
            strict=True,
        ):
            if (
                (row.candidate_id, row.label, row.operation_id, row.plan_sha256)
                != (
                    candidate.candidate_id,
                    candidate.label,
                    candidate.operation_id,
                    plan.plan_sha256,
                )
                or row.requested_values != candidate.values
                or (row.canonical_requested_values != plan.request.values)
            ):
                raise ValueError("candidate comparison row differs from manifest")
        return self


def _conditions(report: ResultReport, plan: CandidateBatchPlan) -> dict[str, Any]:
    conditions = report.conditions()
    conditions.pop("execution_input_sha256")
    varied = set(plan.request.declared_difference_ids)
    conditions["values"] = [
        value for value in conditions["values"] if value["logical_id"] not in varied
    ]
    return conditions


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _metric_key(metric: ReportMetric) -> str:
    return json.dumps(metric.model_dump(mode="json", exclude={"value"}), sort_keys=True)


def _differences(metric: ReportMetric, baseline: ReportMetric | None) -> CandidateMetric:
    value = None if baseline is None else baseline.value
    absolute = relative = None
    reason: DeltaReason = "baseline_unavailable"
    if baseline is not None:
        if value is None or metric.value is None:
            reason = "measurement_unavailable"
        else:
            absolute = metric.value - value
            if not math.isfinite(absolute):
                absolute = None
                reason = "nonfinite_difference"
            elif value == 0:
                reason = "zero_baseline"
            else:
                relative = absolute / abs(value)
                if not math.isfinite(relative):
                    relative = None
                    reason = "nonfinite_difference"
                else:
                    reason = "available"
    return CandidateMetric(
        metric=metric,
        baseline_value=value,
        absolute_change=absolute,
        relative_change=relative,
        delta_reason=reason,
    )


def compare_candidate_reports(
    plan: CandidateBatchPlan,
    expected_plan_sha256: str,
    observations: tuple[CandidateObservation, ...],
) -> CandidateComparison:
    """Validate local retained identities and compare only declared V/A differences."""
    plan = CandidateBatchPlan.model_validate_json(plan.model_dump_json())
    TypeAdapter(Digest).validate_python(expected_plan_sha256)
    if expected_plan_sha256 != plan.plan_sha256:
        raise OperationRejected("candidate_manifest_digest_mismatch")
    observations = tuple(
        CandidateObservation.model_validate_json(observation.model_dump_json())
        for observation in observations
    )
    if len(observations) > len(plan.plans) or (
        len({o.candidate_id for o in observations}) != len(observations)
    ):
        raise OperationRejected("candidate_observation_identity_invalid")
    by_id = {o.candidate_id: o for o in observations}
    candidates = {
        c.candidate_id: (c, child)
        for c, child in zip(
            plan.request.candidates,
            plan.plans,
            strict=True,
        )
    }
    if not set(by_id) <= set(candidates):
        raise OperationRejected("candidate_observation_identity_invalid")
    for identity, retained_observation in by_id.items():
        candidate, child = candidates[identity]
        if retained_observation.record is not None and (
            retained_observation.record.operation_id != candidate.operation_id
            or retained_observation.record.plan != child
        ):
            raise OperationRejected("candidate_retained_operation_mismatch")

    evidence = plan.request.fixed_evidence

    def matches_evidence(report: ResultReport) -> bool:
        return (
            report.analysis_conditions == evidence.conditions
            and report.measurement_id == evidence.measurement_id
            and report.reader_registration_sha256 == evidence.reader_registration_sha256
        )

    baseline_observation = by_id.get(plan.request.baseline_candidate_id)
    baseline_report = None if baseline_observation is None else baseline_observation.report
    if baseline_report is not None and not matches_evidence(baseline_report):
        baseline_report = None
    common = None if baseline_report is None else _digest(_conditions(baseline_report, plan))
    baseline_metrics = (
        {}
        if baseline_report is None
        else {_metric_key(metric): metric for metric in baseline_report.metrics}
    )
    rows = []
    for candidate, child in zip(plan.request.candidates, plan.plans, strict=True):
        observation = by_id.get(candidate.candidate_id)
        record = None if observation is None else observation.record
        report = None if observation is None else observation.report
        status: CandidateStatus = "NOT_RUN" if record is None else record.progress.phase
        reason = None
        digest = None
        metrics: tuple[CandidateMetric, ...] = ()
        if report is not None:
            digest = _digest(_conditions(report, plan))
            if not matches_evidence(report) or (common is not None and digest != common):
                status, reason = "CONDITION_MISMATCH", "fixed_or_common_conditions_differ"
            else:
                metrics = tuple(
                    _differences(metric, baseline_metrics.get(_metric_key(metric)))
                    for metric in report.metrics
                )
                if common is None:
                    reason = "baseline_unavailable"
        elif status == "SUCCEEDED":
            status = "RESULT_UNAVAILABLE"
            reason = (
                observation.unavailable_reason or "retained_report_not_supplied"
                if observation is not None
                else "retained_report_not_supplied"
            )
        elif status != "NOT_RUN":
            reason = "retained_operation_not_succeeded"
        rows.append(
            CandidateReportRow(
                candidate_id=candidate.candidate_id,
                label=candidate.label,
                operation_id=candidate.operation_id,
                plan_sha256=child.plan_sha256,
                status=status,
                reason=reason,
                requested_values=candidate.values,
                canonical_requested_values=child.request.values,
                record=record,
                source_report=report,
                conditions_sha256=digest,
                metrics=metrics,
            )
        )
    return CandidateComparison(
        plan=plan,
        plan_sha256=plan.plan_sha256,
        baseline_candidate_id=plan.request.baseline_candidate_id,
        common_conditions_sha256=common,
        rows=tuple(rows),
    )


def _safe_cell(value: Any) -> Any:
    if not isinstance(value, str):
        return "" if value is None else value
    leading = value
    while leading and (leading[0].isspace() or unicodedata.category(leading[0]).startswith("C")):
        leading = leading[1:]
    return "'" + value if leading.startswith(("=", "+", "-", "@")) else value


def render_candidate_csv(comparison: CandidateComparison) -> bytes:
    """Return BOM CSV, neutralizing untrusted text; never open an output path."""
    comparison = CandidateComparison.model_validate_json(comparison.model_dump_json())
    # Recompute from retained rows rather than trusting caller-edited derived deltas/status.
    rebuilt = compare_candidate_reports(
        comparison.plan,
        comparison.plan_sha256,
        tuple(
            CandidateObservation(
                candidate_id=row.candidate_id,
                record=row.record,
                report=row.source_report,
                unavailable_reason=(
                    "retained_report_read_failed"
                    if row.reason == "retained_report_read_failed"
                    else None
                ),
            )
            for row in comparison.rows
        ),
    )
    if rebuilt != comparison:
        raise OperationRejected("candidate_comparison_content_mismatch")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        (
            "batch_id",
            "manifest_sha256",
            "candidate_id",
            "label",
            "operation_id",
            "plan_sha256",
            "status",
            "reason",
            "requested_values_json",
            "canonical_values_json",
            "metric_kind",
            "signal_id",
            "value",
            "unit",
            "baseline_value",
            "absolute_change",
            "relative_change",
            "delta_reason",
            "metric_definition",
            "metric_conditions_json",
            "measurement_id",
            "execution_input_sha256",
            "reader_registration_sha256",
            "frame_sha256",
            "extraction_receipt_sha256",
            "provider_receipt_sha256",
            "analysis_conditions_json",
            "comparison_conditions_sha256",
            "verification_at_read",
            "effective_values_verification",
        )
    )
    for row in comparison.rows:
        report = row.source_report
        common: tuple[Any, ...] = (
            comparison.plan.request.batch_id,
            comparison.plan_sha256,
            row.candidate_id,
            row.label,
            row.operation_id,
            row.plan_sha256,
            row.status,
            row.reason,
            json.dumps(
                [v.model_dump(mode="json") for v in row.requested_values],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            json.dumps(
                [v.model_dump(mode="json") for v in row.canonical_requested_values],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        for item in row.metrics or (None,):
            metric = None if item is None else item.metric
            fields = common + (
                None if metric is None else metric.kind,
                None if metric is None else metric.signal_id,
                None if metric is None else metric.value,
                None if metric is None else metric.unit,
                None if item is None else item.baseline_value,
                None if item is None else item.absolute_change,
                None if item is None else item.relative_change,
                None if item is None else item.delta_reason,
                None if metric is None else DEFINITIONS[metric.kind],
                None
                if metric is None
                else json.dumps(
                    metric.model_dump(mode="json", exclude={"value"}),
                    separators=(",", ":"),
                ),
                None if report is None else report.measurement_id,
                None if report is None else report.execution_input_sha256,
                None if report is None else report.reader_registration_sha256,
                None if report is None else report.frame_sha256,
                None if report is None else report.extraction_receipt_sha256,
                None if row.record is None else row.record.progress.provider_receipt_sha256,
                None if report is None else report.analysis_conditions.model_dump_json(),
                row.conditions_sha256,
                comparison.verification_at_read,
                row.effective_values_verification,
            )
            writer.writerow(tuple(_safe_cell(value) for value in fields))
            if stream.tell() > CSV_LIMIT:
                raise OperationRejected("candidate_csv_capacity_exceeded")
    raw = stream.getvalue().encode("utf-8-sig")
    if len(raw) > CSV_LIMIT:
        raise OperationRejected("candidate_csv_capacity_exceeded")
    return raw
