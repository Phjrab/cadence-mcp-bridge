"""Operator-only ADE L input compiler and bounded Spectre input verification.

These artifacts do not authorize copying, dispatch, reservation or execution.
Native copy/attestation and provider integration are still required.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from cadence_mcp_bridge import _native_rendering
from cadence_mcp_bridge.designs import BindingName
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import (
    OperationPlan,
    OperationRejected,
    OperationRequest,
    bounded_document,
    load_grant,
    prepare_plan,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext, load_runtime
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)

LIMIT = 262144


class AcInputs(VariableModel):
    analysis: Literal["ac"]
    start_hz: NumberText
    stop_hz: NumberText
    points_per_decade: Annotated[int, Field(ge=1, le=100)]

    @field_validator("start_hz", "stop_hz", mode="before")
    @classmethod
    def scalar(cls, value: str) -> str:
        return number_text(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if (
            not Decimal("0.000001")
            <= Decimal(self.start_hz)
            < Decimal(self.stop_hz)
            <= Decimal("1e12")
        ):
            raise ValueError("bounded AC frequency interval required")
        # Bound the requested logarithmic grid before any netlist exists.
        decades = (Decimal(self.stop_hz) / Decimal(self.start_hz)).log10()
        if decades * self.points_per_decade > 4094:
            raise ValueError("AC sample bound exceeded")
        return self


class TranInputs(VariableModel):
    analysis: Literal["tran"]
    stop_s: NumberText
    maxstep_s: NumberText
    method: Literal["trap", "gear2only"]

    @field_validator("stop_s", "maxstep_s", mode="before")
    @classmethod
    def scalar(cls, value: str) -> str:
        return number_text(value)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not Decimal("1e-12") <= Decimal(self.maxstep_s) <= Decimal(self.stop_s) <= Decimal("10"):
            raise ValueError("bounded transient time interval required")
        # This is an input-grid bound, not a guarantee on adaptive solver output.
        if Decimal(self.stop_s) / Decimal(self.maxstep_s) > 4094:
            raise ValueError("transient input grid bound exceeded")
        return self


class DcInputs(VariableModel):
    analysis: Literal["dc"]
    mode: Literal["saved_operating_point"]
    # DC fields stay opaque in the protected saved state. Verify the complete
    # generated DC statement instead of guessing an unqualified ADE field API.
    statement_sha256: Digest


AnalysisInputs = Annotated[AcInputs | TranInputs | DcInputs, Field(discriminator="analysis")]


class ModelInclude(VariableModel):
    path: Annotated[str, Field(pattern=r"^/[A-Za-z0-9._/-]{1,511}$", max_length=512)]
    section: BindingName
    file_sha256: Digest

    @model_validator(mode="after")
    def canonical(self) -> Self:
        if str(PurePosixPath(self.path)) != self.path or ".." in PurePosixPath(self.path).parts:
            raise ValueError("canonical model reference required")
        return self


class AdeExecutionRegistration(VariableModel):
    schema_version: Literal[1]
    design_id: LogicalId
    analysis_id: LogicalId
    design_profile_sha256: Digest
    variable_set_sha256: Digest | None
    source_tree_sha256: Digest
    ade_state_tree_sha256: Digest
    # Normalized static statements cover topology, stimuli, load and all opaque
    # expressions. Hash is operator-reviewed, never inferred from another job.
    static_statements_sha256: Digest
    model_includes: Annotated[tuple[ModelInclude, ...], Field(max_length=16)]
    inputs: AnalysisInputs

    @field_validator("schema_version", mode="before")
    @classmethod
    def version(cls, value: int) -> int:
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({m.path for m in self.model_includes}) != len(self.model_includes):
            raise ValueError("duplicate model reference")
        return self


# Fixed API syntax. Only validated ASCII identifiers, decimal strings and
# canonical job-owned paths are substituted; no caller expressions or scripts.
_TEMPLATE = _native_rendering.ADE_TEMPLATE


def template_sha256() -> str:
    return hashlib.sha256(_TEMPLATE.encode("ascii")).hexdigest()


def _quoted(value: str) -> str:
    # All call sites pass identifiers, canonical numbers or trusted profile paths.
    if re.fullmatch(r"[A-Za-z0-9_#./-]+", value) is None:
        raise OperationRejected("ade_literal_invalid")
    return '"' + value + '"'


def bind_inputs(
    context: ExecutionContext, plan: OperationPlan, registration: AdeExecutionRegistration
) -> None:
    if (
        plan.resource_domain_sha256,
        plan.ledger_ref,
        plan.runner_sha256,
        plan.environment_sha256,
        plan.design_sha256,
        plan.pdk_sha256,
    ) != (
        context.resource_domain_sha256,
        context.binding.ledger_ref,
        context.binding.runner_sha256,
        context.binding.environment_sha256,
        context.binding.design_sha256,
        context.binding.pdk_sha256,
    ):
        raise OperationRejected("ade_context_binding_mismatch")
    registry = context.contracts.designs
    profile = registry.profile(plan.request.design_id)
    variables = registry.variable_set(profile.design_id)
    contract = next(
        (
            c
            for c in registry.analyses_for(profile.design_id)
            if c.analysis_id == plan.request.analysis_id
        ),
        None,
    )
    if (
        (
            registration.design_id,
            registration.analysis_id,
            registration.design_profile_sha256,
            registration.variable_set_sha256,
            registration.inputs.analysis,
        )
        != (
            profile.design_id,
            plan.request.analysis_id,
            canonical_digest(profile),
            canonical_digest(variables) if variables else None,
            plan.analysis,
        )
        or contract is None
        or contract.analysis != plan.analysis
    ):
        raise OperationRejected("ade_registration_binding_mismatch")
    if profile.binding.ade.kind != "ade_l" or profile.work_copy_policy != "owned_copy_only":
        raise OperationRejected("ade_subtype_or_copy_policy_unsupported")
    if profile.environment_id != context.contracts.environment.environment_id:
        raise OperationRejected("ade_environment_mismatch")
    if plan.analysis not in context.contracts.environment.requested_capabilities:
        raise OperationRejected("ade_environment_capability_missing")
    # Recheck scalar constraints even when a plan arrived from a persisted file.
    supplied = {v.logical_id: v for v in plan.request.values}
    if set(supplied) != set(profile.allowed_variables) or len(supplied) != len(plan.request.values):
        raise OperationRejected("all_explicit_registered_values_required")
    mapped = {v.logical_id: v for v in variables.variables} if variables else {}
    for name, value in supplied.items():
        variable = mapped.get(name)
        if (
            variable is None
            or variable.unit != value.unit
            or variable.mutation_policy == "read_only"
            or variable.check_number(value.value)
        ):
            raise OperationRejected("registered_numeric_contract_denied")
    roots = context.contracts.environment.paths.protected_roots
    for model in registration.model_includes:
        if not any(PurePosixPath(model.path).is_relative_to(root) for root in roots):
            raise OperationRejected("model_reference_outside_protected_roots")


def render_netlist(
    context: ExecutionContext,
    plan: OperationPlan,
    registration: AdeExecutionRegistration,
    operation_id: str,
) -> bytes:
    TypeAdapter(OperationId).validate_python(operation_id)
    bind_inputs(context, plan, registration)
    profile = context.contracts.designs.profile(plan.request.design_id)
    # Provider must exclusively create and attest this owned library/cell/state.
    library = "MCP_GREL_Work"
    if profile.binding.library == library:
        raise OperationRejected("owned_library_source_collision")
    variables = context.contracts.designs.variable_set(profile.design_id)
    bindings = {v.logical_id: v.cadence_binding for v in variables.variables} if variables else {}
    return _native_rendering.netlist(  # type: ignore[no-any-return,no-untyped-call]
        context.contracts.environment.paths.job_root,
        profile.binding.view,
        profile.binding.ade.state,
        tuple(
            (bindings[v.logical_id], v.value)
            for v in sorted(plan.request.values, key=lambda v: v.logical_id)
        ),
        registration.inputs.model_dump(mode="json"),
        plan.plan_sha256,
        operation_id,
    )


def _read_input(path: Path) -> bytes:
    source = _local_path(path)
    metadata = source.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise OperationRejected("ade_input_file_invalid")
    with source.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise OperationRejected("ade_input_file_invalid")
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise OperationRejected("ade_input_size_exceeded")
    return data


def _statements(data: bytes) -> list[str]:
    try:
        return _native_rendering.statements(data)  # type: ignore[no-any-return,no-untyped-call]
    except ValueError as error:
        raise OperationRejected(str(error)) from None


def static_fingerprint(statements: list[str]) -> str:
    return _native_rendering.static_fingerprint(statements)  # type: ignore[no-any-return,no-untyped-call]


def verify_effective_input(
    context: ExecutionContext,
    plan: OperationPlan,
    registration: AdeExecutionRegistration,
    operation_id: str,
    data: bytes,
) -> dict[str, object]:
    TypeAdapter(OperationId).validate_python(operation_id)
    bind_inputs(context, plan, registration)
    variables = context.contracts.designs.variable_set(plan.request.design_id)
    bindings = {v.logical_id: v.cadence_binding for v in variables.variables} if variables else {}
    try:
        checked = _native_rendering.effective_input(  # type: ignore[no-untyped-call]
            data,
            {bindings[v.logical_id]: v.value for v in plan.request.values},
            [(m.path, m.section) for m in registration.model_includes],
            registration.inputs.model_dump(mode="json"),
            registration.static_statements_sha256,
        )
    except ValueError as error:
        raise OperationRejected(str(error)) from None
    return {
        "status": "LOCAL_EFFECTIVE_INPUT_MATCHED",
        "operation_id": operation_id,
        "plan_sha256": plan.plan_sha256,
        "registration_sha256": canonical_digest(registration),
        "template_sha256": template_sha256(),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "source_tree_sha256": registration.source_tree_sha256,
        "ade_state_tree_sha256": registration.ade_state_tree_sha256,
        "analysis": plan.analysis,
        "parameter_count": checked["parameter_count"],
        "model_count": checked["model_count"],
        "native_source_copy_attested": False,
        "native_model_bytes_attested": False,
        "execution_authorized": False,
        "remote_contact": False,
    }


def operator_inputs(
    settings: Path,
    context_id: str,
    grant_path: Path,
    grant_sha256: str,
    request_path: Path,
    registration_path: Path,
    registration_sha256: str,
    operation_id: str,
    expected_plan_sha256: str,
    output: Path | None = None,
    native_input: Path | None = None,
) -> dict[str, object]:
    context = next((c for c in load_runtime(settings) if c.binding.context_id == context_id), None)
    if context is None:
        raise OperationRejected("unknown_context_id")
    grant, digest = load_grant(grant_path, grant_sha256)
    request = OperationRequest.model_validate_json(bounded_document(request_path))
    plan = prepare_plan(context, grant, digest, request, int(time.time()))
    if plan.plan_sha256 != expected_plan_sha256:
        raise OperationRejected("stale_operation_plan")
    raw = bounded_document(registration_path)
    if hashlib.sha256(raw).hexdigest() != registration_sha256:
        raise OperationRejected("stale_ade_registration")
    registration = AdeExecutionRegistration.model_validate_json(raw)
    script = render_netlist(context, plan, registration, operation_id)
    if native_input is not None:
        return verify_effective_input(
            context, plan, registration, operation_id, _read_input(native_input)
        )
    if output is None:
        raise OperationRejected("ade_output_required")
    # Exclusive private artifact; no overwrite, journal, lock or remote contact.
    target = _local_path(output)
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "operation_id": operation_id,
        "plan_sha256": plan.plan_sha256,
        "registration_sha256": canonical_digest(registration),
        "template_sha256": template_sha256(),
        "script_sha256": hashlib.sha256(script).hexdigest(),
        "source_tree_sha256": registration.source_tree_sha256,
        "ade_state_tree_sha256": registration.ade_state_tree_sha256,
        "status": "LOCAL_ADE_INPUTS_PREPARED_NATIVE_UNQUALIFIED",
        "execution_authorized": False,
        "remote_contact": False,
        "provider_required": True,
        "native_source_copy_attested": False,
    }
    # Bind settings/source/model references as well as the legacy operation plan.
    # A production provider must attest this additional immutable identity; the
    # legacy plan alone is insufficient authority for a generic input artifact.
    manifest["execution_input_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    for name, data in (
        ("netlist.ocn", script),
        ("registration.json", raw),
        ("manifest.json", json.dumps(manifest, sort_keys=True).encode("ascii")),
    ):
        descriptor = os.open(target / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return manifest
