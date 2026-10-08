"""Fixed native provider transport for the existing OperatorLifecycle.

No caller command, script, path, grant writer or transport retry is exposed.
Installed runtime qualification/activation is a separate operator action.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Literal

from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.environments import EnvironmentModel, load_environment
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_lifecycle import ProviderAccounting, ProviderObservation
from cadence_mcp_bridge.operator_operations import OperationPlan, OperationRejected, OperatorGrant
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import Digest


class NativeProviderBinding(EnvironmentModel):
    schema_version: Literal[1]
    identity_manifest_sha256: Digest
    runtime_manifest_sha256: Digest


class ProviderEnvelope(EnvironmentModel):
    schema_version: Literal[1]
    runtime_manifest_sha256: Digest
    identity_manifest_sha256: Digest
    action: Literal["authorize", "accept", "lookup", "cancel_pending"]
    payload: dict[str, Any] | None


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
        if action not in {"authorize", "accept", "lookup", "cancel_pending"}:
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
