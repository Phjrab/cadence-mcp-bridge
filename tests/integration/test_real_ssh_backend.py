from __future__ import annotations

import os

import pytest

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("CADENCE_MCP_RUN_INTEGRATION") != "1",
        reason="set CADENCE_MCP_RUN_INTEGRATION=1 to contact cadence-vm",
    ),
]


@pytest.mark.asyncio
async def test_real_cadence_vm_health() -> None:
    report = await OpenSshBackend(BridgeConfig()).health()

    assert report.ssh == "ok"
    assert report.remote_root_accessible is True
    assert report.runner_version == "0.2.0"
    assert report.virtuoso.available is True
    assert report.spectre.available is True
