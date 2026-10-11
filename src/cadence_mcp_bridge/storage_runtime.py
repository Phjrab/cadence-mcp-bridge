"""Pure, fixed reference storage payload construction; never provisions a VM."""

from __future__ import annotations

import hashlib
import json
import shlex
from importlib.resources import files

REFERENCE_STORAGE_ROOT = "/home/buet/cds_work/.cadence_mcp"
REFERENCE_STORAGE_VERSION = "storage-mgmt-v7"
REFERENCE_STORAGE_LAUNCHER = """#!/bin/bash
set -eu
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/storage-mgmt-v7"
[ "$#" -eq 3 ] || exit 64
case "$1" in ''|*[!0-9a-f]*) exit 64 ;; esac
[ "${#1}" -eq 64 ] || exit 64
case "$2" in inventory|cleanup) ;; *) exit 64 ;; esac
case "$3" in ''|*[!0-9a-f]*) exit 64 ;; esac
[ "${#3}" -ge 2 ] && [ "${#3}" -le 16384 ] || exit 64
[ "$(( ${#3} % 2 ))" -eq 0 ] || exit 64
cd "$VERSION"
sha256sum -c manifest.sha256 >/dev/null 2>&1 || exit 69
RUNTIME="$VERSION/runtime/$1"
[ "$(sha256sum "$RUNTIME/manifest.json" | cut -d ' ' -f 1)" = "$1" ] || exit 69
exec /usr/bin/python -E -s -B -c __CADENCE_STORAGE_ENTRY__ "$RUNTIME" "$1" "$2" "$3"
"""


def reference_storage_bundle() -> tuple[str, dict[str, bytes]]:
    """Return the exact hash-bound two-asset runtime and closed launcher.

    An explicit operator deployment, its exact authority and a matching configured
    pin are required. Import, server startup and doctor perform no installation.
    """
    resources = files("cadence_mcp_bridge")
    entry = resources.joinpath("_storage_entry.py").read_bytes()
    if b"\r" in entry or len(entry) > 262144:
        raise ValueError("fixed storage entry bytes required")
    assets = {
        "storage.py": resources.joinpath("_storage_worker.py").read_bytes(),
        "reservations.py": resources.joinpath("_shared_reservations.py").read_bytes(),
    }
    if any(b"\r" in raw or len(raw) > 262144 for raw in assets.values()):
        raise ValueError("fixed storage source bytes required")
    manifest = {
        "schema_version": 1,
        "kind": "REFERENCE_STORAGE_RUNTIME",
        "managed_root": REFERENCE_STORAGE_ROOT,
        "entry_sha256": hashlib.sha256(entry).hexdigest(),
        "files": {
            name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            for name, raw in assets.items()
        },
    }
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )
    pin = hashlib.sha256(raw).hexdigest()
    prefix = f"runtime/{pin}/"
    return pin, {
        "run.sh": REFERENCE_STORAGE_LAUNCHER.replace(
            "__CADENCE_STORAGE_ENTRY__",
            shlex.quote(entry.decode("ascii")),
        ).encode("ascii"),
        **{prefix + name: payload for name, payload in assets.items()},
        prefix + "manifest.json": raw,
    }


def reference_storage_entry(payloads: dict[str, bytes]) -> str:
    prefix = b"exec /usr/bin/python -E -s -B -c "
    suffix = b' "$RUNTIME" "$1" "$2" "$3"\n'
    launcher = payloads["run.sh"]
    if launcher.count(prefix) != 1 or not launcher.endswith(suffix):
        raise ValueError("fixed storage entry shape")
    parts = shlex.split(launcher.split(prefix, 1)[1][:-len(suffix)].decode("ascii"))
    if len(parts) != 1:
        raise ValueError("fixed storage entry shape")
    return parts[0]
