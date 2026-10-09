"""Separate versioned supply-power definition; historical analog v1 stays exact."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.registered_measurements import MeasurementProvenance
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel

REFERENCE_OPERATION = "f154d798-0f7f-47d6-9323-6b046394eef6"
REFERENCE_INPUT = "c9bcf3e3bd8a9329ff0bb1513df2a08f8a4f60e314f04075e15a3422c03e4006"
REFERENCE_PSF = "e5f58c16be9db1c672915d9be455c4ef083ca760908bb20bf4991675e3d77cfc"
REFERENCE_FRAME = "7938b49067e93e7bc3ded96524c34a5778dfbd8d6d190afe9189766b57ac1ba9"
REFERENCE_EXTRACTION = "df5d60fc1db0b07b6e3a5f4bf558b220324f5398b27f5503f7f90074a03c34c8"
Finite = Annotated[float, Field(allow_inf_nan=False)]
SOURCE_SET = (
    ("vdd", "supply", 1.0),
    ("vss", "supply", 0.0),
    ("bias-n", "bias", 0.32),
    ("bias-p", "bias", 0.702),
    ("input-p", "stimulus", 0.5),
    ("input-m", "stimulus", 0.5),
)


class PowerDefinition(ContractModel):
    definition_id: Literal["dc-supply-power-v1"] = "dc-supply-power-v1"
    contract_version: Literal[1] = 1
    unit: Literal["W"] = "W"
    analysis: Literal["dc"] = "dc"
    meaning: Literal[
        "DC power delivered by the VDD/VSS supply rails at the preserved reference operating point."
    ] = "DC power delivered by the VDD/VSS supply rails at the preserved reference operating point."
    current_convention: Literal["positive_into_source_positive_terminal_A"] = (
        "positive_into_source_positive_terminal_A"
    )
    voltage_convention: Literal["positive_minus_negative_terminal_V"] = (
        "positive_minus_negative_terminal_V"
    )
    method: Literal["sum_minus_voltage_times_signed_current_no_abs"] = (
        "sum_minus_voltage_times_signed_current_no_abs"
    )
    scope: Literal["two_supply_rails_bias_and_input_contributions_reported_separately"] = (
        "two_supply_rails_bias_and_input_contributions_reported_separately"
    )
    qualification_scope: Literal["preserved_reference_native_dc_only"] = (
        "preserved_reference_native_dc_only"
    )


class PowerSelection(VariableModel):
    design_id: LogicalId
    measurement_id: LogicalId


class PowerBinding(VariableModel):
    definition_sha256: Digest
    analog_contract_sha256: Digest
    dc_contract_sha256: Digest | None


class PowerQuery(PowerSelection):
    operation_id: OperationId
    expected_contract_sha256: Digest


class PowerDescription(ContractModel):
    design_id: LogicalId
    measurement_id: LogicalId
    contract_sha256: Digest
    definition: PowerDefinition = Field(default_factory=PowerDefinition)
    source_measurement_id: LogicalId | None
    read_eligible: bool
    blocking_reason: Literal["registered_native_dc_source_unavailable"] | None
    artifact_availability_assessed: Literal[False] = False
    extraction_authorized: Literal[False] = False
    execution_authorized: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class SignedSource(ContractModel):
    source_id: Literal["vdd", "vss", "bias-n", "bias-p", "input-p", "input-m"]
    role: Literal["supply", "bias", "stimulus"]
    voltage_v: Finite | None
    current_a: Finite | None


class PowerCounter(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    count: Annotated[int, Field(ge=0, le=500)]
    result_reserved_bytes: Annotated[int, Field(ge=0, le=10 * 1024**3)]


class PowerExtraction(ContractModel):
    schema_version: Literal[1]
    job_id: OperationId
    analysis: Literal["dc"]
    input_sha256: Digest
    psf_sha256: Digest
    frame_sha256: Digest
    sources: Annotated[tuple[SignedSource, ...], Field(min_length=6, max_length=6)]
    status: Literal["EXTRACTED", "UNQUALIFIED"]
    reason: Literal["signed_branch_current_unavailable", "reader_error"] | None
    protected_unchanged: Literal[True]
    counter: PowerCounter
    new_spectre_attempts: Literal[0]
    new_reservation_bytes: Literal[0]

    @model_validator(mode="after")
    def exact_inventory(self) -> Self:
        for source, (identity, role, voltage) in zip(self.sources, SOURCE_SET, strict=True):
            if source.source_id != identity or source.role != role:
                raise ValueError("complete ordered source inventory required")
            if source.voltage_v is not None and abs(source.voltage_v - voltage) > 1e-9:
                raise ValueError("effective source voltage does not match definition")
        if self.status == "EXTRACTED":
            if self.reason is not None or any(
                s.voltage_v is None or s.current_a is None for s in self.sources
            ):
                raise ValueError("extracted power requires all signed currents and voltages")
        elif self.reason is None:
            raise ValueError("unqualified extraction needs a reason")
        return self


class PowerResult(ContractModel):
    contract_version: Literal[1] = 1
    design_id: LogicalId
    measurement_id: LogicalId
    operation_id: OperationId
    contract_sha256: Digest
    definition: PowerDefinition = Field(default_factory=PowerDefinition)
    status: Literal["QUALIFIED", "UNQUALIFIED"]
    reason: Literal["signed_branch_current_unavailable", "reader_error"] | None
    value: Finite | None
    bias_source_delivered_power_w: Finite | None
    input_source_delivered_power_w: Finite | None
    all_sources_delivered_power_w: Finite | None
    sources: Annotated[tuple[SignedSource, ...], Field(min_length=6, max_length=6)]
    source_measurement_id: LogicalId
    source_result_sha256: Digest
    extraction_result_sha256: Digest
    power_frame_sha256: Digest
    provenance: MeasurementProvenance
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"

    @model_validator(mode="after")
    def enforce_result(self) -> Self:
        values = (
            self.value,
            self.bias_source_delivered_power_w,
            self.input_source_delivered_power_w,
            self.all_sources_delivered_power_w,
        )
        for s, (identity, role, voltage) in zip(self.sources, SOURCE_SET, strict=True):
            if s.source_id != identity or s.role != role:
                raise ValueError("result inventory mismatch")
            if s.voltage_v is not None and abs(s.voltage_v - voltage) > 1e-9:
                raise ValueError("result effective voltage mismatch")
        if self.status == "UNQUALIFIED":
            if any(v is not None for v in values) or self.reason is None:
                raise ValueError("unqualified power cannot contain derived values")
        elif self.reason is not None or values != delivered_power(self.sources):
            raise ValueError("qualified values require exact signed source derivation")
        return self


def delivered_power(sources: tuple[SignedSource, ...]) -> tuple[float, float, float, float]:
    """Passive source currents make delivered power -V*I, including absorption."""
    if len(sources) != 6 or any(s.voltage_v is None or s.current_a is None for s in sources):
        raise ValueError("complete signed sources required")
    return signed_power_totals(
        tuple(
            (role, s.voltage_v, s.current_a)
            for s, role in zip(
                sources, ("supply", "supply", "bias", "bias", "stimulus", "stimulus"), strict=True
            )
            if s.voltage_v is not None and s.current_a is not None
        )
    )


def signed_power_totals(
    sources: tuple[tuple[str, float, float], ...],
) -> tuple[float, float, float, float]:
    """Shared signed source calculation; inventory qualification belongs to readers."""
    if not 1 <= len(sources) <= 32 or any(
        role not in ("supply", "bias", "stimulus")
        or not math.isfinite(voltage)
        or not math.isfinite(current)
        for role, voltage, current in sources
    ):
        raise ValueError("bounded signed source inventory required")
    grouped: dict[str, list[float]] = {role: [] for role in ("supply", "bias", "stimulus")}
    for role, voltage, current in sources:
        grouped[role].append(-voltage * current)
    values = tuple(math.fsum(grouped[role]) for role in grouped)
    total = math.fsum(-voltage * current for _, voltage, current in sources)
    if any(not math.isfinite(v) for v in (*values, total)):
        raise ValueError("nonfinite delivered power")
    return values[0], values[1], values[2], total
