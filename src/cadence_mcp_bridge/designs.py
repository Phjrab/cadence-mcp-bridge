"""Bounded operator-owned design descriptions; registration grants no execution."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.models import ContractModel
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


class DesignContractRegistry(RegistryBase):
    schema_version: Literal[2]
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
                pdk_adapter_id="gpdk090-reference-v1",
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


def load_design_registry(path: Path) -> tuple[DesignRegistry | DesignContractRegistry, bytes]:
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
        registry: DesignRegistry | DesignContractRegistry
        if version == 1:
            registry = DesignRegistry.model_validate_json(data)
        elif version == 2:
            registry = DesignContractRegistry.model_validate_json(data)
        else:
            raise ValueError("unsupported registry version")
    except (OSError, ValueError, RecursionError):
        raise DesignRejected() from None
    return registry, data


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
