"""Bounded operator-owned design descriptions; registration grants no execution."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cadence_mcp_bridge.analyses import AnalysisContract, native_adapter_digest
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.fixture_contracts import FixtureAnalysis, FixtureMeasurement
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.pdk_reference import REFERENCE_ID
from cadence_mcp_bridge.registered_measurements import (
    RegisteredMeasurement,
    definition,
    definitions,
)
from cadence_mcp_bridge.variable_contracts import (
    DesignVariables,
    RangeReview,
    VariableContract,
    VariableList,
    VariableValuesRequest,
    VariableValuesResult,
    canonical_digest,
    check_values,
    describe_variables,
)

LogicalId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$", max_length=64)]
BindingName = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$", max_length=64)]
Analysis = Literal["dc", "ac", "tran"]
Ids = Annotated[tuple[LogicalId, ...], Field(max_length=32)]
REGISTRY_LIMIT = 65_536


class DesignRejected(ValueError):
    """A fixed error without private bindings, paths or validation payloads."""

    def __init__(self) -> None:
        super().__init__("design_registry_invalid")


class DesignModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def integer_version(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value


class AdeBinding(DesignModel):
    kind: Literal["ade_l", "ade_xl", "explorer", "assembler"]
    state: BindingName


class DesignBinding(DesignModel):
    library: BindingName
    cell: BindingName
    view: BindingName
    ade: AdeBinding


class DesignProfile(DesignModel):
    schema_version: Literal[1]
    design_id: LogicalId
    environment_id: LogicalId
    pdk_adapter_id: LogicalId
    binding: DesignBinding
    allowed_analyses: Annotated[tuple[Analysis, ...], Field(max_length=3)]
    allowed_variables: Ids
    allowed_measurements: Ids
    allowed_corners: Ids
    protected_source: Literal[True]
    work_copy_policy: Literal["read_only", "owned_copy_only"]

    @field_validator("protected_source", mode="before")
    @classmethod
    def protected_boolean(cls, value: Any) -> bool:
        if value is not True:
            raise ValueError("source protection required")
        return True

    @model_validator(mode="after")
    def unique_allowlists(self) -> Self:
        for values in (
            self.allowed_analyses,
            self.allowed_variables,
            self.allowed_measurements,
            self.allowed_corners,
        ):
            if len(set(values)) != len(values):
                raise ValueError("duplicate allowlist identifier")
        return self


class RegistryBase(DesignModel):
    schema_version: int
    designs: Annotated[tuple[DesignProfile, ...], Field(max_length=16)]

    @model_validator(mode="after")
    def unique_designs(self) -> Self:
        ids = [design.design_id for design in self.designs]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate design identifier")
        return self

    def profile(self, design_id: str) -> DesignProfile:
        for profile in self.designs:
            if profile.design_id == design_id:
                return profile
        raise InvalidInputError("Design ID is not registered")

    def variable_set(self, design_id: str) -> DesignVariables | None:
        self.profile(design_id)
        return None

    def analyses_for(self, design_id: str) -> tuple[AnalysisContract | FixtureAnalysis, ...]:
        self.profile(design_id)
        return ()

    def measurements_for(
        self, design_id: str
    ) -> tuple[RegisteredMeasurement | FixtureMeasurement, ...]:
        self.profile(design_id)
        return ()

    def sweep_identity_digest(self) -> str:
        """Old registries retain their full snapshot identity for durable sweep replay."""
        return canonical_digest(self)

    def variables(self, design_id: str) -> VariableList:
        profile = self.profile(design_id)
        return describe_variables(
            design_id, profile.allowed_variables, self.variable_set(design_id)
        )

    def check_variables(self, request: VariableValuesRequest) -> VariableValuesResult:
        profile = self.profile(request.design_id)
        return check_values(request, self.variable_set(request.design_id), profile.work_copy_policy)

    def describe(self, design_id: str) -> DesignDescription:
        # Exact lookup only. No interpolation, normalization or remote discovery.
        for profile in self.designs:
            if profile.design_id == design_id:
                return DesignDescription(
                    design_id=profile.design_id,
                    environment_id=profile.environment_id,
                    pdk_adapter_id=profile.pdk_adapter_id,
                    allowed_analyses=profile.allowed_analyses,
                    allowed_variables=profile.allowed_variables,
                    allowed_measurements=profile.allowed_measurements,
                    allowed_corners=profile.allowed_corners,
                    work_copy_policy=profile.work_copy_policy,
                )
        raise InvalidInputError("Design ID is not registered")

    def listing(self) -> DesignList:
        return DesignList(
            designs=tuple(
                DesignSummary(
                    design_id=profile.design_id,
                    environment_id=profile.environment_id,
                    pdk_adapter_id=profile.pdk_adapter_id,
                )
                for profile in self.designs
            )
        )


class DesignRegistry(RegistryBase):
    schema_version: Literal[1]


class VariableRegistryBase(RegistryBase):
    variable_sets: Annotated[tuple[DesignVariables, ...], Field(max_length=16)]
    range_reviews: Annotated[tuple[RangeReview, ...], Field(max_length=512)]

    @model_validator(mode="after")
    def bound_numeric_reviews(self) -> Self:
        profiles = {profile.design_id: profile for profile in self.designs}
        sets = [item.design_id for item in self.variable_sets]
        reviews = {review.review_id: review for review in self.range_reviews}
        if len(set(sets)) != len(sets) or len(reviews) != len(self.range_reviews):
            raise ValueError("duplicate variable set or range review")
        used_reviews: set[str] = set()
        for item in self.variable_sets:
            profile = profiles.get(item.design_id)
            if profile is None or item.design_profile_sha256 != canonical_digest(profile):
                raise ValueError("variable set must bind the exact registered design profile")
            if {v.logical_id for v in item.variables} != set(profile.allowed_variables):
                raise ValueError("variable contracts must match the design allowlist")
            for variable in item.variables:
                if variable.range_status != "qualified":
                    continue
                review = reviews.get(variable.review_id or "")
                if (
                    review is None
                    or review.review_id in used_reviews
                    or review.design_id != item.design_id
                    or review.design_profile_sha256 != item.design_profile_sha256
                    or review.variable_contract_sha256 != canonical_digest(variable)
                ):
                    raise ValueError("qualified range requires an exact separate numeric review")
                used_reviews.add(review.review_id)
        if used_reviews != set(reviews):
            raise ValueError("orphan numeric review")
        return self

    def variable_set(self, design_id: str) -> DesignVariables | None:
        self.profile(design_id)
        return next((item for item in self.variable_sets if item.design_id == design_id), None)


class DesignContractRegistry(VariableRegistryBase):
    schema_version: Literal[2]


class AnalysisRegistryBase(VariableRegistryBase):
    analysis_contracts: Annotated[tuple[AnalysisContract, ...], Field(max_length=48)]

    @model_validator(mode="after")
    def bound_analysis_adapters(self) -> Self:
        seen: set[tuple[str, str]] = set()
        modes: set[tuple[str, str]] = set()
        reference = reference_contract_registry()
        for contract in self.analysis_contracts:
            key = (contract.design_id, contract.analysis_id)
            mode = (contract.design_id, contract.analysis)
            if key in seen or mode in modes:
                raise ValueError("duplicate registered analysis identity or mode")
            seen.add(key)
            modes.add(mode)
            profile = next((p for p in self.designs if p.design_id == contract.design_id), None)
            if (
                profile is None
                or contract.design_profile_sha256 != canonical_digest(profile)
                or contract.analysis not in profile.allowed_analyses
            ):
                raise ValueError("analysis must bind an exact allowed design profile")
            variables = self.variable_set(contract.design_id)
            if contract.variable_set_sha256 is not None and (
                variables is None or contract.variable_set_sha256 != canonical_digest(variables)
            ):
                raise ValueError("analysis variable set drift")
            if contract.adapter_kind == "native-fixed-reference-v1" and (
                profile != reference.designs[0] or variables != reference.variable_sets[0]
            ):
                raise ValueError("compiled native adapter is restricted to its reviewed reference")
        return self

    def analyses_for(self, design_id: str) -> tuple[AnalysisContract, ...]:
        self.profile(design_id)
        return tuple(item for item in self.analysis_contracts if item.design_id == design_id)


class DesignAnalysisRegistry(AnalysisRegistryBase):
    schema_version: Literal[3]


class DesignMeasurementRegistry(AnalysisRegistryBase):
    schema_version: Literal[4]
    measurement_contracts: Annotated[tuple[RegisteredMeasurement, ...], Field(max_length=512)]

    @model_validator(mode="after")
    def bound_measurements(self) -> Self:
        seen: set[tuple[str, str]] = set()
        for contract in self.measurement_contracts:
            key = (contract.design_id, contract.measurement_id)
            if key in seen:
                raise ValueError("duplicate measurement identity")
            seen.add(key)
            profile = next((p for p in self.designs if p.design_id == contract.design_id), None)
            analysis = next(
                (
                    c
                    for c in self.analysis_contracts
                    if c.design_id == contract.design_id and c.analysis_id == contract.analysis_id
                ),
                None,
            )
            if (
                profile is None
                or contract.measurement_id not in profile.allowed_measurements
                or analysis is None
                or contract.analysis_contract_sha256 != canonical_digest(analysis)
            ):
                raise ValueError("measurement must bind an exact allowed analysis contract")
            if contract.reader == "native-bounded-result-v1" and (
                analysis.adapter_kind != "native-fixed-reference-v1"
                or contract.output_id is None
                or definition(contract.output_id).analysis != analysis.analysis
            ):
                raise ValueError("compiled reader requires the matching qualified native analysis")
        return self

    def measurements_for(self, design_id: str) -> tuple[RegisteredMeasurement, ...]:
        self.profile(design_id)
        return tuple(c for c in self.measurement_contracts if c.design_id == design_id)


class DesignSummary(ContractModel):
    design_id: LogicalId
    environment_id: LogicalId
    pdk_adapter_id: LogicalId
    registration_status: Literal["registered_description"] = "registered_description"
    qualification_status: Literal["unqualified"] = "unqualified"
    execution_authorized: Literal[False] = False


class DesignDescription(DesignSummary):
    schema_version: Literal[1] = 1
    allowed_analyses: tuple[Analysis, ...]
    allowed_variables: tuple[LogicalId, ...]
    allowed_measurements: tuple[LogicalId, ...]
    allowed_corners: tuple[LogicalId, ...]
    protected_source: Literal[True] = True
    work_copy_policy: Literal["read_only", "owned_copy_only"]
    environment_binding_status: Literal["not_resolved"] = "not_resolved"
    pdk_adapter_status: Literal["not_resolved"] = "not_resolved"
    variable_ranges_status: Literal["unqualified"] = "unqualified"
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class DesignList(ContractModel):
    schema_version: Literal[1] = 1
    designs: tuple[DesignSummary, ...]
    execution_authorized: Literal[False] = False


def reference_registry() -> DesignRegistry:
    """Compatibility description, never a replacement for existing native guards."""
    return DesignRegistry(
        schema_version=1,
        designs=(
            DesignProfile(
                schema_version=1,
                design_id="reference-differential-amplifier-tb2",
                environment_id="cadence-vm",
                pdk_adapter_id=REFERENCE_ID,
                binding=DesignBinding(
                    library="MyDesignLib",
                    cell="Differential_Amplifier_TB2",
                    view="schematic",
                    ade=AdeBinding(kind="ade_l", state="state1"),
                ),
                allowed_analyses=("dc", "ac", "tran"),
                allowed_variables=("vbiasn", "vbiasp", "vdd"),
                allowed_measurements=("dc-scalars", "ac-spectrum", "tran-summary"),
                allowed_corners=("nn", "ff", "ss", "fs", "sf"),
                protected_source=True,
                work_copy_policy="owned_copy_only",
            ),
        ),
    )


def reference_contract_registry() -> DesignContractRegistry:
    """Reference bias ranges are unknown; VDD is a fixed user constraint only."""
    profile = reference_registry().designs[0]
    variables = tuple(
        VariableContract(
            logical_id=logical_id,
            cadence_binding=binding,
            unit="V",
            value_type="real",
            default="1" if logical_id == "vdd" else None,
            mutation_policy="fixed" if logical_id == "vdd" else "owned_copy_only",
            range_status="unqualified",
            minimum=None,
            maximum=None,
            step_policy="fixed" if logical_id == "vdd" else "unqualified",
            step=None,
            fixed_value="1" if logical_id == "vdd" else None,
            review_id=None,
        )
        for logical_id, binding in (("vbiasn", "VBIASN"), ("vbiasp", "VBIASP"), ("vdd", "VDD"))
    )
    return DesignContractRegistry(
        schema_version=2,
        designs=(profile,),
        range_reviews=(),
        variable_sets=(
            DesignVariables(
                design_id=profile.design_id,
                design_profile_sha256=canonical_digest(profile),
                variables=variables,
            ),
        ),
    )


def reference_analysis_registry() -> DesignAnalysisRegistry:
    reference = reference_contract_registry()
    profile = reference.designs[0]
    return DesignAnalysisRegistry(
        schema_version=3,
        designs=reference.designs,
        variable_sets=reference.variable_sets,
        range_reviews=reference.range_reviews,
        analysis_contracts=tuple(
            AnalysisContract(
                design_id=profile.design_id,
                analysis_id="native-" + analysis,
                analysis=analysis,
                design_profile_sha256=canonical_digest(profile),
                variable_set_sha256=canonical_digest(reference.variable_sets[0]),
                adapter_kind="native-fixed-reference-v1",
                adapter_contract_sha256=native_adapter_digest(),
                input_policy="fixed_operating_point_no_parameters",
            )
            for analysis in profile.allowed_analyses
        ),
    )


def load_design_registry(
    path: Path,
) -> tuple[RegistryBase, bytes]:
    """Snapshot an explicit local operator file once, with closed bounded JSON."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise ValueError("nonfinite JSON")

    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("regular registry required")
        with path.open("rb") as stream:
            data = stream.read(REGISTRY_LIMIT + 1)
        if len(data) > REGISTRY_LIMIT:
            raise ValueError("registry too large")
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
            raise ValueError("integer registry version required")
        version = payload["schema_version"]
        registry: RegistryBase
        if version == 1:
            registry = DesignRegistry.model_validate_json(data)
        elif version == 2:
            registry = DesignContractRegistry.model_validate_json(data)
        elif version == 3:
            registry = DesignAnalysisRegistry.model_validate_json(data)
        elif version == 4:
            registry = DesignMeasurementRegistry.model_validate_json(data)
        elif version == 5:
            from cadence_mcp_bridge.sweep_registry import DesignSweepRegistry

            registry = DesignSweepRegistry.model_validate_json(data)
        elif version == 6:
            from cadence_mcp_bridge.analog_registry import DesignAnalogRegistry

            registry = DesignAnalogRegistry.model_validate_json(data)
        else:
            raise ValueError("unsupported registry version")
    except (OSError, ValueError, RecursionError):
        raise DesignRejected() from None
    return registry, data


def reference_measurement_registry() -> DesignMeasurementRegistry:
    """Same pinned reference profile/analyses; additive registered readers only."""
    reference = reference_analysis_registry()
    contracts = tuple(
        RegisteredMeasurement(
            design_id=analysis.design_id,
            measurement_id=measurement_id,
            analysis_id=analysis.analysis_id,
            analysis_contract_sha256=canonical_digest(analysis),
            reader="native-bounded-result-v1",
            output_id=output.output_id,
            definition_sha256=canonical_digest(output),
        )
        for analysis, measurement_id, output in zip(
            reference.analysis_contracts,
            reference.designs[0].allowed_measurements,
            definitions(),
            strict=True,
        )
    )
    return DesignMeasurementRegistry(
        **{**reference.model_dump(), "schema_version": 4},
        measurement_contracts=contracts,
    )


def register_designs(path: Path, output: Path) -> dict[str, object]:
    """Exclusive local copy; no deployment, activation, lookup or source access."""
    registry, data = load_design_registry(path)
    # os.open's exclusive creation also refuses an existing or dangling symlink.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "status": "registered_local_only",
        "design_count": len(registry.designs),
        "registry_sha256": hashlib.sha256(data).hexdigest(),
        "execution_authorized": False,
    }
