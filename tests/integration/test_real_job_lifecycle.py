from __future__ import annotations

import asyncio
import os
from typing import Any, cast

import pytest
from mcp import Client

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.e2e import verify_lifecycle
from cadence_mcp_bridge.models import JobState
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("CADENCE_MCP_RUN_INTEGRATION") != "1",
        reason="set CADENCE_MCP_RUN_INTEGRATION=1 to contact cadence-vm",
    ),
]


@pytest.mark.asyncio
async def test_real_mcp_to_spectre_smoke_lifecycle() -> None:
    report = await verify_lifecycle()

    assert report.health_ok is True
    assert report.runner_version == "0.3.0"
    assert report.exit_code == 0
    assert report.artifact_count >= 1
    assert report.storage_contained is True
    assert report.storage_mode == "0700"


def _content(response: Any) -> dict[str, Any]:
    assert response.is_error is False
    return cast(dict[str, Any], response.structured_content)


@pytest.mark.asyncio
async def test_cancelled_job_does_not_terminate_another_job() -> None:
    server = create_server(CadenceService(OpenSshBackend(BridgeConfig())))
    terminal = {
        JobState.SUCCEEDED.value,
        JobState.FAILED.value,
        JobState.CANCELLED.value,
        JobState.UNKNOWN.value,
    }

    async with Client(server) as client:
        submitted = await asyncio.gather(
            *(client.call_tool("cadence_submit_smoke") for _ in range(5))
        )
        job_ids = [cast(str, _content(response)["job_id"]) for response in submitted]
        cancellable: str | None = None
        cancel_state: str | None = None
        for job_id in job_ids:
            status = _content(await client.call_tool("cadence_job_status", {"job_id": job_id}))
            if status["state"] == JobState.QUEUED.value:
                cancellable = job_id
                cancel = _content(await client.call_tool("cadence_cancel_job", {"job_id": job_id}))
                cancel_state = cast(str, cancel["state"])
                break

        final: dict[str, str] = {}
        for _ in range(150):
            for job_id in job_ids:
                if job_id not in final:
                    status = _content(
                        await client.call_tool("cadence_job_status", {"job_id": job_id})
                    )
                    if status["state"] in terminal:
                        final[job_id] = cast(str, status["state"])
            if len(final) == len(job_ids):
                break
            await asyncio.sleep(0.2)

    assert cancellable is not None, "concurrency=1 did not leave a cancellable queued job"
    assert cancel_state in {JobState.CANCELLING.value, JobState.CANCELLED.value}
    assert final.get(cancellable) == JobState.CANCELLED.value
    survivors = [state for job_id, state in final.items() if job_id != cancellable]
    assert survivors
    assert all(state == JobState.SUCCEEDED.value for state in survivors)
