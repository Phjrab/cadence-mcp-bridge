from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "remote" / "bin" / "cadence-runner"
COMMON = PROJECT_ROOT / "remote" / "lib" / "runner-common.sh"
DEPLOY = PROJECT_ROOT / "scripts" / "deploy-remote.ps1"
RESULT_HELPER = PROJECT_ROOT / "remote" / "py26" / "result_json.py"
DISCOVERY_HELPER = PROJECT_ROOT / "remote" / "py26" / "discovery_json.py"
DISCOVERY_ALLOWLIST = PROJECT_ROOT / "remote" / "config" / "discovery-allowlist.json"


def test_runner_exposes_only_allowlisted_commands() -> None:
    source = RUNNER.read_text(encoding="utf-8")

    for command in (
        "version",
        "health",
        "submit-smoke",
        "status",
        "log-tail",
        "result",
        "cancel",
        "list-libraries",
        "list-cells",
        "inspect-cellview",
        "discovery-health",
        "cleanup-dry-run",
        "audit-tail",
    ):
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
    assert 'kill -TERM -- "-$pgid"' in runner
    assert "RUNNER_VERSION=0.5.0" in runner
    assert "cadence_mcp_worker_matches" in runner
    assert 'unknown "job worker is unavailable; operator review required"' in runner


def test_deploy_script_has_no_remote_path_parameter() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    assert "param()" in source
    assert '$remoteRoot = "/home/buet/cds_work/.cadence_mcp"' in source
    assert "StrictHostKeyChecking=yes" in source
    assert "BatchMode=yes" in source


def test_result_storage_uses_fixed_jobs_root_for_containment() -> None:
    source = RESULT_HELPER.read_text(encoding="utf-8")

    assert 'jobs_root = os.path.realpath("/home/buet/cds_work/.cadence_mcp/jobs")' in source
    assert "os.path.dirname(real_job_dir) == jobs_root" in source


def test_discovery_is_allowlisted_metadata_only() -> None:
    helper = DISCOVERY_HELPER.read_text(encoding="utf-8")
    config = json.loads(DISCOVERY_ALLOWLIST.read_text(encoding="utf-8"))

    assert set(config["libraries"]) == {"MyFirstDesign", "MyDesignLib"}
    assert "gpdk090" not in config["libraries"]
    assert "open(view_path" not in helper
    assert '"proprietary_content_included": False' in helper
    assert "os.path.realpath" in helper
    assert "discovery-runtime" in RUNNER.read_text(encoding="utf-8")
