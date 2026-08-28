from __future__ import annotations

import json
from pathlib import Path

from cadence_mcp_bridge.profiles import ACTUAL_PROFILE, FIXTURE_PROFILE

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
        "submit-profile",
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
    assert "RUNNER_VERSION=0.7.0" in runner
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


def test_profile_runner_is_fixed_and_manifest_backed() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    helper = (PROJECT_ROOT / "remote" / "py26" / "profile_json.py").read_text(encoding="utf-8")
    registry = json.loads(
        (PROJECT_ROOT / "remote" / "profiles" / "fixture-rc-transient" / "profile.json").read_text(
            encoding="utf-8"
        )
    )
    actual_registry = json.loads(
        (
            PROJECT_ROOT
            / "remote"
            / "profiles"
            / "actual-differential-amplifier-tb2-transient"
            / "profile.json"
        ).read_text(encoding="utf-8")
    )

    assert "submit-profile)" in runner
    assert "fixture-rc-transient" in runner
    assert registry["classification"] == "fixture"
    assert registry["corners"] == ["nominal"]
    assert registry["profile_id"] == FIXTURE_PROFILE.profile_id
    assert registry["analyses"] == list(FIXTURE_PROFILE.analyses)
    assert registry["outputs"] == list(FIXTURE_PROFILE.outputs)
    assert registry["timeout_seconds"] == FIXTURE_PROFILE.timeout_seconds
    assert actual_registry["classification"] == "actual"
    assert actual_registry["profile_id"] == ACTUAL_PROFILE.profile_id
    assert actual_registry["variables"] == {}
    assert actual_registry["outputs"] == []
    assert actual_registry["corners"] == ["NN"]
    assert actual_registry["spectre_stop_time"] == "4m"
    assert actual_registry["stop_time_s"] == 0.004
    assert actual_registry["fixed_parameters"] == {"VBIASN": "300m", "VBIASP": "650m"}
    assert actual_registry["warning_policy"] == {
        "allowed_codes": ["CMI-2477"],
        "maximum_count": 2,
    }
    assert "actual-differential-amplifier-tb2-transient" in runner
    assert "run-manifest.json" in helper
    assert "source_sha256" in helper
    assert "design-netlist.scs" in helper
    assert "script_text" not in runner
