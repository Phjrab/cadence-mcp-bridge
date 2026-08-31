from __future__ import annotations

import hashlib
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
V3_HELPER = PROJECT_ROOT / "remote" / "py26" / "v3_validation_json.py"
V3_WORKER = PROJECT_ROOT / "remote" / "lib" / "run-design-write-v3-validation.sh"
V3_SCRIPT = PROJECT_ROOT / "remote" / "write" / "design-write-v3-validation.il"
V3_FORENSIC_HELPER = PROJECT_ROOT / "remote" / "py26" / "v3_forensic_json.py"
V3_FORENSIC_WORKER = PROJECT_ROOT / "remote" / "lib" / "run-design-write-v3-forensic.sh"
V3_FORENSIC_SCRIPT = PROJECT_ROOT / "remote" / "write" / "design-write-v3-property-diff.il"
V3_DEEP_FORENSIC_HELPER = PROJECT_ROOT / "remote" / "py26" / "v3_deep_forensic_json.py"
V3_DEEP_FORENSIC_WORKER = (
    PROJECT_ROOT / "remote" / "lib" / "run-design-write-v3-deep-forensic.sh"
)
V3_DEEP_FORENSIC_SCRIPT = (
    PROJECT_ROOT / "remote" / "write" / "design-write-v3-deep-forensic.il"
)
V3_RECOVERY_PLAN = (
    PROJECT_ROOT / "remote" / "config" / "design-write-v3-conditional-recovery-plan.json"
)
V3_EXACT_ROLLBACK_PLAN = (
    PROJECT_ROOT
    / "remote"
    / "config"
    / "design-write-v3-exact-conditional-rollback-plan.json"
)
V3_EXACT_ROLLBACK_HELPER = PROJECT_ROOT / "remote" / "py26" / "v3_exact_rollback_json.py"
V3_EXACT_ROLLBACK_WORKER = (
    PROJECT_ROOT / "remote" / "lib" / "run-design-write-v3-exact-rollback.sh"
)
V3_EXACT_ROLLBACK_SCRIPT = (
    PROJECT_ROOT / "remote" / "write" / "design-write-v3-exact-rollback.il"
)
V4_PLAN = PROJECT_ROOT / "remote" / "config" / "design-write-v4-plan.json"
V4_HELPER = PROJECT_ROOT / "remote" / "py26" / "v4_validation_json.py"
V4_WORKER = PROJECT_ROOT / "remote" / "lib" / "run-design-write-v4-validation.sh"
V4_SCRIPT = PROJECT_ROOT / "remote" / "write" / "design-write-v4-validation.il"


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
        "design-write-v3-plan-check",
        "design-write-v3-validate",
        "design-write-v3-property-diff",
        "design-write-v3-deep-forensic",
        "design-write-v3-exact-rollback",
        "design-write-v4-plan-check",
        "design-write-v4-validate",
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
    assert "RUNNER_VERSION=0.16.0" in runner
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


def test_v3_validation_is_fixed_confirmation_gated_and_rollback_backed() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    helper = V3_HELPER.read_text(encoding="utf-8")
    worker = V3_WORKER.read_text(encoding="utf-8")
    skill = V3_SCRIPT.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "APPROVE_MCP_WRITE_VALIDATED_V3_3362E4FC" in helper
    assert "design-write-v3-validate" in runner
    assert "design-write-v3-plan-check" in runner
    assert "3362e4fc13874d4f16c78506c24ae6ebd64c882718fe57e9cb2bb60619890c87" in helper
    assert "active Virtuoso process blocks V3 validation" in worker
    assert "timeout 300" in worker
    assert 'v1_master_references" = "sch.oa"' in worker
    assert "protected V1 artifact blocks V3 validation" in worker
    assert "protected V2 artifact blocks V3 validation" in worker
    for path in (
        "Differential_Amplifier_TB2_MCP_TEST/schematic",
        "Differential_Amplifier_TB2_MCP_TEST_V2/schematic",
        "Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic",
        "Differential_Amplifier_TB2_MCP_TEST_V3/schematic",
        "Differential_Amplifier_TB2_MCP_TEST_V3_BACKUP/schematic",
        "/home/buet/cadence/gpdk090_v4.6/libs.oa22/gpdk090",
    ):
        assert path in worker
    assert "source_before" in worker and "source_after" in worker
    assert "v1_before" in worker and "v1_after" in worker
    assert "v2_target_before" in worker and "v2_target_after" in worker
    assert "v2_backup_before" in worker and "v2_backup_after" in worker
    assert "pdk_before" in worker and "pdk_after" in worker
    assert "MCP_V3_STAGE|dry_run|true|absent|1|0|false" in skill
    assert 'dbReplaceProp(targetCv propertyName "string" propertyValue)' in skill
    assert "dbCopyCellView(backupCv workLib targetCell sourceView nil nil t)" in skill
    assert "mcpV3PropertiesContained" in skill
    assert "mcpV3PropertiesEqual" in skill
    assert "MCP_V3_STAGE|exact_diff_verification|true|1" in skill
    assert "MCP_V3_STAGE|baseline_restoration_verification|true" in skill
    assert "return(nil)" not in skill
    for forbidden in ("evalstring", "load(", "dbCreateInst", "dbDeleteObject"):
        assert forbidden not in skill
    assert "property_values_included" in helper
    assert "design_write_v3_" in helper
    assert "run-design-write-v3-validation.sh" in deploy
    assert "v3_validation_json.py" in deploy
    assert "design-write-v3-plan.json" in deploy
    assert "design-write-v3-validation.il" in deploy


