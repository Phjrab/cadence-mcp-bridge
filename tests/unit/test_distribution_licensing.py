"""Distribution rejection tests use synthetic archives, never vendor or private data."""

from __future__ import annotations

import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "distribution_audit", ROOT / "scripts/verify-distribution.py"
)
assert SPEC and SPEC.loader
AUDIT: ModuleType = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    source = root / "src/cadence_mcp_bridge"
    source.mkdir(parents=True)
    (source / "__init__.py").write_bytes(b"# Synthetic original source\n")
    (source / "py.typed").write_bytes(b"")
    (root / "pyproject.toml").write_bytes(
        b'[project]\nversion="1.0.0"\nname="cadence-mcp-bridge"\nlicense="Apache-2.0"\n'
    )
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        (root / name).write_bytes((ROOT / name).read_bytes())
    (root / "README.md").write_bytes(b"Synthetic readme\n")
    (root / "uv.lock").write_bytes(b"version=1\n")
    (root / ".gitignore").write_bytes(b".codex/\n")
    return root


def entries(project: Path, kind: str) -> dict[str, bytes]:
    prefix = "cadence_mcp_bridge-1.0.0"
    metadata = (
        b"Metadata-Version: 2.4\nName: cadence-mcp-bridge\nVersion: 1.0.0\n"
        b"License-Expression: Apache-2.0\nLicense-File: LICENSE\n"
        b"License-File: NOTICE\nLicense-File: THIRD_PARTY_NOTICES.md\n\n"
    )
    if kind == "wheel":
        info = prefix + ".dist-info/"
        files = {p.relative_to(project / "src").as_posix(): p.read_bytes()
                 for p in (project / "src/cadence_mcp_bridge").iterdir()}
        files.update({info + "licenses/" + name: (project / name).read_bytes()
                      for name in AUDIT.LICENSE_FILES})
        files.update({info + name: b"" for name in ("WHEEL", "RECORD", "entry_points.txt")})
        files[info + "METADATA"] = metadata
    else:
        files = {prefix + "/" + p.relative_to(project).as_posix(): p.read_bytes()
                 for p in project.rglob("*") if p.is_file()}
        files[prefix + "/PKG-INFO"] = metadata
    return files


def archive(tmp_path: Path, kind: str, files: dict[str, bytes]) -> Path:
    path = tmp_path / ("test.whl" if kind == "wheel" else "test.tar.gz")
    if kind == "wheel":
        with zipfile.ZipFile(path, "w") as package:
            for name, data in files.items():
                package.writestr(name, data)
    else:
        with tarfile.open(path, "w:gz") as package:
            for name, data in files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                package.addfile(entry, io.BytesIO(data))
    return path


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_original_package_and_license_bytes_pass(project: Path, tmp_path: Path, kind: str) -> None:
    result = AUDIT.inspect_artifact(archive(tmp_path, kind, entries(project, kind)), project)
    assert result["unexpected_files"] == 0 and result["canonical_license"] is True


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize("extra", [".codex/private.sqlite3", "docs/agent_plan/import.md",
                                    "gpdk090/models.scs", "../outside", "cadence.dll"])
def test_unreviewed_content_paths_are_rejected(
    project: Path, tmp_path: Path, kind: str, extra: str,
) -> None:
    files = entries(project, kind)
    files[extra] = b"synthetic"
    with pytest.raises(ValueError):
        AUDIT.inspect_artifact(archive(tmp_path, kind, files), project)


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
@pytest.mark.parametrize("change", ["notice", "expression", "license", "source", "secret", "model"])
def test_content_and_metadata_mismatch_is_rejected(
    project: Path, tmp_path: Path, kind: str, change: str,
) -> None:
    files = entries(project, kind)
    if change == "notice":
        del files[next(n for n in files if n.endswith("/NOTICE"))]
    elif change == "expression":
        key = next(n for n in files if n.endswith(("/METADATA", "/PKG-INFO")))
        files[key] = files[key].replace(b"Apache-2.0", b"Proprietary")
    else:
        suffix = "/LICENSE" if change == "license" else "/__init__.py"
        key = next(n for n in files if n.endswith(suffix))
        files[key] = {
            "license": b"modified canonical text",
            "source": b"different source",
            "secret": b"ghp_" + b"x" * 36,
            "model": b"model synthetic bsim4\n",
        }[change]
    with pytest.raises(ValueError):
        AUDIT.inspect_artifact(archive(tmp_path, kind, files), project)
