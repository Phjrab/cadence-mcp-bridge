"""Read-only derivation through existing admission and measurement safety checks."""

from cadence_mcp_bridge.analog_measurements import (
    AnalogContract,
    AnalogDescription,
    AnalogList,
    AnalogQuery,
    AnalogResult,
    AnalogSelection,
    definition,
    extract,
)
from cadence_mcp_bridge.analog_registry import DesignAnalogRegistry
from cadence_mcp_bridge.designs import RegistryBase
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.measurement_service import MeasurementSupervisor
from cadence_mcp_bridge.registered_measurements import MeasurementQuery, MeasurementSelection
from cadence_mcp_bridge.variable_contracts import canonical_digest


class AnalogSupervisor:
    def __init__(self, registry: RegistryBase, measurements: MeasurementSupervisor) -> None:
        self.registry = registry
        self.measurements = measurements

    def contracts(self, design_id: str) -> tuple[AnalogContract, ...]:
        self.registry.profile(design_id)
        if not isinstance(self.registry, DesignAnalogRegistry):
            return ()
        return tuple(c for c in self.registry.analog_contracts if c.design_id == design_id)

    def contract(self, request: AnalogSelection) -> AnalogContract:
        c = next(
            (
                c
                for c in self.contracts(request.design_id)
                if c.measurement_id == request.measurement_id
            ),
            None,
        )
        if c is None:
            raise InvalidInputError("Analog measurement ID is not registered for this design")
        return c

    def describe(self, request: AnalogSelection) -> AnalogDescription:
        c = self.contract(request)
        d = definition(c.metric)
        reason = d.blocking_reason
        if d.source_output_id is not None:
            if c.source_measurement_id is None:
                reason = "registered_source_measurement_unavailable"
            else:
                source = self.measurements.describe(
                    MeasurementSelection(
                        design_id=c.design_id, measurement_id=c.source_measurement_id
                    )
                )
                if not source.read_eligible:
                    reason = "source_analysis_unqualified"
        return AnalogDescription(
            design_id=c.design_id,
            measurement_id=c.measurement_id,
            contract_sha256=canonical_digest(c),
            definition=d,
            source_measurement_id=c.source_measurement_id,
            read_eligible=reason is None,
            blocking_reason=reason,
        )

    def listing(self, design_id: str) -> AnalogList:
        return AnalogList(
            design_id=design_id,
            measurements=tuple(
                self.describe(AnalogSelection(design_id=design_id, measurement_id=c.measurement_id))
                for c in self.contracts(design_id)
            ),
        )

    async def result(self, request: AnalogQuery) -> AnalogResult:
        c = self.contract(request)
        desc = self.describe(request)
        if desc.contract_sha256 != request.expected_contract_sha256:
            raise InvalidInputError("Analog contract does not match the current registry")
        fields = dict(
            design_id=c.design_id,
            measurement_id=c.measurement_id,
            contract_sha256=desc.contract_sha256,
            operation_id=request.operation_id,
            definition=desc.definition,
            source_measurement_id=c.source_measurement_id,
        )
        if not desc.read_eligible or c.source_measurement_id is None:
            return AnalogResult.model_validate(
                {**fields, "status": "UNQUALIFIED", "value": None, "reason": desc.blocking_reason}
            )
        assert c.source_contract_sha256 is not None
        source = await self.measurements.result(
            MeasurementQuery(
                design_id=c.design_id,
                measurement_id=c.source_measurement_id,
                operation_id=request.operation_id,
                expected_contract_sha256=c.source_contract_sha256,
            )
        )
        try:
            derived = extract(c.metric, source)
        except ValueError:
            raise RemoteFailureError("Analog source failed compiled extraction checks") from None
        return AnalogResult.model_validate(
            {
                **fields,
                **derived,
                "provenance": source.provenance,
                "source_result_sha256": canonical_digest(source),
            }
        )
