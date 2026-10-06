"""Versioned bounded open-loop step diagnostics, separate from generic slew."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.analog_measurements import AnalogResult
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.power_measurements import PowerCounter
from cadence_mcp_bridge.variable_contracts import Digest

REFERENCE_OPERATION = "eca78308-8af8-4810-b848-94c0ad936afe"
REFERENCE_INPUT = "3efc38f937a7fb8e662eb71a82464ea8fff45e50d5d5fcd11d9a453b1c1ce975"
REFERENCE_PSF = "6b3bde9514941767b2fd573649621322ba5b53333dbe9ce77978e0119c0a679a"
TRAN_CONTRACT = "2fa2f552ec2098b17e8b2ad278bf928ef14f8e6ff67a10a94c8b59084f45d057"
# Filled only after real, immutable four-case extraction and protection verification.
REFERENCE_EXTRACTION = "d9e851e5c28e3a88bc4bc540d76f4b462d63ea0f9b3c72447fa9dcf83f5a21f8"
Finite = Annotated[float, Field(allow_inf_nan=False)]
Count = Annotated[int, Field(ge=0, le=160000)]
Case = Literal["coarse", "medium", "fine", "fast"]
Agreement = Literal["OBSERVED_WITHIN_1_PERCENT", "NOT_CONVERGED", "NOT_ASSESSED"]
Linearity = Literal["OBSERVED_WITHIN_RATIO_1_2", "NONLINEAR", "NOT_ASSESSED"]
State = Literal[
    "INSUFFICIENT_DATA",
    "NO_LARGE_TRANSITION",
    "MULTIPLE_CROSSINGS",
    "NO_CROSSING",
    "UNSETTLED",
    "RINGING_OR_OVERSHOOT",
    "INSUFFICIENT_WINDOW_SAMPLES",
    "COARSE_CROSSING_BRACKET",
    "DEFINED_TRANSITION",
]


class StepTransition(ContractModel):
    status: State
    direction: Literal["rise", "fall"] | None
    rate_v_per_s: Finite | None
    start_level_v: Finite | None
    end_level_v: Finite | None
    plateau_span_v: Finite | None
    window_v: tuple[Finite, Finite] | None
    crossings_s: tuple[Finite, Finite] | None
    brackets_s: tuple[tuple[Finite, Finite], tuple[Finite, Finite]] | None
    window_sample_count: Count
    overshoot_fraction: Finite | None
    subwindow_rate_ratio: Finite | None
    input_edge_overlap: bool | None

    @model_validator(mode="after")
    def qualified_secant(self) -> Self:
        if self.status == "DEFINED_TRANSITION":
            if (
                self.rate_v_per_s is None
                or self.direction is None
                or self.crossings_s is None
                or self.window_v is None
                or self.brackets_s is None
                or self.window_sample_count < 8
                or self.overshoot_fraction is None
                or not 0 <= self.overshoot_fraction <= 0.02
                or self.plateau_span_v is None
                or self.subwindow_rate_ratio is None
                or self.input_edge_overlap is None
            ):
                raise ValueError("complete step diagnostics required")
            a, b = self.crossings_s
            if not 0 < a < b < 1e-5:
                raise ValueError("observed ordered crossings required")
            expected = (self.window_v[1] - self.window_v[0]) / (b - a)
            if abs(self.rate_v_per_s - expected) > abs(expected) * 1e-9:
                raise ValueError("signed endpoint secant mismatch")
            if (self.rate_v_per_s > 0) != (self.direction == "rise"):
                raise ValueError("rise/fall sign mismatch")
            for t, (left, right) in zip(self.crossings_s, self.brackets_s, strict=True):
                if not 0 <= left <= t <= right <= 1e-5 or right - left > (b - a) / 8:
                    raise ValueError("observed dense crossing brackets required")
            assert self.start_level_v is not None and self.end_level_v is not None
            swing = self.end_level_v - self.start_level_v
            if abs(swing) < 0.1 or not 0 <= self.plateau_span_v <= 0.001 * abs(swing):
                raise ValueError("settled large output swing required")
            if any(
                abs(v - (self.start_level_v + f * swing)) > 1e-9
                for v, f in zip(self.window_v, (0.2, 0.8), strict=True)
            ):
                raise ValueError("exact endpoint-referenced window required")
        elif self.rate_v_per_s is not None:
            raise ValueError("invalid transition cannot return a rate")
        return self


class StepSummary(ContractModel):
    case: Case
    maxstep_s: Annotated[float, Field(gt=0, le=1e-8, allow_inf_nan=False)]
    input_edge_s: Annotated[float, Field(gt=0, le=1e-9, allow_inf_nan=False)]
    native_point_count: Annotated[int, Field(ge=1001, le=160000)]
    max_observed_step_s: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    output_differential_min_v: Finite
    output_differential_max_v: Finite
    transitions: tuple[StepTransition, StepTransition]

    @model_validator(mode="after")
    def fixed_case(self) -> Self:
        controls = {
            "coarse": (1e-8, 1e-9),
            "medium": (2e-10, 1e-9),
            "fine": (1e-10, 1e-9),
            "fast": (1e-10, 5e-10),
        }
        if (self.maxstep_s, self.input_edge_s) != controls[self.case]:
            raise ValueError("fixed reviewed controls required")
        if self.max_observed_step_s > self.maxstep_s * 1.00001:
            raise ValueError("effective time resolution mismatch")
        if not -2 <= self.output_differential_min_v < self.output_differential_max_v <= 2:
            raise ValueError("bounded differential output required")
        return self


class StepRun(ContractModel):
    schema_version: Literal[1]
    source_job_id: OperationId
    source_input_sha256: Digest
    source_psf_sha256: Digest
    input_sha256: Digest
    psf_sha256: Digest
    frame_sha256: Digest
    summary: StepSummary
    counter: PowerCounter
    warnings: Annotated[int, Field(ge=0, le=2)]
    notices: Annotated[int, Field(ge=0, le=100)]
    protected_unchanged: Literal[True]


class StepExtraction(ContractModel):
    schema_version: Literal[1]
    cases: tuple[StepRun, StepRun, StepRun, StepRun]

    @model_validator(mode="after")
    def complete_study(self) -> Self:
        if tuple(r.summary.case for r in self.cases) != ("coarse", "medium", "fine", "fast"):
            raise ValueError("ordered distinct fixed cases required")
        for index, run in enumerate(self.cases):
            if (
                run.source_job_id != REFERENCE_OPERATION
                or run.source_input_sha256 != REFERENCE_INPUT
                or run.source_psf_sha256 != REFERENCE_PSF
                or run.counter.count != 65 + index
                or run.counter.result_reserved_bytes != 7383023616 + (index + 1) * 128 * 1024**2
            ):
                raise ValueError("source and exact shared reservation sequence required")
        return self


class StepDefinition(ContractModel):
    definition_id: Literal["open-loop-differential-step-20-80-v1"] = (
        "open-loop-differential-step-20-80-v1"
    )
    reader: Literal["native-step-summary-v1"] = "native-step-summary-v1"
    output: Literal["Vop_minus_Vom"] = "Vop_minus_Vom"
    loop: Literal["open_loop"] = "open_loop"
    load: Literal["existing_topology_no_added_external_load"] = (
        "existing_topology_no_added_external_load"
    )
    unit: Literal["V/s"] = "V/s"
    conditions: Literal["NN_27C_VDD1V_bias320_702mV_inputVCM0_5V"] = (
        "NN_27C_VDD1V_bias320_702mV_inputVCM0_5V"
    )
    input: Literal["differential_minus0_1_to_plus0_1V_at2us_return6us_stop10us"] = (
        "differential_minus0_1_to_plus0_1V_at2us_return6us_stop10us"
    )
    method: Literal["signed_endpoint_20_80_secant_bracketed_native_linear_time_interpolation"] = (
        "signed_endpoint_20_80_secant_bracketed_native_linear_time_interpolation"
    )
    plateau_windows_s: tuple[tuple[Finite, Finite], ...] = (
        (1e-6, 1.5e-6),
        (5e-6, 5.5e-6),
        (9e-6, 9.5e-6),
    )
    empirical_relative_change_ceiling: Finite = 0.01
    constant_slope_ratio_ceiling: Finite = 1.2
    absolute_error_bound: Literal[None] = None


class DirectionStudy(ContractModel):
    direction: Literal["rise", "fall"]
    fine_signed_rate_v_per_s: Finite | None
    fine_magnitude_v_per_us: Finite | None
    refinement_relative_change: Finite | None
    faster_edge_relative_change: Finite | None
    resolution_agreement: Literal["OBSERVED_WITHIN_1_PERCENT", "NOT_CONVERGED", "NOT_ASSESSED"]
    input_edge_agreement: Literal["OBSERVED_WITHIN_1_PERCENT", "NOT_CONVERGED", "NOT_ASSESSED"]
    constant_slope: Literal["OBSERVED_WITHIN_RATIO_1_2", "NONLINEAR", "NOT_ASSESSED"]
    status: Literal["PARTIALLY_QUALIFIED", "UNQUALIFIED"]


class SlewStudyResult(ContractModel):
    contract_version: Literal[1] = 1
    study_id: Literal["reference-open-loop-step-study-v1"] = "reference-open-loop-step-study-v1"
    reference_result: AnalogResult
    source_result_sha256: Digest
    extraction_sha256: Digest
    study_definition_sha256: Digest
    definition: StepDefinition = Field(default_factory=StepDefinition)
    runs: tuple[StepRun, StepRun, StepRun, StepRun]
    directions: tuple[DirectionStudy, DirectionStudy]
    status: Literal["PARTIALLY_QUALIFIED", "UNQUALIFIED"]
    conventional_slew_qualification: Literal["UNQUALIFIED"] = "UNQUALIFIED"
    warning: Literal["open_loop_saturated_endpoints_no_added_load_no_general_slew_guarantee"] = (
        "open_loop_saturated_endpoints_no_added_load_no_general_slew_guarantee"
    )
    raw_vectors_included: Literal[False] = False
    execution_authorized: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


def direction_summary(
    extraction: StepExtraction, direction: Literal["rise", "fall"]
) -> DirectionStudy:
    rows = [
        next((t for t in r.summary.transitions if t.direction == direction), None)
        for r in extraction.cases
    ]
    _, medium, fine, fast = rows
    rate = fine.rate_v_per_s if fine else None
    refinement = (
        abs(medium.rate_v_per_s - rate) / abs(rate)
        if medium and medium.rate_v_per_s is not None and rate
        else None
    )
    edge = (
        abs(fast.rate_v_per_s - rate) / abs(rate)
        if fast and fast.rate_v_per_s is not None and rate
        else None
    )
    resolution: Agreement = (
        "NOT_ASSESSED"
        if refinement is None
        else "OBSERVED_WITHIN_1_PERCENT"
        if refinement <= 0.01
        else "NOT_CONVERGED"
    )
    input_agreement: Agreement = (
        "NOT_ASSESSED"
        if edge is None
        else "OBSERVED_WITHIN_1_PERCENT"
        if edge <= 0.01
        and fine
        and not fine.input_edge_overlap
        and fast
        and not fast.input_edge_overlap
        else "NOT_CONVERGED"
    )
    linear: Linearity = (
        "NOT_ASSESSED"
        if not fine or fine.subwindow_rate_ratio is None
        else "OBSERVED_WITHIN_RATIO_1_2"
        if fine.subwindow_rate_ratio <= 1.2
        else "NONLINEAR"
    )
    return DirectionStudy(
        direction=direction,
        fine_signed_rate_v_per_s=rate,
        fine_magnitude_v_per_us=abs(rate) / 1e6 if rate is not None else None,
        refinement_relative_change=refinement,
        faster_edge_relative_change=edge,
        resolution_agreement=resolution,
        input_edge_agreement=input_agreement,
        constant_slope=linear,
        status="PARTIALLY_QUALIFIED" if rate is not None else "UNQUALIFIED",
    )
