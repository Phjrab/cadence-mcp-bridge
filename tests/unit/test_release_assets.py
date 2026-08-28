from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_package_verifier_is_bounded_and_checks_uninstall() -> None:
    source = (PROJECT_ROOT / "scripts" / "verify-package.ps1").read_text(encoding="utf-8")

    assert "GetTempPath" in source
    assert "StartsWith($temporaryBase" in source
    assert "uv build" in source
    assert "uv pip install" in source
    assert "uv pip uninstall" in source
    assert "find_spec('cadence_mcp_bridge') is None" in source
    assert "Remove-Item -LiteralPath $resolvedTemporaryRoot -Recurse -Force" in source


def test_release_is_not_declared_while_write_acceptance_is_blocked() -> None:
    project = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (PROJECT_ROOT / "src" / "cadence_mcp_bridge" / "__init__.py").read_text(
        encoding="utf-8"
    )

    assert 'version = "0.1.0"' in project
    assert '__version__ = "0.1.0"' in package
