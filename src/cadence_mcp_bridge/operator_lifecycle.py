"""Provider seam for existing analysis admission; no native provider is installed.

This coordinator owns no budget ledger, worker, process or independent job engine.
A future fixed trusted provider must perform atomic remote admission/reservation.
The public runtime does not inject one; absent provider denies before local writes.
"""

from __future__ import annotations

import time
from typing import Annotated, Protocol

from pydantic import Field, TypeAdapter

from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.operator_operations import (
    TERMINAL_PHASES,
    DurableOperation,
    OperationPlan,
    OperationProgress,
    OperationRejected,
    OperationRequest,
    OperatorGrant,
    match_grant,
    prepare_plan,
    verify_grant_binding,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext, resource_lock
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel


class ProviderAccounting(VariableModel):
    resource_domain_sha256: Digest
    ledger_ref: LogicalId
    runner_sha256: Digest
    grant_sha256: Digest
    cumulative_attempts: Annotated[int, Field(ge=0)]
    cumulative_reserved_bytes: Annotated[int, Field(ge=0)]
    grant_attempts: Annotated[int, Field(ge=0)]
    grant_reserved_bytes: Annotated[int, Field(ge=0)]
    attempt_ceiling: Annotated[int, Field(ge=0)]
    result_ceiling_bytes: Annotated[int, Field(ge=0)]
    in_flight_reserved_bytes: Annotated[int, Field(ge=0)]
    logical_bytes: Annotated[int, Field(ge=0)]
    allocated_bytes: Annotated[int, Field(ge=0)]
    filesystem_free_bytes: Annotated[int, Field(ge=0)]
    filesystem_total_bytes: Annotated[int, Field(ge=1)]

    def check(self, context: ExecutionContext, grant: OperatorGrant, plan: OperationPlan) -> None:
        if (
            self.resource_domain_sha256,
            self.ledger_ref,
            self.runner_sha256,
            self.grant_sha256,
        ) != (plan.resource_domain_sha256, plan.ledger_ref, plan.runner_sha256, plan.grant_sha256):
            raise OperationRejected("provider_accounting_binding_mismatch")
        limits = context.contracts.environment.limits
        if (self.attempt_ceiling, self.result_ceiling_bytes) != (
            limits.spectre_attempts,
            limits.result_reserved_bytes,
        ) or self.in_flight_reserved_bytes > self.cumulative_reserved_bytes:
            raise OperationRejected("provider_accounting_inconsistent")
        remaining_attempts = min(
            self.attempt_ceiling - self.cumulative_attempts,
            grant.attempt_limit - self.grant_attempts,
        )
        remaining_bytes = min(
            self.result_ceiling_bytes - self.cumulative_reserved_bytes,
            grant.result_reserved_bytes_limit - self.grant_reserved_bytes,
        )
        if (
            remaining_attempts < plan.attempt_cost
            or remaining_bytes < plan.request.result_reservation_bytes
        ):
            raise OperationRejected("authoritative_budget_exhausted")
        floor = max(
            limits.disk_floor_bytes,
            (self.filesystem_total_bytes * limits.disk_floor_percent + 99) // 100,
        )
        if self.filesystem_free_bytes > self.filesystem_total_bytes or (
            self.filesystem_free_bytes
            - self.in_flight_reserved_bytes
            - plan.request.result_reservation_bytes
            < floor
        ):
            raise OperationRejected("authoritative_disk_floor_denied")


class ProviderObservation(VariableModel):
    operation_id: OperationId
    plan_sha256: Digest
    resource_domain_sha256: Digest
    ledger_ref: LogicalId
    progress: OperationProgress

    def check(self, record: DurableOperation) -> None:
        if (self.operation_id, self.plan_sha256, self.resource_domain_sha256, self.ledger_ref) != (
            record.operation_id,
            record.plan.plan_sha256,
            record.plan.resource_domain_sha256,
            record.plan.ledger_ref,
        ) or self.progress.remote_revision is None:
            raise OperationRejected("provider_operation_identity_mismatch")


class OperatorProvider(Protocol):
    """Fixed implementation boundary, never supplied by caller JSON or a MCP tool.

    authorize attests trust/operator consent and reads the existing shared ledger.
    accept MUST atomically deduplicate identity, recheck policy/space/counters,
    reserve once in that ledger, and enforce the remote concurrency-one lock.
    A cached accounting observation alone is never permission to spend capacity.
    lookup cannot dispatch or reserve. cancel_pending atomically records a tombstone
    for an absent/pending identity so another client cannot subsequently accept it;
    it rechecks actual pending state and cannot terminate a process.
    """

    async def authorize(self, plan: OperationPlan, grant: OperatorGrant) -> ProviderAccounting: ...
    async def accept(self, operation_id: str, plan: OperationPlan) -> ProviderObservation: ...
    async def lookup(
        self, operation_id: str, plan: OperationPlan
    ) -> ProviderObservation | None: ...
    async def cancel_pending(
        self, operation_id: str, plan: OperationPlan
    ) -> ProviderObservation: ...


class OperatorLifecycle:
    def __init__(
        self,
        context: ExecutionContext,
        store: AnalysisStore,
        provider: OperatorProvider | None = None,
    ) -> None:
        if store.path != context.binding.analysis_journal.absolute():
            raise OperationRejected("operator_journal_binding_mismatch")
        self.context, self.store, self.provider = context, store, provider

    def _provider(self) -> OperatorProvider:
        if self.provider is None:
            raise OperationRejected("trusted_native_provider_required")
        return self.provider

    def read(self, operation_id: str, expected_plan_sha256: str) -> DurableOperation:
        TypeAdapter(OperationId).validate_python(operation_id)
        record = self.store.operation(operation_id)
        if (
            record.plan.plan_sha256,
            record.plan.resource_domain_sha256,
            record.plan.ledger_ref,
        ) != (
            expected_plan_sha256,
            self.context.resource_domain_sha256,
            self.context.binding.ledger_ref,
        ):
            raise OperationRejected("durable_operation_binding_mismatch")
        return record

    def _observe(self, record: DurableOperation, reply: ProviderObservation) -> DurableOperation:
        reply.check(record)
        return self.store.advance_operation(record.operation_id, record.progress, reply.progress)

    async def _reconcile(self, record: DurableOperation) -> DurableOperation:
        if record.progress.phase in TERMINAL_PHASES:
            return record
        reply = await self._provider().lookup(record.operation_id, record.plan)
        if reply is None:
            # Absence after intent is not proof of no dispatch. Never resend or refund.
            return record
        if record.progress.phase == "ADMITTED":
            # Another client may have admitted remotely. Persist ambiguity before observation.
            record = self.store.advance_operation(
                record.operation_id, record.progress, OperationProgress(phase="UNKNOWN_OUTCOME")
            )
        return self._observe(record, reply)

    async def reconcile(self, operation_id: str, expected_plan_sha256: str) -> DurableOperation:
        record = self.read(operation_id, expected_plan_sha256)
        if record.progress.phase in TERMINAL_PHASES:
            return record
        self._provider()
        with resource_lock(self.context):
            return await self._reconcile(self.read(operation_id, expected_plan_sha256))

    async def submit(
        self,
        operation_id: str,
        grant: OperatorGrant,
        digest: str,
        request: OperationRequest,
        expected_plan_sha256: str,
    ) -> DurableOperation:
        TypeAdapter(OperationId).validate_python(operation_id)
        provider = self._provider()
        with resource_lock(self.context):
            if self.store.path.exists():
                try:
                    existing = self.read(operation_id, expected_plan_sha256)
                except InvalidInputError:
                    existing = None
                if existing is not None:
                    values = tuple(sorted(request.values, key=lambda v: v.logical_id))
                    if existing.plan.request != request.model_copy(update={"values": values}):
                        raise OperationRejected("operation_request_identity_conflict")
                    # Lookup-only retry works after grant expiry; it cannot initiate new work.
                    return await self._reconcile(existing)
            plan = prepare_plan(self.context, grant, digest, request, int(time.time()))
            if plan.plan_sha256 != expected_plan_sha256:
                raise OperationRejected("stale_operation_plan")
            # A matching remote identity is existing work, even when fresh capacity
            # is exhausted. Lookup never reserves and must precede new-spend checks.
            observed = await provider.lookup(operation_id, plan)
            if observed is not None:
                candidate = DurableOperation(
                    operation_id=operation_id,
                    plan=plan,
                    progress=OperationProgress(phase="UNKNOWN_OUTCOME"),
                    event_count=2,
                )
                observed.check(candidate)
                self.store.admit_operation(operation_id, plan, dispatch_intent=True)
                return self._observe(self.read(operation_id, expected_plan_sha256), observed)
            accounting = await provider.authorize(plan, grant)
            accounting.check(self.context, grant, plan)
            # Recheck expiry immediately before durable admission; remote accept also rechecks it.
            match_grant(self.context, grant, int(time.time()))
            first = self.store.admit_operation(operation_id, plan, dispatch_intent=True)
            record = self.read(operation_id, expected_plan_sha256)
            if not first:
                return await self._reconcile(record)
            # Admission and intent commit atomically before send. Ambiguity stays lookup-only.
            return self._observe(record, await provider.accept(operation_id, plan))

    async def cancel_pending(
        self, operation_id: str, expected_plan_sha256: str, grant: OperatorGrant, digest: str
    ) -> DurableOperation:
        initial = self.read(operation_id, expected_plan_sha256)
        if initial.progress.phase in TERMINAL_PHASES:
            return initial
        provider = self._provider()
        with resource_lock(self.context):
            record = self.read(operation_id, expected_plan_sha256)
            if record.progress.phase in TERMINAL_PHASES:
                return record
            verify_grant_binding(grant, digest)
            match_grant(self.context, grant, int(time.time()))
            if "cancel_pending" not in grant.actions or digest != record.plan.grant_sha256:
                raise OperationRejected("pending_cancellation_authority_denied")
            # Consent/trust attestation still required; capacity need not remain to cancel.
            gate = await provider.authorize(record.plan, grant)
            if (
                gate.resource_domain_sha256,
                gate.ledger_ref,
                gate.grant_sha256,
                gate.runner_sha256,
            ) != (
                record.plan.resource_domain_sha256,
                record.plan.ledger_ref,
                digest,
                record.plan.runner_sha256,
            ):
                raise OperationRejected("provider_accounting_binding_mismatch")
            match_grant(self.context, grant, int(time.time()))
            record = await self._reconcile(record)
            if record.progress.phase in TERMINAL_PHASES:
                return record
            absent_intent = (
                record.progress.phase == "UNKNOWN_OUTCOME"
                and record.progress.remote_revision is None
            )
            if record.progress.phase not in ("ADMITTED", "RESERVED") and not absent_intent:
                raise OperationRejected("pending_state_unconfirmed_or_active")
            if record.progress.phase == "ADMITTED":
                # Cancellation also crosses a remote boundary. Persist ambiguity first.
                record = self.store.advance_operation(
                    operation_id, record.progress, OperationProgress(phase="UNKNOWN_OUTCOME")
                )
            # An absent lookup is insufficient to resend, but an atomic cancellation may
            # tombstone it. The provider must reject active/unknown remote state even if
            # lookup missed it; this never dispatches or refunds a reservation.
            return self._observe(record, await provider.cancel_pending(operation_id, record.plan))
