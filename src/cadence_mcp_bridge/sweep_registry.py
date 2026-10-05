"""Registry v5 adds a compiled RC adapter while keeping v1-v4 unchanged."""

from decimal import Decimal
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from cadence_mcp_bridge.analyses import AnalysisContract
from cadence_mcp_bridge.designs import (
    AdeBinding,
    DesignBinding,
    DesignMeasurementRegistry,
    DesignProfile,
    VariableRegistryBase,
)
from cadence_mcp_bridge.fixture_contracts import (
    FixtureAnalysis,
    FixtureMeasurement,
    completion_digest,
    fixture_digest,
)
from cadence_mcp_bridge.profiles import FIXTURE_PROFILE
from cadence_mcp_bridge.registered_measurements import RegisteredMeasurement
from cadence_mcp_bridge.variable_contracts import (
    DesignVariables,
    RangeReview,
    Unit,
    VariableContract,
    canonical_digest,
)

FIXTURE_DESIGN = "registered-rc-fixture"
FIXTURE_PDK = "builtin-rc-no-pdk"
Axis = Literal["resistance_ohm", "capacitance_f", "stop_time_s"]
BINDINGS: dict[str, Axis] = {
    "resistance": "resistance_ohm",
    "capacitance": "capacitance_f",
    "stop-time": "stop_time_s",
}


def fixture_profile() -> DesignProfile:
    return DesignProfile(
        schema_version=1,
        design_id=FIXTURE_DESIGN,
        environment_id="cadence-vm",
        pdk_adapter_id=FIXTURE_PDK,
        binding=DesignBinding(
            library="BuiltinRC",
            cell="RCFixture",
            view="template",
            ade=AdeBinding(kind="ade_l", state="NotApplicable"),
        ),
        allowed_analyses=("tran",),
        allowed_variables=tuple(BINDINGS),
        allowed_measurements=("completion",),
        allowed_corners=("nominal",),
        protected_source=True,
        work_copy_policy="owned_copy_only",
    )


class DesignSweepRegistry(VariableRegistryBase):
    schema_version: Literal[5]
    analysis_contracts: Annotated[
        tuple[AnalysisContract | FixtureAnalysis, ...], Field(max_length=48)
    ]
    measurement_contracts: Annotated[
        tuple[RegisteredMeasurement | FixtureMeasurement, ...], Field(max_length=512)
    ]

    @model_validator(mode="after")
    def closed_adapters(self) -> Self:
        fixtures = [c for c in self.analysis_contracts if isinstance(c, FixtureAnalysis)]
        fixture_readers = [
            c for c in self.measurement_contracts if isinstance(c, FixtureMeasurement)
        ]
        if len(fixtures) > 1 or len(fixture_readers) != len(fixtures):
            raise ValueError("one exact fixture analysis and reader required")
        fixture_ids = {c.design_id for c in fixtures}
        # Reuse every native v4 validator, including compiled route restrictions.
        native_sets = tuple(s for s in self.variable_sets if s.design_id not in fixture_ids)
        native_reviews = tuple(r for r in self.range_reviews if r.design_id not in fixture_ids)
        DesignMeasurementRegistry(
            schema_version=4,
            designs=tuple(p for p in self.designs if p.design_id not in fixture_ids),
            variable_sets=native_sets,
            range_reviews=native_reviews,
            analysis_contracts=tuple(
                c for c in self.analysis_contracts if isinstance(c, AnalysisContract)
            ),
            measurement_contracts=tuple(
                c for c in self.measurement_contracts if isinstance(c, RegisteredMeasurement)
            ),
        )
        for analysis in fixtures:
            profile = self.profile(analysis.design_id)
            variables = self.variable_set(analysis.design_id)
            if (
                profile != fixture_profile()
                or variables is None
                or analysis.analysis_id != "fixture-tran"
                or analysis.design_profile_sha256 != canonical_digest(profile)
                or analysis.variable_set_sha256 != canonical_digest(variables)
                or analysis.adapter_contract_sha256 != fixture_digest()
            ):
                raise ValueError("compiled fixture cannot be redirected")
            specs = {s.name: s for s in FIXTURE_PROFILE.variables}
            for v in variables.variables:
                spec = specs[BINDINGS[v.logical_id]]
                if (
                    v.cadence_binding != spec.name
                    or v.unit != spec.unit
                    or v.value_type != "real"
                    or v.range_status != "qualified"
                    or v.mutation_policy != "owned_copy_only"
                    or v.minimum is None
                    or v.maximum is None
                    or Decimal(v.minimum) < Decimal(str(spec.minimum))
                    or Decimal(v.maximum) > Decimal(str(spec.maximum))
                ):
                    raise ValueError("fixture range must stay within the reviewed profile")
            reader = fixture_readers[0]
            if (
                reader.design_id != analysis.design_id
                or reader.measurement_id != "completion"
                or reader.analysis_id != analysis.analysis_id
                or reader.analysis_contract_sha256 != canonical_digest(analysis)
                or reader.definition_sha256 != completion_digest()
            ):
                raise ValueError("fixture reader must bind exact analysis and definition")
        return self

    def analyses_for(self, design_id: str) -> tuple[AnalysisContract | FixtureAnalysis, ...]:
        self.profile(design_id)
        return tuple(c for c in self.analysis_contracts if c.design_id == design_id)

    def measurements_for(
        self,
        design_id: str,
    ) -> tuple[RegisteredMeasurement | FixtureMeasurement, ...]:
        self.profile(design_id)
        return tuple(c for c in self.measurement_contracts if c.design_id == design_id)


def fixture_sweep_registry() -> DesignSweepRegistry:
    """Explicit operator example using existing passive fixture bounds only."""
    profile = fixture_profile()
    specs = {s.name: s for s in FIXTURE_PROFILE.variables}
    variables = tuple(
        VariableContract(
            logical_id=n,
            cadence_binding=b,
            unit=cast(Unit, specs[b].unit),
            value_type="real",
            default=None,
            mutation_policy="owned_copy_only",
            range_status="qualified",
            minimum=str(specs[b].minimum),
            maximum=str(specs[b].maximum),
            step_policy="continuous",
            step=None,
            fixed_value=None,
            review_id=n + "-review",
        )
        for n, b in BINDINGS.items()
    )
    variable_set = DesignVariables(
        design_id=profile.design_id,
        design_profile_sha256=canonical_digest(profile),
        variables=variables,
    )
    reviews = tuple(
        RangeReview(
            review_id=v.logical_id + "-review",
            design_id=profile.design_id,
            design_profile_sha256=canonical_digest(profile),
            variable_contract_sha256=canonical_digest(v),
            evidence_id="existing-fixture-profile-v1",
            evidence_sha256=fixture_digest(),
            scope="operator_reviewed_project_numeric_contract",
        )
        for v in variables
    )
    analysis = FixtureAnalysis(
        design_id=profile.design_id,
        analysis_id="fixture-tran",
        design_profile_sha256=canonical_digest(profile),
        variable_set_sha256=canonical_digest(variable_set),
        adapter_contract_sha256=fixture_digest(),
    )
    measurement = FixtureMeasurement(
        design_id=profile.design_id,
        measurement_id="completion",
        analysis_id=analysis.analysis_id,
        analysis_contract_sha256=canonical_digest(analysis),
        definition_sha256=completion_digest(),
    )
    return DesignSweepRegistry(
        schema_version=5,
        designs=(profile,),
        variable_sets=(variable_set,),
        range_reviews=reviews,
        analysis_contracts=(analysis,),
        measurement_contracts=(measurement,),
    )
