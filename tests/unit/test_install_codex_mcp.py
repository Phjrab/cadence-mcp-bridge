from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = PROJECT_ROOT / "scripts" / "install-codex-mcp.ps1"


def test_installer_uses_absolute_reviewed_stdio_entrypoint() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert 'Resolve-Path (Join-Path $projectRoot ".venv\\Scripts\\python.exe")' in source
    assert 'args = ["-m", "cadence_mcp_bridge"]' in source
    assert "\"cwd = '$projectRoot'\"" in source
    assert '"startup_timeout_sec = 20"' in source
    assert '"tool_timeout_sec = 180"' in source
    assert '"enabled = true"' in source
    assert '"required = true"' in source


def test_installer_backs_up_and_replaces_only_named_entry() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert "Copy-Item -LiteralPath $configPath -Destination $backupPath" in source
    assert "config.toml.WP06-" in source
    assert "Move-Item -LiteralPath $temporaryPath -Destination $configPath -Force" in source
    assert "[regex]::Escape($serverName)" in source
    assert "Registration already matches the reviewed configuration." in source


def test_installer_prompts_for_every_side_effect_tool() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert 'default_tools_approval_mode = "writes"' in source
    assert "[mcp_servers.$serverName.tools.cadence_submit_smoke]" in source
    assert "[mcp_servers.$serverName.tools.cadence_cancel_job]" in source
    assert "[mcp_servers.$serverName.tools.cadence_execute_design_write_validation]" in source
    assert source.count('approval_mode = "prompt"') == 3
    for forbidden in ("run_shell", "ssh_exec", "eval_skill", "execute_ocean"):
        assert forbidden not in source
