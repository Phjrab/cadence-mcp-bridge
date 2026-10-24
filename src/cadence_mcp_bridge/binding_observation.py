"""Pure closed contracts for a fixed owned-copy OA binding observation.

Rendering and parsing perform no I/O. A valid frame is bounded observation data,
not source authenticity, transport evidence, electrical qualification or execution
authority. The separate operator runner must establish those provenance guards.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    LogicalId,
    VariableModel,
    canonical_digest,
)

MAX_FRAME_BYTES = 65_536
MAX_INSTANCES = 64
MAX_PROPERTIES_PER_INSTANCE = 32
MAX_MATCHES_PER_VARIABLE = 4
MAX_MATCHES = 16
OUTPUT_LEAF = "binding-frame.txt"

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_#-]{0,63}\Z")
_UNIT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_#-]{0,63}\Z")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_COUNT = re.compile(r"(?:0|[1-9][0-9]{0,3})\Z")
_UNAVAILABLE = frozenset({"missing", "read_error", "wrong_type", "unsupported_value"})


class BindingScanVariable(VariableModel):
    logical_id: LogicalId
    cadence_binding: BindingName


class BindingScanRequest(VariableModel):
    schema_version: Literal[1]
    observation_id: OperationId
    nonce: Digest
    library: BindingName
    cell: BindingName
    view: Literal["schematic"]
    variables: Annotated[tuple[BindingScanVariable, ...], Field(min_length=1, max_length=4)]

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_schema(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value

    @model_validator(mode="after")
    def distinct_variables(self) -> Self:
        if len({variable.logical_id for variable in self.variables}) != len(self.variables):
            raise ValueError("distinct logical variables required")
        if len({variable.cadence_binding for variable in self.variables}) != len(self.variables):
            raise ValueError("distinct ADE bindings required")
        return self


def _checked_request(request: BindingScanRequest) -> BindingScanRequest:
    if not isinstance(request, BindingScanRequest):
        raise ValueError("closed binding scan request required")
    # Frozen models can still be forged with model_copy(update=...) or construct.
    # JSON revalidation also traverses forged nested model instances.
    return BindingScanRequest.model_validate_json(request.model_dump_json())


def render_collector(request: BindingScanRequest) -> bytes:
    """Render the single fixed Py2.6-compatible collector, never a caller script.

    The runner must supply the protected owned copy, fixed private library map,
    trusted normal-user OCEAN, locks, process limits and before/after receipts.
    """
    checked = _checked_request(request)
    from cadence_mcp_bridge import _binding_observation

    result = _binding_observation.render_collector(  # type: ignore[no-untyped-call]
        checked.model_dump(mode="json")
    )
    if type(result) is not bytes or len(result) > MAX_FRAME_BYTES:
        raise ValueError("invalid fixed binding collector")
    return result


def _count(value: str, maximum: int) -> int:
    if _COUNT.fullmatch(value) is None or int(value) > maximum:
        raise ValueError("invalid binding scan count")
    return int(value)


def _name(value: str) -> str:
    if _NAME.fullmatch(value) is None:
        raise ValueError("unsupported source binding name")
    return value


def _cdf(fields: list[str], binding: str) -> dict[str, object]:
    status, parameter_type, units, value_type, value = fields
    if status in _UNAVAILABLE:
        if fields[1:] != ["-"] * 4:
            raise ValueError("unavailable CDF cannot contain inferred values")
        return {
            "status": status,
            "parameter_type": None,
            "units": None,
            "value_type": None,
            "value": None,
        }
    if (
        status != "observed"
        or _NAME.fullmatch(parameter_type) is None
        or _UNIT.fullmatch(units) is None
        or value_type not in {"string", "symbol", "fixnum", "flonum"}
        or len(value) > 64
        or (value != binding and _DECIMAL.fullmatch(value) is None)
        or (value_type in {"fixnum", "flonum"} and _DECIMAL.fullmatch(value) is None)
        or (value_type == "symbol" and value != binding)
    ):
        raise ValueError("unsupported or executable CDF observation")
    # Preserve the observed spelling/type; do not evaluate expressions or derive
    # effective numbers, default values, units, ranges, or W/L semantics.
    return {
        "status": "observed",
        "parameter_type": parameter_type,
        "units": units,
        "value_type": value_type,
        "value": value,
    }


def parse_frame(raw: bytes, request: BindingScanRequest) -> dict[str, object]:
    """Reject incomplete, aliased, drifted or excessive private observation data."""
    checked = _checked_request(request)
    if (
        type(raw) is not bytes
        or not raw
        or len(raw) > MAX_FRAME_BYTES
        or not raw.endswith(b"\n")
        or any(byte != 10 and not 32 <= byte <= 126 for byte in raw)
    ):
        raise ValueError("invalid or excessive binding frame")
    lines = raw.decode("ascii").split("\n")[:-1]
    if len(lines) > 87 or any(not line or len(line) > 1024 for line in lines):
        raise ValueError("invalid binding frame lines")
    digest = canonical_digest(checked)
    prefix = [
        f"BINDING_OBSERVATION_V1|{checked.observation_id}|{checked.nonce}|{digest}",
        f"SOURCE|{checked.library}|{checked.cell}|schematic",
        *[
            f"VARIABLE|{variable.logical_id}|{variable.cadence_binding}"
            for variable in checked.variables
        ],
    ]
    if lines[: len(prefix)] != prefix or len(lines) <= len(prefix):
        raise ValueError("binding observation request identity mismatch")
    complete = lines[-1].split("|")
    if len(complete) != 4 or complete[0] != "COMPLETE":
        raise ValueError("incomplete binding frame")
    totals = (
        _count(complete[1], MAX_INSTANCES),
        _count(complete[2], MAX_INSTANCES * MAX_PROPERTIES_PER_INSTANCE),
        _count(complete[3], MAX_MATCHES),
    )
    variables = {variable.logical_id: variable.cadence_binding for variable in checked.variables}
    matches_by_variable = dict.fromkeys(variables, 0)
    source_properties: set[tuple[str, str]] = set()
    instance_scans: dict[str, int] = {}
    scan_identity: dict[int, tuple[str, ...]] = {}
    bindings: list[dict[str, object]] = []
    ordinal = property_total = property_count = scan_matches = 0
    for line in lines[len(prefix) : -1]:
        fields = line.split("|")
        if fields[0] == "SCAN" and len(fields) == 3:
            next_ordinal = _count(fields[1], MAX_INSTANCES)
            if next_ordinal != ordinal + 1:
                raise ValueError("nonsequential binding scan")
            ordinal = next_ordinal
            property_count = _count(fields[2], MAX_PROPERTIES_PER_INSTANCE)
            property_total += property_count
            scan_matches = 0
            continue
        if fields[0] != "BIND" or len(fields) != 16 or ordinal == 0:
            raise ValueError("unexpected binding frame record")
        (
            _, scan, logical_id, binding, instance, master_library, master_cell,
            master_view, property_name, stored_type, stored_value, *cdf_fields,
        ) = fields
        if (
            _count(scan, MAX_INSTANCES) != ordinal
            or variables.get(logical_id) != binding
            or stored_value != binding
            or stored_type not in {"string", "symbol"}
        ):
            raise ValueError("binding target or stored value mismatch")
        identity = tuple(
            _name(name) for name in (instance, master_library, master_cell, master_view)
        )
        _name(property_name)
        source_property = (instance, property_name)
        if (
            source_property in source_properties
            or instance_scans.get(instance, ordinal) != ordinal
            or scan_identity.get(ordinal, identity) != identity
        ):
            raise ValueError("duplicate, aliased or conflicting binding source")
        source_properties.add(source_property)
        instance_scans[instance] = ordinal
        scan_identity[ordinal] = identity
        matches_by_variable[logical_id] += 1
        scan_matches += 1
        if (
            matches_by_variable[logical_id] > MAX_MATCHES_PER_VARIABLE
            or scan_matches > property_count
            or len(bindings) >= MAX_MATCHES
        ):
            raise ValueError("excessive binding matches")
        bindings.append(
            {
                "logical_id": logical_id,
                "cadence_binding": binding,
                "scan_ordinal": ordinal,
                "instance_path": instance,
                "master_library": master_library,
                "master_cell": master_cell,
                "master_view": master_view,
                "property_name": property_name,
                "stored_type": stored_type,
                "stored_value": stored_value,
                "effective_cdf": _cdf(cdf_fields, binding),
            }
        )
    if (
        (ordinal, property_total, len(bindings)) != totals
        or not all(matches_by_variable.values())
    ):
        raise ValueError("incomplete binding scan or missing variable")
    return {
        "schema_version": 1,
        "status": "OBSERVED_OWNED_COPY_BINDINGS",
        "record_scope": "FIXED_FRAME_ONLY_NO_TRANSPORT_OR_SOURCE_ATTESTATION",
        "observation_id": checked.observation_id,
        "nonce": checked.nonce,
        "request_sha256": digest,
        "request": checked.model_dump(mode="json"),
        "scan_counts": {
            "instances": ordinal, "properties": property_total, "matches": len(bindings),
        },
        "bindings": bindings,
        "effective_cdf_complete": all(
            isinstance(binding["effective_cdf"], dict)
            and binding["effective_cdf"]["status"] == "observed"
            for binding in bindings
        ),
        "qualification": "NOT_ESTABLISHED_BY_BINDING_SCAN",
        "new_simulations": 0,
        "new_extractions": 0,
        "new_result_reservation_bytes": 0,
    }
