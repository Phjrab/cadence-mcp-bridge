"""Application service boundary, independent from SSH and MCP transports."""

from __future__ import annotations

from typing import Protocol

from cadence_mcp_bridge.errors import BackendUnavailableError, BridgeError
from cadence_mcp_bridge.models import HealthReport


class CadenceBackend(Protocol):
    async def health(self) -> HealthReport: ...


class CadenceService:
    def __init__(self, backend: CadenceBackend) -> None:
        self._backend = backend

    async def health(self) -> HealthReport:
        try:
            return await self._backend.health()
        except BridgeError:
            raise
        except Exception as exc:
            raise BackendUnavailableError("Cadence backend is unavailable") from exc

