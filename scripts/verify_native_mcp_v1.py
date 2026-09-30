"""Resumable real stdio MCP E2E for fixed native DC/AC/trap TRAN."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import ade_qual as dc
import deploy_native_mcp_v1 as deployment
import phase_campaign as campaign
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from cadence_mcp_bridge.native_diagnostics import NativeDiagnosticResult

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / ".codex/native-mcp-v1-e2e-journal.json"
REPORT = ROOT / ".codex/native-mcp-v1-e2e-private.json"
NEW_TOOLS = {
    "cadence_list_native_diagnostics",
    "cadence_submit_native_diagnostic",
    "cadence_native_diagnostic_status",
    "cadence_native_diagnostic_result",
}


async def call(
    client: Client, name: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = await client.call_tool(name, arguments, read_timeout_seconds=90)
    if response.is_error or not isinstance(response.structured_content, dict):
        raise ValueError("native MCP call failed: " + name)
    return response.structured_content


def compare(actual: dict[str, Any], reference: dict[str, Any], analysis: str) -> dict[str, Any]:
    if analysis == "dc":
        values = [item["value"] for item in actual["scalars"]]
        old = [item["value"] for item in reference["scalars"]]
        difference = max(abs(a - b) for a, b in zip(values, old, strict=True))
        if difference > 1e-5:
            raise ValueError("native DC reference regression")
        return {"max_abs_difference_v": difference, "scalar_count": len(values)}
    if analysis == "ac":
        maximum_gain = 0.0
        maximum_phase = 0.0
        for a, b in zip(actual["spectrum"], reference["spectrum"], strict=True):
            if abs(a["frequency_hz"] - b["frequency_hz"]) > max(1e-4, b["frequency_hz"] * 1e-6):
                raise ValueError("native AC reference frequency")
            gain = abs(a["gain_v_per_v"] - b["gain_v_per_v"]) / max(b["gain_v_per_v"], 1e-12)
            phase = abs(a["phase_deg"] - b["phase_deg"])
            phase = min(phase, abs(phase - 360))
            maximum_gain = max(maximum_gain, gain)
            maximum_phase = max(maximum_phase, phase)
        if maximum_gain > 1e-3 or maximum_phase > 0.05:
            raise ValueError("native AC reference regression")
        return {
            "point_count": len(actual["spectrum"]),
            "max_relative_gain_difference": maximum_gain,
            "max_phase_difference_deg": maximum_phase,
        }
    a, b = actual["transient"], reference["transient"]
    if a["point_count"] != b["point_count"]:
        raise ValueError("native TRAN reference sampling count")
    difference = max(
        abs(a[key] - b[key])
        for key in (
            "output_differential_min_v",
            "output_differential_max_v",
            "output_common_mode_min_v",
            "output_common_mode_max_v",
        )
    )
    if difference > 1e-4:
        raise ValueError("native TRAN reference extrema")
    return {
        "point_count": a["point_count"],
        "max_abs_extrema_difference_v": difference,
        "full_waveform_equivalence": "not_claimed",
    }


async def verify(resume: bool) -> dict[str, Any]:
    _, digest = deployment.authority()
    deployed = campaign._read_json(deployment.JOURNAL)
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest:
        raise ValueError("native MCP deployment unverified")
    if resume:
        journal = campaign._read_json(JOURNAL)
        if journal.get("policy_sha256") != digest:
            raise ValueError("native E2E policy mismatch")
    else:
        before = deployment.postflight()
        journal = {
            "phase": "started",
            "policy_sha256": digest,
            "before": before,
            "jobs": {a: str(uuid4()) for a in ("dc", "ac", "tran")},
            "at": datetime.now(UTC).isoformat(),
        }
        dc.save_new(JOURNAL, journal)
    reference = campaign._read_json(deployment.REFERENCE)
    results: dict[str, dict[str, Any]] = {}
    comparisons: dict[str, dict[str, Any]] = {}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cadence_mcp_bridge"],
        cwd=str(ROOT),
        env={"PYTHONUTF8": "1"},
    )
    async with Client(params) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        if len(names) != 35 or not names >= NEW_TOOLS:
            raise ValueError("native MCP registry mismatch")
        contract = await call(client, "cadence_list_native_diagnostics")
        if contract["analyses"] != ["dc", "ac", "tran"]:
            raise ValueError("native MCP contract mismatch")
        for analysis in ("dc", "ac", "tran"):
            job_id = journal["jobs"][analysis]
            arguments = {
                "request": {
                    "operation_id": job_id,
                    "analysis": analysis,
                    "revision_id": "wp14-native-ade-v1",
                    "operating_point_id": "candidate-320-702mv-v1",
                }
            }
            journal["phase"] = analysis + "_submit_reserved"
            campaign._replace_record(JOURNAL, journal)
            submitted = await call(client, "cadence_submit_native_diagnostic", arguments)
            if submitted["job_id"] != job_id or submitted["analysis"] != analysis:
                raise ValueError("native MCP identity")
            # Reusing the same operation ID during or after execution is a read.
            duplicate = await call(client, "cadence_submit_native_diagnostic", arguments)
            if duplicate["job_id"] != job_id:
                raise ValueError("native replay identity")
            for _ in range(180):
                status = await call(
                    client,
                    "cadence_native_diagnostic_status",
                    {"job_id": job_id, "analysis": analysis},
                )
                if status["state"] == "succeeded":
                    break
                if status["state"] in ("failed", "unknown"):
                    raise ValueError("native MCP incomplete: " + analysis + " " + status["stage"])
                await asyncio.sleep(2)
            else:
                raise ValueError("native E2E polling bound")
            result = await call(
                client, "cadence_native_diagnostic_result", {"job_id": job_id, "analysis": analysis}
            )
            NativeDiagnosticResult.model_validate(result)
            comparisons[analysis] = compare(result, reference[analysis], analysis)
            results[analysis] = result
            duplicate = await call(client, "cadence_submit_native_diagnostic", arguments)
            if duplicate["state"] != "succeeded":
                raise ValueError("native completed replay state")
            wrong = await client.call_tool(
                "cadence_native_diagnostic_status",
                {"job_id": job_id, "analysis": "tran" if analysis == "dc" else "dc"},
            )
            if not wrong.is_error:
                raise ValueError("native analysis mismatch was accepted")
            journal["phase"] = analysis + "_complete"
            campaign._replace_record(JOURNAL, journal)
    after = deployment.postflight()
    if (
        after["counter"]["count"] != journal["before"]["counter"]["count"] + 3
        or after["counter"]["result_reserved_bytes"]
        != journal["before"]["counter"]["result_reserved_bytes"] + 3 * 128 * 1024**2
    ):
        raise ValueError("native E2E ledger or replay mismatch")
    report = {
        "phase": "NATIVE-MCP-01",
        "policy_sha256": digest,
        "transport": "stdio",
        "mcp_tool_count": len(names),
        "results": results,
        "comparisons": comparisons,
        "before": journal["before"],
        "postflight": after,
        "replay_did_not_consume_attempts": True,
        "wrong_analysis_rejected": True,
        "spec_evaluation": "not_evaluated",
        "at": datetime.now(UTC).isoformat(),
    }
    dc.save_new(REPORT, report)
    journal["phase"] = "complete"
    journal["report_sha256"] = dc.digest(REPORT.read_bytes())
    campaign._replace_record(JOURNAL, journal)
    return {
        "state": "passed",
        "report_sha256": journal["report_sha256"],
        "counter": after["counter"],
        "mcp_tool_count": len(names),
        "transport": "stdio",
    }


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("run", "resume"):
            raise ValueError("usage: verify_native_mcp_v1.py run|resume")
        print(json.dumps(asyncio.run(verify(sys.argv[1] == "resume")), sort_keys=True))
    except (OSError, ValueError, campaign.CampaignError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
