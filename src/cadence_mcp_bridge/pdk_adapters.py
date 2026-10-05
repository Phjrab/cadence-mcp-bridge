"""Path-free PDK capability contracts; metadata never grants execution authority."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.models import ContractModel

Id = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$", max_length=64)]
Ids = Annotated[tuple[Id, ...], Field(max_length=16)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", max_length=64)]
CapabilityId = Literal[
    "native-dc",
    "native-ac",
    "native-tran",
    "process-corners",
    "operating-point",
    "statistical",
    "device-mapping",
    "layout",
    "drc",
    "lvs",
    "pex",
]
Status = Literal["unqualified", "observed", "fixed_native_compatibility"]
LIMIT = 65_536


class PdkRejected(ValueError):
    def __init__(self) -> None:
        super().__init__("pdk_registry_invalid")


class PdkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def version(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("integer version required")
        return value


class PdkCapability(PdkModel):
    capability_id: CapabilityId
    status: Status
    evidence_ref: Id | None

    @model_validator(mode="after")
    def evidence_required(self) -> Self:
        if (self.status == "unqualified") != (self.evidence_ref is None):
            raise ValueError("observations require a logical evidence reference")
        return self


class PdkAdapter(PdkModel):
    schema_version: Literal[2]
    adapter_id: Id
    technology_id: Id
    role: Literal["regression_reference", "target_candidate"]
    environment_ids: Ids
    process_corner_ids: Ids
    rc_corner_ids: Ids
    binding_kind: Literal["unqualified", "compiled_native_reference_v1"]
    binding_ref: Id | None
    binding_sha256: Digest | None
    capabilities: Annotated[tuple[PdkCapability, ...], Field(max_length=16)]

    @model_validator(mode="after")
    def closed_binding(self) -> Self:
        for values in (self.environment_ids, self.process_corner_ids, self.rc_corner_ids):
            if len(set(values)) != len(values):
                raise ValueError("duplicate PDK identifier")
        ids = [c.capability_id for c in self.capabilities]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate PDK capability")
        if self.binding_kind == "unqualified" and (
            self.binding_ref is not None
            or self.binding_sha256 is not None
            or any(c.status == "fixed_native_compatibility" for c in self.capabilities)
        ):
            raise ValueError("unqualified adapter cannot claim a compiled binding")
        # Recomputed hashes and logical IDs must not redirect the compiled route.
        from cadence_mcp_bridge.pdk_reference import REFERENCE_ID, reference_adapter

        if (
            self.binding_kind == "compiled_native_reference_v1" or self.adapter_id == REFERENCE_ID
        ) and self.model_dump(mode="json") != reference_adapter().model_dump(mode="json"):
            raise ValueError("compiled PDK reference drift")
        return self

    def supports_native(self, environment_id: str, analysis: str) -> bool:
        return (
            self.binding_kind == "compiled_native_reference_v1"
            and environment_id in self.environment_ids
            and any(
                c.capability_id == "native-" + analysis and c.status == "fixed_native_compatibility"
                for c in self.capabilities
            )
        )


class PdkDescription(ContractModel):
    adapter_id: Id
    technology_id: Id
    role: Literal["regression_reference", "target_candidate"]
    process_corner_ids: tuple[Id, ...]
    rc_corner_ids: tuple[Id, ...]
    capabilities: tuple[PdkCapability, ...]
    execution_authorized: Literal[False] = False
    physical_bindings_included: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class PdkList(ContractModel):
    schema_version: Literal[2] = 2
    adapters: tuple[PdkDescription, ...]
    execution_authorized: Literal[False] = False


class DesignPdkStatus(ContractModel):
    design_id: Id
    adapter_id: Id
    status: Literal[
        "not_registered", "environment_mismatch", "unqualified", "fixed_native_compatibility"
    ]
    native_analyses: tuple[Literal["dc", "ac", "tran"], ...]
    generic_execution_qualified: Literal[False] = False
    execution_authorized: Literal[False] = False


class PdkRegistry(PdkModel):
    schema_version: Literal[2]
    adapters: Annotated[tuple[PdkAdapter, ...], Field(max_length=16)]

    @model_validator(mode="after")
    def unique_adapters(self) -> Self:
        ids = [a.adapter_id for a in self.adapters]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate PDK adapter")
        return self

    def find(self, adapter_id: str) -> PdkAdapter | None:
        return next((a for a in self.adapters if a.adapter_id == adapter_id), None)

    def describe(self, adapter_id: str) -> PdkDescription:
        adapter = self.find(adapter_id)
        if adapter is None:
            raise InvalidInputError("PDK adapter ID is not registered")
        return PdkDescription(
            adapter_id=adapter.adapter_id,
            technology_id=adapter.technology_id,
            role=adapter.role,
            process_corner_ids=adapter.process_corner_ids,
            rc_corner_ids=adapter.rc_corner_ids,
            capabilities=adapter.capabilities,
        )

    def listing(self) -> PdkList:
        return PdkList(adapters=tuple(self.describe(a.adapter_id) for a in self.adapters))

    def resolve(self, design_id: str, adapter_id: str, environment_id: str) -> DesignPdkStatus:
        adapter = self.find(adapter_id)
        analyses: tuple[Literal["dc", "ac", "tran"], ...] = ()
        status: Literal[
            "not_registered", "environment_mismatch", "unqualified", "fixed_native_compatibility"
        ] = "not_registered"
        if adapter is not None:
            status = "unqualified"
            if environment_id not in adapter.environment_ids:
                status = "environment_mismatch"
            elif adapter.binding_kind == "compiled_native_reference_v1":
                status = "fixed_native_compatibility"
                modes: tuple[Literal["dc", "ac", "tran"], ...] = ("dc", "ac", "tran")
                analyses = tuple(a for a in modes if adapter.supports_native(environment_id, a))
        return DesignPdkStatus(
            design_id=design_id, adapter_id=adapter_id, status=status, native_analyses=analyses
        )


def load_pdk_registry(path: Path) -> tuple[PdkRegistry, bytes]:
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
            data = stream.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError("registry too large")
        json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        registry = PdkRegistry.model_validate_json(data)
    except (OSError, ValueError, RecursionError):
        raise PdkRejected() from None
    return registry, data


def register_pdk_adapters(path: Path, output: Path) -> dict[str, object]:
    registry, data = load_pdk_registry(path)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "status": "registered_local_only",
        "adapter_count": len(registry.adapters),
        "registry_sha256": hashlib.sha256(data).hexdigest(),
        "execution_authorized": False,
    }
