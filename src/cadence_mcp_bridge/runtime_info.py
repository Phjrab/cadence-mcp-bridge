"""Bounded local metadata for the loaded server, never an execution preflight."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.variable_contracts import Digest


class LoadedCatalog(ContractModel):
    source: Literal["builtin_reference", "operator_supplied"]
    schema_version: Annotated[int, Field(ge=1, le=7)]
    entry_count: Annotated[int, Field(ge=0, le=16)]
    semantic_sha256: Digest


class JournalSelection(ContractModel):
    analysis: Literal["platform_default", "operator_supplied"]
    sweep: Literal["package_relative_default", "operator_supplied"]
    health_assessed: Literal[False] = False


class RuntimeInfo(ContractModel):
    schema_version: Literal[1] = 1
    bridge_version: Annotated[str, Field(min_length=1, max_length=64)]
    transport: Literal["stdio"] = "stdio"
    observation_scope: Literal["loaded_local_configuration"] = "loaded_local_configuration"
    designs: LoadedCatalog
    pdks: LoadedCatalog
    journals: JournalSelection
    remote_contact: Literal[False] = False
    execution_authority_assessed: Literal[False] = False
    environment_qualification_assessed: Literal[False] = False