def test_v4_validation_is_plan_bound_fixed_and_rollback_backed() -> None:
    plan = json.loads(V4_PLAN.read_text(encoding="utf-8"))
    runner = RUNNER.read_text(encoding="utf-8")
    helper = V4_HELPER.read_text(encoding="utf-8")
    worker = V4_WORKER.read_text(encoding="utf-8")
    skill = V4_SCRIPT.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert plan["execution_enabled"] is False
    assert "c5b2f418c5a76bfe54adc24c2ee947a33d904122b404bba323706dfbe3cbdd66" in helper
    assert "APPROVE_MCP_WRITE_VALIDATED_V4_C5B2F418" in helper
    assert "design-write-v4-plan-check" in runner
    assert "design-write-v4-validate" in runner
    assert "active Virtuoso process blocks V4 validation" in worker
    assert "Differential_Amplifier_TB2_MCP_TEST_V4/schematic" in worker
    assert "Differential_Amplifier_TB2_MCP_TEST_V4_BACKUP/schematic" in worker
    assert "source_before" in worker and "source_after" in worker
    assert "v3_target_before" in worker and "v3_target_after" in worker
    assert "v3_backup_before" in worker and "v3_backup_after" in worker
    assert "pdk_before" in worker and "pdk_after" in worker
    assert 'dbReplaceProp(targetCv propertyName "string" propertyValue)' in skill
    assert "schGeometryLastUpdated" in skill
    assert "MCP_V4_METADATA" in skill
    assert "dbCopyCellView(backupCv workLib targetCell sourceView nil nil t)" in skill
    assert "V4_CLEAN_VALIDATION_VERIFIED" in helper
    for forbidden in ("evalstring", "load(", "dbCreateInst", "dbDeleteObject"):
        assert forbidden not in skill
    assert "design-write-v4-plan.json" in deploy
    assert "run-design-write-v4-validation.sh" in deploy
    assert "v4_validation_json.py" in deploy
    assert "design-write-v4-validation.il" in deploy


def test_v3_forensic_is_fixed_read_only_and_value_redacted() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    helper = V3_FORENSIC_HELPER.read_text(encoding="utf-8")
    worker = V3_FORENSIC_WORKER.read_text(encoding="utf-8")
    skill = V3_FORENSIC_SCRIPT.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "design-write-v3-property-diff" in runner
    assert "0b9bf93c-11e9-416f-9e4a-69b1060fbd8e" in worker
    assert "active Virtuoso process blocks V3 forensic inspection" in worker
    assert "fingerprint_tree" in worker
    for token in (
        "source_before",
        "source_after",
        "v1_before",
        "v1_after",
        "v2_target_before",
        "v2_target_after",
        "v2_backup_before",
        "v2_backup_after",
        "v3_target_before",
        "v3_target_after",
        "v3_backup_before",
        "v3_backup_after",
        "pdk_before",
        "pdk_after",
    ):
        assert token in worker
    assert 'dbOpenCellViewByType' in skill
    assert '"r"' in skill
    assert "MCP_V3_FORENSIC_DIFF" in skill
    assert "approvedEqual" in skill
    assert "~>value" in skill
    for forbidden in (
        "dbSave",
        "dbCopyCellView",
        "dbReplaceProp",
        "dbCreateInst",
        "dbDeleteObject",
        "evalstring",
        "load(",
        "return(nil)",
    ):
        assert forbidden not in skill
    assert '"property_values_included": False' in helper
    assert '"differences": differences' in helper
    assert '"approved_value_equal"' in helper
    assert '"validated-v1"' not in helper
    assert "run-design-write-v3-forensic.sh" in deploy
    assert "v3_forensic_json.py" in deploy
    assert "design-write-v3-property-diff.il" in deploy


def test_v3_conditional_recovery_plan_is_immutable_and_non_executable() -> None:
    raw = V3_RECOVERY_PLAN.read_bytes()
    plan = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "edb34edf04b8ef4616f2215381cedf10f7ccf3ca7dfdcc8836e01d6e9f3b2d1b"
    )
    assert plan["plan_id"] == "mcp-cellview-property-v3-conditional-recovery"
    assert plan["status"] == "awaiting_explicit_recovery_approval"
    assert plan["execution_enabled"] is False
    assert plan["required_confirmation"] is None
    assert plan["target_overwrite_required"] is True
    assert plan["deletion_required"] is False
    assert plan["fallback_name_allowed"] is False
    assert plan["automatic_retry_allowed"] is False
    assert plan["forensic_evidence_sha256"] == (
        "8e1bbd824b1d4ea130c3f921e2745dddfffe9ef533a696e77e7a46884954abf6"
    )
    assert len(plan["observed_differences"]) == 2
    assert len(plan["acceptance_criteria"]) == 14
    assert len(plan["sequence"]) == 14
    assert plan["release_gate_enabled"] is False
    assert "design-write-v3-conditional-recovery-plan.json" not in DEPLOY.read_text(
        encoding="utf-8"
    )


