"""Inspect built wheel/sdist licensing and exact curated contents without extraction."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

APACHE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
LICENSE_FILES = {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"}
_SECRET = re.compile(
    rb"-----BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY-----"
    rb"|\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"
    rb"|\b(?:CDS_LIC_FILE|LM_LICENSE_FILE)\s*=\s*[\"']?(?:\d{2,6}@|[A-Z]:\\|/)",
    re.IGNORECASE,
)
_MODEL = re.compile(rb"(?im)^\s*model\s+\S+\s+bsim[34]\b")


def _check_name(name: str) -> None:
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or ".." in path.parts:
        raise ValueError("Distribution path is unsafe")


def _members(artifact: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    total = 0

    def add(name: str, data: bytes) -> None:
        nonlocal total
        _check_name(name)
        total += len(data)
        if name in result or len(result) >= 1024 or total > 64 * 1024**2:
            raise ValueError("Distribution member inventory is invalid")
        if _SECRET.search(data) or _MODEL.search(data):
            raise ValueError("Protected content pattern in distribution")
        result[name] = data

    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as wheel:
            for item in wheel.infolist():
                if item.is_dir() or item.file_size > 16 * 1024**2:
                    raise ValueError("Unexpected wheel member")
                # Wheels contain regular files; Unix symlink attributes are not accepted.
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Distribution links are forbidden")
                add(item.filename, wheel.read(item))
    else:
        with tarfile.open(artifact, "r:gz") as sdist:
            for item in sdist:
                if item.isdir():
                    _check_name(item.name)
                    continue
                if not item.isfile() or item.size > 16 * 1024**2:
                    raise ValueError("Unexpected source distribution member")
                stream = sdist.extractfile(item)
                if stream is None:
                    raise ValueError("Source distribution file unavailable")
                with stream:
                    add(item.name, stream.read())
    return result


def inspect_artifact(artifact: Path, project: Path) -> dict[str, object]:
    metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    version = metadata["project"]["version"]
    dist_name = "cadence_mcp_bridge-" + version
    source = {
        p.relative_to(project / "src").as_posix(): p.read_bytes()
        for p in (project / "src/cadence_mcp_bridge").iterdir()
        if p.is_file() and (p.suffix == ".py" or p.name == "py.typed")
    }
    required = {name: (project / name).read_bytes() for name in LICENSE_FILES}
    if hashlib.sha256(required["LICENSE"]).hexdigest() != APACHE_SHA256:
        raise ValueError("Canonical Apache license bytes differ")
    members = _members(artifact)
    if artifact.suffix == ".whl":
        prefix = dist_name + ".dist-info/"
        expected = {
            **source,
            **{prefix + "licenses/" + name: data for name, data in required.items()},
        }
        generated = {prefix + name for name in ("METADATA", "WHEEL", "RECORD", "entry_points.txt")}
        meta_path = prefix + "METADATA"
        kind = "wheel"
    else:
        prefix = dist_name + "/"
        expected = {
            **{prefix + "src/" + name: data for name, data in source.items()},
            **{prefix + name: data for name, data in required.items()},
            **{prefix + name: (project / name).read_bytes()
               for name in ("README.md", "pyproject.toml", "uv.lock", ".gitignore")},
        }
        generated = {prefix + "PKG-INFO"}
        meta_path = prefix + "PKG-INFO"
        kind = "sdist"
    if set(members) != set(expected) | generated:
        raise ValueError("Distribution differs from the curated allowlist")
    if any(members[name] != data for name, data in expected.items()):
        raise ValueError("Distribution source or notice bytes differ")
    parsed = BytesParser().parsebytes(members[meta_path])
    if (
        parsed["Name"] != "cadence-mcp-bridge"
        or parsed["Version"] != version
        or parsed["License-Expression"] != "Apache-2.0"
        or set(parsed.get_all("License-File", [])) != LICENSE_FILES
        or tuple(map(int, parsed["Metadata-Version"].split("."))) < (2, 4)
        or parsed.get("License") is not None
    ):
        raise ValueError("Modern package license metadata differs")
    return {
        "kind": kind,
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "members": len(members),
        "license_expression": parsed["License-Expression"],
        "license_files": sorted(LICENSE_FILES),
        "canonical_license": True,
        "unexpected_files": 0,
        "protected_content_patterns": 0,
        "source_and_notices_match": True,
        "imported_planning_included": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    wheels = list(args.artifacts.glob("*.whl"))
    sdists = list(args.artifacts.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Expected exactly one wheel and source distribution")
    print(json.dumps({"distribution_audit": [inspect_artifact(p, args.project)
                                           for p in (*wheels, *sdists)]}, sort_keys=True))


if __name__ == "__main__":
    main()
