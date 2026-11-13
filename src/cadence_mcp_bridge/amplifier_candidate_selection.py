"""Select over retained finite-grid amplifier sweep results and their original IDs."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from cadence_mcp_bridge.amplifier_specifications import (
    AmplifierSpecificationEvaluation,
    AmplifierSpecificationRegistry,
    MeasurementId,
    binding,
    evaluate_source,
)
from cadence_mcp_bridge.amplifier_sweeps import (
    DESIGN,
    GRID,
    REVISION,
    AmplifierPoint,
    AmplifierSweepRequest,
    AmplifierSweepResult,
    make_amplifier_plan,
)
from cadence_mcp_bridge.candidate_selection import (
    CandidateGoal,
    CandidateMeasurement,
    CandidateSelectionRequest,
    CandidateSelectionRow,
    SelectionStatus,
    _selection,
)
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.power_measurements import require_same_resource_policy
from cadence_mcp_bridge.sweeps import PointState, child_id, operation_key, point_id, sweep_id
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)

POWER = CandidateMeasurement(
    metric_id="dc-supply-power-grid-v2",
    kind="supply_power",
    supply_source_ids=("vdd", "vss"),
)
GAIN = CandidateMeasurement(
    metric_id="gain-10hz-grid-v1",
    kind="voltage_gain_db",
    frequency_hz=10.0,
)


class AmplifierCandidateSelectionRequest(VariableModel):
    candidate_values_v: Annotated[tuple[NumberText, ...], Field(min_length=2, max_length=3)]
    baseline_vbiasn_v: NumberText
    goals: Annotated[tuple[CandidateGoal, ...], Field(max_length=2)] = ()

    @field_validator("candidate_values_v")
    @classmethod
    def canonical_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(number_text(value) for value in values)

    @field_validator("baseline_vbiasn_v")
    @classmethod
    def canonical_baseline(cls, value: str) -> str:
        return number_text(value)

    @model_validator(mode="after")
    def finite_scope(self) -> Self:
        values = set(self.candidate_values_v)
        if len(values) != len(self.candidate_values_v) or not values <= set(GRID):
            raise ValueError("distinct reviewed finite-grid values required")
        if self.baseline_vbiasn_v not in values:
            raise ValueError("baseline must be an explicit candidate")
        CandidateSelectionRequest(measurements=(POWER, GAIN), goals=self.goals)
        return self


class AmplifierCandidateRow(CandidateSelectionRow):
    requested_vbiasn_v: NumberText
    dc_point: AmplifierPoint | None
    ac_point: AmplifierPoint | None


class AmplifierCandidateSelection(VariableModel):
    design_id: Literal["reference-differential-amplifier-tb2"] = DESIGN
    revision_id: Literal["reference-amplifier-bias-grid-v1"] = REVISION
    request: AmplifierCandidateSelectionRequest
    dc: AmplifierSpecificationEvaluation
    ac: AmplifierSpecificationEvaluation
    status: SelectionStatus
    selected_candidate_id: LogicalId | None
    rows: tuple[AmplifierCandidateRow, ...]
    verification_at_read: Literal["LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"] = (
        "LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"
    )
    scope: Literal["EXPLICIT_EVALUATED_CANDIDATES_ONLY"] = "EXPLICIT_EVALUATED_CANDIDATES_ONLY"
    layout_handoff: Literal["NONE_SELECTED", "SCHEMATIC_AND_LAYOUT_BINDING_UNVERIFIED"]
    new_simulations: Literal[0] = 0
    new_extractions: Literal[0] = 0
    new_reservations: Literal[0] = 0


def _checked_source(
    source: AmplifierSweepResult,
    expected_sha256: str,
    measurement_id: MeasurementId,
) -> AmplifierSpecificationEvaluation:
    TypeAdapter(Digest).validate_python(expected_sha256)
    source = AmplifierSweepResult.model_validate_json(source.model_dump_json())
    if canonical_digest(source) != expected_sha256:
        raise OperationRejected("amplifier_candidate_capture_digest_mismatch")
    engine = source.engine
    plan = make_amplifier_plan(
        AmplifierSweepRequest.model_validate(
            {
                "design_id": DESIGN,
                "variable_id": "vbiasn",
                "unit": "V",
                "analysis_id": binding(measurement_id).analysis_id,
                "measurement_id": measurement_id,
                "values": tuple(point.requested_value for point in engine.points),
                "fixed": engine.fixed,
            }
        )
    )
    if engine.plan_hash != plan.plan_hash or engine.sweep_id != sweep_id(
        plan.plan_hash,
        engine.experiment_key,
    ):
        raise OperationRejected("amplifier_candidate_plan_identity_mismatch")
    for index, point in enumerate(engine.points):
        if (
            (point.point_id, point.child_job_id, point.operation_key)
            != (
                point_id(engine.sweep_id, index),
                child_id(engine.sweep_id, index),
                operation_key(engine.sweep_id, index),
            )
            or point.state == PointState.SUCCEEDED
            and (
                point.applied_value != point.requested_value or point.applied_fixed != engine.fixed
            )
        ):
            raise OperationRejected("amplifier_candidate_point_identity_mismatch")
    return evaluate_source(source, AmplifierSpecificationRegistry(), measurement_id)


def select_retained_amplifier_candidates(
    dc: AmplifierSweepResult,
    ac: AmplifierSweepResult,
    *,
    expected_dc_sha256: str,
    expected_ac_sha256: str,
    request: AmplifierCandidateSelectionRequest,
) -> AmplifierCandidateSelection:
    """Compare fixed-condition DC power and 10 Hz gain in the original result format."""
    request = AmplifierCandidateSelectionRequest.model_validate_json(request.model_dump_json())
    dc_evaluation = _checked_source(dc, expected_dc_sha256, "dc-supply-power-grid-v2")
    ac_evaluation = _checked_source(ac, expected_ac_sha256, "gain-10hz-grid-v1")
    try:
        require_same_resource_policy(
            tuple(
                metric.counter
                for source in (dc_evaluation.source, ac_evaluation.source)
                for metric in source.measurements
            )
        )
    except ValueError:
        raise OperationRejected("amplifier_candidate_resource_policy_mismatch") from None
    dc_points = {point.requested_value: point for point in dc_evaluation.source.engine.points}
    ac_points = {point.requested_value: point for point in ac_evaluation.source.engine.points}
    if set(request.candidate_values_v) - (dc_points.keys() | ac_points.keys()):
        raise OperationRejected("amplifier_candidate_not_in_retained_sweeps")
    power = {row.requested_vbiasn_v: row.observed_value for row in dc_evaluation.evaluations}
    gain = {row.requested_vbiasn_v: row.observed_value for row in ac_evaluation.evaluations}
    ids = {
        value: f"bias-n-{int(Decimal(value) * 1000)}mv-v1" for value in request.candidate_values_v
    }
    measurements = {}
    points = {}
    for value, candidate_id in ids.items():
        dc_point, ac_point = dc_points.get(value), ac_points.get(value)
        points[candidate_id] = (value, dc_point, ac_point)
        measurements[candidate_id] = {
            POWER.metric_id: _observed(dc_point, power.get(value)),
            GAIN.metric_id: _observed(ac_point, gain.get(value)),
        }
    selection = _selection(
        measurements,
        ids[request.baseline_vbiasn_v],
        CandidateSelectionRequest(measurements=(POWER, GAIN), goals=request.goals),
    )
    rows = []
    for row in selection.rows:
        value, dc_point, ac_point = points[row.candidate_id]
        rows.append(
            AmplifierCandidateRow(
                **row.model_dump(),
                requested_vbiasn_v=value,
                dc_point=dc_point,
                ac_point=ac_point,
            )
        )
    return AmplifierCandidateSelection(
        request=request,
        dc=dc_evaluation,
        ac=ac_evaluation,
        status=selection.status,
        selected_candidate_id=selection.selected_candidate_id,
        rows=tuple(rows),
        layout_handoff=(
            "SCHEMATIC_AND_LAYOUT_BINDING_UNVERIFIED"
            if selection.selected_candidate_id
            else "NONE_SELECTED"
        ),
    )


def _observed(
    point: AmplifierPoint | None,
    value: float | None,
) -> tuple[float | None, str | None]:
    if point is None:
        return None, "analysis_not_supplied"
    if point.state != PointState.SUCCEEDED:
        return None, f"retained_analysis_{point.state.value.lower()}"
    return value, "required_metric_not_retained" if value is None else None
