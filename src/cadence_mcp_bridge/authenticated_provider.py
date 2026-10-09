"""Fixed native provider transport for the existing OperatorLifecycle.

No caller command, script, path, grant writer or transport retry is exposed.
Installed runtime qualification/activation is a separate operator action.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.environments import EnvironmentModel, load_environment
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration, project_frame
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_lifecycle import ProviderAccounting, ProviderObservation
from cadence_mcp_bridge.operator_operations import OperationPlan, OperationRejected, OperatorGrant
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import Digest, canonical_digest


class NativeProviderBinding(EnvironmentModel):
    schema_version: Literal[1]
    identity_manifest_sha256: Digest
    runtime_manifest_sha256: Digest


class ProviderEnvelope(EnvironmentModel):
    schema_version: Literal[1]
    runtime_manifest_sha256: Digest
    identity_manifest_sha256: Digest
    action: Literal["authorize", "accept", "lookup", "cancel_pending", "result"]
    payload: dict[str, Any] | None


class ExtractionReceipt(EnvironmentModel):
    schema_version: Literal[1]
    operation_id: str
    plan_sha256: Digest
    native_input_sha256: Digest
    reader_registration_sha256: Digest
    reader_script_sha256: Digest
    frame_sha256: Digest
    psf_tree_fingerprint: Digest
    pre_receipt_tree_fingerprint: Digest
    logical_bytes: Annotated[int, Field(ge=0)]
    allocated_bytes: Annotated[int, Field(ge=0)]
    originals_preserved: Literal[True]


class TerminalEvent(EnvironmentModel):
    schema_version: Literal[1]
    operation_id: str
    plan_sha256: Digest
    revision: Annotated[int, Field(ge=1, le=64)]
    previous_sha256: Digest
    phase: Literal["SUCCEEDED"]
    evidence_sha256: Digest


class CompletedJobSize(EnvironmentModel):
    logical_bytes: Annotated[int, Field(ge=0)]
    allocated_bytes: Annotated[int, Field(ge=0)]
    tree_fingerprint: Digest


class NativeResultPayload(EnvironmentModel):
    observation: ProviderObservation
    terminal_event: TerminalEvent
    receipt: ExtractionReceipt
    ade: AdeExecutionRegistration
    reader: GenericReaderRegistration
    frame: Annotated[str, Field(max_length=65536)]
    completed_size: CompletedJobSize


class AuthenticatedOperatorProvider:
    """Production wire implementation, never constructed from MCP arguments.

    Remote errors and timeouts are bounded; no call is automatically resent.
    OperatorLifecycle commits intent first and reconciles only through lookup.
    The remote fixed gate must independently authenticate consent and reserve.
    """

    def __init__(self, context: ExecutionContext, binding: NativeProviderBinding) -> None:
        if binding.runtime_manifest_sha256 != context.binding.runner_sha256:
            raise OperationRejected("native_provider_runtime_binding_mismatch")
        environment, raw = load_environment(context.binding.environment_profile)
        if hashlib.sha256(raw).hexdigest() != context.binding.environment_sha256:
            raise OperationRejected("native_provider_environment_changed")
        self.context = context
        self.binding = binding
        self.environment = environment
        self.runner = (
            environment.paths.managed_root
            + "/runtime/"
            + binding.runtime_manifest_sha256
            + "/provider.py"
        )

    def _plan(self, plan: OperationPlan) -> None:
        if (
            plan.runner_sha256,
            plan.resource_domain_sha256,
            plan.ledger_ref,
            plan.environment_sha256,
            plan.design_sha256,
            plan.pdk_sha256,
        ) != (
            self.context.binding.runner_sha256,
            self.context.resource_domain_sha256,
            self.context.binding.ledger_ref,
            self.context.binding.environment_sha256,
            self.context.binding.design_sha256,
            self.context.binding.pdk_sha256,
        ):
            raise OperationRejected("native_provider_plan_binding_mismatch")

    async def _call(
        self,
        action: str,
        plan: OperationPlan,
        operation_id: str | None = None,
    ) -> dict[str, Any] | None:
        if action not in {"authorize", "accept", "lookup", "cancel_pending", "result"}:
            raise OperationRejected("native_provider_fixed_action_required")
        self._plan(plan)
        request = {
            "schema_version": 1,
            "action": action,
            "operation_id": operation_id,
            "plan": plan.model_dump(mode="json"),
            "plan_sha256": plan.plan_sha256,
            "identity_manifest_sha256": self.binding.identity_manifest_sha256,
        }
        try:
            code, stdout, stderr = await asyncio.to_thread(
                run_fixed,
                _ssh(self.environment)
                + [self.runner, self.binding.runtime_manifest_sha256, action],
                _canonical(request),
                OpenSshBackend._ssh_environment(),
                timeout=60,
                limit=262144,
            )
        except (OSError, ValueError):
            raise OperationRejected("native_provider_transport_unknown") from None
        if code or stderr:
            raise OperationRejected("native_provider_rejected")
        try:
            _closed_document(stdout)
            result = ProviderEnvelope.model_validate_json(stdout)
        except ValueError:
            raise OperationRejected("native_provider_response_invalid") from None
        if (
            result.runtime_manifest_sha256 != self.binding.runtime_manifest_sha256
            or result.identity_manifest_sha256 != self.binding.identity_manifest_sha256
            or result.action != action
        ):
            raise OperationRejected("native_provider_response_binding_mismatch")
        return result.payload

    async def authorize(self, plan: OperationPlan, grant: OperatorGrant) -> ProviderAccounting:
        # The canonical grant is confirmed separately by the OS operator. A
        # caller-provided document is never sent as native confirmation evidence.
        if any(
            getattr(grant, key) != getattr(plan, key)
            for key in (
                "resource_domain_sha256",
                "runner_sha256",
                "ledger_ref",
                "environment_sha256",
                "design_sha256",
                "pdk_sha256",
            )
        ):
            raise OperationRejected("native_provider_grant_binding_mismatch")
        reply = await self._call("authorize", plan)
        try:
            result = ProviderAccounting.model_validate_json(_canonical(reply))
        except ValueError:
            raise OperationRejected("native_provider_accounting_invalid") from None
        if (
            result.resource_domain_sha256,
            result.ledger_ref,
            result.runner_sha256,
            result.grant_sha256,
        ) != (
            plan.resource_domain_sha256,
            plan.ledger_ref,
            plan.runner_sha256,
            plan.grant_sha256,
        ):
            raise OperationRejected("native_provider_accounting_binding_mismatch")
        return result

    async def _observation(
        self,
        action: str,
        operation_id: str,
        plan: OperationPlan,
    ) -> ProviderObservation | None:
        from pydantic import TypeAdapter

        from cadence_mcp_bridge.native_diagnostics import OperationId

        TypeAdapter(OperationId).validate_python(operation_id)
        payload = await self._call(action, plan, operation_id)
        if payload is None:
            if action == "lookup":
                return None
            raise OperationRejected("native_provider_missing_acceptance")
        try:
            result = ProviderObservation.model_validate_json(_canonical(payload))
        except ValueError:
            raise OperationRejected("native_provider_observation_invalid") from None
        if (
            result.operation_id,
            result.plan_sha256,
            result.resource_domain_sha256,
            result.ledger_ref,
        ) != (operation_id, plan.plan_sha256, plan.resource_domain_sha256, plan.ledger_ref) or (
            result.progress.remote_revision is None
        ):
            raise OperationRejected("native_provider_operation_identity_mismatch")
        return result

    async def accept(self, operation_id: str, plan: OperationPlan) -> ProviderObservation:
        result = await self._observation("accept", operation_id, plan)
        assert result is not None
        return result

    async def lookup(self, operation_id: str, plan: OperationPlan) -> ProviderObservation | None:
        return await self._observation("lookup", operation_id, plan)

    async def cancel_pending(self, operation_id: str, plan: OperationPlan) -> ProviderObservation:
        result = await self._observation("cancel_pending", operation_id, plan)
        assert result is not None
        return result

    async def result(
        self, operation_id: str, plan: OperationPlan
    ) -> tuple[ProviderObservation, dict[str, object]]:
        from pydantic import TypeAdapter

        from cadence_mcp_bridge.native_diagnostics import OperationId

        TypeAdapter(OperationId).validate_python(operation_id)
        payload = await self._call("result", plan, operation_id)
        try:
            data = NativeResultPayload.model_validate_json(_canonical(payload))
            frame = data.frame.encode("ascii")
        except (ValueError, UnicodeError):
            raise OperationRejected("native_provider_result_invalid") from None
        observation, receipt, event = data.observation, data.receipt, data.terminal_event
        if (
            observation.operation_id,
            observation.plan_sha256,
            observation.resource_domain_sha256,
            observation.ledger_ref,
            observation.progress.phase,
            observation.progress.remote_revision,
            receipt.operation_id,
            receipt.plan_sha256,
            event.operation_id,
            event.plan_sha256,
        ) != (
            operation_id,
            plan.plan_sha256,
            plan.resource_domain_sha256,
            plan.ledger_ref,
            "SUCCEEDED",
            event.revision,
            operation_id,
            plan.plan_sha256,
            operation_id,
            plan.plan_sha256,
        ) or (
            canonical_digest(event) != observation.progress.provider_receipt_sha256
            or canonical_digest(receipt) != event.evidence_sha256
            or canonical_digest(data.reader) != receipt.reader_registration_sha256
            or hashlib.sha256(frame).hexdigest() != receipt.frame_sha256
            or max(receipt.logical_bytes, receipt.allocated_bytes)
            > plan.request.result_reservation_bytes
        ):
            raise OperationRejected("native_provider_result_binding_mismatch")
        if (
            max(data.completed_size.logical_bytes, data.completed_size.allocated_bytes)
            > plan.request.result_reservation_bytes
            or data.completed_size.logical_bytes < receipt.logical_bytes
            or data.completed_size.allocated_bytes < receipt.allocated_bytes
        ):
            raise OperationRejected("native_provider_completed_size_invalid")
        projected = project_frame(
            self.context,
            plan,
            data.ade,
            data.reader,
            operation_id,
            receipt.native_input_sha256,
            frame,
        )
        if projected["reader_script_sha256"] != receipt.reader_script_sha256:
            raise OperationRejected("native_provider_result_reader_drift")
        projected.update(
            status="NATIVE_RESULT_RETRIEVED",
            native_provenance="FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
            remote_contact=True,
            extraction_receipt_sha256=canonical_digest(receipt),
            logical_bytes=receipt.logical_bytes,
            allocated_bytes=receipt.allocated_bytes,
            originals_preserved=receipt.originals_preserved,
        )
        projected.update(
            logical_bytes=data.completed_size.logical_bytes,
            allocated_bytes=data.completed_size.allocated_bytes,
            completed_tree_fingerprint=data.completed_size.tree_fingerprint,
            size_observation="COMPLETED_JOB_READONLY",
        )
        return observation, projected


async def operator_action(
    context: ExecutionContext,
    binding_path: Path,
    expected_binding_sha256: str,
    action: str,
    operation_id: str,
    expected_plan_sha256: str,
    grant_path: Path | None = None,
    expected_grant_sha256: str | None = None,
    request_path: Path | None = None,
) -> dict[str, object]:
    """Explicit operator CLI connection; no setup, authority writer or resend."""
    from cadence_mcp_bridge.analysis_store import AnalysisStore
    from cadence_mcp_bridge.operator_lifecycle import OperatorLifecycle
    from cadence_mcp_bridge.operator_operations import (
        OperationRequest,
        bounded_document,
        load_grant,
    )

    if action not in ("submit", "reconcile", "cancel-pending", "result"):
        raise OperationRejected("native_operator_fixed_action")
    raw = bounded_document(binding_path)
    if hashlib.sha256(raw).hexdigest() != expected_binding_sha256:
        raise OperationRejected("native_operator_binding_changed")
    binding = NativeProviderBinding.model_validate_json(raw)
    provider = AuthenticatedOperatorProvider(context, binding)
    lifecycle = OperatorLifecycle(
        context,
        AnalysisStore(context.binding.analysis_journal),
        provider,
    )
    if action == "result":
        record = await lifecycle.reconcile(operation_id, expected_plan_sha256)
        if record.progress.phase != "SUCCEEDED":
            raise OperationRejected("native_operator_result_not_succeeded")
        observed, projected = await provider.result(operation_id, record.plan)
        observed.check(record)
        if observed.progress != record.progress:
            raise OperationRejected("native_operator_result_terminal_mismatch")
        return projected
    if action == "reconcile":
        record = await lifecycle.reconcile(operation_id, expected_plan_sha256)
    else:
        if grant_path is None or expected_grant_sha256 is None:
            raise OperationRejected("native_operator_grant_required")
        grant, grant_sha = load_grant(grant_path, expected_grant_sha256)
        if action == "submit":
            if request_path is None:
                raise OperationRejected("native_operator_explicit_request_required")
            request = OperationRequest.model_validate_json(bounded_document(request_path))
            record = await lifecycle.submit(
                operation_id,
                grant,
                grant_sha,
                request,
                expected_plan_sha256,
            )
        else:
            record = await lifecycle.cancel_pending(
                operation_id,
                expected_plan_sha256,
                grant,
                grant_sha,
            )
    return {
        "status": "OPERATOR_DURABLE_OPERATION_OBSERVED",
        "operation_id": record.operation_id,
        "plan_sha256": record.plan.plan_sha256,
        "progress": record.progress.model_dump(mode="json"),
        "event_count": record.event_count,
        "observation_scope": "DURABLE_PROVIDER_RECEIPT_OR_RETAINED_TERMINAL",
        "simulation_retry": False,
        "budget_reset_or_refund": False,
    }
