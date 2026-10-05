"""Exercise an installed wheel from a new workspace without contacting Cadence."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters

import cadence_mcp_bridge


def cli(arguments: list[str], workspace: Path) -> dict[str, Any]:
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith("CADENCE_MCP_")
        and k.upper() not in ("PYTHONPATH", "PYTHONHOME")
    }
    process = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-m", "cadence_mcp_bridge", *arguments],
        cwd=workspace,
        env=environment,
        capture_output=True,
        timeout=30,
        check=True,
    )
    value: dict[str, Any] = json.loads(process.stdout.decode("utf-8"))
    if value.get("execution_authorized") is not False:
        raise ValueError("local CLI granted execution")
    return value


async def verify(
    examples: Path, workspace: Path, baseline: Path, expected_version: str
) -> dict[str, object]:
    origin = Path(cadence_mcp_bridge.__file__).resolve()
    if not origin.is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("import did not originate from isolated installed environment")
    metadata_version = importlib.metadata.version("cadence-mcp-bridge")
    if cadence_mcp_bridge.__version__ != expected_version or metadata_version != expected_version:
        raise ValueError("installed runtime and distribution versions disagree")
    process = subprocess.run(
        [sys.executable, "-I", "-m", "cadence_mcp_bridge", "--version"],
        cwd=workspace.parent,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    if process.stdout.strip() != expected_version:
        raise ValueError("installed CLI version disagrees")
    workspace.mkdir(mode=0o700, parents=False, exist_ok=False)
    paths = {name: workspace / (name + ".json") for name in ("environment", "designs", "pdks")}
    for name, path in paths.items():
        with path.open("xb") as stream:
            stream.write((examples / (name + ".json")).read_bytes())
    designs, pdks = workspace / "registered-designs.json", workspace / "registered-pdks.json"
    for kind, proposed, target in (
        ("design", paths["designs"], designs),
        ("pdk", paths["pdks"], pdks),
    ):
        cli([kind, "register", "--registry", str(proposed), "--output", str(target)], workspace)
    options = [
        "--profile",
        str(paths["environment"]),
        "--design-registry",
        str(designs),
        "--pdk-registry",
        str(pdks),
    ]
    checked = cli(["verify", *options], workspace)
    if checked["status"] != "consistent_local_contracts" or checked["remote_contact"]:
        raise ValueError("joined local verification failed")
    baseline_data = json.loads(baseline.read_bytes())
    baseline_names = set(baseline_data["tools"])
    if (
        len(baseline_names) != 22
        or baseline_data["release_tag"] != "v1.0.0"
        or baseline_data["tag_commit"] != "8a0d44fab90e2095cc39322baef60fc09d741cd6"
    ):
        raise ValueError("legacy snapshot does not identify the published 22-tool baseline")
    counts: dict[str, int] = {}
    for format, filename in (("codex", "client.toml"), ("mcp-json", "client.json")):
        output, journal = workspace / filename, workspace / (format + ".sqlite3")
        cli(
            [
                "client-config",
                *options,
                "--journal",
                str(journal),
                "--format",
                format,
                "--output",
                str(output),
            ],
            workspace,
        )
        if format == "codex":
            exported = tomllib.loads(output.read_text(encoding="utf-8"))["mcp_servers"][
                "cadence-mcp-bridge"
            ]
            if (
                exported["default_tools_approval_mode"] != "writes"
                or exported["tools"]["cadence_submit_analysis"]["approval_mode"] != "prompt"
            ):
                raise ValueError("Codex approval configuration changed")
        else:
            exported = json.loads(output.read_bytes())["mcpServers"]["cadence-mcp-bridge"]
        parameters = StdioServerParameters(
            command=exported["command"],
            args=exported["args"],
            env=exported["env"],
            cwd=str(workspace),
        )
        async with Client(parameters) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            if len(names) != 48 or not baseline_names.issubset(names):
                raise ValueError("installed MCP tool inventory incompatible")
            counts[format] = len(names)
            listing = await client.call_tool("cadence_list_designs")
            if listing.is_error or listing.structured_content is None:
                raise ValueError("installed registry inspection failed")
            if listing.structured_content["designs"][0]["design_id"] != "example-amplifier":
                raise ValueError("installed registry settings were not honored")
            plan = await client.call_tool(
                "cadence_plan_analysis",
                {
                    "request": {"design_id": "example-amplifier", "analysis_id": "example-dc"},
                },
            )
            if (
                plan.is_error
                or plan.structured_content is None
                or plan.structured_content["dispatch_eligible"]
            ):
                raise ValueError("fictional analysis qualified")
            denied = await client.call_tool(
                "cadence_submit_analysis",
                {
                    "submission": {
                        "design_id": "example-amplifier",
                        "analysis_id": "example-dc",
                        "operation_id": "00000000-0000-4000-8000-000000000000",
                        "expected_plan_hash": plan.structured_content["plan_hash"],
                    }
                },
            )
            if not denied.is_error or journal.exists():
                raise ValueError("unqualified installed analysis admitted")
            extra = await client.call_tool(
                "cadence_describe_design",
                {
                    "design_id": "example-amplifier",
                    "path": "/private",
                },
            )
            if not extra.is_error:
                raise ValueError("installed MCP input is not closed")
    return {
        "status": "installed_package_verified",
        "version": expected_version,
        "wheel_import_isolated": True,
        "client_tool_counts": counts,
        "legacy_tools_preserved": len(baseline_names),
        "unqualified_admission": "denied",
        "remote_contact": False,
        "new_simulations": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                verify(args.examples, args.workspace, args.baseline, args.expected_version)
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
