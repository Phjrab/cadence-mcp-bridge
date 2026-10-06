"""Admission-bound reads of the immutable fixed refinement study."""

from typing import Protocol

from cadence_mcp_bridge.analog_measurements import AnalogQuery
from cadence_mcp_bridge.analog_service import AnalogSupervisor
from cadence_mcp_bridge.bandwidth_study import (
    REFERENCE_EXTRACTION,
    REFERENCE_INPUT,
    REFERENCE_OPERATION,
    REFERENCE_PSF,
    BandwidthStudyResult,
    RefinementExtraction,
    RefinementProvenance,
    StudyPoint,
    convergence,
    study_definition,
    summarize,
)
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.registered_measurements import MeasurementQuery
from cadence_mcp_bridge.variable_contracts import canonical_digest


class BandwidthBackend(Protocol):
    async def bandwidth_refinement_result(self, operation_id: str) -> RefinementExtraction: ...


class BandwidthSupervisor:
    def __init__(self, analog: AnalogSupervisor, backend: BandwidthBackend) -> None:
        self.analog = analog
        self.backend = backend

    async def result(self, request: AnalogQuery) -> BandwidthStudyResult:
        c = self.analog.contract(request)
        if (
            c.metric != "bandwidth"
            or c.source_measurement_id is None
            or c.source_contract_sha256 is None
        ):
            raise InvalidInputError("Registered native bandwidth source required")
        if request.operation_id != REFERENCE_OPERATION:
            raise InvalidInputError("No reviewed bandwidth study for this operation")
        baseline = await self.analog.result(request)
        if baseline.provenance is None or (
            baseline.provenance.input_sha256 != REFERENCE_INPUT
            or baseline.provenance.psf_sha256 != REFERENCE_PSF
        ):
            raise RemoteFailureError("Bandwidth source does not match the reviewed study")
        source = await self.analog.measurements.result(
            MeasurementQuery(
                design_id=c.design_id,
                measurement_id=c.source_measurement_id,
                operation_id=request.operation_id,
                expected_contract_sha256=c.source_contract_sha256,
            )
        )
        if canonical_digest(source) != baseline.source_result_sha256:
            raise RemoteFailureError("Bandwidth source changed between admitted reads")
        artifact = await self.backend.bandwidth_refinement_result(request.operation_id)
        if canonical_digest(artifact) != REFERENCE_EXTRACTION:
            raise RemoteFailureError("Bandwidth refinement receipt changed")
        try:
            grids = (
                summarize(
                    tuple(
                        StudyPoint(frequency_hz=p.frequency_hz, gain_db=p.gain_db)
                        for p in source.spectrum
                    ),
                    10,
                ),
                *(summarize(g.spectrum, g.grid) for g in artifact.grids),
            )
            state, changes, agreement = convergence(grids)
            return BandwidthStudyResult(
                reference_result=baseline,
                extraction_sha256=canonical_digest(artifact),
                study_definition_sha256=canonical_digest(study_definition()),
                grids=grids,
                refinements=tuple(
                    RefinementProvenance.model_validate(
                        g.model_dump(
                            exclude={
                                "schema_version",
                                "source_job_id",
                                "source_input_sha256",
                                "source_psf_sha256",
                                "spectrum",
                                "protected_unchanged",
                            }
                        )
                    )
                    for g in artifact.grids
                ),
                convergence=state,
                successive_relative_changes=changes,
                reference_gain_max_difference_db=agreement,
            )
        except (ValueError, OverflowError):
            raise RemoteFailureError(
                "Bandwidth refinement failed bounded scientific checks"
            ) from None
