"""Local exact-diff validation. Inputs remain private and are never transmitted."""

from __future__ import annotations

import json
import re

Changes = dict[str, dict[str, tuple[str, str]]]


def oa_records(before: list[str], after: list[str], changes: Changes) -> int:
    if len(set(before)) != len(before) or len(set(after)) != len(after):
        raise ValueError("duplicate OA record")
    expected: list[str] = []
    seen: set[tuple[str, str]] = set()
    for row in before:
        parts = row.split("|", 4)
        if len(parts) == 5 and parts[0] == "P" and parts[1] in changes:
            instance, prop = parts[1:3]
            if prop in changes[instance]:
                old, new = changes[instance][prop]
                if parts[3] != "string" or parts[4] != json.dumps(old):
                    raise ValueError("OA property preimage")
                parts[4] = json.dumps(new)
                row = "|".join(parts)
                seen.add((instance, prop))
        expected.append(row)
    required = {(inst, prop) for inst, props in changes.items() for prop in props}
    if not required or seen != required or sorted(expected) != sorted(after):
        raise ValueError("unexpected OA structural/property difference")
    return len(seen)


def statements(text: str) -> list[str]:
    return [
        " ".join(line.split())
        for line in text.replace("\\\n", " ").splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]


def native_circuit(before: str, after: str, changes: Changes) -> int:
    expected: list[str] = []
    seen: set[tuple[str, str]] = set()
    instances: set[str] = set()
    for row in statements(before):
        name = row.split(" ", 1)[0]
        if name in changes:
            if name in instances:
                raise ValueError("duplicate changed native instance")
            instances.add(name)
            for prop, (old, new) in changes[name].items():
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", prop):
                    raise ValueError("native property token")
                pattern = re.compile(r"(?<!\S)" + re.escape(prop + "=" + old) + r"(?=\s|$)")
                replacement = prop + "=" + new
                if "\\" in new or any(c.isspace() for c in new):
                    raise ValueError("native replacement must be one literal token")
                row, count = pattern.subn(replacement, row)
                if count != 1:
                    raise ValueError("native field preimage")
                seen.add((name, prop))
        expected.append(row)
    required = {(inst, prop) for inst, props in changes.items() for prop in props}
    if not required or seen != required or expected != statements(after):
        raise ValueError("unexpected native circuit difference")
    return len(seen)
