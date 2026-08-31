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
WRITE_POLICY = PROJECT_ROOT / "remote" / "config" / "design-write-policy.json"
WRITE_HELPER = PROJECT_ROOT / "remote" / "py26" / "write_validation_json.py"
WRITE_SCRIPT = PROJECT_ROOT / "remote" / "write" / "design-write-validation.il"
WRITE_WORKER = PROJECT_ROOT / "remote" / "lib" / "run-design-write-validation.sh"
V2_RECOVERY_HELPER = PROJECT_ROOT / "remote" / "py26" / "v2_recovery_json.py"
V2_RECOVERY_WORKER = PROJECT_ROOT / "remote" / "lib" / "run-design-write-v2-recovery.sh"
V2_FORENSIC_SCRIPT = PROJECT_ROOT / "remote" / "write" / "design-write-v2-forensic.il"
V2_PROPERTY_DIFF_SCRIPT = PROJECT_ROOT / "remote" / "write" / "design-write-v2-property-diff.il"
V2_ROLLBACK_SCRIPT = PROJECT_ROOT / "remote" / "write" / "design-write-v2-rollback.il"
V3_PLAN = PROJECT_ROOT / "remote" / "config" / "design-write-v3-plan.json"


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
        "design-write-plan",
        "design-write-preflight",
        "design-write-validate",
        "design-write-v2-forensic",
        "design-write-v2-property-diff",
        "design-write-v2-rollback",
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
    assert "RUNNER_VERSION=0.11.0" in runner
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


def test_design_write_contract_is_single_target_copy_only_and_rollback_backed() -> None:
    policy = json.loads(WRITE_POLICY.read_text(encoding="utf-8"))
    helper = WRITE_HELPER.read_text(encoding="utf-8")
    skill = WRITE_SCRIPT.read_text(encoding="utf-8")
    worker = WRITE_WORKER.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert policy["source"] == {
        "library": "MyDesignLib",
        "cell": "Differential_Amplifier_TB2",
        "view": "schematic",
        "path": "/home/buet/cds_work/MyDesignLib/Differential_Amplifier_TB2/schematic",
    }
    assert policy["target"]["library"] == "MCP_WorkLib"
    assert policy["target"]["library_path"] == "/home/buet/cds_work/MCP_WorkLib"
    assert policy["target"]["cell"] == "Differential_Amplifier_TB2_MCP_TEST_V2"
    assert policy["backup_cell"] == "Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP"
    assert policy["preserved_target"]["cell"] == "Differential_Amplifier_TB2_MCP_TEST"
    assert policy["property"] == {
        "name": "mcpMutationTest",
        "type": "string",
        "old_value": None,
        "proposed_value": "validated-v1",
    }
    assert policy["affected_objects"] == 1
    assert policy["original_library_mutations"] == 0
    assert policy["destructive"] is False
    assert "dbCopyCellView" in skill
    assert "mcpFindPropertyByName" in skill
    assert "dbFindProp(cellView name)" in skill
    assert "dbFindPropByName" not in skill
    assert 'dbReplaceProp(targetCv propertyName "string" propertyValue)' in skill
    assert "dbCopyCellView(backupCv workLib targetCell targetView nil nil t)" in skill
    assert "valueType" in skill
    assert "MCP_FINGERPRINT" in skill
    assert "instances" in skill and "nets" in skill and "terminals" in skill
    for forbidden in ("dbCreateInst", "dbDeleteObject", "evalstring", "load("):
        assert forbidden not in skill
    assert "source_before" in worker and "source_after" in worker
    assert "preserved_before" in worker and "preserved_after" in worker
    assert "source-check" in worker
    assert "source_master_is_authoritative" in helper
    assert 'references == ["sch.oa"]' in helper
    assert "source baseline topology mismatch" in skill
    assert "list(35 14 8)" in skill
    assert "V2 cellview lock or recovery artifact remains" in worker
    assert "target cellview already exists" in worker
    assert "EXPECTED_SEQUENCE" in helper
    assert "baseline logical fingerprint was not restored" in helper
    assert "write-events.jsonl" in worker
    assert "design-write-policy.json" in deploy
    assert "design-write-validation.il" in deploy
    assert "design-write-readonly-preflight.il" in deploy


def test_v2_recovery_is_fixed_read_only_then_exact_backup_restore() -> None:
    helper = V2_RECOVERY_HELPER.read_text(encoding="utf-8")
    worker = V2_RECOVERY_WORKER.read_text(encoding="utf-8")
    forensic = V2_FORENSIC_SCRIPT.read_text(encoding="utf-8")
    property_diff = V2_PROPERTY_DIFF_SCRIPT.read_text(encoding="utf-8")
    rollback = V2_ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "APPROVE_MCP_V2_BACKUP_ROLLBACK" in RUNNER.read_text(encoding="utf-8")
    assert "active Virtuoso process blocks V2 recovery" in worker
    assert "source-check" in worker
    assert "fingerprint_tree" in worker
    assert "/home/buet/cadence/gpdk090_v4.6/libs.oa22/gpdk090" in worker
    assert "pdk_before" in worker and "pdk_after" in worker
    assert "MCP_V2_FORENSIC|true|35|14|8|8|9|validated-v1" in forensic
    assert "dbOpenCellViewByType" in forensic
    assert "dbCopyCellView" not in forensic
    assert "dbSave" not in forensic
    assert "MCP_V2_PROPERTY_DIFF" in property_diff
    assert '"r"' in property_diff
    assert "~>value" in property_diff
    assert "MCP_V2_PROPERTY_DIFF|%s|%s|%s|true|true|false" in property_diff
    assert "validated-v1" not in property_diff
    assert "dbCopyCellView" not in property_diff
    assert "dbSave" not in property_diff
    assert "MCP_V2_ROLLBACK|true|35|14|8|8|8|absent" in rollback
    assert "dbCopyCellView(backupCv workLib targetCell sourceView nil nil t)" in rollback
    assert "dbDeleteObject" not in rollback
    assert "design_write_v2_recovery_rollback" in helper
    assert "v2-forensic-evidence.json" in helper
    assert "v2-rollback-evidence.json" in helper
    for source in (forensic, property_diff, rollback):
        for forbidden in ("evalstring", "load(", "dbCreateInst", "dbDeleteObject"):
            assert forbidden not in source
        assert "return(nil)" not in source
    assert "run-design-write-v2-recovery.sh" in deploy
    assert "v2_recovery_json.py" in deploy
    assert "design-write-v2-forensic.il" in deploy
    assert "design-write-v2-property-diff.il" in deploy
    assert "design-write-v2-rollback.il" in deploy


def test_v3_plan_is_non_executable_and_preserves_prior_evidence() -> None:
    plan = json.loads(V3_PLAN.read_text(encoding="utf-8"))

    assert plan["plan_id"] == "mcp-cellview-property-v3"
    assert plan["status"] == "blocked_on_v2_exact_diff_failure"
    assert plan["execution_enabled"] is False
    assert plan["target"] == "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3/schematic"
    assert plan["backup"] == (
        "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic"
    )
    assert plan["property"] == {
        "name": "mcpMutationTest",
        "type": "string",
        "old_value": None,
        "proposed_value": "validated-v1",
    }
    assert len(plan["preserved_evidence"]) == 3
    assert plan["required_confirmation"] is None
    assert len(plan["acceptance_criteria"]) == 10
    assert plan["release_gate_enabled"] is False
