"""Operator registry v6: derived allowlists around unchanged v5 source contracts."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.analog_measurements import AnalogContract, definition, definitions
from cadence_mcp_bridge.designs import reference_measurement_registry
from cadence_mcp_bridge.registered_measurements import RegisteredMeasurement
from cadence_mcp_bridge.sweep_registry import DesignSweepRegistry
from cadence_mcp_bridge.variable_contracts import canonical_digest


class DesignAnalogRegistry(DesignSweepRegistry):
    schema_version: Literal[6]  # type: ignore[assignment]
    analog_contracts: Annotated[tuple[AnalogContract, ...], Field(max_length=96)]

    def sweep_identity_digest(self) -> str:
        # Only new read-only analog metadata is excluded. Every v5 execution field
        # passes the original closed validators and contributes to durable identity.
        payload = self.model_dump(exclude={"analog_contracts"})
        payload["schema_version"] = 5
        return canonical_digest(DesignSweepRegistry.model_validate(payload))

    @model_validator(mode="after")
    def bound_analog(self) -> Self:
        seen: set[tuple[str, str]] = set()
        metrics: set[tuple[str, str]] = set()
        for c in self.analog_contracts:
            self.profile(c.design_id)
            key, metric = (c.design_id, c.measurement_id), (c.design_id, c.metric)
            if key in seen or metric in metrics:
                raise ValueError("duplicate analog identity or metric")
            seen.add(key)
            metrics.add(metric)
            sources = self.measurements_for(c.design_id)
            if any(s.measurement_id == c.measurement_id for s in sources):
                raise ValueError("derived and source measurement IDs must differ")
            if c.source_measurement_id is None:
                continue
            source = next((s for s in sources if s.measurement_id == c.source_measurement_id), None)
            if (
                not isinstance(source, RegisteredMeasurement)
                or c.source_contract_sha256 != canonical_digest(source)
                or source.reader != "native-bounded-result-v1"
                or source.output_id != definition(c.metric).source_output_id
            ):
                raise ValueError("analog reader requires exact registered native source")
        return self


def reference_analog_registry() -> DesignAnalogRegistry:
    """Keep the existing reference design/profile/variable/analysis identities exact."""
    source = reference_measurement_registry()
    ac = next(
        c for c in source.measurement_contracts if c.output_id == "ac-differential-spectrum-v1"
    )
    return DesignAnalogRegistry(
        **{**source.model_dump(), "schema_version": 6},
        analog_contracts=tuple(
            AnalogContract(
                design_id=source.designs[0].design_id,
                measurement_id="analog-" + d.metric,
                metric=d.metric,
                definition_sha256=canonical_digest(d),
                source_measurement_id=ac.measurement_id if d.source_output_id else None,
                source_contract_sha256=canonical_digest(ac) if d.source_output_id else None,
            )
            for d in definitions()
        ),
    )
