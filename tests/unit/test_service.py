from __future__ import annotations

import pytest

from cadence_mcp_bridge.errors import BackendUnavailableError
from cadence_mcp_bridge.models import (
    HealthReport,
    LicenseEnvironment,
    ToolAvailability,
)
from cadence_mcp_bridge.service import CadenceService


def health_report() -> HealthReport:
    return HealthReport(
        ssh="ok",
        remote_host="cadence",
        remote_user="buet",
        remote_root_accessible=True,
        virtuoso=ToolAvailability(available=True, version="IC6.1.5.500.15"),
        spectre=ToolAvailability(available=True, version="12.1.0.347.isr3"),
        ocean=ToolAvailability(available=True),
        license_env=LicenseEnvironment(CDS_LIC_FILE="SET"),
        runner_version="test",
    )


class FakeBackend:
    async def health(self) -> HealthReport:
        return health_report()


class FailingBackend:
    async def health(self) -> HealthReport:
        raise RuntimeError("sensitive backend details")


@pytest.mark.asyncio
async def test_service_uses_typed_fake_backend() -> None:
    report = await CadenceService(FakeBackend()).health()

    assert report.ssh == "ok"
    assert report.license_env.CDS_LIC_FILE == "SET"


@pytest.mark.asyncio
async def test_service_maps_unexpected_backend_failure() -> None:
    with pytest.raises(BackendUnavailableError, match="unavailable"):
        await CadenceService(FailingBackend()).health()
