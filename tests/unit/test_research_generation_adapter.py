"""Registered generation wire checks over the real host sequencer and a fake worker."""

import hashlib
import json
from types import SimpleNamespace

import pytest
import test_research_generation_provider
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from test_research_generation_service import _fixture

from cadence_mcp_bridge import research_generation_adapter as adapter
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.research_circuit import MosBlockRegistrationHandoff
from cadence_mcp_bridge.research_generation_adapter import register_research_generation_tools
from cadence_mcp_bridge.research_generation_service import RegisteredResearchGeneration
from cadence_mcp_bridge.server import create_default_server

generation_packet = test_research_generation_provider.packet


@pytest.mark.asyncio
async def test_generation_tools_are_fixed_and_replay_without_new_claim():
    service, query, worker = _fixture()
    server = MCPServer(name="registered-generation-fixture")
    register_research_generation_tools(server, service._binding, service)
    names = {
        "cadence_plan_registered_research_generation",
        "cadence_apply_registered_research_generation",
        "cadence_registered_research_generation_status",
        "cadence_registered_research_generation_handoff",
    }
    assert {tool.name for tool in await server.list_tools()} == names
    args = {"request": query.model_dump(mode="json")}
    extra = {"request": {**args["request"], "path": "caller"}}
    wrong = {"request": {**args["request"], "expected_binding_sha256": "0" * 64}}
    apply = "cadence_apply_registered_research_generation"
    observe = "cadence_registered_research_generation_handoff"
    with pytest.raises(ToolError):
        await server.call_tool(apply, extra)
    with pytest.raises(ToolError, match="registered_research_generation_rejected"):
        await server.call_tool(apply, wrong)
    with pytest.raises(ToolError, match="registered_research_generation_rejected"):
        await server.call_tool(observe, args)
    assert worker.claims == 0 and worker.phases == []
    plan = await server.call_tool("cadence_plan_registered_research_generation", args)
    assert plan.structured_content["identity"] == args["request"]
    assert plan.structured_content["execution_authorized"] is False
    original = await server.call_tool(apply, args)
    assert original.structured_content["status"] == "VERIFIED"
    assert original.structured_content["replayed"] is False
    restarted = RegisteredResearchGeneration(
        service._binding,
        service._plan,
        service._bench,
        service._conditions,
        service._cdf_frames,
        worker,
        expected_binding_sha256=query.expected_binding_sha256,
    )
    next_server = MCPServer(name="registered-generation-restart-fixture")
    register_research_generation_tools(next_server, restarted._binding, restarted)
    for name in (apply, "cadence_registered_research_generation_status"):
        replay = await next_server.call_tool(name, args)
        assert replay.structured_content == {**original.structured_content, "replayed": True}
    handoff = await next_server.call_tool(observe, args)
    assert (
        handoff.structured_content["handoff_sha256"]
        == original.structured_content["handoff_sha256"]
    )
    assert "source_cell" not in handoff.structured_content
    assert "bench_cell" not in handoff.structured_content
    assert handoff.structured_content["execution_authorized"] is False
    assert worker.claims == 1 and worker.phases == ["save", "reopen", "netlist"]


@pytest.mark.asyncio
async def test_generation_stdio_profile_and_cli_use_real_provider(
    generation_packet,
    monkeypatch,
    tmp_path,
    capsys,
):
    ctx, registration, evidence, query, calls, clock, _ = generation_packet
    monkeypatch.setenv("CADENCE_MCP_RUNTIME_SETTINGS_PATH", str(tmp_path / "runtime-settings.json"))
    ctx.lock_path = tmp_path / "lock"

    class Binding(SimpleNamespace):
        model_fields = {"analysis_journal": None, "sweep_journal": None}

    ctx.binding = Binding(
        context_id=ctx.binding.context_id,
        runner_sha256=ctx.binding.runner_sha256,
        analysis_journal=tmp_path / "analysis.db",
        sweep_journal=tmp_path / "sweep.db",
    )
    monkeypatch.setattr(adapter, "select_context", lambda config: ctx)
    registration_file = evidence / "registration.json"
    registration_file.write_bytes(registration)
    pin = hashlib.sha256(registration).hexdigest()
    request_file = tmp_path / "request.json"
    request_raw = query.model_dump_json().encode()
    request_file.write_bytes(request_raw)
    request_args = ["--request", str(request_file), hashlib.sha256(request_raw).hexdigest()]
    cli = ["operator-research-generation", "--registration", str(registration_file), pin]

    with pytest.raises(ConfigurationError):
        create_default_server(
            operator_mode=True, registered_research_generation=(registration_file, "0" * 64)
        )
    with pytest.raises(ConfigurationError):
        create_default_server(
            operator_mode=True,
            registered_research_generation=(registration_file, pin),
            fixed_amp_pm0=True,
        )

    server = create_default_server(
        operator_mode=True, registered_research_generation=(registration_file, pin)
    )
    result = await server.call_tool(
        "cadence_registered_research_generation_status",
        {"request": query.model_dump(mode="json")},
    )
    assert result.structured_content["status"] == "NOT_SUBMITTED"
    assert calls == []
    assert main([*cli, "apply", *request_args]) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["status"] == "VERIFIED" and not applied["replayed"]
    assert calls == ["save", "reopen", "netlist"]

    clock[0] = 101
    assert main([*cli, "apply", *request_args]) == 0
    assert json.loads(capsys.readouterr().out) == {**applied, "replayed": True}
    denied = ["handoff", *request_args, "--output", str(ctx.binding.analysis_journal)]
    assert main([*cli, *denied]) == 2
    assert not ctx.binding.analysis_journal.exists()
    capsys.readouterr()
    output = tmp_path / "handoff.json"
    export = ["handoff", *request_args, "--output", str(output)]
    assert main([*cli, *export]) == 0
    exported = json.loads(capsys.readouterr().out)
    raw = output.read_bytes()
    assert exported["file_sha256"] == hashlib.sha256(raw).hexdigest()
    saved = MosBlockRegistrationHandoff.model_validate_json(raw)
    assert saved.handoff_sha256 == exported["handoff_sha256"] == applied["handoff_sha256"]
    assert main([*cli, *export]) == 2
    assert output.read_bytes() == raw
    assert registration_file.read_bytes() == registration
    assert calls == ["save", "reopen", "netlist"]
