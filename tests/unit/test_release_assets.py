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


def test_release_candidate_versions_are_consistent() -> None:
    project = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (PROJECT_ROOT / "src" / "cadence_mcp_bridge" / "__init__.py").read_text(
        encoding="utf-8"
    )
    verifier = (PROJECT_ROOT / "scripts" / "verify-package.ps1").read_text(encoding="utf-8")
    lock = (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8")

    assert 'version = "1.0.0"' in project
    assert '__version__ = "1.0.0"' in package
    assert '$installedVersion -ne "1.0.0"' in verifier
    assert 'name = "cadence-mcp-bridge"\nversion = "1.0.0"' in lock


def test_final_release_notes_replace_the_draft() -> None:
    final_notes = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.0.md"
    draft_notes = PROJECT_ROOT / "docs" / "RELEASE_NOTES_v1.0.0_DRAFT.md"

    assert final_notes.is_file()
    assert not draft_notes.exists()
    notes = final_notes.read_text(encoding="utf-8")
    assert "Release Candidate" in notes
    assert "not yet published" in notes


def test_design_write_verifier_requires_the_exact_confirmation() -> None:
    source = (PROJECT_ROOT / "scripts" / "verify-design-write.ps1").read_text(encoding="utf-8")
    cli = (
        PROJECT_ROOT / "src" / "cadence_mcp_bridge" / "write_validation_cli.py"
    ).read_text(encoding="utf-8")

    assert 'ValidateSet("APPROVE_MCP_WRITE_VALIDATED_V2")' in source
    assert "cadence_design_write_plan" in cli
    assert "cadence_execute_design_write_validation" in cli
    assert "if not plan.get(\"ready\")" in cli
