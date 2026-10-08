"""Explicit operator-configured native service; no setup or grant writing."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Literal

from pydantic import field_validator

from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.authenticated_provider import (
    AuthenticatedOperatorProvider,
    NativeProviderBinding,
)
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.operator_lifecycle import OperatorLifecycle
from cadence_mcp_bridge.operator_operations import (
    OperationPlan,
    OperationProgress,
    OperationRejected,
    OperationRequest,
    bounded_document,
    load_grant,
    prepare_plan,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel


class NativeOperationRequest(OperationRequest):
    @field_validator("values", mode="before")
    @classmethod
    def json_array(cls, values: Any) -> Any:
        # MCP SDK validates Python dictionaries. Convert only the declared JSON array;
        # numbers, units, extra fields and explicit-value inventory remain strict.
        return tuple(values) if type(values) is list else values


class NativeOperationQuery(VariableModel):
    operation_id: OperationId
    expected_plan_sha256: Digest


class NativeOperationSubmission(NativeOperationQuery):
    request: NativeOperationRequest


class NativeOperationPlan(ContractModel):
    plan: OperationPlan
    plan_sha256: Digest
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False

    @field_validator("plan", mode="before")
    @classmethod
    def json_plan(cls, value: Any) -> Any:
        if type(value) is dict:
            from cadence_mcp_bridge.domain_provisioning import _canonical

            return OperationPlan.model_validate_json(_canonical(value))
        return value


class NativeOperationStatus(ContractModel):
    operation_id: OperationId
    plan_sha256: Digest
    progress: OperationProgress
    event_count: int
    simulation_retry: Literal[False] = False
    budget_reset_or_refund: Literal[False] = False


class NativeOperationResult(ContractModel):
    # Values come solely from the registered bounded projection, never caller content.
    operation_id: OperationId
    plan_sha256: Digest
    result: dict[str, object]


class NativeOperationService:
    def __init__(self, context: ExecutionContext) -> None:
        binding = context.binding
        if (
            binding.native_provider_binding is None
            or binding.native_provider_sha256 is None
            or binding.operator_grant is None
            or binding.operator_grant_sha256 is None
        ):
            raise ConfigurationError("Explicit native provider and operator grant required")
        try:
            raw = bounded_document(binding.native_provider_binding)
            if hashlib.sha256(raw).hexdigest() != binding.native_provider_sha256:
                raise OperationRejected("native_operator_binding_changed")
            provider = AuthenticatedOperatorProvider(
                context, NativeProviderBinding.model_validate_json(raw)
            )
            grant, sha = load_grant(binding.operator_grant, binding.operator_grant_sha256)
        except (OSError, ValueError):
            raise ConfigurationError("Native operator binding rejected") from None
        self.context, self.provider, self.grant, self.grant_sha256 = context, provider, grant, sha
        self.lifecycle = OperatorLifecycle(
            context, AnalysisStore(binding.analysis_journal), provider
        )

    def current(self) -> None:
        # Snapshot never silently adopts file replacement; restart required for new policy.
        binding = self.context.binding
        assert binding.native_provider_binding is not None and binding.operator_grant is not None
        try:
            if (
                hashlib.sha256(bounded_document(binding.native_provider_binding)).hexdigest()
                != binding.native_provider_sha256
                or hashlib.sha256(bounded_document(binding.operator_grant)).hexdigest()
                != binding.operator_grant_sha256
            ):
                raise ValueError("changed")
        except (OSError, ValueError):
            raise ConfigurationError(
                "Native operator binding changed; review and restart"
            ) from None

    async def plan(self, request: OperationRequest) -> NativeOperationPlan:
        self.current()
        request = OperationRequest.model_validate_json(request.model_dump_json())
        try:
            plan = prepare_plan(
                self.context, self.grant, self.grant_sha256, request, int(time.time())
            )
        except OperationRejected as error:
            raise InvalidInputError(
                "Operation plan rejected", details={"reason": error.reason}
            ) from None
        return NativeOperationPlan(plan=plan, plan_sha256=plan.plan_sha256)

    async def observe(
        self,
        request: NativeOperationQuery,
        submission: OperationRequest | None = None,
        cancel: bool = False,
    ) -> NativeOperationStatus:
        self.current()
        try:
            if submission is not None:
                submission = OperationRequest.model_validate_json(submission.model_dump_json())
                record = await self.lifecycle.submit(
                    request.operation_id,
                    self.grant,
                    self.grant_sha256,
                    submission,
                    request.expected_plan_sha256,
                )
            elif cancel:
                record = await self.lifecycle.cancel_pending(
                    request.operation_id,
                    request.expected_plan_sha256,
                    self.grant,
                    self.grant_sha256,
                )
            else:
                record = await self.lifecycle.reconcile(
                    request.operation_id, request.expected_plan_sha256
                )
        except OperationRejected as error:
            raise InvalidInputError(
                "Native operation rejected", details={"reason": error.reason}
            ) from None
        return NativeOperationStatus(
            operation_id=record.operation_id,
            plan_sha256=record.plan.plan_sha256,
            progress=record.progress,
            event_count=record.event_count,
        )

    async def result(self, request: NativeOperationQuery) -> NativeOperationResult:
        self.current()
        try:
            record = await self.lifecycle.reconcile(
                request.operation_id, request.expected_plan_sha256
            )
            if record.progress.phase != "SUCCEEDED":
                raise OperationRejected("native_operator_result_not_succeeded")
            observed, result = await self.provider.result(request.operation_id, record.plan)
            observed.check(record)
            if observed.progress != record.progress:
                raise OperationRejected("native_operator_result_terminal_mismatch")
        except OperationRejected as error:
            raise InvalidInputError(
                "Native result rejected", details={"reason": error.reason}
            ) from None
        return NativeOperationResult(
            operation_id=record.operation_id, plan_sha256=record.plan.plan_sha256, result=result
        )
