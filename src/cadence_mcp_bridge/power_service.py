"""Read already extracted source currents only after existing native admission."""

from typing import Protocol

from cadence_mcp_bridge.analog_measurements import AnalogSelection
from cadence_mcp_bridge.analog_service import AnalogSupervisor
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.power_measurements import (
    REFERENCE_EXTRACTION,
    REFERENCE_FRAME,
    REFERENCE_INPUT,
    REFERENCE_OPERATION,
    REFERENCE_PSF,
    PowerBinding,
    PowerDefinition,
    PowerDescription,
    PowerExtraction,
    PowerQuery,
    PowerResult,
    PowerSelection,
    delivered_power,
)
from cadence_mcp_bridge.registered_measurements import (
    MeasurementQuery,
    MeasurementSelection,
    RegisteredMeasurement,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


class PowerBackend(Protocol):
    async def power_extraction_result(self, operation_id: str) -> PowerExtraction: ...


class PowerSupervisor:
    def __init__(self, analog: AnalogSupervisor, backend: PowerBackend) -> None:
        self.analog = analog
        self.backend = backend

    def source(self, request: PowerSelection) -> RegisteredMeasurement | None:
        c = self.analog.contract(
            AnalogSelection(**request.model_dump(include={"design_id", "measurement_id"}))
        )
        if c.metric != "power":
            raise InvalidInputError("Selected registered measurement is not power")
        sources = [
            m
            for m in self.analog.registry.measurements_for(request.design_id)
            if isinstance(m, RegisteredMeasurement)
            and m.output_id == "dc-node-scalars-v1"
            and m.reader == "native-bounded-result-v1"
        ]
        return sources[0] if len(sources) == 1 else None

    def describe(self, request: PowerSelection) -> PowerDescription:
        source = self.source(request)
        eligible = False
        if source is not None:
            eligible = self.analog.measurements.describe(
                MeasurementSelection(
                    design_id=request.design_id, measurement_id=source.measurement_id
                )
            ).read_eligible
        c = self.analog.contract(
            AnalogSelection(design_id=request.design_id, measurement_id=request.measurement_id)
        )
        digest = canonical_digest(
            PowerBinding(
                definition_sha256=canonical_digest(PowerDefinition()),
                analog_contract_sha256=canonical_digest(c),
                dc_contract_sha256=canonical_digest(source) if source is not None else None,
            )
        )
        return PowerDescription(
            design_id=request.design_id,
            measurement_id=request.measurement_id,
            contract_sha256=digest,
            source_measurement_id=source.measurement_id if source else None,
            read_eligible=eligible,
            blocking_reason=None if eligible else "registered_native_dc_source_unavailable",
        )

    async def result(self, request: PowerQuery) -> PowerResult:
        description = self.describe(request)
        if request.expected_contract_sha256 != description.contract_sha256:
            raise InvalidInputError("Power contract does not match the current registered contract")
        source = self.source(request)
        if not description.read_eligible or source is None:
            raise InvalidInputError("Registered power reader is unqualified")
        if request.operation_id != REFERENCE_OPERATION:
            raise InvalidInputError("No reviewed power extraction exists for this operation")
        # Existing path checks PDK qualification, exact native settings/result and
        # durable design/analysis/operation identity before this additional read.
        dc = await self.analog.measurements.result(
            MeasurementQuery(
                design_id=request.design_id,
                measurement_id=source.measurement_id,
                expected_contract_sha256=canonical_digest(source),
                operation_id=request.operation_id,
            )
        )
        artifact = await self.backend.power_extraction_result(request.operation_id)
        if (
            canonical_digest(artifact) != REFERENCE_EXTRACTION
            or artifact.job_id != dc.operation_id
            or artifact.input_sha256 != REFERENCE_INPUT
            or artifact.psf_sha256 != REFERENCE_PSF
            or artifact.input_sha256 != dc.provenance.input_sha256
            or artifact.psf_sha256 != dc.provenance.psf_sha256
            or artifact.frame_sha256 != REFERENCE_FRAME
        ):
            raise RemoteFailureError("Power extraction does not match the admitted native source")
        values: tuple[float | None, ...] = (None, None, None, None)
        if artifact.status == "EXTRACTED":
            try:
                values = delivered_power(artifact.sources)
            except (ValueError, OverflowError):
                raise RemoteFailureError("Power derivation failed scientific checks") from None
        return PowerResult(
            design_id=request.design_id,
            measurement_id=request.measurement_id,
            operation_id=request.operation_id,
            contract_sha256=description.contract_sha256,
            status="QUALIFIED" if artifact.status == "EXTRACTED" else "UNQUALIFIED",
            reason=artifact.reason,
            value=values[0],
            bias_source_delivered_power_w=values[1],
            input_source_delivered_power_w=values[2],
            all_sources_delivered_power_w=values[3],
            sources=artifact.sources,
            source_measurement_id=source.measurement_id,
            source_result_sha256=canonical_digest(dc),
            extraction_result_sha256=canonical_digest(artifact),
            power_frame_sha256=artifact.frame_sha256,
            provenance=dc.provenance,
        )
