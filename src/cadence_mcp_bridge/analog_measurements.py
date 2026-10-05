"""Compiled analog definitions and bounded extraction from validated measurements."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.registered_measurements import MeasurementProvenance, MeasurementResult
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

Metric = Literal["gain", "bandwidth", "phase-margin", "power", "offset", "slew-rate"]
Status = Literal["QUALIFIED", "PARTIALLY_QUALIFIED", "UNQUALIFIED"]
EvidenceClass = Literal[
    "IMPLEMENTABLE_FROM_EXISTING_EVIDENCE",
    "REQUIRES_EXTRACTION_WORK",
    "REQUIRES_STIMULUS_CHANGE",
    "REQUIRES_USER_SCIENTIFIC_INPUT",
    "UNQUALIFIED",
]
Number = Annotated[float, Field(allow_inf_nan=False)]


class AnalogDefinition(ContractModel):
    contract_version: Literal[1] = 1
    metric: Metric
    unit: Literal["dB", "Hz", "deg", "W", "V", "V/s"]
    meaning: Annotated[str, Field(max_length=320)]
    method: Annotated[str, Field(max_length=320)]
    source_output_id: Literal["ac-differential-spectrum-v1"] | None
    evidence_class: EvidenceClass
    blocking_reason: Annotated[str, Field(max_length=160)] | None
    qualification_requirement: Annotated[str, Field(max_length=320)]


def definitions() -> tuple[AnalogDefinition, ...]:
    return (
        AnalogDefinition(
            metric="gain",
            unit="dB",
            source_output_id="ac-differential-spectrum-v1",
            meaning=(
                "Differential voltage magnitude gain at the first measured AC frequency, 10 Hz; "
                "not DC, maximum or closed-loop gain."
            ),
            method="Use the validated 10 Hz sample: 20 log10(abs(Vout_diff / Vin_diff)).",
            evidence_class="IMPLEMENTABLE_FROM_EXISTING_EVIDENCE",
            blocking_reason=None,
            qualification_requirement=(
                "Admitted valid differential spectrum and its effective conditions; nonzero "
                "reference magnitude."
            ),
        ),
        AnalogDefinition(
            metric="bandwidth",
            unit="Hz",
            source_output_id="ac-differential-spectrum-v1",
            meaning=(
                "First downward 3.0 dB magnitude crossing relative to measured differential "
                "gain at 10 Hz; not unity-gain or closed-loop bandwidth."
            ),
            method=(
                "Bracket the first downward crossing and linearly interpolate dB against "
                "log10(frequency); never extrapolate."
            ),
            evidence_class="IMPLEMENTABLE_FROM_EXISTING_EVIDENCE",
            blocking_reason=None,
            qualification_requirement=(
                "A finite observed crossing; sampled-reference estimate only, without DC "
                "plateau or interpolation-error qualification."
            ),
        ),
        AnalogDefinition(
            metric="phase-margin",
            unit="deg",
            source_output_id=None,
            meaning="Loop-gain stability margin at a qualified unity loop-gain crossing.",
            method="No qualified loop-gain or stability-analysis reader is registered.",
            evidence_class="REQUIRES_STIMULUS_CHANGE",
            blocking_reason="qualified_loop_gain_measurement_unavailable",
            qualification_requirement=(
                "Review loop break/injection, loading, sign and loop-gain definition; qualify "
                "STB or equivalent extraction. Output AC phase is insufficient."
            ),
        ),
        AnalogDefinition(
            metric="power",
            unit="W",
            source_output_id=None,
            meaning=(
                "DC power delivered by all identified supplies, with verified current direction "
                "and supply voltages."
            ),
            method="No signed supply-current set is present in the registered DC node scalars.",
            evidence_class="REQUIRES_EXTRACTION_WORK",
            blocking_reason="qualified_signed_supply_current_set_unavailable",
            qualification_requirement=(
                "Identify every supply and sign convention, qualify bounded branch-current "
                "extraction and effective voltages, then sum delivered V times I."
            ),
        ),
        AnalogDefinition(
            metric="offset",
            unit="V",
            source_output_id=None,
            meaning=(
                "Input-referred or output offset requires a selected definition and qualified "
                "test conditions."
            ),
            method="No offset reader; ordinary DC differential output is not relabelled as offset.",
            evidence_class="REQUIRES_USER_SCIENTIFIC_INPUT",
            blocking_reason="offset_definition_and_test_conditions_unqualified",
            qualification_requirement=(
                "Select input-referred versus output offset, loop condition and stimulus; "
                "qualify zero crossing or the selected method separately."
            ),
        ),
        AnalogDefinition(
            metric="slew-rate",
            unit="V/s",
            source_output_id=None,
            meaning=(
                "Rising/falling large-signal output slew rate under a qualified step stimulus "
                "and measurement window."
            ),
            method=(
                "Existing sinusoidal TRAN extrema contain neither a qualified step response nor "
                "waveform intervals."
            ),
            evidence_class="REQUIRES_STIMULUS_CHANGE",
            blocking_reason="qualified_step_stimulus_and_waveform_window_unavailable",
            qualification_requirement=(
                "Review output signal, step amplitude, rising/falling direction, time interval "
                "and percentage/voltage window; qualify bounded waveform extraction."
            ),
        ),
    )


def definition(metric: Metric) -> AnalogDefinition:
    return next(d for d in definitions() if d.metric == metric)


class AnalogContract(VariableModel):
    design_id: LogicalId
    measurement_id: LogicalId
    metric: Metric
    definition_sha256: Digest
    source_measurement_id: LogicalId | None
    source_contract_sha256: Digest | None

    @model_validator(mode="after")
    def compiled_only(self) -> Self:
        d = definition(self.metric)
        if self.definition_sha256 != canonical_digest(d):
            raise ValueError("exact compiled analog definition required")
        if (self.source_measurement_id is None) != (self.source_contract_sha256 is None):
            raise ValueError("source identity and digest must be paired")
        if d.source_output_id is None and self.source_measurement_id is not None:
            raise ValueError("unqualified metric cannot acquire a source reader")
        return self


class AnalogSelection(VariableModel):
    design_id: LogicalId
    measurement_id: LogicalId


class AnalogQuery(AnalogSelection):
    expected_contract_sha256: Digest
    operation_id: OperationId


class AnalogDescription(ContractModel):
    design_id: LogicalId
    measurement_id: LogicalId
    contract_sha256: Digest
    definition: AnalogDefinition
    source_measurement_id: LogicalId | None
    read_eligible: bool
    blocking_reason: Annotated[str, Field(max_length=160)] | None
    execution_authorized: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class AnalogList(ContractModel):
    design_id: LogicalId
    measurements: Annotated[tuple[AnalogDescription, ...], Field(max_length=6)]


class AnalogResult(ContractModel):
    contract_version: Literal[1] = 1
    design_id: LogicalId
    measurement_id: LogicalId
    contract_sha256: Digest
    operation_id: OperationId
    definition: AnalogDefinition
    status: Status
    value: Number | None
    reason: Annotated[str, Field(max_length=160)] | None
    reference_frequency_hz: Number | None = None
    reference_gain_db: Number | None = None
    crossing_bracket_hz: tuple[Number, Number] | None = None
    source_measurement_id: LogicalId | None
    source_result_sha256: Digest | None = None
    provenance: MeasurementProvenance | None = None
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"

    @model_validator(mode="after")
    def qualified_shape(self) -> Self:
        if self.status == "UNQUALIFIED":
            if self.value is not None or self.reason is None:
                raise ValueError("unqualified metric has no value and needs a reason")
        elif self.value is None or self.provenance is None or self.source_result_sha256 is None:
            raise ValueError("measurement value requires source provenance")
        if self.definition.metric == "bandwidth" and self.value is not None:
            if self.status != "PARTIALLY_QUALIFIED" or self.crossing_bracket_hz is None:
                raise ValueError("bandwidth is a bracketed sampled-reference estimate")
            low, high = self.crossing_bracket_hz
            if not 0 < low <= self.value <= high:
                raise ValueError("bandwidth cannot leave its observed bracket")
        return self


def extract(metric: Metric, source: MeasurementResult) -> dict[str, object]:
    """Pure local derivation; inputs already passed registered native validation."""
    if definition(metric).source_output_id != source.definition.output_id:
        raise ValueError("analog source definition mismatch")
    points = source.spectrum
    if not points or points[0].frequency_hz != 10.0:
        raise ValueError("exact 10 Hz reference required")
    reference = points[0].gain_db
    context: dict[str, object] = {
        "reference_frequency_hz": 10.0,
        "reference_gain_db": reference,
    }
    if reference is None:
        return {**context, "status": "UNQUALIFIED", "value": None, "reason": "zero_reference_gain"}
    if metric == "gain":
        return {**context, "status": "QUALIFIED", "value": reference, "reason": None}
    if metric != "bandwidth":
        raise ValueError("no compiled extraction for this metric")
    target = reference - 3.0
    for left, right in zip(points, points[1:], strict=False):
        if left.gain_db is None or right.gain_db is None:
            return {
                **context,
                "status": "UNQUALIFIED",
                "value": None,
                "reason": "finite_crossing_bracket_unavailable",
            }
        if left.gain_db > target >= right.gain_db:
            fraction = (target - left.gain_db) / (right.gain_db - left.gain_db)
            value = 10 ** (
                math.log10(left.frequency_hz)
                + fraction * (math.log10(right.frequency_hz) - math.log10(left.frequency_hz))
            )
            # At an exactly sampled crossing, preserve that sample without roundoff escape.
            value = right.frequency_hz if fraction == 1 else value
            return {
                **context,
                "status": "PARTIALLY_QUALIFIED",
                "value": value,
                "crossing_bracket_hz": (left.frequency_hz, right.frequency_hz),
                "reason": "sampled_reference_log_frequency_interpolation_no_error_bound",
            }
    return {
        **context,
        "status": "UNQUALIFIED",
        "value": None,
        "reason": "crossing_not_observed_within_registered_frequency_range",
    }
