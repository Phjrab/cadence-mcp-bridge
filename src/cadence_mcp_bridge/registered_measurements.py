"""Versioned measurement definitions over qualified bounded analysis results only."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.actual_diagnostics import DiagnosticScalar, SpectrumPoint
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import (
    Analysis,
    NativeSettings,
    NativeTransient,
    OperationId,
)
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

OutputId = Literal["dc-node-scalars-v1", "ac-differential-spectrum-v1", "native-tran-summary-v1"]


class MeasurementDefinition(ContractModel):
    output_id: OutputId
    analysis: Analysis
    quantity: Literal["node_voltage_set", "differential_transfer_spectrum", "transient_summary"]
    units: tuple[Literal["V", "Hz", "V/V", "dB", "deg", "s", "count"], ...]
    maximum_records: Annotated[int, Field(ge=1, le=72)]
    method: Literal["validated_native_result_projection_v1"] = (
        "validated_native_result_projection_v1"
    )


def definitions() -> tuple[MeasurementDefinition, ...]:
    return (
        MeasurementDefinition(
            output_id="dc-node-scalars-v1",
            analysis="dc",
            quantity="node_voltage_set",
            units=("V",),
            maximum_records=7,
        ),
        MeasurementDefinition(
            output_id="ac-differential-spectrum-v1",
            analysis="ac",
            quantity="differential_transfer_spectrum",
            units=("Hz", "V/V", "dB", "deg"),
            maximum_records=72,
        ),
        MeasurementDefinition(
            output_id="native-tran-summary-v1",
            analysis="tran",
            quantity="transient_summary",
            units=("V", "Hz", "s", "count"),
            maximum_records=1,
        ),
    )


def definition(output_id: OutputId) -> MeasurementDefinition:
    return next(item for item in definitions() if item.output_id == output_id)


class RegisteredMeasurement(VariableModel):
    contract_version: Literal[1] = 1
    design_id: LogicalId
    measurement_id: LogicalId
    analysis_id: LogicalId
    analysis_contract_sha256: Digest
    reader: Literal["native-bounded-result-v1", "unqualified"]
    output_id: OutputId | None
    definition_sha256: Digest | None

    @field_validator("contract_version", mode="before")
    @classmethod
    def integer_version(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("integer measurement version required")
        return value

    @model_validator(mode="after")
    def compiled_definition(self) -> Self:
        if self.reader == "unqualified":
            if self.output_id is not None or self.definition_sha256 is not None:
                raise ValueError("unqualified reader cannot bind a compiled definition")
        elif self.output_id is None or self.definition_sha256 != canonical_digest(
            definition(self.output_id)
        ):
            raise ValueError("reader must bind an exact compiled measurement definition")
        return self


class MeasurementSelection(VariableModel):
    design_id: LogicalId
    measurement_id: LogicalId


class MeasurementQuery(MeasurementSelection):
    operation_id: OperationId
    expected_contract_sha256: Digest


class MeasurementDescription(ContractModel):
    contract_version: Literal[1] = 1
    design_id: LogicalId
    measurement_id: LogicalId
    analysis_id: LogicalId
    contract_sha256: Digest
    analysis_plan_hash: Digest
    definition: MeasurementDefinition | None
    read_eligible: bool
    qualification_scope: Literal["fixed_native_compatibility", "unqualified"]
    blocking_reason: Literal["reader_unqualified", "analysis_unqualified"] | None
    source_policy: Literal["admitted_completed_analysis_only"] = "admitted_completed_analysis_only"
    execution_authorized: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class MeasurementList(ContractModel):
    design_id: LogicalId
    declared_measurements: Annotated[tuple[LogicalId, ...], Field(max_length=32)]
    measurements: Annotated[tuple[MeasurementDescription, ...], Field(max_length=32)]


class MeasurementProvenance(ContractModel):
    analysis_plan_hash: Digest
    analysis_contract_sha256: Digest
    definition_sha256: Digest
    reader: Literal["native-bounded-result-v1"] = "native-bounded-result-v1"
    revision_id: LogicalId
    operating_point_id: LogicalId
    settings: NativeSettings
    source_sha256: Digest
    copy_sha256: Digest
    state_sha256: Digest
    model_sha256: Digest
    circuit_sha256: Digest
    input_sha256: Digest
    owned_variables_sha256: Digest
    psf_sha256: Digest
    measurement_frame_sha256: Digest
    native_result_sha256: Digest
    warnings: Annotated[int, Field(ge=0, le=2, strict=True)]
    notices: Literal[0]
    protected_unchanged: Literal[True] = True


class MeasurementResult(ContractModel):
    contract_version: Literal[1] = 1
    design_id: LogicalId
    measurement_id: LogicalId
    analysis_id: LogicalId
    operation_id: OperationId
    contract_sha256: Digest
    definition: MeasurementDefinition
    provenance: MeasurementProvenance
    quality: Literal["valid"] = "valid"
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"
    scalars: Annotated[tuple[DiagnosticScalar, ...], Field(max_length=7)] = ()
    spectrum: Annotated[tuple[SpectrumPoint, ...], Field(max_length=72)] = ()
    transient: NativeTransient | None = None

    @model_validator(mode="after")
    def bounded_shape(self) -> Self:
        mode = self.definition.analysis
        if (
            (mode == "dc" and (len(self.scalars) != 7 or self.spectrum or self.transient))
            or (
                mode == "ac"
                and (self.scalars or not 70 <= len(self.spectrum) <= 72 or self.transient)
            )
            or (mode == "tran" and (self.scalars or self.spectrum or self.transient is None))
        ):
            raise ValueError("measurement payload differs from its registered definition")
        return self
