from __future__ import annotations

import os
from typing import Any, cast

import pytest
from mcp import Client

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

pytestmark = pytest.mark.skipif(
    os.environ.get("CADENCE_MCP_RUN_INTEGRATION") != "1",
    reason="set CADENCE_MCP_RUN_INTEGRATION=1 to contact cadence-vm",
)


@pytest.mark.asyncio
async def test_real_read_only_discovery_through_mcp() -> None:
    server = create_server(CadenceService(OpenSshBackend(BridgeConfig())))

    async with Client(server) as client:
        libraries = await client.call_tool("cadence_list_libraries")
        cells = await client.call_tool("cadence_list_cells", {"library": "MyFirstDesign"})
        cellview = await client.call_tool(
            "cadence_inspect_cellview",
            {"library": "MyFirstDesign", "cell": "NOT_gate", "view": "schematic"},
        )
        denied = await client.call_tool("cadence_list_cells", {"library": "gpdk090"})

    library_payload = cast(dict[str, Any], libraries.structured_content)
    cell_payload = cast(dict[str, Any], cells.structured_content)
    view_payload = cast(dict[str, Any], cellview.structured_content)
    denied_payload = cast(dict[str, Any], denied.structured_content)

    assert library_payload["allowlist_enforced"] is True
    assert library_payload["proprietary_content_included"] is False
    assert cell_payload["cells"] == ["NOT_gate"]
    assert view_payload["exists"] is True
    assert denied.is_error is True
    assert denied_payload["error"]["code"] == "invalid_input"
    serialized = " ".join(
        str(payload) for payload in (library_payload, cell_payload, view_payload)
    ).lower()
    for forbidden in ("/home/", "sch.oa", "symbol.oa", "cds.lib", "file_bytes"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_real_fixed_ade_profile_introspection_through_mcp() -> None:
    server = create_server(CadenceService(OpenSshBackend(BridgeConfig())))

    async with Client(server) as client:
        result = await client.call_tool(
            "cadence_inspect_ade_profile",
            {"profile_id": "actual-differential-amplifier-tb2-transient"},
        )
        denied = await client.call_tool(
            "cadence_inspect_ade_profile",
            {"profile_id": "fixture-rc-transient"},
        )

    payload = cast(dict[str, Any], result.structured_content)
    assert result.is_error is False
    assert payload["status"] in {"ok", "profile_drift"}
    assert payload["profile_id"] == "actual-differential-amplifier-tb2-transient"
    assert payload["read_only"] is True
    assert payload["paths_included"] is False
    assert payload["raw_content_included"] is False
    assert payload["fingerprints"]["all_unchanged"] is True
    assert payload["locks"]["blocking"] is False
    assert payload["source_structural_fingerprint"] | {
        "instances": 35,
        "nets": 14,
        "terminals": 8,
    } == payload["source_structural_fingerprint"]
    if payload["status"] == "profile_drift":
        assert payload["drift_codes"]
        assert payload["profile_contract_match"] is False
    serialized = str(payload).lower()
    for forbidden in (
        "/home/",
        "sch.oa",
        "cds.lib",
        "model_file",
        "state_path",
        "source_content",
    ):
        assert forbidden not in serialized
    assert denied.is_error is True
