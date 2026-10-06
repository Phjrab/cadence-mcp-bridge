"""Bounded nominal input-nulling diagnostics, separate from generic offset v1."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import Field

from cadence_mcp_bridge.analog_measurements import AnalogResult
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.power_measurements import PowerCounter
from cadence_mcp_bridge.variable_contracts import Digest

Finite = Annotated[float, Field(allow_inf_nan=False)]
Method = Literal["nominal-open-loop-input-nulling-v1", "nominal-open-loop-output-v1"]
Case = Literal["zero", "minus1", "plus1", "minus05", "plus05"]
REFERENCE_OPERATION = "f154d798-0f7f-47d6-9323-6b046394eef6"
REFERENCE_INPUT = "c9bcf3e3bd8a9329ff0bb1513df2a08f8a4f60e314f04075e15a3422c03e4006"
REFERENCE_PSF = "e5f58c16be9db1c672915d9be455c4ef083ca760908bb20bf4991675e3d77cfc"
REFERENCE_EXTRACTION = "9b67df9fcc717ad35838acc9ab62f9888e3f8d63457da14e8c56a4ae76fc9c10"
DC_CONTRACT = "3b14c9277db69a570a85135ced16e8a2ef0831cb4fe25c3f22e6360d24d70259"
ExtractionStatus = Literal[
    "INSUFFICIENT_POINTS",
    "UNQUALIFIED_POINTS",
    "BRACKET_OUTSIDE_LOCAL_OUTPUT_WINDOW",
    "FLAT_ZERO_INTERVAL",
    "ENDPOINT_ONLY_ZERO",
    "NO_CROSSING",
    "MULTIPLE_CROSSINGS",
    "NON_MONOTONIC",
    "EXACT_SAMPLED_ZERO",
    "BRACKETED_ZERO",
]


class OffsetDefinition(ContractModel):
    """Scientific choices remain operator owned; no default chooses a user intent."""

    schema_version: Literal[1] = 1
    definition_id: Method
    loop_condition: Literal["open_loop"] = "open_loop"
    input_definition: Literal["Vp_minus_Vm"] = "Vp_minus_Vm"
    output_definition: Literal["Vop_minus_Vom"] = "Vop_minus_Vom"
    corner: Literal["NN"] = "NN"
    temperature_c: Literal[27] = 27
    vdd_v: Annotated[float, Field(ge=1, le=1, allow_inf_nan=False)] = 1.0
    input_common_mode_v: Annotated[float, Field(ge=0.5, le=0.5, allow_inf_nan=False)] = 0.5
    bias_values_v: tuple[
        Annotated[float, Field(ge=0.320, le=0.320, allow_inf_nan=False)],
        Annotated[float, Field(ge=0.702, le=0.702, allow_inf_nan=False)],
    ] = (0.320, 0.702)
    load: Literal["existing_topology_no_added_external_load"] = (
        "existing_topology_no_added_external_load"
    )
    mismatch: Literal["not_simulated"] = "not_simulated"
    ideal_differential_output_reference_v: Annotated[
        float, Field(ge=0, le=0, allow_inf_nan=False)
    ] = 0.0
    nulling_sign: Literal["applied_Vp_minus_Vm_at_zero_output_not_negated"] = (
        "applied_Vp_minus_Vm_at_zero_output_not_negated"
    )
    source_binding: Literal["requires_reviewed_admitted_DC_and_effective_input"] = (
        "requires_reviewed_admitted_DC_and_effective_input"
    )
    specification: Literal["not_evaluated"] = "not_evaluated"


class OffsetPoint(ContractModel):
    """Bounded internal scalars, never caller-controlled MCP sweep points."""

    input_differential_v: Annotated[float, Field(ge=-0.01, le=0.01, allow_inf_nan=False)]
    output_differential_v: Annotated[float, Field(ge=-2, le=2, allow_inf_nan=False)]
    valid_dc: bool
    effective_input_verified: bool
    local_output_window_reviewed: bool


class OffsetEstimate(ContractModel):
    """A numerical extraction is separate from real-source qualification."""

    schema_version: Literal[1] = 1
    status: ExtractionStatus
    nulling_input_v: Finite | None = None
    input_bracket_v: tuple[Finite, Finite] | None = None
    local_gain_v_per_v: tuple[Finite, Finite] | None = None
    point_count: Annotated[int, Field(ge=0, le=17)]
    extraction: Literal["bounded_observed_zero_or_linear_bracket_no_extrapolation"] = (
        "bounded_observed_zero_or_linear_bracket_no_extrapolation"
    )
    qualification: Literal["UNQUALIFIED"] = "UNQUALIFIED"
    qualification_reason: Literal["scientific_selection_and_real_source_qualification_required"] = (
        "scientific_selection_and_real_source_qualification_required"
    )
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


def input_nulling_estimate(points: tuple[OffsetPoint, ...]) -> OffsetEstimate:
    """Inspect at most17 points. Never expand, choose among roots or extrapolate."""
    if len(points) > 17:
        raise ValueError("bounded point count required")
    count = len(points)

    def unavailable(status: ExtractionStatus) -> OffsetEstimate:
        return OffsetEstimate(status=status, point_count=count)

    if count < 3:
        return unavailable("INSUFFICIENT_POINTS")
    x = [p.input_differential_v for p in points]
    y = [p.output_differential_v for p in points]
    if any(a >= b for a, b in zip(x, x[1:], strict=False)):
        raise ValueError("unique increasing observed inputs required")
    if not all(
        p.valid_dc and p.effective_input_verified and p.local_output_window_reviewed for p in points
    ):
        return unavailable("UNQUALIFIED_POINTS")
    if any(a == b == 0 for a, b in zip(y, y[1:], strict=False)):
        return unavailable("FLAT_ZERO_INTERVAL")
    zeros = [i for i, value in enumerate(y) if value == 0]
    crossings = [
        i for i, (a, b) in enumerate(zip(y, y[1:], strict=False)) if (a < 0 < b) or (b < 0 < a)
    ]
    if len(zeros) + len(crossings) > 1:
        return unavailable("MULTIPLE_CROSSINGS")
    if not zeros and not crossings:
        return unavailable("NO_CROSSING")
    if zeros and zeros[0] in (0, count - 1):
        return unavailable("ENDPOINT_ONLY_ZERO")
    increments = [b - a for a, b in zip(y, y[1:], strict=False)]
    if not (all(v > 0 for v in increments) or all(v < 0 for v in increments)):
        return unavailable("NON_MONOTONIC")
    if zeros:
        i = zeros[0]
        left, right = i - 1, i + 1
        value = x[i]
        gains = ((y[i] - y[left]) / (x[i] - x[left]), (y[right] - y[i]) / (x[right] - x[i]))
        status: ExtractionStatus = "EXACT_SAMPLED_ZERO"
    else:
        left, right = crossings[0], crossings[0] + 1
        value = x[left] - y[left] * (x[right] - x[left]) / (y[right] - y[left])
        gain = (y[right] - y[left]) / (x[right] - x[left])
        gains = (gain, gain)
        status = "BRACKETED_ZERO"
    # This fixed near-zero-output diagnostic is not a transistor absolute rating.
    # MOS-region proof is not supplied here; a rail-limited secant
    # cannot be declared an offset extraction merely because it changes sign.
    if max(abs(y[left]), abs(y[right])) > 0.1:
        return unavailable("BRACKET_OUTSIDE_LOCAL_OUTPUT_WINDOW")
    if not all(math.isfinite(v) for v in (value, *gains)):
        return unavailable("UNQUALIFIED_POINTS")
    if not x[left] <= value <= x[right]:
        raise ValueError("observed root bracket required")
    return OffsetEstimate(
        status=status,
        nulling_input_v=value,
        input_bracket_v=(x[left], x[right]),
        local_gain_v_per_v=gains,
        point_count=count,
    )


def output_difference_at_zero_input(point: OffsetPoint) -> float:
    """Internal candidate scalar only; selected definition/provenance still required."""
    if point.input_differential_v != 0:
        raise ValueError("equal effective differential inputs required")
    if not (
        point.valid_dc and point.effective_input_verified and point.local_output_window_reviewed
    ):
        raise ValueError("qualified source conditions required")
    return point.output_differential_v


class OffsetScalars(ContractModel):
    Vop: Finite
    Vom: Finite
    Vp: Finite
    Vm: Finite
    VDD: Finite


class OffsetRun(ContractModel):
    schema_version: Literal[1]
    case: Case
    source_job_id: OperationId
    source_input_sha256: Digest
    source_psf_sha256: Digest
    input_sha256: Digest
    psf_sha256: Digest
    frame_sha256: Digest
    scalars: OffsetScalars
    counter: PowerCounter
    new_simulation: bool
    warnings: Annotated[int, Field(ge=0, le=2)]
    notices: Annotated[int, Field(ge=0, le=16)]
    protected_unchanged: Literal[True]


class OffsetExtraction(ContractModel):
    schema_version: Literal[1]
    cases: tuple[OffsetRun, OffsetRun, OffsetRun, OffsetRun, OffsetRun]


class OffsetDiagnostics(ContractModel):
    coarse: OffsetEstimate
    fine: OffsetEstimate
    root_pair_difference_v: Finite | None
    gain_pair_relative_difference: Finite | None
    local_output_window_review: bool
    fixed_input_verified: bool
    observed_refinement_agreement: bool
    status: Literal["PARTIALLY_QUALIFIED", "UNQUALIFIED"]
    value_v: Finite | None
    unit: Literal["V"] = "V"
    reason: Literal[
        "nominal_observed_nulling_no_absolute_error_or_mismatch_qualification",
        "fixed_input_local_window_or_refinement_not_qualified",
    ]


def study_diagnostics(extraction: OffsetExtraction) -> OffsetDiagnostics:
    rows = extraction.cases
    names = ("zero", "minus1", "plus1", "minus05", "plus05")
    expected = (0, -1e-6, 1e-6, -0.5e-6, 0.5e-6)
    verified = True
    local = True
    points = []
    for i, (r, name, dx) in enumerate(zip(rows, names, expected, strict=True)):
        if (
            r.case != name
            or r.source_job_id != REFERENCE_OPERATION
            or r.source_input_sha256 != REFERENCE_INPUT
            or r.source_psf_sha256 != REFERENCE_PSF
            or r.new_simulation != (i != 0)
            or r.counter.count != 68 + i
            or r.counter.result_reserved_bytes != 7919894528 + i * 128 * 1024**2
        ):
            raise ValueError("immutable offset cases/source/admission sequence required")
        if i == 0 and (r.psf_sha256 != REFERENCE_PSF or r.input_sha256 != REFERENCE_INPUT):
            raise ValueError("zero point must reuse original admitted DC")
        s = r.scalars
        actual = s.Vp - s.Vm
        effective = (
            abs(actual - dx) <= 1e-12
            and abs((s.Vp + s.Vm) / 2 - 0.5) <= 1e-12
            and abs(s.VDD - 1) <= 1e-12
        )
        # A fixed local response/headroom diagnostic, not MOS-region or rating proof.
        within = 0.1 < s.Vop < 0.9 and 0.1 < s.Vom < 0.9 and abs(s.Vop - s.Vom) <= 0.1
        verified = verified and effective
        local = local and within
        points.append(
            OffsetPoint(
                input_differential_v=actual,
                output_differential_v=s.Vop - s.Vom,
                valid_dc=True,
                effective_input_verified=effective,
                local_output_window_reviewed=within,
            )
        )
    coarse = input_nulling_estimate((points[1], points[0], points[2]))
    fine = input_nulling_estimate((points[3], points[0], points[4]))
    difference = None
    gain_change = None
    agreement = False
    if (
        coarse.nulling_input_v is not None
        and fine.nulling_input_v is not None
        and coarse.local_gain_v_per_v is not None
        and fine.local_gain_v_per_v is not None
    ):
        difference = abs(fine.nulling_input_v - coarse.nulling_input_v)
        a = sum(coarse.local_gain_v_per_v) / 2
        b = sum(fine.local_gain_v_per_v) / 2
        if a != 0 and b != 0:
            gain_change = abs(b - a) / abs(b)
            agreement = difference <= 1e-8 and gain_change <= 0.01
    ok = verified and local and agreement
    return OffsetDiagnostics(
        coarse=coarse,
        fine=fine,
        root_pair_difference_v=difference,
        gain_pair_relative_difference=gain_change,
        local_output_window_review=local,
        fixed_input_verified=verified,
        observed_refinement_agreement=agreement,
        status="PARTIALLY_QUALIFIED" if ok else "UNQUALIFIED",
        value_v=fine.nulling_input_v if ok else None,
        reason="nominal_observed_nulling_no_absolute_error_or_mismatch_qualification"
        if ok
        else "fixed_input_local_window_or_refinement_not_qualified",
    )


class OffsetStudyResult(ContractModel):
    contract_version: Literal[1] = 1
    study_id: Literal["reference-nominal-input-nulling-study-v1"] = (
        "reference-nominal-input-nulling-study-v1"
    )
    reference_result: AnalogResult
    source_result_sha256: Digest
    extraction_sha256: Digest
    study_definition_sha256: Digest
    definition: OffsetDefinition
    runs: tuple[OffsetRun, OffsetRun, OffsetRun, OffsetRun, OffsetRun]
    diagnostics: OffsetDiagnostics
    generic_offset_qualification: Literal["UNQUALIFIED"] = "UNQUALIFIED"
    warning: Literal["numerical_residual_consistent_with_nominal_zero_not_physical_precision"] = (
        "numerical_residual_consistent_with_nominal_zero_not_physical_precision"
    )
    operating_region_warning: Literal["local_output_window_is_not_MOS_region_or_rating_proof"] = (
        "local_output_window_is_not_MOS_region_or_rating_proof"
    )
    absolute_error_bound_v: Literal[None] = None
    mismatch_qualification: Literal["not_simulated"] = "not_simulated"
    raw_vectors_included: Literal[False] = False
    execution_authorized: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"
