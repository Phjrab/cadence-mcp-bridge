"""Closed registered analysis contracts; only compiled adapters can dispatch."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import model_validator

from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import (
    Analysis,
    NativeDiagnosticProfiles,
    NativeDiagnosticResult,
    NativeDiagnosticStatus,
    NativeSettings,
    OperationId,
)
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest


def native_adapter_digest() -> str:
    """Bind the compiled fixed contract, not operator-supplied executable bytes."""
    return canonical_digest(NativeDiagnosticProfiles())


class AnalysisContract(VariableModel):
    design_id: LogicalId
    analysis_id: LogicalId
    analysis: Analysis
    design_profile_sha256: Digest
    variable_set_sha256: Digest | None
    adapter_kind: Literal["native-fixed-reference-v1", "unqualified"]
    adapter_contract_sha256: Digest | None
    input_policy: Literal["fixed_operating_point_no_parameters", "unqualified"]

    @model_validator(mode="after")
    def adapter_shape(self) -> Self:
        if self.adapter_kind == "unqualified":
            if self.adapter_contract_sha256 is not None or self.input_policy != "unqualified":
                raise ValueError("unqualified analysis cannot grant an adapter")
        elif (
            self.adapter_contract_sha256 != native_adapter_digest()
            or self.variable_set_sha256 is None
            or self.input_policy != "fixed_operating_point_no_parameters"
        ):
            raise ValueError("fixed adapter must match the compiled native contract")
        return self


class AnalysisSelection(VariableModel):
    design_id: LogicalId
    analysis_id: LogicalId


class AnalysisJobQuery(AnalysisSelection):
    operation_id: OperationId


class AnalysisSubmission(AnalysisJobQuery):
    expected_plan_hash: Digest


class AnalysisPlan(ContractModel):
    contract_version: Literal[1] = 1
    design_id: LogicalId
    analysis_id: LogicalId
    analysis: Analysis
    plan_hash: Digest
    dispatch_eligible: bool
    qualification_scope: Literal["fixed_native_compatibility", "unqualified"]
    blocking_reason: Literal["adapter_unqualified"] | None
    input_policy: Literal["fixed_operating_point_no_parameters", "unqualified"]
    fixed_settings: NativeSettings | None
    runtime_verification: Literal["existing_native_guards_required"] = (
        "existing_native_guards_required"
    )
    resource_accounting: Literal["existing_remote_shared_ledger_no_reset"] = (
        "existing_remote_shared_ledger_no_reset"
    )
    cancellation_supported: Literal[False] = False
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class AnalysisList(ContractModel):
    design_id: LogicalId
    declared_analyses: tuple[Analysis, ...]
    analyses: tuple[AnalysisPlan, ...]


class AnalysisStatus(ContractModel):
    design_id: LogicalId
    analysis_id: LogicalId
    operation_id: OperationId
    plan_hash: Digest
    native: NativeDiagnosticStatus


class AnalysisResult(ContractModel):
    design_id: LogicalId
    analysis_id: LogicalId
    operation_id: OperationId
    plan_hash: Digest
    native: NativeDiagnosticResult
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class AnalysisCancellation(ContractModel):
    status: AnalysisStatus
    outcome: Literal["terminal_noop", "unsupported_active_cancellation"]
    cancellation_supported: Literal[False] = False
    cancelled: Literal[False] = False
