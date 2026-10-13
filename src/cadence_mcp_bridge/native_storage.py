"""Path-free storage over the selected, authenticated native runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

from cadence_mcp_bridge.authenticated_provider import AuthenticatedOperatorProvider
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.environments import EnvironmentModel
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.storage import CleanupOutcome, CleanupRequest, StorageSnapshot
from cadence_mcp_bridge.variable_contracts import Digest


class StorageEnvelope(EnvironmentModel):
    schema_version: Literal[1]
    runtime_manifest_sha256: Digest
    identity_manifest_sha256: Digest
    action: Literal["storage_inventory", "storage_cleanup"]
    payload: dict[str, Any]


class NativeStorageBackend:
    """Internal backend: neither roots nor installation commands are model inputs."""

    def __init__(
        self, provider: AuthenticatedOperatorProvider, current: Callable[[], None],
    ) -> None:
        self.provider = provider
        self.current = current

    async def _call(
        self, action: Literal["storage_inventory", "storage_cleanup"], payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.current()
        binding = self.provider.binding
        request = dict(
            schema_version=1, action=action,
            identity_manifest_sha256=binding.identity_manifest_sha256, payload=payload,
        )
        if len(_canonical(payload)) > 8192:
            raise InvalidInputError("Native storage request bound exceeded")
        try:
            code, stdout, stderr = await asyncio.to_thread(
                run_fixed,
                _ssh(self.provider.environment)
                + [self.provider.runner, binding.runtime_manifest_sha256, action],
                _canonical(request), OpenSshBackend._ssh_environment(),
                timeout=60, limit=262144,
            )
        except (OSError, ValueError):
            raise InvalidInputError("Native storage transport outcome unavailable") from None
        if code or stderr:
            raise InvalidInputError("Native storage request rejected")
        try:
            _closed_document(stdout)
            envelope = StorageEnvelope.model_validate_json(stdout)
            if (
                envelope.runtime_manifest_sha256 != binding.runtime_manifest_sha256
                or envelope.identity_manifest_sha256 != binding.identity_manifest_sha256
                or envelope.action != action
                or len(_canonical(envelope.payload)) > 65536
            ):
                raise ValueError("binding")
        except ValueError:
            raise InvalidInputError("Native storage response binding rejected") from None
        return envelope.payload

    async def storage_snapshot(self) -> StorageSnapshot:
        raw = await self._call("storage_inventory", {})
        try:
            return StorageSnapshot.model_validate_json(_canonical(raw))
        except ValueError:
            raise InvalidInputError("Native storage snapshot rejected") from None

    async def storage_cleanup(self, request: CleanupRequest) -> CleanupOutcome:
        raw = await self._call("storage_cleanup", request.model_dump(mode="json"))
        try:
            result = CleanupOutcome.model_validate_json(_canonical(raw))
            if (
                result.operation_id != str(request.operation_id)
                or result.cleanup_plan_id != request.cleanup_plan_id
                or result.selected_artifact_ids != request.selected_artifact_ids
                or (request.dry_run and result.state != "DRY_RUN")
            ):
                raise ValueError("cleanup binding")
        except ValueError:
            raise InvalidInputError("Native storage cleanup response rejected") from None
        return result
