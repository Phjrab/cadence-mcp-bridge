"""Bounded MCP-to-Spectre lifecycle verification."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from time import monotonic
from typing import Any, cast

from mcp import Client
from mcp.server import MCPServer
from pydantic import BaseModel, ConfigDict

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.models import JobState
from cadence_mcp_bridge.server import create_default_server


class E2EReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    health_ok: bool
    runner_version: str
    job_id: str
    submit_seconds: float
    observed_states: tuple[JobState, ...]
    exit_code: int
    artifact_count: int
    storage_contained: bool
    storage_mode: str
    log_lines_requested: int
    log_bytes: int


def _content(response: Any, operation: str) -> dict[str, Any]:
    value = response.structured_content
    if response.is_error or not isinstance(value, dict):
        raise RuntimeError(f"{operation} returned a safe MCP error")
    return cast(dict[str, Any], value)


async def verify_lifecycle(
    *, server: MCPServer | None = None, config: BridgeConfig | None = None
) -> E2EReport:
    settings = config or BridgeConfig()
    target_server = server or create_default_server()
    observed: list[JobState] = []

    async with Client(target_server) as client:
        health = _content(await client.call_tool("cadence_health"), "health")
        if health.get("ssh") != "ok" or not health.get("spectre", {}).get("available"):
            raise RuntimeError("health did not confirm the SSH and Spectre boundary")

        started = monotonic()
        submitted = _content(await client.call_tool("cadence_submit_smoke"), "submit")
        submit_seconds = monotonic() - started
        if submit_seconds > settings.submit_target_seconds:
            raise RuntimeError("submit exceeded the configured response target")
        job_id = cast(str, submitted["job_id"])
        observed.append(JobState(cast(str, submitted["state"])))

        deadline = monotonic() + settings.max_poll_seconds
        terminal = {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.UNKNOWN}
        state = observed[-1]
        while state not in terminal:
            if monotonic() >= deadline:
                raise RuntimeError("job did not reach a terminal state before the poll deadline")
            await asyncio.sleep(settings.poll_interval_seconds)
            status = _content(
                await client.call_tool("cadence_job_status", {"job_id": job_id}), "status"
            )
            state = JobState(cast(str, status["state"]))
            if state != observed[-1]:
                observed.append(state)

        if state is JobState.SUCCEEDED:
            log = _content(
                await client.call_tool(
                    "cadence_job_log_tail",
                    {"job_id": job_id, "stream": "stdout", "lines": 50},
                ),
                "log-tail",
            )
            result = _content(
                await client.call_tool("cadence_job_result", {"job_id": job_id}), "result"
            )

    if state is not JobState.SUCCEEDED:
        raise RuntimeError(f"job reached safe terminal state {state.value}")

    summary = cast(dict[str, Any], result["summary"])
    artifacts = cast(list[dict[str, Any]], result["artifacts"])
    storage = cast(dict[str, Any], result.get("storage"))
    if result.get("exit_code") != 0 or summary.get("errors") != 0 or not artifacts:
        raise RuntimeError("Spectre result did not satisfy the smoke acceptance contract")
    if (
        not storage
        or storage.get("contained") is not True
        or storage.get("directory_mode") != "0700"
    ):
        raise RuntimeError("remote job storage did not satisfy containment and permission checks")
    log_text = cast(str, log["text"])
    log_bytes = len(log_text.encode("utf-8"))
    if log_bytes > settings.max_output_bytes:
        raise RuntimeError("log tail exceeded the configured byte limit")

    return E2EReport(
        health_ok=True,
        runner_version=cast(str, health["runner_version"]),
        job_id=job_id,
        submit_seconds=round(submit_seconds, 3),
        observed_states=tuple(observed),
        exit_code=cast(int, result["exit_code"]),
        artifact_count=len(artifacts),
        storage_contained=True,
        storage_mode="0700",
        log_lines_requested=cast(int, log["lines_requested"]),
        log_bytes=log_bytes,
    )


def main(argv: Sequence[str] | None = None) -> int:
    argparse.ArgumentParser(description="Verify the fixed MCP-to-Spectre lifecycle").parse_args(
        argv
    )
    try:
        report = asyncio.run(verify_lifecycle())
    except Exception as exc:
        print(f"E2E verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
