"""Typed, read-only operator adapters over the research cores."""

import json
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator

from cadence_mcp_bridge.designs import BindingName
from cadence_mcp_bridge.native_service import NativeOperationQuery, NativeOperationService
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    ChangeValue,
    RegisteredMosQualification,
    plan_registered_mos_change,
)
from cadence_mcp_bridge.research_circuit import (
    MosBlockEvidence,
    OwnedMosBlockPlan,
    ResearchCircuit,
    plan_owned_mos_block,
    validate_research_circuit,
    verify_owned_mos_block,
)
from cadence_mcp_bridge.research_measurements import (
    AcGainDefinition,
    capture_ac_gain,
    capture_supply_power,
)
from cadence_mcp_bridge.research_transient import ResearchTransientQuery, capture_research_transient
from cadence_mcp_bridge.result_reports import ResultReport
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
)


class ResearchCircuitRequest(VariableModel):
    definition: ResearchCircuit

    @field_validator("definition", mode="before")
    @classmethod
    def decode_json_arrays(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return ResearchCircuit.model_validate_json(json.dumps(value, allow_nan=False))
        return value


class ResearchCircuitValidation(VariableModel):
    definition_sha256: Digest
    definition: ResearchCircuit
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False


def validate_circuit(request: ResearchCircuitRequest) -> ResearchCircuitValidation:
    definition = validate_research_circuit(request.definition)
    return ResearchCircuitValidation(
        definition=definition, definition_sha256=canonical_digest(definition)
    )


class ResearchMosBlockRequest(ResearchCircuitRequest):
    expected_binding: RevisionBinding
    expected_definition_sha256: Digest
    output_library: BindingName


class ResearchMosBlockPreparation(VariableModel):
    plan: OwnedMosBlockPlan
    plan_sha256: Digest
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False


def prepare_mos_block(request: ResearchMosBlockRequest) -> ResearchMosBlockPreparation:
    plan = plan_owned_mos_block(
        request.definition,
        expected_binding=request.expected_binding,
        expected_definition_sha256=request.expected_definition_sha256,
        output_library=request.output_library,
    )
    return ResearchMosBlockPreparation(plan=plan, plan_sha256=canonical_digest(plan))


class ResearchMosBlockEvidenceRequest(VariableModel):
    plan: OwnedMosBlockPlan
    evidence: MosBlockEvidence
    expected_plan_sha256: Digest
    expected_reopened_tree_sha256: Digest
    expected_reopen_artifact_sha256: Digest
    expected_netlist_artifact_sha256: Digest

    @field_validator("plan", mode="before")
    @classmethod
    def decode_plan(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return OwnedMosBlockPlan.model_validate_json(json.dumps(value, allow_nan=False))
        return value

    @field_validator("evidence", mode="before")
    @classmethod
    def decode_evidence(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return MosBlockEvidence.model_validate_json(json.dumps(value, allow_nan=False))
        return value


class ResearchMosBlockVerification(VariableModel):
    plan_sha256: Digest
    reopened_tree_sha256: Digest
    reopen_artifact_sha256: Digest
    netlist_artifact_sha256: Digest
    status: Literal["MATCHED"] = "MATCHED"
    provenance: Literal["LOCAL_EVIDENCE_COMPARISON"] = "LOCAL_EVIDENCE_COMPARISON"
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False


def compare_mos_block(request: ResearchMosBlockEvidenceRequest) -> ResearchMosBlockVerification:
    verify_owned_mos_block(
        request.plan,
        request.evidence,
        expected_plan_sha256=request.expected_plan_sha256,
        expected_reopened_tree_sha256=request.expected_reopened_tree_sha256,
        expected_reopen_artifact_sha256=request.expected_reopen_artifact_sha256,
        expected_netlist_artifact_sha256=request.expected_netlist_artifact_sha256,
    )
    return ResearchMosBlockVerification(
        plan_sha256=request.expected_plan_sha256,
        reopened_tree_sha256=request.expected_reopened_tree_sha256,
        reopen_artifact_sha256=request.expected_reopen_artifact_sha256,
        netlist_artifact_sha256=request.expected_netlist_artifact_sha256,
    )


class RegisteredMosChangeRequest(VariableModel):
    qualification: RegisteredMosQualification
    candidate_id: LogicalId
    candidate_revision: RevisionBinding
    requested: ChangeValue

    @field_validator("qualification", mode="before")
    @classmethod
    def decode_json_arrays(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return RegisteredMosQualification.model_validate_json(
                json.dumps(value, allow_nan=False)
            )
        return value


class ResearchMosPlan(VariableModel):
    plan: ChangePlan
    plan_sha256: Digest
    evidence: Literal["CALLER_SUPPLIED_QUALIFICATION"] = "CALLER_SUPPLIED_QUALIFICATION"
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False


def plan_mos(request: RegisteredMosChangeRequest) -> ResearchMosPlan:
    plan = plan_registered_mos_change(
        request.qualification, request.candidate_id, request.candidate_revision, request.requested
    )
    return ResearchMosPlan(plan=plan, plan_sha256=plan.plan_sha256)


class ResearchTransientRequest(ResearchTransientQuery):
    @field_validator("signals", mode="before")
    @classmethod
    def decode_signals(cls, value: Any) -> Any:
        return tuple(value) if type(value) is list else value


class RetainedResearchResult(VariableModel):
    source: ResultReport
    new_simulations: Literal[0]
    new_extractions: Literal[0]
    new_reservations: Literal[0]
    remote_contact: Literal[True]


class ResearchTransientResult(RetainedResearchResult):
    definition: ResearchTransientQuery
    signals: dict[LogicalId, dict[str, Any]]
    measurements: dict[str, dict[str, Any]]
    sample_kind: Literal["NATIVE_SAVED_VECTOR"]
    qualification: Literal["SAVED_SAMPLE_ESTIMATES_NO_SOLVER_GRID_CONVERGENCE"]
    declared_maxstep_s: NumberText
    waveforms_sha256: Digest
    terminal_receipt_sha256: Digest
    tran_supply_evidence_sha256: Digest | None = None


class ResearchSupplyPowerRequest(NativeOperationQuery):
    supply_ids: Annotated[tuple[LogicalId, ...], Field(min_length=1, max_length=8)]

    @field_validator("supply_ids", mode="before")
    @classmethod
    def decode_supply_ids(cls, value: Any) -> Any:
        return tuple(value) if type(value) is list else value

    @field_validator("supply_ids")
    @classmethod
    def distinct_supply_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("supply IDs must be distinct")
        return value


class ResearchPowerResult(RetainedResearchResult):
    measurement: dict[str, Any]
    conditions_sha256: Digest


class ResearchAcGainResult(ResearchPowerResult):
    spectrum_sha256: Digest


class ResearchAcGainRequest(NativeOperationQuery):
    definition: AcGainDefinition


async def transient_result(
    native: NativeOperationService, request: ResearchTransientRequest
) -> ResearchTransientResult:
    raw = await capture_research_transient(native, request)
    return ResearchTransientResult.model_validate_json(json.dumps(raw, allow_nan=False))


async def supply_power_result(
    native: NativeOperationService, request: ResearchSupplyPowerRequest
) -> ResearchPowerResult:
    raw = await capture_supply_power(
        native, request.operation_id, request.expected_plan_sha256, request.supply_ids
    )
    return ResearchPowerResult.model_validate_json(json.dumps(raw, allow_nan=False))


async def ac_gain_result(
    native: NativeOperationService, request: ResearchAcGainRequest
) -> ResearchAcGainResult:
    raw = await capture_ac_gain(
        native, request.operation_id, request.expected_plan_sha256, request.definition
    )
    return ResearchAcGainResult.model_validate_json(json.dumps(raw, allow_nan=False))
