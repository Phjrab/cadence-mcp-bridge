from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "remote" / "bin" / "cadence-runner"
COMMON = PROJECT_ROOT / "remote" / "lib" / "runner-common.sh"
DEPLOY = PROJECT_ROOT / "scripts" / "deploy-remote.ps1"


def test_runner_exposes_only_allowlisted_commands() -> None:
    source = RUNNER.read_text(encoding="utf-8")

    for command in ("version", "health", "submit-smoke", "status", "log-tail", "result", "cancel"):
        assert f"{command})" in source
    for forbidden in ("eval ", "bash -c", "sh -c", "run-shell", "ssh-exec"):
        assert forbidden not in source


def test_runner_uses_fixed_remote_and_cadence_paths() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    common = COMMON.read_text(encoding="utf-8")

    assert "CADENCE_MCP_ROOT=/home/buet/cds_work/.cadence_mcp" in common
    assert "CADENCE_MCP_JOB_ID_PATTERN" in common
    assert "/home/buet/cadence/MMSIM121/tools/bin/spectre" in runner
    assert "setsid" in runner
    assert "kill -TERM -- \"-$pgid\"" in runner


def test_deploy_script_has_no_remote_path_parameter() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    assert 'param()' in source
    assert '$remoteRoot = "/home/buet/cds_work/.cadence_mcp"' in source
    assert "StrictHostKeyChecking=yes" in source
    assert "BatchMode=yes" in source
