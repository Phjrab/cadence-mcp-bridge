"""Private real MCP three-point fixture sweep with resumable experiment key."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import deploy_sweep_mcp_v1 as deployment
from mcp import Client

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / ".codex/sweep-mcp-v1-e2e-journal.json"
REPORT = ROOT / ".codex/sweep-mcp-v1-e2e-private.json"
REQUEST = {
    "profile_id": "fixture-rc-transient",
    "corner": "nominal",
    "axis": "resistance_ohm",
    "unit": "ohm",
    "values": ["900", "1000", "1100"],
    "fixed": {"capacitance_f": "1e-12", "stop_time_s": "1e-9"},
    "measurements": ["simulation_completion"],
    "initial_condition": "independent",
}


class VerificationError(RuntimeError):
    pass


def save(path: Path, data: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
        raise VerificationError("private sweep record missing or unsafe")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError("private sweep record invalid")
    return value


def remote_facts() -> dict:
    command = (
        "cat /home/buet/cds_work/.cadence_mcp/sim-mcp-v2-jobs/counter.json; echo; "
        "df -B1 /home/buet/cds_work/.cadence_mcp | tail -1; "
        "test ! -e /home/buet/cds_work/.cadence_mcp/sim-mcp-v2-jobs/active || exit 69; "
        "ps -eo comm | grep -Ec '^(spectre|ocean|virtuoso)$' || true"
    )
    done = subprocess.run((*deployment.SSH, command), capture_output=True, timeout=45, check=False)
    if done.returncode or len(done.stdout) > 4096:
        raise VerificationError("remote sweep postflight unavailable")
    lines = done.stdout.decode("ascii").splitlines()
    if len(lines) != 3:
        raise VerificationError("remote sweep postflight shape mismatch")
    counter = json.loads(lines[0])
    fields = lines[1].split()
    if len(fields) < 4 or lines[2] != "0":
        raise VerificationError("remote disk or EDA state mismatch")
    return {
        "counter": counter,
        "disk_total_bytes": int(fields[1]),
        "disk_free_bytes": int(fields[3]),
        "active_eda_processes": 0,
    }


def payload(response: object) -> dict:
    if getattr(response, "is_error", None) or not isinstance(
        getattr(response, "structured_content", None), dict
    ):
        raise VerificationError("MCP sweep tool returned an error")
    return response.structured_content


async def call(client: Client, name: str, arguments: dict) -> dict:
    return payload(await client.call_tool(name, arguments, read_timeout_seconds=120))


async def verify(resume: bool) -> dict:
    policy, digest = deployment.authority()
    record = load(deployment.JOURNAL)
    if record.get("state") != "succeeded" or record.get("policy_sha256") != digest:
        raise VerificationError("verified sweep helper deployment absent")
    if resume:
        journal = load(JOURNAL)
        if journal.get("policy_sha256") != digest:
            raise VerificationError("sweep journal policy mismatch")
    else:
        if JOURNAL.exists() or REPORT.exists():
            raise VerificationError("sweep experiment already reserved; use resume")
        deployment.verify(policy)
        journal = {
            "phase": "started",
            "policy_sha256": digest,
            "experiment_key": str(uuid4()),
            "at": datetime.now(UTC).isoformat(),
            "before": remote_facts(),
        }
        save(JOURNAL, journal)
    service = CadenceService(OpenSshBackend(BridgeConfig()))
    async with Client(create_server(service)) as client:
        listing = await client.list_tools()
        names = {tool.name for tool in listing.tools}
        required = {
            "cadence_plan_sweep",
            "cadence_submit_sweep",
            "cadence_sweep_status",
            "cadence_sweep_result",
            "cadence_cancel_sweep",
        }
        if len(names) != 31 or not required <= names:
            raise VerificationError("MCP sweep tool registry mismatch")
        plan = await call(client, "cadence_plan_sweep", {"request": REQUEST})
        if plan["point_count"] != 3 or plan["classification"] != "one_variable_fixture":
            raise VerificationError("three-point fixture plan mismatch")
        journal["plan_hash"] = plan["plan_hash"]
        journal["phase"] = "submit_reserved"
        save(JOURNAL, journal)
        submitted = await call(
            client,
            "cadence_submit_sweep",
            {"submission": {"plan": plan, "experiment_key": journal["experiment_key"]}},
        )
        journal["sweep_id"] = submitted["sweep_id"]
        journal["phase"] = "submitted"
        save(JOURNAL, journal)
        for _ in range(900):
            status = await call(client, "cadence_sweep_status", {"sweep_id": journal["sweep_id"]})
            if status.get("sweep_id") != journal["sweep_id"]:
                raise VerificationError("MCP sweep status identity changed")
            task = service._sweeps.tasks[UUID(journal["sweep_id"])]
            if task.done():
                await task
                break
            await asyncio.sleep(1)
        else:
            raise VerificationError("bounded sweep poll ended before terminal state")
        result = await call(client, "cadence_sweep_result", {"sweep_id": journal["sweep_id"]})
        if result["state"] != "SUCCEEDED" or len(result["points"]) != 3:
            raise VerificationError("fixture sweep did not complete all three points")
        if [point["requested_value"] for point in result["points"]] != ["900", "1000", "1100"]:
            raise VerificationError("fixture sweep values changed")
        if any(
            float(Decimal(point["applied_value"])) != float(Decimal(point["requested_value"]))
            or any(
                float(Decimal(point["applied_fixed"][name])) != float(Decimal(value))
                for name, value in plan["canonical_fixed"].items()
            )
            or point["quality"] != "valid"
            or point["measurement_value"] is not True
            or point["provenance"] != "remote_spectre_profile"
            for point in result["points"]
        ):
            raise VerificationError("per-point effective inputs or measurement provenance invalid")
        if len({point["child_job_id"] for point in result["points"]}) != 3:
            raise VerificationError("duplicate child job identity")
        # Repeated same-key request must return the same parent, with no extra run.
        again = await call(
            client,
            "cadence_submit_sweep",
            {"submission": {"plan": plan, "experiment_key": journal["experiment_key"]}},
        )
        if again["sweep_id"] != journal["sweep_id"]:
            raise VerificationError("same experiment key created a second parent")
    after = remote_facts()
    before = journal["before"]["counter"]
    if (
        after["counter"]["count"] != before["count"] + 3
        or after["counter"]["result_reserved_bytes"]
        != before["result_reserved_bytes"] + 3 * 134217728
    ):
        raise VerificationError("campaign ledger did not advance exactly three attempts")
    report = {
        "phase": "SWEEP-MCP-01",
        "policy_sha256": digest,
        "mcp_tool_count": len(names),
        "sweep": result,
        "before": journal["before"],
        "after": after,
        "spec_evaluation": "not_evaluated",
        "at": datetime.now(UTC).isoformat(),
    }
    if REPORT.exists():
        raise VerificationError("private sweep result already exists")
    save(REPORT, report)
    journal["phase"] = "complete"
    save(JOURNAL, journal)
    return {
        "phase": report["phase"],
        "state": result["state"],
        "point_count": len(result["points"]),
        "attempts_after": after["counter"]["count"],
        "private_sha256": hashlib.sha256(REPORT.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    try:
        if sys.argv[1:] not in (["run"], ["resume"]):
            raise VerificationError("usage: verify_sweep_mcp_v1.py run|resume")
        print(json.dumps(asyncio.run(verify(sys.argv[1] == "resume")), sort_keys=True))
    except (VerificationError, OSError, ValueError, KeyError, deployment.DeployError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
