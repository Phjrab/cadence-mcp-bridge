"""Reviewed read-only Cadence design discovery allowlist."""

from __future__ import annotations

import re

from cadence_mcp_bridge.errors import InvalidInputError

DISCOVERY_ALLOWLIST: dict[str, dict[str, tuple[str, ...]]] = {
    "MyFirstDesign": {
        "NOT_gate": ("schematic", "symbol"),
    },
    "MyDesignLib": {
        "Inverter": ("schematic", "symbol"),
        "Inverter_TB": ("schematic",),
    },
}

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$")


def validate_library(library: str) -> str:
    safe = _validate_identifier(library, "library")
    if safe not in DISCOVERY_ALLOWLIST:
        raise InvalidInputError("library is outside the read-only discovery allowlist")
    return safe


def validate_cell(library: str, cell: str) -> str:
    safe_library = validate_library(library)
    safe = _validate_identifier(cell, "cell")
    if safe not in DISCOVERY_ALLOWLIST[safe_library]:
        raise InvalidInputError("cell is outside the read-only discovery allowlist")
    return safe


def validate_view(library: str, cell: str, view: str) -> str:
    safe_library = validate_library(library)
    safe_cell = validate_cell(safe_library, cell)
    safe = _validate_identifier(view, "view")
    if safe not in DISCOVERY_ALLOWLIST[safe_library][safe_cell]:
        raise InvalidInputError("view is outside the read-only discovery allowlist")
    return safe


def _validate_identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise InvalidInputError(f"{label} must be a reviewed Cadence identifier")
    return value
