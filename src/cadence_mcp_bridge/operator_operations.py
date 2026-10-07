"""Local reusable authority and immutable plans; remote admission remains gated.

No ledger, grant writer, native dispatcher or parallel lifecycle engine is created.
The existing AnalysisStore is used only by the existing qualified supervisor.
"""

from __future__ import annotations

import hashlib
import os
import stat
import time
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.environments import _closed_json
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    Unit,
    VariableModel,
    VariableValue,
    VariableValuesRequest,
    canonical_digest,
    number_text,
)


class OperationRejected(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("Operator operation rejected")


class NumericRegion(VariableModel):
    logical_id: LogicalId
    unit: Unit
    minimum: NumberText
    maximum: NumberText

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def canonical_number(cls, value: str) -> str:
        return number_text(value)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if Decimal(self.minimum) > Decimal(self.maximum):
            raise ValueError("ordered numeric region required")
        return self


class OperatorGrant(VariableModel):
    schema_version: Literal[1]
    grant_id: LogicalId
    authorization_source: Literal["explicit_operator_record"]
    resource_domain_sha256: Digest
    runner_sha256: Digest
    ledger_ref: LogicalId
    environment_sha256: Digest
    design_sha256: Digest
    pdk_sha256: Digest
    design_ids: Annotated[tuple[LogicalId, ...], Field(min_length=1, max_length=16)]
    analyses: Annotated[tuple[Literal["dc", "ac", "tran"], ...], Field(min_length=1, max_length=3)]
    actions: Annotated[
        tuple[Literal["submit", "cancel_pending", "recover_extraction"], ...],
        Field(min_length=1, max_length=3),
    ]
    numeric_regions: Annotated[tuple[NumericRegion, ...], Field(max_length=32)]
    attempt_limit: Annotated[int, Field(ge=1, le=500)]
    result_reserved_bytes_limit: Annotated[int, Field(ge=1, le=1099511627776)]
    valid_from_unix: Annotated[int, Field(ge=1)]
    valid_until_unix: Annotated[int, Field(ge=1)]
    status: Literal["active", "revoked"]

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_integer(cls, value: int) -> int:
        if type(value) is not int:
            raise ValueError("integer version required")
        return value

    @model_validator(mode="after")
    def coherent(self) -> Self:
        for values in (
            self.design_ids,
            self.analyses,
            self.actions,
            tuple(r.logical_id for r in self.numeric_regions),
        ):
            if len(values) != len(set(values)):
                raise ValueError("duplicate authority identifier")
        if self.valid_from_unix >= self.valid_until_unix:
            raise ValueError("positive authority lifetime required")
        return self


class ExplicitValue(VariableValue):
    logical_id: LogicalId


class OperationRequest(VariableModel):
    schema_version: Literal[1]
    design_id: LogicalId
    analysis_id: LogicalId
    values: Annotated[tuple[ExplicitValue, ...], Field(max_length=32)]
    result_reservation_bytes: Annotated[int, Field(ge=1, le=1099511627776)]

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_integer(cls, value: int) -> int:
        if type(value) is not int:
            raise ValueError("integer version required")
        return value

    @model_validator(mode="after")
    def unique_values(self) -> Self:
        if len({v.logical_id for v in self.values}) != len(self.values):
            raise ValueError("duplicate value")
        return self


class OperationPlan(VariableModel):
    schema_version: Literal[1] = 1
    resource_domain_sha256: Digest
    runner_sha256: Digest
    ledger_ref: LogicalId
    environment_sha256: Digest
    design_sha256: Digest
    pdk_sha256: Digest
    grant_sha256: Digest
    request: OperationRequest
    analysis: Literal["dc", "ac", "tran"]
    attempt_cost: Literal[1] = 1
    accounting: Literal["existing_remote_shared_ledger_no_reset"] = (
        "existing_remote_shared_ledger_no_reset"
    )

    @property
    def plan_sha256(self) -> str:
        return canonical_digest(self)


def bounded_document(path: Path) -> bytes:
    source = _local_path(path)
    metadata = source.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise OperationRejected("operator_document_identity_invalid")
    with source.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            raise OperationRejected("operator_document_identity_invalid")
        data = stream.read(65537)
    _closed_json(data)
    return data


def load_grant(path: Path, expected_sha256: str) -> tuple[OperatorGrant, str]:
    data = bounded_document(path)
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256:
        raise OperationRejected("stale_grant_digest")
    return OperatorGrant.model_validate_json(data), digest


def match_grant(context: ExecutionContext, grant: OperatorGrant, now: int) -> None:
    bindings = (
        (grant.grant_id, context.binding.authority_ref),
        (grant.resource_domain_sha256, context.resource_domain_sha256),
        (grant.runner_sha256, context.binding.runner_sha256),
        (grant.ledger_ref, context.binding.ledger_ref),
        (grant.environment_sha256, context.binding.environment_sha256),
        (grant.design_sha256, context.binding.design_sha256),
        (grant.pdk_sha256, context.binding.pdk_sha256),
    )
    if any(actual != expected for actual, expected in bindings):
        raise OperationRejected("authority_binding_mismatch")
    if grant.status != "active" or not grant.valid_from_unix <= now < grant.valid_until_unix:
        raise OperationRejected("authority_inactive")
    profile = context.contracts.environment
    if (
        grant.attempt_limit > profile.limits.spectre_attempts
        or grant.result_reserved_bytes_limit > profile.limits.result_reserved_bytes
    ):
        raise OperationRejected("authority_exceeds_environment_ceiling")
    for design_id in grant.design_ids:
        context.resolve(design_id)


def prepare_plan(
    context: ExecutionContext,
    grant: OperatorGrant,
    digest: str,
    request: OperationRequest,
    now: int,
) -> OperationPlan:
    match_grant(context, grant, now)
    if request.design_id not in grant.design_ids or "submit" not in grant.actions:
        raise OperationRejected("authority_scope_denied")
    registry = context.contracts.designs
    profile = registry.profile(request.design_id)
    contract = next(
        (
            c
            for c in registry.analyses_for(request.design_id)
            if c.analysis_id == request.analysis_id
        ),
        None,
    )
    if contract is None or contract.analysis not in grant.analyses:
        raise OperationRejected("analysis_scope_denied")
    if request.result_reservation_bytes > grant.result_reserved_bytes_limit:
        raise OperationRejected("reservation_exceeds_authority")
    # Require every declared variable: no ADE defaults or prior-job inheritance.
    supplied = {v.logical_id: VariableValue(value=v.value, unit=v.unit) for v in request.values}
    if set(supplied) != set(profile.allowed_variables):
        raise OperationRejected("all_explicit_registered_values_required")
    if supplied:
        checked = registry.check_variables(
            VariableValuesRequest(design_id=request.design_id, values=supplied)
        )
        if not checked.locally_admissible:
            raise OperationRejected("registered_numeric_contract_denied")
    regions = {r.logical_id: r for r in grant.numeric_regions}
    if set(regions) != set(supplied):
        raise OperationRejected("authority_numeric_scope_mismatch")
    for logical_id, value in supplied.items():
        region = regions[logical_id]
        if region.unit != value.unit or not (
            Decimal(region.minimum) <= Decimal(value.value) <= Decimal(region.maximum)
        ):
            raise OperationRejected("authority_numeric_scope_denied")
    # Canonical ordering ensures request order cannot create another plan identity.
    canonical = request.model_copy(
        update={"values": tuple(sorted(request.values, key=lambda v: v.logical_id))}
    )
    return OperationPlan(
        resource_domain_sha256=context.resource_domain_sha256,
        runner_sha256=context.binding.runner_sha256,
        ledger_ref=context.binding.ledger_ref,
        environment_sha256=context.binding.environment_sha256,
        design_sha256=context.binding.design_sha256,
        pdk_sha256=context.binding.pdk_sha256,
        grant_sha256=digest,
        request=canonical,
        analysis=contract.analysis,
    )


def inspect_authority(context: ExecutionContext, path: Path, digest: str) -> dict[str, object]:
    grant, actual_digest = load_grant(path, digest)
    match_grant(context, grant, int(time.time()))
    return {
        "status": "LOCAL_AUTHORITY_DESCRIPTION_MATCHED",
        "grant_id": grant.grant_id,
        "grant_sha256": actual_digest,
        "resource_domain_sha256": context.resource_domain_sha256,
        "attempt_ceiling": grant.attempt_limit,
        "result_reservation_ceiling_bytes": grant.result_reserved_bytes_limit,
        "remaining_remote_attempts": None,
        "remaining_remote_reserved_bytes": None,
        "operator_authenticity": "NOT_ATTESTED",
        "remote_ledger": "NOT_ASSESSED",
        "execution_authorized": False,
        "remote_contact": False,
    }


def inspect_plan(
    context: ExecutionContext, path: Path, digest: str, request_path: Path
) -> dict[str, object]:
    grant, actual_digest = load_grant(path, digest)
    request = OperationRequest.model_validate_json(bounded_document(request_path))
    plan = prepare_plan(context, grant, actual_digest, request, int(time.time()))
    return {
        "status": "LOCAL_OPERATION_PLAN_PREPARED",
        "plan_sha256": plan.plan_sha256,
        "plan": plan.model_dump(mode="json"),
        "dispatch_eligible": False,
        "blocking_reasons": [
            "trusted_runner_required",
            "remote_shared_ledger_required",
            "generic_analysis_adapter_required",
            "operator_attestation_required",
        ],
        "execution_authorized": False,
        "remote_contact": False,
        "admission_created": False,
    }