def test_v3_deep_forensic_is_fixed_three_object_read_only_and_exact() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    helper = V3_DEEP_FORENSIC_HELPER.read_text(encoding="utf-8")
    worker = V3_DEEP_FORENSIC_WORKER.read_text(encoding="utf-8")
    skill = V3_DEEP_FORENSIC_SCRIPT.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "design-write-v3-deep-forensic" in runner
    assert "0b9bf93c-11e9-416f-9e4a-69b1060fbd8e" in worker
    assert "active Virtuoso process blocks V3 deep forensics" in worker
    assert "deep-forensic-v1" in worker
    assert "source_before" in worker and "source_after" in worker
    assert "target_before" in worker and "target_after" in worker
    assert "backup_before" in worker and "backup_after" in worker
    for forbidden_scope in (
        "MCP_TEST/schematic",
        "MCP_TEST_V2/schematic",
        "MCP_TEST_V2_BACKUP/schematic",
        "gpdk090_v4.6/libs.oa22",
    ):
        assert forbidden_scope not in worker
    assert 'dbOpenCellViewByType' in skill and '"r"' in skill
    assert "MCP_V3_DEEP_PROPERTY" in skill
    assert "%L" in skill
    assert "list(35 14 8)" in skill
    for forbidden in (
        "dbSave",
        "dbCopyCellView",
        "dbReplaceProp",
        "dbCreateInst",
        "dbDeleteObject",
        "evalstring",
        "load(",
    ):
        assert forbidden not in skill
    assert '"value": value' in helper
    assert '"SAFE_ROLLBACK_CANDIDATE"' in helper
    assert '"actual_rollback_performed": False' in helper
    assert "run-design-write-v3-deep-forensic.sh" in deploy
    assert "v3_deep_forensic_json.py" in deploy
    assert "design-write-v3-deep-forensic.il" in deploy


def test_v3_exact_conditional_rollback_plan_is_immutable_and_confirmation_bound() -> None:
    raw = V3_EXACT_ROLLBACK_PLAN.read_bytes()
    plan = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == (
        "eb057da2a866b92be5e1474bc3d06aba05f6ae49b5001465dd65ed9921afc911"
    )
    assert plan["forensic_classification"] == "SAFE_ROLLBACK_CANDIDATE"
    assert plan["status"] == "awaiting_separate_explicit_rollback_approval"
    assert plan["execution_enabled"] is False
    assert plan["required_confirmation"] is None
    assert plan["target_overwrite_required"] is True
    assert plan["deletion_required"] is False
    assert plan["forensic_report_sha256"] == (
        "6329eafc458098b744a40b70fc0a1a0d876af57c326d2d79e854e1ceaeb9b02f"
    )
    assert len(plan["exact_expected_property_changes"]) == 2
    assert len(plan["conditional_sequence"]) == 14
    assert len(plan["acceptance_criteria"]) == 15
    assert plan["release_gate_enabled"] is False
    assert "design-write-v3-exact-conditional-rollback-plan.json" in DEPLOY.read_text(
        encoding="utf-8"
    )


def test_v3_exact_rollback_is_plan_bound_fixed_and_confirmation_gated() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    helper = V3_EXACT_ROLLBACK_HELPER.read_text(encoding="utf-8")
    worker = V3_EXACT_ROLLBACK_WORKER.read_text(encoding="utf-8")
    skill = V3_EXACT_ROLLBACK_SCRIPT.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "APPROVE_V3_ROLLBACK_EB057DA2" in helper
    assert "design-write-v3-exact-rollback" in runner
    assert "invalid rollback origin" in runner
    assert "BLOCKED_PLAN_HASH_MISMATCH" in helper
    assert "acceptance_criteria" in helper
    assert "V3_ROLLBACK_VERIFIED" in helper
    assert "v3-rollback-events.jsonl" in worker
    assert 'evidence_root="$CADENCE_MCP_ROOT/write-rollback-v3"' in worker
    assert "write-rollback-v3" in deploy
    assert "source_before" in worker and "source_after" in worker
    assert "backup_before" in worker and "backup_after" in worker
    assert "target_before" in worker and "target_after" in worker
    assert "dbCopyCellView(backupCv workLib targetCell sourceView nil nil t)" in skill
    assert 'dbOpenCellViewByType(sourceLib sourceCell sourceView "schematic" "r")' in skill
    assert "dbSave" not in skill
    for forbidden in ("dbDeleteObject", "dbReplaceProp", "evalstring", "load("):
        assert forbidden not in skill
    assert "run-design-write-v3-exact-rollback.sh" in deploy
    assert "v3_exact_rollback_json.py" in deploy
    assert "design-write-v3-exact-rollback.il" in deploy
