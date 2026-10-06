"""Supplemental sampled-reference study; never upgrades the analog v1 definition."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.analog_measurements import AnalogResult
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.power_measurements import PowerCounter
from cadence_mcp_bridge.variable_contracts import Digest

REFERENCE_OPERATION = "1afa2677-e264-4e80-a23d-dc722e34bb4a"
REFERENCE_INPUT = "53dd6c3bdee80808bfd67880f7e43be289fb275abf4f5486adf5b13f6aad275a"
REFERENCE_PSF = "5f13ca23a7d49aacaef51a59c0922e570da5dc2639baef5719956499ce5909fc"
# Exact real two-grid receipt, admitted under BANDWIDTH_QUAL_V1.json.
REFERENCE_EXTRACTION = "241968378eefc1f65655331d59ea2f8d15445dba6a25d991fe629c4a2037164e"
Finite = Annotated[float, Field(allow_inf_nan=False)]


class StudyPoint(ContractModel):
    frequency_hz: Annotated[float, Field(gt=0, le=1e8, allow_inf_nan=False)]
    gain_db: Finite | None


class RefinementGrid(ContractModel):
    schema_version: Literal[1]
    grid: Literal[50, 100]
    source_job_id: OperationId
    source_input_sha256: Digest
    source_psf_sha256: Digest
    input_sha256: Digest
    psf_sha256: Digest
    frame_sha256: Digest
    spectrum: Annotated[tuple[StudyPoint, ...], Field(min_length=251, max_length=501)]
    counter: PowerCounter
    warnings: Annotated[int, Field(ge=0, le=2)]
    notices: Annotated[int, Field(ge=0, le=100)]
    protected_unchanged: Literal[True]

    @model_validator(mode="after")
    def bound_grid(self) -> Self:
        if len(self.spectrum) != self.grid * 5 + 1:
            raise ValueError("exact finite grid required")
        if (
            self.source_job_id != REFERENCE_OPERATION
            or self.source_input_sha256 != REFERENCE_INPUT
            or self.source_psf_sha256 != REFERENCE_PSF
        ):
            raise ValueError("refinement source mismatch")
        for index, point in enumerate(self.spectrum):
            expected = 10 ** (1 + index / self.grid)
            if point.gain_db is None or abs(point.frequency_hz - expected) > expected * 1e-6:
                raise ValueError("exact finite refinement samples required")
        return self


class RefinementExtraction(ContractModel):
    schema_version: Literal[1]
    grids: Annotated[tuple[RefinementGrid, ...], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def ordered_grids(self) -> Self:
        a, b = self.grids
        if a.grid != 50 or b.grid != 100:
            raise ValueError("ordered distinct grids required")
        if (
            b.counter.count != a.counter.count + 1
            or b.counter.result_reserved_bytes != a.counter.result_reserved_bytes + 128 * 1024**2
        ):
            raise ValueError("shared consecutive reservation history required")
        return self


class GridSummary(ContractModel):
    points_per_decade: Literal[10, 50, 100]
    point_count: Annotated[int, Field(ge=3, le=501)]
    start_hz: Finite
    stop_hz: Finite
    reference_gain_db: Finite | None
    sampled_flat_window_hz: tuple[Literal[10], Literal[1000]] = (10, 1000)
    flat_window_point_count: Annotated[int, Field(ge=0, le=201)]
    sampled_gain_span_db: Finite | None
    peaking_above_reference_db: Finite | None
    downward_crossing_count: Annotated[int, Field(ge=0, le=500)]
    crossing_status: Literal[
        "FIRST_CROSSING", "MULTIPLE_DOWNWARD_CROSSINGS", "NO_CROSSING", "INSUFFICIENT_DATA"
    ]
    estimate_hz: Finite | None
    crossing_bracket_hz: tuple[Finite, Finite] | None
    # Two points describe the containing bracket, never an absolute error bound.
    crossing_bracket_relative_width: Finite | None


Convergence = Literal["OBSERVED_WITHIN_0_1_PERCENT", "NOT_CONVERGED", "NOT_ASSESSED"]


class StudyDefinition(ContractModel):
    study_id: Literal["bandwidth-grid-study-v1"] = "bandwidth-grid-study-v1"
    reference_hz: Literal[10] = 10
    drop_db: Annotated[float, Field(ge=3.0, le=3.0, allow_inf_nan=False)] = 3.0
    crossing: Literal["first_downward_no_extrapolation"] = "first_downward_no_extrapolation"
    interpolation: Literal["linear_dB_vs_log10_frequency"] = "linear_dB_vs_log10_frequency"
    grids_points_per_decade: tuple[Literal[10], Literal[50], Literal[100]] = (10, 50, 100)
    refinement_stop_hz: Literal[1000000] = 1000000
    flatness_observation_window_hz: tuple[Literal[10], Literal[1000]] = (10, 1000)
    sampled_flatness_criterion_db: Annotated[
        float, Field(ge=0.05, le=0.05, allow_inf_nan=False)
    ] = 0.05
    peaking_flag_threshold_db: Annotated[float, Field(ge=0.05, le=0.05, allow_inf_nan=False)] = 0.05
    empirical_successive_relative_change_criterion: Annotated[
        float, Field(ge=0.001, le=0.001, allow_inf_nan=False)
    ] = 0.001
    reference_gain_agreement_criterion_db: Annotated[
        float, Field(ge=0.001, le=0.001, allow_inf_nan=False)
    ] = 0.001
    absolute_error_bound: Literal[None] = None
    status: Literal["PARTIALLY_QUALIFIED"] = "PARTIALLY_QUALIFIED"


class RefinementProvenance(ContractModel):
    grid: Literal[50, 100]
    input_sha256: Digest
    psf_sha256: Digest
    frame_sha256: Digest
    warnings: Annotated[int, Field(ge=0, le=2)]
    notices: Annotated[int, Field(ge=0, le=100)]
    counter: PowerCounter


class BandwidthStudyResult(ContractModel):
    contract_version: Literal[1] = 1
    study_id: Literal["bandwidth-grid-study-v1"] = "bandwidth-grid-study-v1"
    reference_result: AnalogResult
    extraction_sha256: Digest
    definition: StudyDefinition = Field(default_factory=StudyDefinition)
    study_definition_sha256: Digest
    grids: Annotated[tuple[GridSummary, ...], Field(min_length=3, max_length=3)]
    refinements: Annotated[tuple[RefinementProvenance, ...], Field(min_length=2, max_length=2)]
    successive_relative_changes: tuple[Finite | None, Finite | None]
    reference_gain_max_difference_db: Finite
    convergence: Convergence
    status: Literal["PARTIALLY_QUALIFIED"] = "PARTIALLY_QUALIFIED"
    absolute_error_bound_hz: Literal[None] = None
    qualification_scope: Literal[
        "same_reference_circuit_NN_27C_VDD1V_bias320_702mV_fixed_grids_only"
    ] = "same_reference_circuit_NN_27C_VDD1V_bias320_702mV_fixed_grids_only"
    raw_vectors_included: Literal[False] = False
    execution_authorized: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


def study_definition() -> StudyDefinition:
    return StudyDefinition()


def summarize(points: tuple[StudyPoint, ...], density: Literal[10, 50, 100]) -> GridSummary:
    if len(points) < 3 or len(points) > 501 or points[0].frequency_hz != 10:
        raise ValueError("bounded study requires a 10 Hz reference")
    if any(b.frequency_hz <= a.frequency_hz for a, b in zip(points, points[1:], strict=False)):
        raise ValueError("strictly increasing study frequencies required")
    reference = points[0].gain_db
    flat = [p.gain_db for p in points if 10 <= p.frequency_hz <= 1000]
    missing = reference is None or any(p.gain_db is None for p in points) or len(flat) < 3
    span = (
        None
        if missing
        else max(v for v in flat if v is not None) - min(v for v in flat if v is not None)
    )
    peaking = None
    if not missing:
        assert reference is not None
        peaking = max(p.gain_db for p in points if p.gain_db is not None) - reference
    crosses: list[tuple[float, tuple[float, float]]] = []
    if not missing:
        assert reference is not None
        target = reference - 3.0
        for left, right in zip(points, points[1:], strict=False):
            assert left.gain_db is not None and right.gain_db is not None
            if left.gain_db > target >= right.gain_db:
                fraction = (target - left.gain_db) / (right.gain_db - left.gain_db)
                f = (
                    right.frequency_hz
                    if fraction == 1
                    else 10
                    ** (
                        math.log10(left.frequency_hz)
                        + fraction * math.log10(right.frequency_hz / left.frequency_hz)
                    )
                )
                crosses.append((f, (left.frequency_hz, right.frequency_hz)))
    estimate, bracket = crosses[0] if crosses else (None, None)
    state: Literal[
        "FIRST_CROSSING", "MULTIPLE_DOWNWARD_CROSSINGS", "NO_CROSSING", "INSUFFICIENT_DATA"
    ] = (
        "INSUFFICIENT_DATA"
        if missing
        else "NO_CROSSING"
        if not crosses
        else "MULTIPLE_DOWNWARD_CROSSINGS"
        if len(crosses) > 1
        else "FIRST_CROSSING"
    )
    return GridSummary(
        points_per_decade=density,
        point_count=len(points),
        start_hz=10,
        stop_hz=points[-1].frequency_hz,
        reference_gain_db=reference,
        flat_window_point_count=len(flat),
        sampled_gain_span_db=span,
        peaking_above_reference_db=peaking,
        downward_crossing_count=len(crosses),
        crossing_status=state,
        estimate_hz=estimate,
        crossing_bracket_hz=bracket,
        crossing_bracket_relative_width=(bracket[1] - bracket[0]) / estimate
        if bracket and estimate
        else None,
    )


def convergence(
    grids: tuple[GridSummary, ...],
) -> tuple[Convergence, tuple[float | None, float | None], float]:
    if len(grids) != 3 or tuple(g.points_per_decade for g in grids) != (10, 50, 100):
        raise ValueError("exact ordered study summaries required")
    changes = tuple(
        abs(b.estimate_hz - a.estimate_hz) / b.estimate_hz
        if a.estimate_hz is not None and b.estimate_hz is not None
        else None
        for a, b in zip(grids, grids[1:], strict=False)
    )
    refs = [g.reference_gain_db for g in grids if g.reference_gain_db is not None]
    agreement = max(refs) - min(refs) if refs else 0.0
    state: Convergence = "NOT_ASSESSED"
    if all(g.crossing_status == "FIRST_CROSSING" for g in grids):
        assert changes[0] is not None and changes[1] is not None
        widths = [g.crossing_bracket_relative_width for g in grids]
        state = (
            "OBSERVED_WITHIN_0_1_PERCENT"
            if (
                changes[1] <= 0.001
                and changes[1] <= changes[0]
                and agreement <= 0.001
                and all(
                    g.sampled_gain_span_db is not None and g.sampled_gain_span_db <= 0.05
                    for g in grids
                )
                and all(
                    g.peaking_above_reference_db is not None
                    and g.peaking_above_reference_db <= 0.05
                    for g in grids
                )
                and all(
                    a is not None and b is not None and b < a
                    for a, b in zip(widths, widths[1:], strict=False)
                )
            )
            else "NOT_CONVERGED"
        )
    return state, (changes[0], changes[1]), agreement
