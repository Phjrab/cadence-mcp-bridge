"""Registered admitted DC supplemental offset diagnostics, without execution."""

from typing import Protocol

from cadence_mcp_bridge.analog_measurements import AnalogQuery
from cadence_mcp_bridge.analog_service import AnalogSupervisor
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.offset_study import (
    DC_CONTRACT,
    REFERENCE_EXTRACTION,
    REFERENCE_INPUT,
    REFERENCE_OPERATION,
    REFERENCE_PSF,
    OffsetDefinition,
    OffsetExtraction,
    OffsetStudyResult,
    study_diagnostics,
)
from cadence_mcp_bridge.registered_measurements import MeasurementQuery
from cadence_mcp_bridge.variable_contracts import canonical_digest


class OffsetBackend(Protocol):
    async def offset_study_result(self, operation_id: str) -> OffsetExtraction: ...


class OffsetSupervisor:
    def __init__(self, analog: AnalogSupervisor, backend: OffsetBackend) -> None:
        self.analog = analog
        self.backend = backend

    async def result(self, request: AnalogQuery) -> OffsetStudyResult:
        c = self.analog.contract(request)
        if (
            c.metric != "offset"
            or c.design_id != "reference-differential-amplifier-tb2"
            or request.operation_id != REFERENCE_OPERATION
        ):
            raise InvalidInputError(
                "Registered offset contract and preserved reference DC required"
            )
        baseline = await self.analog.result(request)
        source = await self.analog.measurements.result(
            MeasurementQuery(
                design_id=c.design_id,
                measurement_id="dc-scalars",
                operation_id=request.operation_id,
                expected_contract_sha256=DC_CONTRACT,
            )
        )
        if (
            source.provenance.input_sha256 != REFERENCE_INPUT
            or source.provenance.psf_sha256 != REFERENCE_PSF
        ):
            raise RemoteFailureError("Preserved offset source identity changed")
        artifact = await self.backend.offset_study_result(request.operation_id)
        if canonical_digest(artifact) != REFERENCE_EXTRACTION:
            raise RemoteFailureError("Offset study completion receipt changed")
        d = OffsetDefinition(definition_id="nominal-open-loop-input-nulling-v1")
        return OffsetStudyResult(
            reference_result=baseline,
            source_result_sha256=canonical_digest(source),
            extraction_sha256=canonical_digest(artifact),
            study_definition_sha256=canonical_digest(d),
            definition=d,
            runs=artifact.cases,
            diagnostics=study_diagnostics(artifact),
        )
