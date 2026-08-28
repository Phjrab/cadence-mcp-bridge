"""Fail-closed readiness policy for future copy-based design mutations."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.models import ContractModel

_LIBRARY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_PROTECTED_LIBRARY_NAMES = frozenset({"analoglib", "basic", "gpdk090"})
_SOURCE_LIBRARY_NAMES = frozenset({"MyDesignLib", "MyFirstDesign"})
_WORK_LIBRARY_NAME = "MCP_WorkLib"


class LibraryWriteClassification(ContractModel):
    library: str
    classification: Literal["pdk-or-shared", "source", "work", "unconfigured"]
    writable: bool = False
    reason: str


class DesignWriteReadiness(ContractModel):
    policy_version: Literal[2] = 2
    status: Literal["ready"] = "ready"
    protected_library_names: tuple[str, ...]
    source_library_names: tuple[str, ...]
    work_library: Literal["MCP_WorkLib"] = "MCP_WorkLib"
    allowed_mutations: tuple[Literal["set_cellview_property:mcpMutationTest=validated-v1"], ...]
    dry_run_available: Literal[True] = True
    apply_available: Literal[True] = True
    rollback_available: Literal[True] = True
    release_ready: Literal[False] = False
    required_inputs: tuple[str, ...] = Field(min_length=3)


WRITE_READINESS = DesignWriteReadiness(
    protected_library_names=("analogLib", "basic", "gpdk090"),
    source_library_names=("MyDesignLib", "MyFirstDesign"),
    allowed_mutations=("set_cellview_property:mcpMutationTest=validated-v1",),
    required_inputs=("none", "user contract approved", "fixed confirmation still required"),
)


def get_write_readiness() -> DesignWriteReadiness:
    """Return the immutable readiness state without contacting Cadence."""

    return WRITE_READINESS


def classify_write_target(library: str) -> LibraryWriteClassification:
    """Classify a proposed library while keeping every current target non-writable."""

    if not _LIBRARY_PATTERN.fullmatch(library):
        raise InvalidInputError("library name does not match the closed identifier schema")
    lowered = library.lower()
    if lowered in _PROTECTED_LIBRARY_NAMES or lowered.startswith("gpdk"):
        return LibraryWriteClassification(
            library=library,
            classification="pdk-or-shared",
            reason="PDK and shared libraries are permanently read-only",
        )
    if library in _SOURCE_LIBRARY_NAMES:
        return LibraryWriteClassification(
            library=library,
            classification="source",
            reason="reviewed source libraries remain read-only; mutations require a copy",
        )
    if library == _WORK_LIBRARY_NAME:
        return LibraryWriteClassification(
            library=library,
            classification="work",
            writable=True,
            reason="only the reviewed copy-based mutation is eligible after confirmation",
        )
    return LibraryWriteClassification(
        library=library,
        classification="unconfigured",
        reason="no dedicated work library is configured or approved",
    )


def require_write_ready(library: str) -> None:
    """Reject every write until a reviewed work-library contract replaces this gate."""

    classification = classify_write_target(library)
    if classification.classification == "work":
        return
    if classification.classification != "unconfigured":
        raise InvalidInputError(classification.reason)
    raise ConfigurationError(
        "design writes are blocked until the work-library contract is approved"
    )
