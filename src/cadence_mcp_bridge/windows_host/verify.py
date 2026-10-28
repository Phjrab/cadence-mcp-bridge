"""Local installed-byte verification, never remote qualification or publisher proof."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.resources
import json
import struct
import sys
from pathlib import Path

from cadence_mcp_bridge import __version__


def verify(root: Path) -> dict[str, object]:
    manifest = json.loads((root / "INSTALL-MANIFEST.json").read_text(encoding="utf-8"))
    if manifest["version"] != __version__ or struct.calcsize("P") != 8:
        raise ValueError("version_architecture_mismatch")
    for name, record in manifest["files"].items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("payload_path_invalid")
        data = path.read_bytes()
        if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("payload_content_mismatch")
    resource = importlib.resources.files("cadence_mcp_bridge").joinpath("_environment_probe.py")
    if not resource.is_file() or importlib.metadata.version("cadence-mcp-bridge") != __version__:
        raise ValueError("installed_resource_missing")
    if not sys.flags.isolated or any(
        not Path(p).resolve().is_relative_to(root.resolve()) for p in sys.path
    ):
        raise ValueError("runtime_not_isolated")
    return {
        "status": "HOST_PAYLOAD_VERIFIED",
        "version": __version__,
        "files": len(manifest["files"]),
        "publisher_signature_verified": False,
        "remote_contact": False,
        "execution_authorized": False,
    }


def main() -> int:
    try:
        result = verify(Path(sys.executable).parent.parent)
    except (OSError, ValueError, KeyError):
        print('{"status":"HOST_PAYLOAD_REJECTED"}')
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
