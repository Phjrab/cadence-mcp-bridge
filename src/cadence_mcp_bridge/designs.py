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


class DesignRegistry(DesignModel):
    schema_version: Literal[1]
    designs: Annotated[tuple[DesignProfile, ...], Field(max_length=16)]

    @model_validator(mode="after")
    def unique_designs(self) -> Self:
        ids = [design.design_id for design in self.designs]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate design identifier")
        return self

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


def load_design_registry(path: Path) -> tuple[DesignRegistry, bytes]:
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
        json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        registry = DesignRegistry.model_validate_json(data)
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
