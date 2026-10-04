"""Real MCP replay/read verification of the budget adapter; zero new simulations."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ade_qual as dc
import phase_campaign as campaign
import spectre_limit as deployment
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from cadence_mcp_bridge.native_diagnostics import NativeDiagnosticResult

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / ".codex/native-mcp-v2-e2e-journal.json"
REPORT = ROOT / ".codex/native-mcp-v2-e2e-private.json"
JOBS = {
    "dc": "f154d798-0f7f-47d6-9323-6b046394eef6",
    "ac": "1afa2677-e264-4e80-a23d-dc722e34bb4a",
    "tran": "eca78308-8af8-4810-b848-94c0ad936afe",
}


async def call(
    client: Client, name: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = await client.call_tool(name, arguments, read_timeout_seconds=45)
    if response.is_error or not isinstance(response.structured_content, dict):
        raise ValueError("bounded native MCP replay/read failed")
    return response.structured_content


async def run() -> dict[str, Any]:
    _, digest = deployment.authority()
    if campaign._read_json(deployment.JOURNAL).get("state") != "succeeded":
        raise ValueError("qualified budget deployment required")
    before = deployment.postflight()
    dc.save_new(
        JOURNAL,
        {
            "state": "reserved",
            "policy_sha256": digest,
            "at": datetime.now(UTC).isoformat(),
            "before": before,
        },
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cadence_mcp_bridge"],
        cwd=str(ROOT),
        env={"PYTHONUTF8": "1"},
    )
    results = {}
    async with Client(params) as client:
        if len((await client.list_tools()).tools) != 35:
            raise ValueError("native registry changed")
        profile = await call(client, "cadence_list_native_diagnostics")
        if (
            profile["contract_version"] != 2
            or profile["campaign_max_spectre_attempts"] != 500
            or profile["campaign_max_result_bytes"] != 5 * 1024**3
            or profile["reservation_bytes_per_job"] != 128 * 1024**2
        ):
            raise ValueError("effective MCP budget metadata mismatch")
        for analysis, job in JOBS.items():
            replay = await call(
                client,
                "cadence_submit_native_diagnostic",
                {
                    "request": {
                        "operation_id": job,
                        "revision_id": "wp14-native-ade-v1",
                        "operating_point_id": "candidate-320-702mv-v1",
                        "analysis": analysis,
                    }
                },
            )
            if replay["job_id"] != job or replay["state"] != "succeeded":
                raise ValueError("preserved same-ID replay failed")
            result = await call(
                client, "cadence_native_diagnostic_result", {"job_id": job, "analysis": analysis}
            )
            NativeDiagnosticResult.model_validate(result)
            if result["job_id"] != job or result["analysis"] != analysis:
                raise ValueError("preserved native result identity")
            results[analysis] = {
                "measurement_frame_sha256": result["measurement_frame_sha256"],
                "settings": result["settings"],
                "quality": result["quality"],
            }
        wrong = await client.call_tool(
            "cadence_native_diagnostic_status",
            {"job_id": JOBS["dc"], "analysis": "ac"},
            read_timeout_seconds=45,
        )
        if not wrong.is_error:
            raise ValueError("cross-analysis replay was not rejected")
    after = deployment.postflight()
    if (
        before["native"]["counter"] != after["native"]["counter"]
        or before["native"]["jobs"] != after["native"]["jobs"]
        or before["protected_corner_jobs"]["jobs"] != after["protected_corner_jobs"]["jobs"]
    ):
        raise ValueError("read-only native E2E changed evidence or ledger")
    report = {
        "state": "succeeded",
        "policy_sha256": digest,
        "new_spectre_attempts": 0,
        "before": before,
        "after": after,
        "profile": profile,
        "results": results,
        "wrong_analysis_rejected": True,
        "tool_count": 35,
    }
    dc.save_new(REPORT, report)
    campaign._replace_record(
        JOURNAL,
        {
            "state": "succeeded",
            "policy_sha256": digest,
            "report_sha256": dc.digest(REPORT.read_bytes()),
        },
    )
    return {
        "state": "succeeded",
        "tool_count": 35,
        "max_spectre_attempts": 500,
        "new_spectre_attempts": 0,
        "counter": after["native"]["counter"],
        "same_id_replay": "three_analyses_verified",
        "wrong_analysis_rejected": True,
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 1:
            raise ValueError("fixed E2E takes no arguments")
        print(json.dumps(asyncio.run(run()), sort_keys=True))
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
