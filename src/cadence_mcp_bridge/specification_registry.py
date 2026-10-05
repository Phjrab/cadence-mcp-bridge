"""Registry v7 adds read-only goal contracts, preserving every execution identity."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.analog_measurements import definition
from cadence_mcp_bridge.analog_registry import DesignAnalogRegistry, reference_analog_registry
from cadence_mcp_bridge.specifications import SpecificationContract
from cadence_mcp_bridge.variable_contracts import canonical_digest


class DesignSpecificationRegistry(DesignAnalogRegistry):
    schema_version: Literal[7]  # type: ignore[assignment]
    specification_contracts: Annotated[tuple[SpecificationContract, ...], Field(max_length=128)]

    def sweep_identity_digest(self) -> str:
        payload = self.model_dump(exclude={"specification_contracts"})
        payload["schema_version"] = 6
        return DesignAnalogRegistry.model_validate(payload).sweep_identity_digest()

    @model_validator(mode="after")
    def bound_specifications(self) -> Self:
        seen: set[tuple[str, str]] = set()
        counts: dict[str, int] = {}
        for c in self.specification_contracts:
            self.profile(c.design_id)
            key = (c.design_id, c.spec_id)
            counts[c.design_id] = counts.get(c.design_id, 0) + 1
            if key in seen or counts[c.design_id] > 32:
                raise ValueError("duplicate specification or per-design limit exceeded")
            seen.add(key)
            if not any(
                a.analysis_id == c.conditions.analysis_id for a in self.analyses_for(c.design_id)
            ):
                raise ValueError("specification analysis must be registered for this design")
            analog = next(
                (
                    a
                    for a in self.analog_contracts
                    if (a.design_id, a.measurement_id) == (c.design_id, c.measurement_id)
                ),
                None,
            )
            if (
                analog is None
                or canonical_digest(analog) != c.measurement_contract_sha256
                or analog.definition_sha256 != c.definition_sha256
                or definition(analog.metric).unit != c.unit
            ):
                raise ValueError("specification requires exact registered measurement and unit")
            if analog.source_measurement_id is not None:
                source = next(
                    m
                    for m in self.measurements_for(c.design_id)
                    if m.measurement_id == analog.source_measurement_id
                )
                if source.analysis_id != c.conditions.analysis_id:
                    raise ValueError("specification analysis differs from measurement source")
        return self


def reference_specification_registry() -> DesignSpecificationRegistry:
    """No user numerical targets exist for the reference; never invent them."""
    return DesignSpecificationRegistry(
        **{**reference_analog_registry().model_dump(), "schema_version": 7},
        specification_contracts=(),
    )
