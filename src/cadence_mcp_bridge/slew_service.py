"""Admitted fixed-source supplemental study; never upgrades the generic definition."""

from typing import Protocol

from cadence_mcp_bridge.analog_measurements import AnalogQuery
from cadence_mcp_bridge.analog_service import AnalogSupervisor
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.registered_measurements import MeasurementQuery
from cadence_mcp_bridge.slew_study import (
    REFERENCE_EXTRACTION,
    REFERENCE_INPUT,
    REFERENCE_OPERATION,
    REFERENCE_PSF,
    TRAN_CONTRACT,
    SlewStudyResult,
    StepDefinition,
    StepExtraction,
    direction_summary,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


class SlewBackend(Protocol):
    async def slew_step_result(self, operation_id: str) -> StepExtraction: ...


class SlewSupervisor:
    def __init__(self, analog: AnalogSupervisor, backend: SlewBackend) -> None:
        self.analog = analog
        self.backend = backend

    async def result(self, request: AnalogQuery) -> SlewStudyResult:
        c = self.analog.contract(request)
        if (
            c.metric != "slew-rate"
            or c.design_id != "reference-differential-amplifier-tb2"
            or request.operation_id != REFERENCE_OPERATION
        ):
            raise InvalidInputError(
                "Registered reference slew contract and preserved TRAN required"
            )
        baseline = await self.analog.result(request)
        source = await self.analog.measurements.result(
            MeasurementQuery(
                design_id=c.design_id,
                measurement_id="tran-summary",
                operation_id=request.operation_id,
                expected_contract_sha256=TRAN_CONTRACT,
            )
        )
        if (
            source.provenance.input_sha256 != REFERENCE_INPUT
            or source.provenance.psf_sha256 != REFERENCE_PSF
        ):
            raise RemoteFailureError("Preserved step-study source identity changed")
        artifact = await self.backend.slew_step_result(request.operation_id)
        if canonical_digest(artifact) != REFERENCE_EXTRACTION:
            raise RemoteFailureError("Step study completion receipt changed")
        directions = (direction_summary(artifact, "rise"), direction_summary(artifact, "fall"))
        return SlewStudyResult(
            reference_result=baseline,
            source_result_sha256=canonical_digest(source),
            extraction_sha256=canonical_digest(artifact),
            study_definition_sha256=canonical_digest(StepDefinition()),
            runs=artifact.cases,
            directions=directions,
            status="PARTIALLY_QUALIFIED"
            if all(d.status == "PARTIALLY_QUALIFIED" for d in directions)
            else "UNQUALIFIED",
        )
