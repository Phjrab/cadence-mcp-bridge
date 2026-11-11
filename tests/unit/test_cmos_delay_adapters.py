"""Public adapter checks with local registered context and fake result transport."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import Client
from test_cmos_delay_service import connected as connected
from test_runtime_context import make_settings

import cadence_mcp_bridge.cmos_delay_service as service_module
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.cmos_delay_adapters import DELAY_TOOL, create_cmos_delay_service
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.native_service import NativeOperationService
from cadence_mcp_bridge.runtime_context import OperatorService
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService


def settings(path: Path) -> BridgeConfig:
    return BridgeConfig(runtime_mode="operator", runtime_settings_path=path,
                        runtime_context_id="context-1")


def server(config: BridgeConfig | None) -> Any:
    return create_server(cast(CadenceService, OperatorService(None)), layout_settings=config)


def test_discovery_without_configuration_and_cli_schema(capsys: Any) -> None:
    async def check() -> None:
        async with Client(server(None)) as client:
            tools = (await client.list_tools()).tools
            tool = next(t for t in tools if t.name == DELAY_TOOL)
            assert tool.annotations is not None and tool.annotations.read_only_hint
            assert tool.input_schema["additionalProperties"] is False
            request = tool.input_schema["$defs"]["CmosDelayResultQuery"]
            assert request["additionalProperties"] is False
            assert set(request["properties"]) == {
                "operation_id", "expected_plan_sha256", "definition", "supply_signal",
            }
            assert tool.output_schema is not None
            assert len([t for t in tools if t.name.startswith("cadence_layout_")]) == 6

    asyncio.run(check())
    assert main(["cmos-delay", "schema"]) == 0
    assert json.loads(capsys.readouterr().out)["additionalProperties"] is False


@pytest.mark.parametrize("route", ["mcp", "cli"])
@pytest.mark.parametrize("case", ["success", "auth", "operation", "missing_supply"])
def test_public_registered_result_routes(
    connected: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: Any, route: str, case: str,
) -> None:
    _, native, query, _, _, data = connected
    runtime = make_settings(tmp_path)
    config = settings(runtime)
    # Real adapter factory loads this local runtime and constructs the unchanged
    # CmosDelayService, whose NativeOperationService boundary is faked by connected.
    if case == "auth":
        native.current.side_effect = ConfigurationError("Native operator binding changed")
    elif case == "operation":
        query = query.model_copy(update={"operation_id": "00000000-0000-4000-8000-000000000001"})
    elif case == "missing_supply":
        del data["tran_waveforms"]["vdd"]

    if route == "mcp":
        async def call() -> Any:
            async with Client(server(config)) as client:
                return await client.call_tool(
                    DELAY_TOOL, {"request": query.model_dump(mode="json")},
                )

        response = asyncio.run(call())
        output = response.structured_content
        assert response.is_error == (case != "success")
    else:
        request = tmp_path / "query.json"
        request.write_text(query.model_dump_json(), encoding="utf-8")
        status = main(["cmos-delay", "result", "--request", str(request),
                       "--settings", str(runtime), "--context", "context-1"])
        assert status == (0 if case == "success" else 1)
        output = json.loads(capsys.readouterr().out)
    assert output is not None
    if case == "success":
        assert output["evaluation"]["tphl"]["status"] == "OBSERVED_SAMPLED_DELAY"
        assert output["evaluation"]["evidence"]["operation_id"] == query.operation_id
        assert output["vm_logic_physical_qualification"] == "NOT_ASSESSED"
        assert output["new_simulations"] == output["new_extractions"] == 0
        assert output["new_reservations"] == 0
        assert "tran_waveforms" not in json.dumps(output)
    elif case == "operation":
        assert output["error"]["details"]["reason"] == "cmos_delay_operation_identity_mismatch"
    elif case == "missing_supply":
        assert output["error"]["details"]["reason"] == "missing_supply_evidence"
    native.lifecycle.submit.assert_not_called()
    native.provider.accept.assert_not_called()
    native.provider.authorize.assert_not_called()


def test_real_factory_requires_native_registration(tmp_path: Path) -> None:
    # No injected service/native factory: the actual production constructor must
    # reject this otherwise valid local runtime that lacks native bindings/grant.
    with pytest.raises(ConfigurationError, match="native provider and operator grant"):
        create_cmos_delay_service(settings(make_settings(tmp_path)))
    with pytest.raises(ConfigurationError, match="explicit operator context"):
        create_cmos_delay_service(None)


@pytest.mark.parametrize("bad", ["extra", "waveform", "provider", "no_request"])
def test_mcp_closed_envelope(connected: Any, bad: str) -> None:
    _, native, query, *_ = connected
    envelope = {"request": query.model_dump(mode="json")}
    if bad == "extra":
        envelope["command"] = "unsupported"
    elif bad == "no_request":
        envelope = {}
    else:
        envelope["request"][bad] = {}

    async def call() -> None:
        async with Client(server(None)) as client:
            response = await client.call_tool(DELAY_TOOL, envelope)
            assert response.is_error

    asyncio.run(call())
    native.provider.analog_result.assert_not_called()


@pytest.mark.parametrize("route", ["mcp", "cli"])
def test_setup_errors_use_public_envelope(
    connected: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: Any, route: str,
) -> None:
    _, _, query, *_ = connected
    monkeypatch.setattr(service_module, "NativeOperationService", NativeOperationService)
    runtime = make_settings(tmp_path)
    if route == "cli":
        request = tmp_path / "query.json"
        request.write_text(query.model_dump_json(), encoding="utf-8")
        assert main(["cmos-delay", "result", "--request", str(request),
                     "--settings", str(runtime), "--context", "context-1"]) == 1
        output = json.loads(capsys.readouterr().out)
    else:
        async def call() -> Any:
            async with Client(server(settings(runtime))) as client:
                return await client.call_tool(
                    DELAY_TOOL, {"request": query.model_dump(mode="json")},
                )

        response = asyncio.run(call())
        assert response.is_error
        output = response.structured_content
    assert output["error"]["code"] == "invalid_configuration"
