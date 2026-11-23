"""Typed, read-only operator adapters over the research cores."""

import json
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from pydantic import ConfigDict, Field, field_validator, with_config

from cadence_mcp_bridge.designs import BindingName
from cadence_mcp_bridge.generic_measurements import Selector
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import NativeOperationQuery, NativeOperationService
from cadence_mcp_bridge.parameter_changes import (
    ChangePlan,
    ChangeValue,
    RegisteredMosQualification,
    plan_registered_mos_change,
)
from cadence_mcp_bridge.research_circuit import (
    MosBlockEvidence,
    NetlistedCircuit,
    OwnedMosBlockPlan,
    ResearchCircuit,
    plan_owned_mos_block,
    project_mos_block_netlist,
    validate_research_circuit,
    verify_owned_mos_block,
)
from cadence_mcp_bridge.research_measurements import (
    AcGainDefinition,
    DeviceOpQuery,
    DeviceOpSourceBinding,
    DevicePath,
    Finite,
    OpField,
    capture_ac_gain,
    capture_device_operating_points,
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


class ResearchRawNetlistResult(VariableModel):
    plan_sha256: Digest
    netlist_artifact_sha256: Digest
    netlisted: Annotated[tuple[NetlistedCircuit, ...], Field(min_length=1, max_length=31)]
    status: Literal["MATCHED"] = "MATCHED"
    provenance: Literal["LOCAL_DUT_NETLIST_COMPARISON"] = "LOCAL_DUT_NETLIST_COMPARISON"
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False


def compare_raw_netlist(
    plan: OwnedMosBlockPlan,
    raw: bytes,
    *,
    expected_plan_sha256: str,
    expected_netlist_artifact_sha256: str,
) -> ResearchRawNetlistResult:
    netlisted = project_mos_block_netlist(
        plan,
        raw,
        expected_plan_sha256=expected_plan_sha256,
        expected_netlist_artifact_sha256=expected_netlist_artifact_sha256,
    )
    return ResearchRawNetlistResult(
        plan_sha256=expected_plan_sha256,
        netlist_artifact_sha256=expected_netlist_artifact_sha256,
        netlisted=netlisted,
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


@with_config(ConfigDict(extra="forbid"))
class TransientSupplyContribution(TypedDict):
    source_id: LogicalId
    role: Literal["supply"]
    positive_node: LogicalId | None
    negative_node: LogicalId | None
    current_selector: Selector
    current_convention: Literal["positive_into_source_positive_terminal_A"]
    status: Literal["ESTIMATED", "NOT_EVALUATED"]
    reason: str | None
    value: Finite | None
    unit: Literal["W"]
    maximum_observed_gap_s: NotRequired[Finite]
    saved_vector_samples: NotRequired[int]


@with_config(ConfigDict(extra="forbid"))
class TransientAveragePower(TypedDict):
    status: Literal["ESTIMATED", "NOT_EVALUATED"]
    reason: str | None
    value: Finite | None
    unit: Literal["W"]
    sources: NotRequired[
        Annotated[list[TransientSupplyContribution], Field(min_length=1, max_length=6)]
    ]
    method: NotRequired[
        Literal["time_mean_of_negative_terminal_voltage_times_signed_current_piecewise_linear"]
    ]


@with_config(ConfigDict(extra="forbid"))
class TransientMeasurements(TypedDict):
    delay: NotRequired[dict[str, Any]]
    slew: NotRequired[dict[str, Any]]
    settling: NotRequired[dict[str, Any]]
    average_supply_power: TransientAveragePower


class ResearchTransientResult(RetainedResearchResult):
    definition: ResearchTransientQuery
    signals: dict[LogicalId, dict[str, Any]]
    measurements: TransientMeasurements
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


class DeviceOpMeasurementRow(VariableModel):
    instance_path: DevicePath
    field: OpField
    unit: Literal["A", "S", "V", "1"]
    value: Finite | None
    reason: Literal["field_not_available", "instance_not_available", "field_not_retained"] | None
    interpretation_reason: Literal["registered_model_region_meaning_unavailable"] | None


class DeviceOpMeasurement(VariableModel):
    operation_id: OperationId
    plan_sha256: Digest
    execution_input_sha256: Digest
    registration_sha256: Digest
    op_frame_sha256: Digest
    verification_at_read: Literal["LOCAL_OP_PAYLOAD_IDENTITY_ONLY"]
    measurements: Annotated[list[DeviceOpMeasurementRow], Field(max_length=448)]


class DeviceOpResult(VariableModel):
    status: Literal["AVAILABLE", "NOT_AVAILABLE"]
    reason: (
        Literal["device_op_source_not_configured", "registered_op_record_unavailable"] | None
    ) = None
    registration_id: LogicalId | None = None
    measurement: DeviceOpMeasurement | None = None
    source: ResultReport | None = None
    source_report_sha256: Digest | None = None
    terminal_sha256: Digest | None = None
    catalog_sha256: Digest | None = None
    verification_at_read: (
        Literal["OPERATOR_PINNED_ARTIFACT_AND_RETAINED_TERMINAL_VERIFIED"] | None
    ) = None
    remote_contact: Literal[False]
    new_simulations: Literal[0]
    new_extractions: Literal[0]
    new_reservations: Literal[0]


def device_op_result(native: NativeOperationService, request: DeviceOpQuery) -> DeviceOpResult:
    binding = native.context.binding
    path, digest = binding.device_op_catalog_path, binding.device_op_catalog_sha256
    source = (
        DeviceOpSourceBinding(catalog_path=path, catalog_sha256=digest)
        if path is not None and digest is not None
        else None
    )
    raw = capture_device_operating_points(native, request, source=source)
    return DeviceOpResult.model_validate_json(json.dumps(raw, allow_nan=False))
