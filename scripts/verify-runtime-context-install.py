"""Isolated installed-package operator stdio acceptance; synthetic, no Cadence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from cadence_mcp_bridge.runtime_context import load_runtime, resource_lock


async def verify(workspace: Path, examples: Path) -> dict[str, object]:
    workspace.mkdir(parents=True, exist_ok=False)
    bindings = []
    for number in (1, 2):
        environment = json.loads((examples / "environment.json").read_bytes())
        environment["environment_id"] = f"installed-lab-{number}"
        environment["ssh_alias"] = f"installed-alias-{number}"
        environment["host"]["hostname"] = "same-synthetic-host"
        design = json.loads((examples / "designs.json").read_bytes())["designs"][0]
        design.update(
            design_id=f"installed-design-{number}", environment_id=environment["environment_id"]
        )
        design["binding"]["cell"] = f"InstalledTest{number}"
        pdk = json.loads((examples / "pdks.json").read_bytes())
        pdk["adapters"][0]["environment_ids"] = [environment["environment_id"]]
        paths = [workspace / f"{name}-{number}.json" for name in ("environment", "design", "pdk")]
        for path, data in zip(
            paths, (environment, {"schema_version": 1, "designs": [design]}, pdk), strict=True
        ):
            path.write_text(json.dumps(data), encoding="utf-8")
        bindings.append(
            {
                "context_id": f"installed-context-{number}",
                "environment_profile": str(paths[0]),
                "environment_sha256": hashlib.sha256(paths[0].read_bytes()).hexdigest(),
                "design_registry": str(paths[1]),
                "design_sha256": hashlib.sha256(paths[1].read_bytes()).hexdigest(),
                "pdk_registry": str(paths[2]),
                "pdk_sha256": hashlib.sha256(paths[2].read_bytes()).hexdigest(),
                "runner_sha256": "b" * 64,
                "authority_ref": "synthetic-unverified",
                "ledger_ref": "preserve-existing-ledger",
                "analysis_journal": str(workspace / f"analysis-{number}.sqlite3"),
                "sweep_journal": str(workspace / f"sweep-{number}.sqlite3"),
            }
        )
    settings = workspace / "runtime.json"
    settings.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "resource_state_root": str(workspace),
                "contexts": bindings,
            }
        ),
        encoding="utf-8",
    )
    contexts = load_runtime(settings)
    assert contexts[0].lock_path == contexts[1].lock_path
    with resource_lock(contexts[0]):
        pass
    with resource_lock(contexts[1]):
        pass
    environment = {k: v for k, v in os.environ.items() if not k.startswith("CADENCE_MCP_")}
    cli = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "cadence_mcp_bridge",
            "runtime",
            "resolve",
            "--settings",
            str(settings),
            "--context",
            "installed-context-2",
            "--design-id",
            "installed-design-2",
        ],
        capture_output=True,
        timeout=20,
        cwd=workspace,
        env=environment,
        check=True,
    )
    observation = json.loads(cli.stdout)
    assert observation["context_id"] == "installed-context-2"
    assert observation["status"] == "RUNNER_SETUP_REQUIRED"
    assert observation["execution_authorized"] is False
    assert observation["build"]["commit_sha"] is None
    assert str(workspace) not in cli.stdout.decode("utf-8")
    schemas = None
    for number in (1, 2, 1):
        env = {
            **environment,
            "CADENCE_MCP_RUNTIME_SETTINGS_PATH": str(settings),
            "CADENCE_MCP_RUNTIME_CONTEXT_ID": f"installed-context-{number}",
        }
        params = StdioServerParameters(
            command=sys.executable,
            args=["-I", "-m", "cadence_mcp_bridge", "serve-operator"],
            env=env,
            cwd=str(workspace),
        )
        async with Client(params) as client:
            current = [
                t.model_dump(mode="json", by_alias=True) for t in (await client.list_tools()).tools
            ]
            assert len(current) == 85
            if schemas is None:
                schemas = current
            assert current == schemas
            listing = await client.call_tool("cadence_list_designs")
            assert not listing.is_error and listing.structured_content is not None
            assert (
                listing.structured_content["designs"][0]["design_id"]
                == f"installed-design-{number}"
            )
            foreign = await client.call_tool(
                "cadence_describe_design",
                {
                    "design_id": f"installed-design-{3 - number}",
                },
            )
            assert foreign.is_error
            denied = await client.call_tool("cadence_submit_smoke")
            assert denied.is_error and "RUNNER_SETUP_REQUIRED" in str(denied.content)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-I", "-m", "cadence_mcp_bridge"],
        env=environment,
        cwd=str(workspace),
    )
    async with Client(params) as client:
        denied = await client.call_tool("cadence_health")
        assert denied.is_error and "SETUP_REQUIRED" in str(denied.content)
        listing = await client.call_tool("cadence_list_designs")
        assert listing.structured_content is not None and not listing.structured_content["designs"]
    assert not list(workspace.glob("*.sqlite3"))
    return {
        "status": "PASS",
        "evidence": "INSTALLED_PACKAGE_SDK_PROTOCOL_SYNTHETIC",
        "operator_contexts": 2,
        "startup_sequence": [1, 2, 1],
        "mcp_schemas": 85,
        "default_setup_required": True,
        "new_simulations": 0,
        "journals_created": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--examples", type=Path, required=True)
    arguments = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(verify(arguments.workspace.resolve(), arguments.examples.resolve())),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
