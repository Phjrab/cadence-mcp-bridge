"""One-shot operator verifier that exercises the public MCP write-validation tools."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, cast

from mcp import Client

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

CONFIRMATION = "APPROVE_MCP_WRITE_VALIDATED_V1"


async def verify() -> dict[str, Any]:
    server = create_server(CadenceService(OpenSshBackend(BridgeConfig())))
    async with Client(server) as client:
        plan_result = await client.call_tool("cadence_design_write_plan")
        if plan_result.is_error:
            raise RuntimeError("design write plan failed")
        plan = cast(dict[str, Any], plan_result.structured_content)
        if not plan.get("ready") or plan.get("confirmation") != CONFIRMATION:
            raise RuntimeError("design write plan is not ready or does not match confirmation")
        validation_result = await client.call_tool(
            "cadence_execute_design_write_validation",
            {"confirmation": CONFIRMATION},
        )
        if validation_result.is_error:
            raise RuntimeError("design write validation failed")
        return cast(dict[str, Any], validation_result.structured_content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the one approved design write validation.")
    parser.add_argument("--confirmation", choices=(CONFIRMATION,), required=True)
    arguments = parser.parse_args()
    if arguments.confirmation != CONFIRMATION:
        return 64
    result = asyncio.run(verify())
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
