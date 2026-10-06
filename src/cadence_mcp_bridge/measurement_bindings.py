"""Versioned discovery and goals for the existing signed DC power reader."""

import json
from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.analog_measurements import AnalogDescription, AnalogResult
from cadence_mcp_bridge.analog_registry import DesignAnalogRegistry
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.power_measurements import PowerBinding, PowerDefinition, PowerDescription
from cadence_mcp_bridge.power_measurements import PowerResult as PowerResult
from cadence_mcp_bridge.registered_measurements import RegisteredMeasurement
from cadence_mcp_bridge.specification_registry import (
    DesignSpecificationRegistry,
    reference_specification_registry,
)
from cadence_mcp_bridge.specifications import (
    SpecificationContract,
    SpecificationDescription,
    SpecificationEvaluation,
)
from cadence_mcp_bridge.variable_contracts import LogicalId, canonical_digest


class PowerSpecificationContract(SpecificationContract):
    contract_version: Literal[2] = 2  # type: ignore[assignment]
    unit: Literal["W"]


def power_binding(
    registry: DesignAnalogRegistry, design_id: str, measurement_id: str
) -> tuple[str, RegisteredMeasurement | None]:
    """Same immutable binding as PowerSupervisor; no eligibility/transport assertion."""
    analog = next(
        (
            c
            for c in registry.analog_contracts
            if (c.design_id, c.measurement_id, c.metric) == (design_id, measurement_id, "power")
        ),
        None,
    )
    if analog is None:
        raise ValueError("power specification requires registered power metric")
    sources = [
        m
        for m in registry.measurements_for(design_id)
        if isinstance(m, RegisteredMeasurement)
        and m.reader == "native-bounded-result-v1"
        and m.output_id == "dc-node-scalars-v1"
    ]
    source = sources[0] if len(sources) == 1 else None
    return canonical_digest(
        PowerBinding(
            definition_sha256=canonical_digest(PowerDefinition()),
            analog_contract_sha256=canonical_digest(analog),
            dc_contract_sha256=canonical_digest(source) if source else None,
        )
    ), source


class DesignPowerSpecificationRegistry(DesignSpecificationRegistry):
    schema_version: Literal[8]  # type: ignore[assignment]
    power_specification_contracts: Annotated[
        tuple[PowerSpecificationContract, ...], Field(max_length=128)
    ]

    def sweep_identity_digest(self) -> str:
        payload = self.model_dump(exclude={"power_specification_contracts"})
        payload["schema_version"] = 7
        return DesignSpecificationRegistry.model_validate(payload).sweep_identity_digest()

    @model_validator(mode="after")
    def bound_power_goals(self) -> Self:
        seen = {(c.design_id, c.spec_id) for c in self.specification_contracts}
        counts: dict[str, int] = {}
        for c in (*self.specification_contracts, *self.power_specification_contracts):
            counts[c.design_id] = counts.get(c.design_id, 0) + 1
            if counts[c.design_id] > 32:
                raise ValueError("combined per-design specification limit exceeded")
        for c in self.power_specification_contracts:
            self.profile(c.design_id)
            key = c.design_id, c.spec_id
            if key in seen:
                raise ValueError("duplicate versioned specification identity")
            seen.add(key)
            digest, source = power_binding(self, c.design_id, c.measurement_id)
            if (
                source is None
                or c.measurement_contract_sha256 != digest
                or c.definition_sha256 != canonical_digest(PowerDefinition())
                or c.conditions.analysis_id != source.analysis_id
            ):
                raise ValueError(
                    "power goal requires exact definition, DC source and reader binding"
                )
        return self


def reference_power_specification_registry() -> DesignPowerSpecificationRegistry:
    """Empty user goals; adding a catalog cannot manufacture a design requirement."""
    return DesignPowerSpecificationRegistry(
        **{**reference_specification_registry().model_dump(), "schema_version": 8},
        power_specification_contracts=(),
    )


class PowerSpecificationDescription(ContractModel):
    contract: PowerSpecificationContract
    contract_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_status: Literal["registered", "not_selected"]
    execution_authorized: Literal[False] = False

    @field_validator("contract", mode="before")
    @classmethod
    def json_contract(cls, value: Any) -> PowerSpecificationContract:
        if isinstance(value, PowerSpecificationContract):
            return value
        return PowerSpecificationContract.model_validate_json(json.dumps(value))


class SpecificationEvaluationV2(SpecificationEvaluation):
    contract_version: Literal[2] = 2  # type: ignore[assignment]
    specification: SpecificationDescription | PowerSpecificationDescription  # type: ignore[assignment]
    measurement: AnalogResult | PowerResult | None = None  # type: ignore[assignment]


class MeasurementCatalog(ContractModel):
    schema_version: Literal[1] = 1
    design_id: LogicalId
    analog: Annotated[tuple[AnalogDescription, ...], Field(max_length=6)]
    signed_dc_power: Annotated[tuple[PowerDescription, ...], Field(max_length=1)]
    specifications: Annotated[
        tuple[SpecificationDescription | PowerSpecificationDescription, ...], Field(max_length=32)
    ]
    analog_result_tool: Literal["cadence_analog_measurement_result"] = (
        "cadence_analog_measurement_result"
    )
    signed_dc_power_result_tool: Literal["cadence_power_measurement_result"] = (
        "cadence_power_measurement_result"
    )
    specification_result_tool: Literal["cadence_evaluate_specification_v2"] = (
        "cadence_evaluate_specification_v2"
    )
    target_status: Literal["registered", "not_selected"]
    execution_authorized: Literal[False] = False
