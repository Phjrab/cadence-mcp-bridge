"""Read-only specification orchestration through admitted analog measurement readers."""

from cadence_mcp_bridge.analog_measurements import AnalogQuery, AnalogSelection
from cadence_mcp_bridge.analog_service import AnalogSupervisor
from cadence_mcp_bridge.designs import RegistryBase
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.specification_registry import DesignSpecificationRegistry
from cadence_mcp_bridge.specifications import (
    SpecificationContract,
    SpecificationDescription,
    SpecificationEvaluation,
    SpecificationList,
    SpecificationQuery,
    SpecificationSelection,
    evaluate,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


class SpecificationSupervisor:
    def __init__(self, registry: RegistryBase, analog: AnalogSupervisor) -> None:
        self.registry, self.analog = registry, analog

    def contracts(self, design_id: str) -> tuple[SpecificationContract, ...]:
        self.registry.profile(design_id)
        if not isinstance(self.registry, DesignSpecificationRegistry):
            return ()
        return tuple(c for c in self.registry.specification_contracts if c.design_id == design_id)

    def describe(self, request: SpecificationSelection) -> SpecificationDescription:
        c = next(
            (c for c in self.contracts(request.design_id) if c.spec_id == request.spec_id), None
        )
        if c is None:
            raise InvalidInputError("Specification ID is not registered for this design")
        return SpecificationDescription(
            contract=c,
            contract_sha256=canonical_digest(c),
            target_status="not_selected" if c.target is None else "registered",
        )

    def listing(self, design_id: str) -> SpecificationList:
        descriptions = tuple(
            self.describe(SpecificationSelection(design_id=design_id, spec_id=c.spec_id))
            for c in self.contracts(design_id)
        )
        return SpecificationList(
            design_id=design_id,
            specifications=descriptions,
            target_status="registered"
            if any(d.contract.target is not None for d in descriptions)
            else "not_selected",
        )

    async def result(self, query: SpecificationQuery) -> SpecificationEvaluation:
        desc = self.describe(query)
        if desc.contract_sha256 != query.expected_contract_sha256:
            raise InvalidInputError("Specification contract does not match the current registry")
        c = desc.contract
        fields = dict(specification=desc, operation_id=query.operation_id)
        if c.target is None:
            return SpecificationEvaluation(
                specification=desc,
                operation_id=query.operation_id,
                status="NOT_EVALUATED",
                reason="target_not_selected",
            )
        analog = self.analog.describe(
            AnalogSelection(design_id=c.design_id, measurement_id=c.measurement_id)
        )
        if not analog.read_eligible:
            return SpecificationEvaluation(
                specification=desc,
                operation_id=query.operation_id,
                status="UNQUALIFIED",
                reason="measurement_unqualified",
            )
        if query.operation_id is None:
            return SpecificationEvaluation(
                specification=desc,
                operation_id=query.operation_id,
                status="MISSING_MEASUREMENT",
                reason="measurement_not_selected",
            )
        # Invalid admission, malformed/failed simulator results remain errors, never spec FAIL.
        measurement = await self.analog.result(
            AnalogQuery(
                design_id=c.design_id,
                measurement_id=c.measurement_id,
                expected_contract_sha256=c.measurement_contract_sha256,
                operation_id=query.operation_id,
            )
        )
        try:
            status = evaluate(c, measurement)
        except ValueError:
            raise RemoteFailureError(
                "Specification measurement identity failed validation"
            ) from None
        reasons = {
            "PASS": "target_met",
            "FAIL": "target_not_met",
            "UNQUALIFIED": "measurement_unqualified",
            "CONDITION_MISMATCH": "measurement_conditions_differ",
        }
        return SpecificationEvaluation.model_validate(
            {
                **fields,
                "status": status,
                "reason": reasons[status],
                "measurement": measurement,
                "measurement_result_sha256": canonical_digest(measurement),
            }
        )
