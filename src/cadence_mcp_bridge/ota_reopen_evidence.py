"""Read the 17-device OTA properties emitted by the detached OA reopen phase."""

from __future__ import annotations

import re
from collections.abc import Collection
from hashlib import sha256
from typing import cast

from cadence_mcp_bridge.registered_mos_edit import _PROPERTIES, MosProperty, MosPropertyValue

_PREFIX = b"OTA17_TARGET_"
_ROW = b"OTA17_TARGET_PROP"
_END = b"OTA17_TARGET_PROPERTIES_END"
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_#-]{0,63}")
_SHA = re.compile(r"[0-9a-f]{64}")


def _atom(raw: bytes) -> str | None:
    if raw == b"nil":
        return None
    value = re.fullmatch(rb'"([^"\\|]{1,128})"', raw)
    if value is None:
        raise ValueError("unsupported OTA reopen property atom")
    return value[1].decode("ascii")


def parse_ota_reopen_properties(
    stdout: bytes,
    *,
    stdout_sha256: str,
    plan_sha256: str,
    cell: str,
    instance_names: Collection[str],
) -> dict[str, dict[MosProperty, MosPropertyValue]]:
    """Use pins from the original same-operation generation/reopen receipts."""
    names = frozenset(instance_names)
    if (
        len(names) != 17
        or len(instance_names) != 17
        or not all(_ID.fullmatch(name) for name in (*names, cell))
        or not _SHA.fullmatch(plan_sha256)
        or not 0 < len(stdout) <= 65_536
        or sha256(stdout).hexdigest() != stdout_sha256
    ):
        raise ValueError("OTA reopen stdout, plan or named inventory pin mismatch")
    evidence: dict[str, dict[MosProperty, MosPropertyValue]] = {name: {} for name in names}
    end = False
    for line in stdout.splitlines():
        if not line.startswith(_PREFIX):
            continue
        fields = line.split(b"|")
        if end:
            raise ValueError("OTA reopen properties follow the terminal marker")
        if fields == [_END, plan_sha256.encode("ascii")]:
            end = True
            continue
        if len(fields) != 9 or fields[:2] != [_ROW, cell.encode("ascii")]:
            raise ValueError("unexpected OTA reopen property record")
        name, key = fields[2].decode("ascii"), fields[3].decode("ascii")
        if name not in evidence or key not in _PROPERTIES or key in evidence[name]:
            raise ValueError("unknown or duplicate OTA reopen instance/property")
        oa_type, oa_value, cdf_type, cdf_units, cdf_value = atoms = tuple(
            _atom(raw) for raw in fields[4:]
        )
        if key == "nf":
            valid = atoms == (None, None, None, None, None)
        elif key == "dfm":
            valid = atoms == (None, None, "instData", None, "Minimum")
        else:
            valid = oa_type == "string" and cdf_type == "instData" and oa_value == cdf_value
        if not valid:
            raise ValueError("OTA reopen OA/CDF property and type disagree")
        evidence[name][cast(MosProperty, key)] = MosPropertyValue.model_validate(
            {
                "oa_type": oa_type,
                "oa_value": oa_value,
                "cdf_type": cdf_type,
                "cdf_units": cdf_units,
                "cdf_value": cdf_value,
            }
        )
    if not end or any(properties.keys() != _PROPERTIES for properties in evidence.values()):
        raise ValueError("incomplete OTA reopen property inventory")
    return evidence
