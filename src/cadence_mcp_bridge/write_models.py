"""Typed contracts for the single approved copy-based write validation."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from cadence_mcp_bridge.models import ContractModel

WriteConfirmation = Literal["APPROVE_MCP_WRITE_VALIDATED_V2"]


class DesignWritePlan(ContractModel):
    policy_version: Literal[2]
    plan_id: Literal["mcp-cellview-property-v2"]
    plan_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source: Literal["MyDesignLib/Differential_Amplifier_TB2/schematic"]
    target: Literal["MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic"]
    backup: Literal["MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic"]
    preserved_target: Literal["MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic"]
    operation: Literal["set_cellview_property"]
    property_name: Literal["mcpMutationTest"]
    old_value: None
    proposed_value: Literal["validated-v1"]
    affected_objects: Literal[1]
    original_library_mutations: Literal[0]
    destructive: Literal[False]
    source_exists: bool
    source_master_authoritative: bool
    source_artifact_present: bool
    target_exists: bool
    backup_exists: bool
    preserved_target_exists: bool
    ready: bool
    confirmation: WriteConfirmation


class DesignWriteValidationResult(ContractModel):
    validation_id: UUID
    plan_id: Literal["mcp-cellview-property-v2"]
    plan_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source: Literal["MyDesignLib/Differential_Amplifier_TB2/schematic"]
    target: Literal["MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic"]
    backup: Literal["MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic"]
    preserved_target: Literal["MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic"]
    operation: Literal["set_cellview_property"]
    property_name: Literal["mcpMutationTest"]
    old_value: None
    proposed_value: Literal["validated-v1"]
    affected_objects: Literal[1]
    original_library_mutations: Literal[0]
    destructive: Literal[False]
    copy_verified: Literal[True]
    dry_run_unchanged: Literal[True]
    backup_verified: Literal[True]
    apply_verified: Literal[True]
    rollback_verified: Literal[True]
    source_unchanged: Literal[True]
    preserved_target_unchanged: Literal[True]
    topology_unchanged: Literal[True]
    baseline_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    rollback_fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    audit_recorded: Literal[True]
    sequence: tuple[
        Literal["source_verify"],
        Literal["copy"],
        Literal["baseline"],
        Literal["dry_run"],
        Literal["dry_run_unchanged"],
        Literal["backup"],
        Literal["apply"],
        Literal["verify_apply"],
        Literal["source_unchanged_before_rollback"],
        Literal["rollback"],
        Literal["verify_rollback"],
        Literal["source_unchanged"],
        Literal["complete"],
    ]
