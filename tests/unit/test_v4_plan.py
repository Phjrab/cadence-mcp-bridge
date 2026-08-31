from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAN = PROJECT_ROOT / "remote" / "config" / "design-write-v4-plan.json"
RUNNER = PROJECT_ROOT / "remote" / "bin" / "cadence-runner"
DEPLOY = PROJECT_ROOT / "scripts" / "deploy-remote.ps1"


def test_v4_plan_is_non_executable_and_uses_only_new_fixed_names() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))

    assert plan["plan_id"] == "mcp-cellview-property-v4-clean-validation"
    assert plan["status"] == "awaiting_separate_explicit_mutation_approval"
    assert plan["execution_enabled"] is False
    assert plan["implementation_enabled"] is False
    assert plan["required_confirmation"] is None
    assert plan["target"] == (
        "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V4/schematic"
    )
    assert plan["backup"] == (
        "MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V4_BACKUP/schematic"
    )
    assert len(plan["preserved_read_only_evidence"]) == 5
    assert len(plan["acceptance_criteria"]) == 18
    assert len(plan["sequence"]) == 18
    assert plan["automatic_retry_allowed"] is False
    assert plan["cleanup_allowed"] is False
    assert plan["fallback_name_allowed"] is False
    assert plan["release_gate_enabled"] is False


def test_v4_plan_bounds_semantic_and_oa_metadata_changes() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))

    assert plan["proposed_semantic_change"] == {
        "name": "mcpMutationTest",
        "object_scope": "cellview",
        "type": "string",
        "before_present": False,
        "proposed_value": "validated-v1",
    }
    assert plan["bounded_oa_metadata_side_effect"]["name"] == (
        "schGeometryLastUpdated"
    )
    assert plan["bounded_oa_metadata_side_effect"]["type"] == "int"
    assert plan["bounded_oa_metadata_side_effect"]["semantic_mutation"] is False
    assert plan["affected_semantic_objects"] == 1
    assert plan["original_library_mutations"] == 0
    assert plan["destructive"] is False


def test_v4_plan_is_not_exposed_or_deployed() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "design-write-v4" not in runner
    assert "design-write-v4-plan.json" not in deploy
    assert "APPROVE_MCP_WRITE_VALIDATED_V4" not in runner


def test_v4_plan_canonical_sha256() -> None:
    digest = hashlib.sha256(PLAN.read_bytes()).hexdigest()

    assert digest == "c5b2f418c5a76bfe54adc24c2ee947a33d904122b404bba323706dfbe3cbdd66"
