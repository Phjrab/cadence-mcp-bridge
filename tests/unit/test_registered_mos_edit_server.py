"""Wire checks for the dedicated registered MOS edit profile."""

import json
from hashlib import sha256
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_registered_mos_edit import _service

from cadence_mcp_bridge import registered_mos_edit_server as adapter
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.server import create_default_server


@pytest.mark.asyncio
async def test_mos_profile_pins_context_and_replays_c6_result(monkeypatch):
    service, worker, publication = _service(primary="w", joint=True)
    worker.publication = publication
    context = SimpleNamespace(context_sha256="a" * 64)
    monkeypatch.setattr(adapter, "select_context", lambda _: context)

    def not_registered(_):
        raise OperationRejected("registered_mos_edit_not_registered")

    monkeypatch.setattr(adapter, "registered_mos_edit", not_registered)
    with pytest.raises(ConfigurationError):
        create_default_server(operator_mode=True, registered_mos_edit=True)
    with pytest.raises(ConfigurationError):
        create_default_server(operator_mode=True, registered_mos_edit=True, fixed_amp_pm0=True)

    monkeypatch.setattr(adapter, "registered_mos_edit", lambda _: service)
    server = create_default_server(operator_mode=True, registered_mos_edit=True)
    plan = "cadence_plan_registered_mos_edit"
    apply = "cadence_apply_registered_mos_edit"
    lookup = "cadence_lookup_registered_mos_edit"
    assert {tool.name for tool in await server.list_tools()} == {plan, apply, lookup}
    request = service.identity.model_dump(mode="json")
    args = {"request": request}
    planned = await server.call_tool(plan, args)
    assert planned.structured_content["plan"] == service.plan.model_dump(mode="json")
    assert planned.structured_content["execution_authorized"] is False
    assert (await server.call_tool(lookup, args)).structured_content["outcome"] == "NOT_FOUND"

    wrong = {"request": {**request, "expected_scope_sha256": "0" * 64}}
    with pytest.raises(ToolError, match="registered_mos_edit_rejected"):
        await server.call_tool(apply, wrong)
    with pytest.raises(ToolError):
        await server.call_tool(apply, {"request": {**request, "path": "caller"}})
    context.context_sha256 = "b" * 64
    with pytest.raises(ToolError, match="registered_mos_edit_rejected"):
        await server.call_tool(apply, args)
    assert worker.dispatches == 0

    context.context_sha256 = "a" * 64
    applied = (await server.call_tool(apply, args)).structured_content
    assert applied["outcome"] == "VERIFIED" and not applied["replayed"]
    assert applied["analysis_execution_authorized"] is False
    restarted = create_default_server(operator_mode=True, registered_mos_edit=True)
    for name in (apply, lookup):
        result = (await restarted.call_tool(name, args)).structured_content
        assert result == {**applied, "replayed": True, "dispatched_this_call": False}
    assert worker.dispatches == 1


def test_registered_mos_cli_uses_the_same_closed_identity_and_retained_result(
    monkeypatch,
    tmp_path,
    capsys,
):
    service, worker, publication = _service()
    worker.publication = publication
    settings = tmp_path / "settings.json"
    settings.write_bytes(b"{}")
    context = SimpleNamespace(context_sha256="a" * 64)

    def selected(config):
        assert config.runtime_settings_path == settings
        assert config.runtime_context_id == "owned-mos"
        return context

    monkeypatch.setattr(adapter, "select_context", selected)
    monkeypatch.setattr(adapter, "registered_mos_edit", lambda _: service)
    request_path = tmp_path / "request.json"
    raw = service.identity.model_dump_json().encode()
    request_path.write_bytes(raw)
    base = ["operator-mos-edit", "--settings", str(settings), "--context", "owned-mos"]

    def invoke(action, digest):
        status = main([*base, action, "--request", str(request_path), digest])
        return status, json.loads(capsys.readouterr().out)

    pin = sha256(raw).hexdigest()
    assert invoke("apply", "0" * 64)[0] == 2
    foreign = service.identity.model_copy(update={"expected_scope_sha256": "0" * 64})
    foreign_raw = foreign.model_dump_json().encode()
    foreign_path = tmp_path / "foreign.json"
    foreign_path.write_bytes(foreign_raw)
    assert (
        main(
            [
                *base,
                "apply",
                "--request",
                str(foreign_path),
                sha256(foreign_raw).hexdigest(),
            ]
        )
        == 2
    )
    capsys.readouterr()
    assert worker.dispatches == 0
    status, planned = invoke("plan", pin)
    assert status == 0 and planned == adapter._plan(service).model_dump(mode="json")
    assert invoke("lookup", pin)[1]["outcome"] == "NOT_FOUND"
    status, applied = invoke("apply", pin)
    assert status == 0 and applied["outcome"] == "VERIFIED"
    for action in ("lookup", "apply"):
        assert invoke(action, pin) == (
            0,
            {**applied, "replayed": True, "dispatched_this_call": False},
        )
    assert worker.dispatches == 1
    assert request_path.read_bytes() == raw and settings.read_bytes() == b"{}"
