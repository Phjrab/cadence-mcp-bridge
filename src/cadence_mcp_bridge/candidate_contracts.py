"""Pure, bounded V/A candidate planning; no admission, dispatcher or accounting store.

The manifest is a local plan, not proof of operator authenticity or permission to
execute. Its children reuse the existing complete-request and grant validators.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.operator_operations import (
    GRANT_DOCUMENT,
    OperationPlan,
    OperationRejected,
    OperationRequest,
    OperatorGrant,
    prepare_plan,
)
from cadence_mcp_bridge.result_reports import ReportConditions
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    LogicalId,
    Unit,
    VariableContract,
    VariableModel,
    canonical_digest,
    number_text,
)


class SuppliedValue(VariableModel):
    """Retain the supplied decimal spelling as well as the canonical child plan."""

    logical_id: LogicalId
    value: Annotated[str, Field(min_length=1, max_length=48)]
    unit: Unit

    @field_validator("value")
    @classmethod
    def decimal_text(cls, value: str) -> str:
        number_text(value)
        return value


class CandidateDefinition(VariableModel):
    candidate_id: LogicalId
    label: Annotated[str, Field(min_length=1, max_length=128)]
    operation_id: OperationId
    design_id: LogicalId
    analysis_id: LogicalId
    values: Annotated[tuple[SuppliedValue, ...], Field(min_length=1, max_length=32)]
    result_reservation_bytes: Annotated[int, Field(ge=1, le=1099511627776)]

    @model_validator(mode="after")
    def explicit_inventory(self) -> Self:
        if len({v.logical_id for v in self.values}) != len(self.values):
            raise ValueError("distinct complete values required")
        if "\0" in self.label:
            raise ValueError("NUL label is unsupported")
        return self

    def operation_request(self) -> OperationRequest:
        # The existing model independently applies all canonical numeric rules.
        request = OperationRequest.model_validate_json(
            json.dumps(
                {
                    "schema_version": 1,
                    "design_id": self.design_id,
                    "analysis_id": self.analysis_id,
                    "values": [v.model_dump(mode="json") for v in self.values],
                    "result_reservation_bytes": self.result_reservation_bytes,
                }
            )
        )
        return request.model_copy(
            update={
                "values": tuple(sorted(request.values, key=lambda value: value.logical_id)),
            }
        )


class CandidateSourceTarget(VariableModel):
    instance_path: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_#/-]{0,255}$")]
    master_library: BindingName
    master_cell: BindingName
    master_view: BindingName
    property_name: BindingName


class CandidateVariableBinding(VariableModel):
    logical_id: LogicalId
    cadence_binding: BindingName
    targets: Annotated[tuple[CandidateSourceTarget, ...], Field(min_length=1, max_length=16)]
    binding_evidence_sha256: Digest

    @model_validator(mode="after")
    def distinct_targets(self) -> Self:
        if len({canonical_digest(target) for target in self.targets}) != len(self.targets):
            raise ValueError("distinct exact source targets required")
        return self


class CandidateFixedEvidence(VariableModel):
    """Prospective references, not an independent source or electrical attestation."""

    source_revision_sha256: Digest
    testbench_revision_sha256: Digest
    source_baseline_sha256: Digest
    design_profile_sha256: Digest
    analysis_contract_sha256: Digest
    measurement_id: LogicalId
    reader_registration_sha256: Digest
    conditions: ReportConditions
    variable_bindings: Annotated[
        tuple[CandidateVariableBinding, ...], Field(min_length=1, max_length=32)
    ]
    verification: Literal["OPERATOR_SUPPLIED_REFERENCES_NOT_INDEPENDENTLY_ATTESTED"] = (
        "OPERATOR_SUPPLIED_REFERENCES_NOT_INDEPENDENTLY_ATTESTED"
    )

    @model_validator(mode="after")
    def unique_bindings(self) -> Self:
        ids = tuple(binding.logical_id for binding in self.variable_bindings)
        names = tuple(binding.cadence_binding for binding in self.variable_bindings)
        if len(set(ids)) != len(ids) or len(set(names)) != len(names):
            raise ValueError("distinct logical and ADE bindings required")
        targets = [
            (target.instance_path, target.property_name)
            for binding in self.variable_bindings
            for target in binding.targets
        ]
        if len(set(targets)) != len(targets):
            raise ValueError("source properties cannot alias independent variables")
        return self


class CandidateBatchRequest(VariableModel):
    schema_version: Literal[1] = 1
    batch_id: OperationId
    baseline_candidate_id: LogicalId
    declared_difference_ids: Annotated[tuple[LogicalId, ...], Field(min_length=1, max_length=32)]
    candidates: Annotated[tuple[CandidateDefinition, ...], Field(min_length=2, max_length=16)]
    fixed_evidence: CandidateFixedEvidence
    failure_policy: Literal["halt_all"] = "halt_all"

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_schema(cls, value: int) -> int:
        if type(value) is not int:
            raise ValueError("integer version required")
        return value

    @model_validator(mode="after")
    def identities_and_differences(self) -> Self:
        identities = tuple(c.candidate_id for c in self.candidates)
        operation_ids = tuple(c.operation_id for c in self.candidates)
        if len(set(identities)) != len(identities) or (
            len(set(operation_ids)) != len(operation_ids) or self.batch_id in operation_ids
        ):
            raise ValueError("distinct candidate and operation identities required")
        if self.baseline_candidate_id not in identities:
            raise ValueError("explicit baseline candidate required")
        if len(set(self.declared_difference_ids)) != len(self.declared_difference_ids):
            raise ValueError("distinct declared differences required")
        requests = tuple(c.operation_request() for c in self.candidates)
        baseline = requests[identities.index(self.baseline_candidate_id)]
        source = {(v.logical_id, v.unit): v.value for v in baseline.values}
        if {b.logical_id for b in self.fixed_evidence.variable_bindings} != {
            v.logical_id for v in baseline.values
        }:
            raise ValueError("exact source binding for every supplied variable required")
        vectors = set()
        differences: set[str] = set()
        for request in requests:
            if (request.design_id, request.analysis_id) != (
                baseline.design_id,
                baseline.analysis_id,
            ):
                raise ValueError("one registered design and analysis per batch required")
            values = {(v.logical_id, v.unit): v.value for v in request.values}
            if set(values) != set(source):
                raise ValueError("complete matching variable inventory and units required")
            vector = tuple(sorted(values.items()))
            if vector in vectors:
                raise ValueError("distinct canonical candidate vectors required")
            vectors.add(vector)
            differences.update(key[0] for key, value in values.items() if source[key] != value)
        if differences != set(self.declared_difference_ids):
            raise ValueError("declared differences must exactly match supplied differences")
        return self


class CandidateBatchPlan(VariableModel):
    schema_version: Literal[1] = 1
    request: CandidateBatchRequest
    plans: Annotated[tuple[OperationPlan, ...], Field(min_length=2, max_length=16)]
    varied_variables: Annotated[tuple[VariableContract, ...], Field(min_length=1, max_length=32)]
    expected_executions: Annotated[int, Field(ge=2, le=16)]
    result_reservation_bytes: Annotated[int, Field(ge=2, le=1099511627776)]
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False
    admission_created: Literal[False] = False
    new_reservations: Literal[0] = 0
    accounting: Literal["existing_remote_shared_ledger_no_reset"] = (
        "existing_remote_shared_ledger_no_reset"
    )
    qualification: Literal["LOCAL_PLAN_NOT_NATIVE_CANDIDATE_QUALIFICATION"] = (
        "LOCAL_PLAN_NOT_NATIVE_CANDIDATE_QUALIFICATION"
    )

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_schema(cls, value: int) -> int:
        if type(value) is not int:
            raise ValueError("integer version required")
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len(self.plans) != len(self.request.candidates):
            raise ValueError("candidate plan count differs")
        if self.expected_executions != len(self.plans) or self.result_reservation_bytes != sum(
            p.request.result_reservation_bytes for p in self.plans
        ):
            raise ValueError("candidate totals differ")
        first = self.plans[0]
        if first.analysis != self.request.fixed_evidence.conditions.analysis_inputs.analysis:
            raise ValueError("fixed analysis evidence differs from the child analysis")
        if (first.analysis == "ac") != (
            self.request.fixed_evidence.conditions.transfer is not None
        ):
            raise ValueError("fixed transfer evidence differs from the child analysis")
        for candidate, plan in zip(self.request.candidates, self.plans, strict=True):
            if plan.request != candidate.operation_request():
                raise ValueError("candidate child request differs")
            if plan.model_copy(update={"request": first.request}) != first:
                raise ValueError("candidate authority or runtime binding differs")
        ids = tuple(v.logical_id for v in self.varied_variables)
        if ids != tuple(sorted(self.request.declared_difference_ids)) or (
            len({v.cadence_binding for v in self.varied_variables}) != len(ids)
        ):
            raise ValueError("registered difference bindings differ")
        for variable in self.varied_variables:
            if variable.unit not in ("V", "A") or (
                variable.mutation_policy != "owned_copy_only"
                or variable.range_status != "qualified"
            ):
                raise ValueError("candidate difference requires a qualified owned-copy V/A region")
            for plan in self.plans:
                value = next(v for v in plan.request.values if v.logical_id == variable.logical_id)
                if value.unit != variable.unit or variable.check_number(value.value) is not None:
                    raise ValueError("candidate value violates its registered difference contract")
        return self

    @property
    def plan_sha256(self) -> str:
        return canonical_digest(self)


def prepare_candidate_plan(
    context: ExecutionContext,
    grant: OperatorGrant,
    grant_sha256: str,
    request: CandidateBatchRequest,
    now: int,
) -> CandidateBatchPlan:
    """Validate complete child plans locally; never create authority or contact a VM."""
    # Reparse even frozen models: model_copy(update=...) can bypass Pydantic validation.
    if type(now) is not int or now < 1:
        raise OperationRejected("candidate_planning_time_invalid")
    request = CandidateBatchRequest.model_validate_json(request.model_dump_json())
    checked_grant = GRANT_DOCUMENT.validate_json(grant.model_dump_json())
    checked_grant._source_document = grant._source_document
    TypeAdapter(Digest).validate_python(grant_sha256)
    plans = tuple(
        prepare_plan(
            context,
            checked_grant,
            grant_sha256,
            candidate.operation_request(),
            now,
        )
        for candidate in request.candidates
    )
    if len(plans) > checked_grant.attempt_limit or (
        sum(plan.request.result_reservation_bytes for plan in plans)
        > checked_grant.result_reserved_bytes_limit
    ):
        raise OperationRejected("candidate_batch_exceeds_authority")
    registry = context.contracts.designs
    design_id = request.candidates[0].design_id
    variable_set = registry.variable_set(design_id)
    if variable_set is None:
        raise OperationRejected("candidate_difference_contract_denied")
    registered = {v.logical_id: v for v in variable_set.variables}
    contract = next(
        c
        for c in registry.analyses_for(design_id)
        if c.analysis_id == request.candidates[0].analysis_id
    )
    evidence = request.fixed_evidence
    if (
        evidence.design_profile_sha256 != canonical_digest(registry.profile(design_id))
        or (evidence.analysis_contract_sha256 != canonical_digest(contract))
        or evidence.measurement_id not in registry.profile(design_id).allowed_measurements
        or (evidence.conditions.analysis_inputs.analysis != plans[0].analysis)
        or any(
            registered[b.logical_id].cadence_binding != b.cadence_binding
            for b in evidence.variable_bindings
        )
    ):
        raise OperationRejected("candidate_fixed_registration_mismatch")
    try:
        varied = tuple(registered[key] for key in sorted(request.declared_difference_ids))
        return CandidateBatchPlan(
            request=request,
            plans=plans,
            varied_variables=varied,
            expected_executions=len(plans),
            result_reservation_bytes=sum(p.request.result_reservation_bytes for p in plans),
        )
    except (KeyError, ValueError):
        raise OperationRejected("candidate_difference_contract_denied") from None
