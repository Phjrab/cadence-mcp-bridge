from __future__ import annotations

import asyncio
import os
from typing import Any, cast

import pytest
from mcp import Client

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

pytestmark = pytest.mark.skipif(
    os.environ.get("CADENCE_MCP_RUN_INTEGRATION") != "1",
    reason="set CADENCE_MCP_RUN_INTEGRATION=1 to contact cadence-vm",
)


def content(result: Any) -> dict[str, Any]:
    assert result.is_error is False
    return cast(dict[str, Any], result.structured_content)


@pytest.mark.asyncio
async def test_real_allowlisted_profile_lifecycle_through_mcp() -> None:
    server = create_server(CadenceService(OpenSshBackend(BridgeConfig())))

    async with Client(server) as client:
        listing = content(await client.call_tool("cadence_list_profiles"))
        profile = content(
            await client.call_tool("cadence_get_profile", {"profile_id": "fixture-rc-transient"})
        )
        submitted = content(
            await client.call_tool(
                "cadence_submit_profile",
                {
                    "profile_id": "fixture-rc-transient",
                    "corner": "nominal",
                    "variables": {
                        "resistance_ohm": 1000.0,
                        "capacitance_f": 1e-12,
                        "stop_time_s": 1e-9,
                    },
                },
            )
        )
        job_id = cast(str, submitted["job_id"])
        status: dict[str, Any] = submitted
        for _ in range(30):
            if status["state"] in {"succeeded", "failed", "cancelled", "unknown"}:
                break
            await asyncio.sleep(1)
            status = content(await client.call_tool("cadence_job_status", {"job_id": job_id}))
        result = content(await client.call_tool("cadence_job_result", {"job_id": job_id}))

    assert listing["registry_version"] == 1
    assert profile["classification"] == "fixture"
    assert status["state"] == "succeeded"
    assert result["exit_code"] == 0
    assert result["summary"]["errors"] == 0
    assert result["summary"]["warnings"] == 0
    artifacts = {item["name"] for item in result["artifacts"]}
    assert "run-manifest.json" in artifacts
    assert "variables" not in result


@pytest.mark.asyncio
async def test_real_actual_ade_profile_lifecycle_through_mcp() -> None:
    server = create_server(CadenceService(OpenSshBackend(BridgeConfig())))

    async with Client(server) as client:
        profile = content(
            await client.call_tool(
                "cadence_get_profile",
                {"profile_id": "actual-differential-amplifier-tb2-transient"},
            )
        )
        submitted = content(
            await client.call_tool(
                "cadence_submit_profile",
                {
                    "profile_id": "actual-differential-amplifier-tb2-transient",
                    "corner": "NN",
                    "variables": {},
                },
            )
        )
        job_id = cast(str, submitted["job_id"])
        status: dict[str, Any] = submitted
        for _ in range(300):
            if status["state"] in {"succeeded", "failed", "cancelled", "unknown"}:
                break
            await asyncio.sleep(1)
            status = content(await client.call_tool("cadence_job_status", {"job_id": job_id}))
        result = content(await client.call_tool("cadence_job_result", {"job_id": job_id}))

    assert profile["classification"] == "actual"
    assert profile["variables"] == []
    assert profile["outputs"] == []
    assert profile["corners"] == ["NN"]
    assert profile["ade"]["library"] == "MyDesignLib"
    assert profile["ade"]["cell"] == "Differential_Amplifier_TB2"
    assert profile["ade"]["state"] == "state1"
    assert profile["ade"]["spectre_stop_time"] == "4m"
    assert "/home/" not in str(profile)
    assert status["state"] == "succeeded"
    assert result["exit_code"] == 0
    assert result["summary"]["errors"] == 0
    assert result["summary"]["warnings"] == 2
    artifacts = {item["name"] for item in result["artifacts"]}
    assert "run-manifest.json" in artifacts
    assert "variables" not in result
