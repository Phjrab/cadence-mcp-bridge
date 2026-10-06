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
            fixture = (
                examples.parent / "design-registry-v8.fictional.json"
                if name == "designs"
                else examples / (name + ".json")
            )
            stream.write(fixture.read_bytes())
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
    if checked["designs"][0]["measurement_contract_count"] != 2:
        raise ValueError("installed v4 measurement contracts were not registered")
    baseline_data = json.loads(baseline.read_bytes())
    baseline_names = set(baseline_data["tools"])
    if (
        len(baseline_names) != 22
        or baseline_data["release_tag"] != "v1.0.0"
        or baseline_data["tag_commit"] != "8a0d44fab90e2095cc39322baef60fc09d741cd6"
    ):
        raise ValueError("legacy snapshot does not identify the published 22-tool baseline")
    counts: dict[str, int] = {}
    for format, filename in (
        ("codex", "client.toml"),
        ("mcp-json", "client.json"),
        ("claude-desktop", "claude.json"),
    ):
        output, journal = workspace / filename, workspace / (format + ".sqlite3")
        cli(
            [
                "client-config",
                *options,
                "--journal",
                str(journal),
                "--sweep-journal",
                str(workspace / "sweeps.sqlite3"),
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
            if len(names) != 78 or not baseline_names.issubset(names):
                raise ValueError("installed MCP tool inventory incompatible")
            counts[format] = len(names)
            runtime = await client.call_tool("cadence_runtime_info_v2")
            if (
                runtime.is_error
                or runtime.structured_content is None
                or runtime.structured_content["bridge_version"] != expected_version
                or runtime.structured_content["designs"]["source"] != "operator_supplied"
                or runtime.structured_content["designs"]["schema_version"] != 8
                or runtime.structured_content["pdks"]["source"] != "operator_supplied"
                or runtime.structured_content["journals"]["analysis"] != "operator_supplied"
                or runtime.structured_content["journals"]["health_assessed"]
                or runtime.structured_content["remote_contact"]
                or journal.exists()
                or str(workspace) in json.dumps(runtime.structured_content)
            ):
                raise ValueError("installed runtime metadata leaked paths or misreported loading")
            specifications = await client.call_tool(
                "cadence_list_specifications", {"design_id": "example-amplifier"}
            )
            if (
                specifications.is_error
                or specifications.structured_content is None
                or specifications.structured_content["target_status"] != "not_selected"
                or len(specifications.structured_content["specifications"]) != 1
            ):
                raise ValueError("installed v7 specifications fabricated a target")
            spec = specifications.structured_content["specifications"][0]
            catalog = await client.call_tool(
                "cadence_measurement_catalog", {"design_id": "example-amplifier"}
            )
            if (
                catalog.is_error
                or catalog.structured_content is None
                or len(catalog.structured_content["analog"]) != 6
                or len(catalog.structured_content["signed_dc_power"]) != 1
                or catalog.structured_content["signed_dc_power"][0]["read_eligible"]
                or catalog.structured_content["specifications"] != [spec]
            ):
                raise ValueError("installed combined measurement catalog differs")
            selection = {"design_id": "example-amplifier", "spec_id": spec["contract"]["spec_id"]}
            described = await client.call_tool(
                "cadence_describe_specification", {"request": selection}
            )
            evaluated = await client.call_tool(
                "cadence_evaluate_specification",
                {"request": {**selection, "expected_contract_sha256": spec["contract_sha256"]}},
            )
            if (
                described.is_error
                or described.structured_content != spec
                or evaluated.is_error
                or evaluated.structured_content is None
                or evaluated.structured_content["status"] != "NOT_EVALUATED"
                or evaluated.structured_content["measurement"] is not None
                or journal.exists()
            ):
                raise ValueError("installed missing target must stay NOT_EVALUATED without IO")
            versioned = await client.call_tool(
                "cadence_evaluate_specification_v2",
                {"request": {**selection, "expected_contract_sha256": spec["contract_sha256"]}},
            )
            if (
                versioned.is_error
                or versioned.structured_content is None
                or versioned.structured_content["contract_version"] != 2
                or versioned.structured_content["status"] != "NOT_EVALUATED"
                or versioned.structured_content["measurement"] is not None
                or journal.exists()
            ):
                raise ValueError("installed versioned evaluation fabricated a target or fact")
            analog = await client.call_tool(
                "cadence_list_analog_measurements", {"design_id": "example-amplifier"}
            )
            if (
                analog.is_error
                or analog.structured_content is None
                or len(analog.structured_content["measurements"]) != 6
                or any(d["read_eligible"] for d in analog.structured_content["measurements"])
            ):
                raise ValueError("installed analog registry qualification changed")
            metric = analog.structured_content["measurements"][0]
            analog_result = await client.call_tool(
                "cadence_analog_measurement_result",
                {
                    "request": {
                        "design_id": "example-amplifier",
                        "measurement_id": metric["measurement_id"],
                        "expected_contract_sha256": metric["contract_sha256"],
                        "operation_id": "00000000-0000-4000-8000-000000000000",
                    }
                },
            )
            if (
                analog_result.is_error
                or analog_result.structured_content is None
                or analog_result.structured_content["status"] != "UNQUALIFIED"
                or analog_result.structured_content["value"] is not None
                or journal.exists()
            ):
                raise ValueError("installed analog fixture fabricated physical measurement")
            power_metric = next(
                d
                for d in analog.structured_content["measurements"]
                if d["definition"]["metric"] == "power"
            )
            power_selection = {
                "design_id": "example-amplifier",
                "measurement_id": power_metric["measurement_id"],
            }
            power = await client.call_tool(
                "cadence_describe_power_measurement", {"request": power_selection}
            )
            if (
                power.is_error
                or power.structured_content is None
                or power.structured_content["read_eligible"]
                or power.structured_content["artifact_availability_assessed"]
            ):
                raise ValueError("installed example acquired a physical power reader")
            denied = await client.call_tool(
                "cadence_power_measurement_result",
                {
                    "request": {
                        **power_selection,
                        "operation_id": "00000000-0000-4000-8000-000000000000",
                        "expected_contract_sha256": power.structured_content["contract_sha256"],
                    }
                },
            )
            if not denied.is_error or journal.exists():
                raise ValueError("unqualified installed power request must deny without journal IO")
            listing = await client.call_tool("cadence_list_designs")
            if listing.is_error or listing.structured_content is None:
                raise ValueError("installed registry inspection failed")
            if listing.structured_content["designs"][0]["design_id"] != "example-amplifier":
                raise ValueError("installed registry settings were not honored")
            measurements = await client.call_tool(
                "cadence_list_measurements", {"design_id": "example-amplifier"}
            )
            if (
                measurements.is_error
                or measurements.structured_content is None
                or len(measurements.structured_content["measurements"]) != 2
            ):
                raise ValueError("installed measurement registry inspection failed")
            measured = measurements.structured_content["measurements"][0]
            denied_measurement = await client.call_tool(
                "cadence_measurement_result",
                {
                    "request": {
                        "design_id": "example-amplifier",
                        "measurement_id": measured["measurement_id"],
                        "operation_id": "00000000-0000-4000-8000-000000000000",
                        "expected_contract_sha256": measured["contract_sha256"],
                    }
                },
            )
            if not denied_measurement.is_error or journal.exists():
                raise ValueError("unqualified installed measurement bypassed admission")
            selection = {
                "design_id": "example-amplifier",
                "analysis_id": "example-dc",
                "variable_id": "bias-n",
                "measurement_ids": ["dc-output"],
            }
            described = await client.call_tool(
                "cadence_describe_design_sweep", {"request": selection}
            )
            if described.is_error or described.structured_content is None:
                raise ValueError("installed registered sweep description failed")
            planned = await client.call_tool(
                "cadence_plan_design_sweep",
                {
                    "request": {
                        **selection,
                        "expected_contract_sha256": described.structured_content["contract_sha256"],
                        "unit": "V",
                        "values": ["0.1"],
                        "fixed": {"bias-p": {"value": "0.2", "unit": "V"}},
                    }
                },
            )
            if (
                planned.is_error
                or planned.structured_content is None
                or planned.structured_content["execution_authorized"]
                or planned.structured_content["locally_admissible"]
                or planned.structured_content["points"][0]["state"] != "NOT_RUN"
                or journal.exists()
            ):
                raise ValueError("unqualified registered sweep gained execution/admission")
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
        "registered_measurements": "v4_list_and_unqualified_read_denial_verified",
        "registered_analog": "v6_six_definitions_unqualified_null_values_no_admission",
        "registered_specifications": "v7_missing_target_NOT_EVALUATED_no_admission",
        "versioned_measurement_bindings": "v8_catalog_v2_evaluation_NOT_EVALUATED_no_admission",
        "registered_sweep": "local_contract_plan_unqualified_NOT_RUN_no_admission",
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
