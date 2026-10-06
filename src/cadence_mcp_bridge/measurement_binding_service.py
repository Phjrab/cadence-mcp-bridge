"""Discovery/evaluation adapters reuse existing admitted readers and comparison."""

from cadence_mcp_bridge.analog_service import AnalogSupervisor
from cadence_mcp_bridge.designs import RegistryBase
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.measurement_bindings import (
    DesignPowerSpecificationRegistry,
    MeasurementCatalog,
    PowerSpecificationDescription,
    SpecificationEvaluationV2,
)
from cadence_mcp_bridge.power_measurements import PowerDefinition, PowerQuery, PowerSelection
from cadence_mcp_bridge.power_service import PowerSupervisor
from cadence_mcp_bridge.specification_service import SpecificationSupervisor
from cadence_mcp_bridge.specifications import SpecificationQuery, evaluate_fact
from cadence_mcp_bridge.variable_contracts import canonical_digest


class MeasurementBindingSupervisor:
    def __init__(
        self,
        registry: RegistryBase,
        analog: AnalogSupervisor,
        power: PowerSupervisor,
        specifications: SpecificationSupervisor,
    ) -> None:
        self.registry, self.analog = registry, analog
        self.power, self.specifications = power, specifications

    def catalog(self, design_id: str) -> MeasurementCatalog:
        analog = self.analog.listing(design_id)
        power = tuple(
            self.power.describe(
                PowerSelection(design_id=design_id, measurement_id=c.measurement_id)
            )
            for c in self.analog.contracts(design_id)
            if c.metric == "power"
        )
        goals = self.specifications.listing(design_id).specifications
        new_goals: tuple[PowerSpecificationDescription, ...] = ()
        if isinstance(self.registry, DesignPowerSpecificationRegistry):
            new_goals = tuple(
                PowerSpecificationDescription(
                    contract=c,
                    contract_sha256=canonical_digest(c),
                    target_status="not_selected" if c.target is None else "registered",
                )
                for c in self.registry.power_specification_contracts
                if c.design_id == design_id
            )
        return MeasurementCatalog(
            design_id=design_id,
            analog=analog.measurements,
            signed_dc_power=power,
            specifications=(*goals, *new_goals),
            target_status="registered"
            if (
                any(d.target_status == "registered" for d in goals)
                or any(d.target_status == "registered" for d in new_goals)
            )
            else "not_selected",
        )

    async def result(self, query: SpecificationQuery) -> SpecificationEvaluationV2:
        desc = next(
            (
                d
                for d in self.catalog(query.design_id).specifications
                if d.contract.spec_id == query.spec_id
            ),
            None,
        )
        if desc is None:
            raise InvalidInputError("Specification ID is not registered for this design")
        if desc.contract_sha256 != query.expected_contract_sha256:
            raise InvalidInputError("Specification contract does not match the current registry")
        if not isinstance(desc, PowerSpecificationDescription):
            legacy = await self.specifications.result(query)
            return SpecificationEvaluationV2.model_validate(
                {**legacy.model_dump(), "contract_version": 2}
            )
        c = desc.contract
        fields = dict(specification=desc, operation_id=query.operation_id)
        if c.target is None:
            return SpecificationEvaluationV2(
                specification=desc,
                operation_id=query.operation_id,
                status="NOT_EVALUATED",
                reason="target_not_selected",
            )
        selected = PowerSelection(design_id=c.design_id, measurement_id=c.measurement_id)
        binding = self.power.describe(selected)
        if not binding.read_eligible:
            return SpecificationEvaluationV2(
                specification=desc,
                operation_id=query.operation_id,
                status="UNQUALIFIED",
                reason="measurement_unqualified",
            )
        if query.operation_id is None:
            return SpecificationEvaluationV2(
                specification=desc,
                operation_id=query.operation_id,
                status="MISSING_MEASUREMENT",
                reason="measurement_not_selected",
            )
        measurement = await self.power.result(
            PowerQuery(
                **selected.model_dump(),
                operation_id=query.operation_id,
                expected_contract_sha256=c.measurement_contract_sha256,
            )
        )
        if (
            measurement.design_id != c.design_id
            or measurement.measurement_id != c.measurement_id
            or measurement.operation_id != query.operation_id
            or measurement.contract_sha256 != c.measurement_contract_sha256
            or canonical_digest(measurement.definition) != c.definition_sha256
            or measurement.definition != PowerDefinition()
            or measurement.definition.unit != c.unit
            or binding.source_measurement_id != measurement.source_measurement_id
        ):
            raise RemoteFailureError("Specification measurement identity failed validation")
        status = evaluate_fact(c, measurement.status, measurement.value, measurement.provenance)
        reasons = {
            "PASS": "target_met",
            "FAIL": "target_not_met",
            "UNQUALIFIED": "measurement_unqualified",
            "CONDITION_MISMATCH": "measurement_conditions_differ",
        }
        return SpecificationEvaluationV2.model_validate(
            {
                **fields,
                "status": status,
                "reason": reasons[status],
                "measurement": measurement,
                "measurement_result_sha256": canonical_digest(measurement),
            }
        )
