"""Private, resumable real MCP client check for the fixed DC/AC work-copy tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import deploy_sim_mcp_v2 as deployment
from mcp import Client

from cadence_mcp_bridge.server import create_default_server

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / ".codex/sim-mcp-v2-e2e-journal.json"
REPORT = ROOT / ".codex/sim-mcp-v2-e2e-private.json"
FIXED = {
    "revision_id": "wp14-copied-netlist-v1",
    "operating_point_id": "candidate-320-702mv-v1",
}
OLD_TOOLS = {
    "cadence_health",
    "cadence_submit_smoke",
    "cadence_job_status",
    "cadence_job_log_tail",
    "cadence_job_result",
    "cadence_cancel_job",
    "cadence_list_libraries",
    "cadence_list_cells",
    "cadence_inspect_cellview",
    "cadence_list_profiles",
    "cadence_get_profile",
    "cadence_submit_profile",
    "cadence_get_measurement_contract",
    "cadence_measure_dc_power",
    "cadence_measure_offset",
    "cadence_measure_settling",
    "cadence_measure_fft_metrics",
    "cadence_measure_linearity",
    "cadence_compare_corner_results",
    "cadence_summarize_monte_carlo",
    "cadence_design_write_plan",
    "cadence_execute_design_write_validation",
}
NEW_TOOLS = {
    "cadence_list_actual_diagnostics",
    "cadence_submit_actual_diagnostic",
    "cadence_actual_diagnostic_status",
    "cadence_actual_diagnostic_result",
}


class VerificationError(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
        raise VerificationError("private verification record missing or oversized")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError("invalid private verification record")
    return value


def payload(response: Any) -> dict[str, Any]:
    if response.is_error or not isinstance(response.structured_content, dict):
        raise VerificationError("MCP tool returned an error or invalid structured response")
    return response.structured_content


async def call(client: Client, name: str, arguments: dict | None = None) -> dict:
    return payload(await client.call_tool(name, arguments, read_timeout_seconds=60))


def compare_dc(result: dict, old: dict) -> dict:
    names = {
        "vop": "Vop",
        "vom": "Vom",
        "vdd": "VDD",
        "vp": "Vp",
        "vm": "Vm",
        "output_common_mode": "output_common_mode_v",
        "output_differential": "output_diff_v",
    }
    current = {scalar["logical_id"]: scalar["value"] for scalar in result["scalars"]}
    if set(current) != set(names):
        raise VerificationError("DC result scalar set mismatch")
    maximum_difference = 0.0
    for key, old_key in names.items():
        reference = old["values_v"]["candidate"][old_key]
        difference = abs(current[key] - reference)
        maximum_difference = max(maximum_difference, difference)
        if difference > max(1e-5, abs(reference) * 1e-3):
            raise VerificationError("DC prior-result regression tolerance exceeded")
    return {
        "point_count": len(current),
        "max_abs_difference_v": maximum_difference,
        "comparison": "within_tolerance",
    }


def compare_ac(result: dict, old: dict) -> dict:
    current = result["spectrum"]
    reference = old["points"]
    if len(current) != len(reference) or len(current) != 71:
        raise VerificationError("AC point count mismatch")
    maximum_relative_gain = 0.0
    maximum_phase_difference = 0.0
    for point, prior in zip(current, reference, strict=True):
        if abs(point["frequency_hz"] - prior["frequency_hz"]) > max(
            1e-4, prior["frequency_hz"] * 1e-6
        ):
            raise VerificationError("AC frequency mismatch")
        gain_difference = abs(point["gain_v_per_v"] - prior["gain_v_per_v"])
        relative = gain_difference / max(abs(prior["gain_v_per_v"]), 1e-12)
        maximum_relative_gain = max(maximum_relative_gain, relative)
        if gain_difference > max(1e-5, abs(prior["gain_v_per_v"]) * 1e-3):
            raise VerificationError("AC gain regression tolerance exceeded")
        phase_difference = abs(point["phase_deg"] - prior["gain_phase_deg"])
        phase_difference = min(phase_difference, abs(phase_difference - 360))
        maximum_phase_difference = max(maximum_phase_difference, phase_difference)
        if phase_difference > 0.05:
            raise VerificationError("AC phase regression tolerance exceeded")
    return {
        "point_count": len(current),
        "max_relative_gain_difference": maximum_relative_gain,
        "max_phase_difference_deg": maximum_phase_difference,
        "comparison": "within_tolerance",
    }


async def one_analysis(client: Client, journal: dict, analysis: str) -> dict:
    output = "dc-node-scalars-v1" if analysis == "dc" else "ac-differential-spectrum-v1"
    key = analysis + "_job_id"
    job_id = journal.get(key)
    if job_id is None:
        journal["phase"] = analysis + "_submit_reserved"
        save(JOURNAL, journal)
        submitted = await call(
            client,
            "cadence_submit_actual_diagnostic",
            {"request": {**FIXED, "analysis": analysis, "output_id": output}},
        )
        job_id = submitted["job_id"]
        journal[key] = job_id
        journal["phase"] = analysis + "_submitted"
        save(JOURNAL, journal)
    elif journal.get("phase") == analysis + "_submit_reserved":
        raise VerificationError("submit outcome uncertain; do not create a second job")
    for _ in range(300):
        status = await call(
            client, "cadence_actual_diagnostic_status", {"job_id": job_id, "analysis": analysis}
        )
        if status["state"] in ("succeeded", "failed"):
            break
        await asyncio.sleep(1)
    else:
        raise VerificationError("diagnostic did not complete within bounded poll interval")
    if status["state"] != "succeeded":
        raise VerificationError("diagnostic simulator or extraction failed")
    result = await call(
        client, "cadence_actual_diagnostic_result", {"job_id": job_id, "analysis": analysis}
    )
    if result["quality"] != "valid" or result["spec_evaluation"] != "not_evaluated":
        raise VerificationError("diagnostic result quality mismatch")
    journal["phase"] = analysis + "_completed"
    save(JOURNAL, journal)
    return result


async def verify(resume: bool) -> dict:
    policy, digest_value, state_root = deployment.authority()
    deployed = load(state_root / "sim-mcp-v2-deploy.json")
    if deployed.get("state") != "succeeded" or deployed.get("policy_sha256") != digest_value:
        raise VerificationError("verified deployment is absent")
    if resume:
        journal = load(JOURNAL)
        if journal.get("policy_sha256") != digest_value:
            raise VerificationError("verification journal policy mismatch")
    else:
        if JOURNAL.exists() or REPORT.exists():
            raise VerificationError("verification already reserved; use resume")
        journal = {
            "phase": "started",
            "policy_sha256": digest_value,
            "at": datetime.now(UTC).isoformat(),
        }
        save(JOURNAL, journal)
    old_root = state_root
    old_dc = load(old_root / "phasef-dc-scalars-v1-read.output")
    old_ac = load(old_root / "phasep-candidate-wideband-scalars-v1-read.output")
    async with Client(create_default_server()) as client:
        listing = await client.list_tools()
        names = {tool.name for tool in listing.tools}
        if names != OLD_TOOLS | NEW_TOOLS:
            raise VerificationError("MCP registry changed")
        profiles = await call(client, "cadence_list_actual_diagnostics")
        if len(profiles["profiles"]) != 2 or {
            item["analysis"] for item in profiles["profiles"]
        } != {"dc", "ac"}:
            raise VerificationError("MCP diagnostic profile registry mismatch")
        dc = await one_analysis(client, journal, "dc")
        dc_comparison = compare_dc(dc, old_dc)
        ac = await one_analysis(client, journal, "ac")
        ac_comparison = compare_ac(ac, old_ac)
    report = {
        "phase": "SIM-MCP-01",
        "policy_sha256": digest_value,
        "mcp_tool_count": len(names),
        "prior_tool_count": len(OLD_TOOLS),
        "dc": dc,
        "dc_comparison": dc_comparison,
        "ac": ac,
        "ac_comparison": ac_comparison,
        "spec_evaluation": "not_evaluated",
        "at": datetime.now(UTC).isoformat(),
    }
    if REPORT.exists():
        raise VerificationError("private result already exists")
    save(REPORT, report)
    journal["phase"] = "complete"
    journal["report_sha256"] = digest(REPORT.read_bytes())
    save(JOURNAL, journal)
    return {
        "status": "passed",
        "mcp_tool_count": len(names),
        "dc_job_id": dc["job_id"],
        "ac_job_id": ac["job_id"],
        "report_sha256": journal["report_sha256"],
        "spec_evaluation": "not_evaluated",
    }


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("run", "resume"):
        print("usage: verify_sim_mcp_v2.py run|resume", file=sys.stderr)
        return 2
    try:
        result = asyncio.run(verify(sys.argv[1] == "resume"))
    except (VerificationError, deployment.DeploymentError, Exception) as exc:
        print(f"SIM-MCP-01 E2E incomplete: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
