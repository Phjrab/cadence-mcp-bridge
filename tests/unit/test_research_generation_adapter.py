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
from cadence_mcp_bridge import research_generation_provider as host
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.domain_provisioning import _canonical
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


def test_generation_cli_exports_only_verified_analysis_source(
    generation_packet, monkeypatch, tmp_path, capsys
):
    ctx, registration, evidence, query, calls, clock, _ = generation_packet
    service = host.registered_research_generation(ctx, registration, evidence)
    assert service.submit(query).status == "VERIFIED"
    handoff = service.registration_handoff(query)
    clock[0] = 101
    ctx.lock_path = tmp_path / "lock"

    class Binding(SimpleNamespace):
        model_fields = {"analysis_journal": None, "sweep_journal": None}

    ctx.binding = Binding(**vars(ctx.binding))
    ctx.binding.analysis_journal = tmp_path / "analysis.db"
    ctx.binding.sweep_journal = tmp_path / "sweep.db"
    settings = tmp_path / "settings.json"
    settings.write_bytes(b"fixture operator settings")

    def select(config):
        assert config.runtime_settings_path == settings
        assert config.runtime_context_id == ctx.binding.context_id
        return ctx

    monkeypatch.setattr(adapter, "select_context", select)
    capture = json.loads((evidence / "generation-netlist-stdout.private.json").read_bytes())
    scope = json.loads((evidence / "execution-scope.private.json").read_bytes())
    phase = _canonical(
        {
            "receipt": capture["receipt"],
            "scope_sha256": capture["scope_sha256"],
            "previous_receipt_sha256": capture["previous_receipt_sha256"],
            "protected": {
                "source": "4" * 64,
                "state": "5" * 64,
                "protected": scope["protected_sha256"],
                "retained_jobs_sha256": scope["retained_jobs_sha256"],
                "counter": scope["counter"],
                "ledger_records_sha256": scope["ledger_records_sha256"],
            },
            "trees": {
                "library": handoff.library.tree_sha256,
                "strict_library": "6" * 64,
                "dut": handoff.source_tree_sha256,
                "bench": handoff.bench_tree_sha256,
                "state": "7" * 64,
            },
            "ocean_calls": 1,
            "simulations": 0,
            "reservations": 0,
            "output_sha256": "8" * 64,
            "dut_sha256": handoff.pins.raw_netlist_sha256,
        }
    )
    receipt_sha = hashlib.sha256(phase).hexdigest()
    intent = (evidence / "generation-netlist-intent.private.json").read_bytes()
    complete = _canonical(
        {
            "intent_sha256": hashlib.sha256(intent).hexdigest(),
            "receipt_sha256": receipt_sha,
        }
    )

    def pair(name, raw=None):
        path = tmp_path / name
        if raw is not None:
            path.write_bytes(raw)
        return [str(path), hashlib.sha256(path.read_bytes()).hexdigest()]

    manifest_args = pair("runtime-manifest.json")
    registered = evidence / "registration.json"
    registered.write_bytes(registration)
    base = [
        "operator-research-generation",
        "--registration",
        str(registered),
        hashlib.sha256(registration).hexdigest(),
        "handoff",
        "--request",
        *pair("request.json", query.model_dump_json().encode()),
        "--analysis-source",
        "--settings",
        str(settings),
        "--context",
        ctx.binding.context_id,
        "--phase-record",
        *pair("receipt.json", phase),
        "--completion",
        *pair("complete.json", complete),
        "--runtime-registration",
        *pair("runtime-registration.json"),
    ]
    output = tmp_path / "analysis-source.json"
    request = [*base, "--output", str(output)]
    initial = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert main(request) == 2
    assert main([*request, "--runtime-manifest", manifest_args[0], "0" * 64]) == 2
    assert not output.exists()
    custody = ["--runtime-manifest", *manifest_args]
    assert main([*request, *custody, "--recovery-enrollment", *manifest_args]) == 2
    foreign = pair(
        "foreign-completion.json",
        _canonical(
            {
                "intent_sha256": "0" * 64,
                "receipt_sha256": receipt_sha,
            }
        ),
    )
    wrong_completion = [*request]
    index = wrong_completion.index("--completion") + 1
    wrong_completion[index : index + 2] = foreign
    assert main([*wrong_completion, *custody]) == 2
    assert not output.exists()
    confined = [*base, "--output", str(evidence / "source.json"), *custody]
    assert main(confined) == 2
    capsys.readouterr()
    assert main([*request, *custody]) == 0
    raw = output.read_bytes()
    assert json.loads(capsys.readouterr().out) == {
        "status": "RESEARCH_GENERATION_ANALYSIS_SOURCE_EXPORTED",
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "execution_authorized": False,
    }
    source = host.ResearchGenerationAnalysisSource.model_validate_json(raw)
    assert source.source_cell == handoff.bench_cell
    assert source.source_tree_sha256 == handoff.bench_tree_sha256
    assert source.ade_state_tree_sha256 == "7" * 64
    assert source.native_phase_record_sha256 == receipt_sha
    assert main([*request, *custody]) == 2
    assert output.read_bytes() == raw
    assert all(p.read_bytes() == contents for p, contents in initial.items())
    assert calls == ["save", "reopen", "netlist"]
