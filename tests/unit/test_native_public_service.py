"""Configured MCP lifecycle with a synthetic wire; no VM or approval creation."""

import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_authenticated_provider import accounting, observation
from test_cmos_delay_service import connected, no_dispatch
from test_generic_measurements import operator, operator_base

from cadence_mcp_bridge import authenticated_provider as wire
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.native_service import NativeOperationService
from cadence_mcp_bridge.runtime_context import create_operator_service, load_runtime
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService

__all__ = ["connected", "operator", "operator_base"]
NAMES = {
    "cadence_verify_change_readback",
    "cadence_validate_research_circuit",
    "cadence_plan_research_mos_block",
    "cadence_verify_research_mos_block",
    "cadence_plan_registered_mos_change",
    "cadence_research_transient_result",
    "cadence_research_ac_gain_result",
    "cadence_research_supply_power_result",
    "cadence_plan_operation",
    "cadence_submit_operation",
    "cadence_operation_status",
    "cadence_operation_result",
    "cadence_cancel_pending_operation",
}


@pytest.fixture
def configured(operator, tmp_path, monkeypatch):
    context, grant, request, settings = operator
    provider_path, grant_path = tmp_path / "provider.json", tmp_path / "grant.json"
    provider_path.write_bytes(
        wire.NativeProviderBinding(
            schema_version=1,
            identity_manifest_sha256="a" * 64,
            runtime_manifest_sha256=context.binding.runner_sha256,
        )
        .model_dump_json()
        .encode()
    )
    grant_path.write_bytes(grant.model_dump_json().encode())
    runtime = json.loads(settings.read_bytes())
    runtime["contexts"][0].update(
        native_provider_binding=str(provider_path),
        native_provider_sha256=hashlib.sha256(provider_path.read_bytes()).hexdigest(),
        operator_grant=str(grant_path),
        operator_grant_sha256=hashlib.sha256(grant_path.read_bytes()).hexdigest(),
    )
    settings.write_text(json.dumps(runtime))
    config = BridgeConfig(
        runtime_mode="operator",
        runtime_settings_path=settings,
        runtime_context_id=context.binding.context_id,
    )
    monkeypatch.setattr(wire, "_ssh", lambda _: ["fixed-synthetic-ssh", "python", "-B"])
    service = create_operator_service(config, factory=lambda _: object())
    assert not context.binding.analysis_journal.exists()
    return create_server(cast(CadenceService, service)), service, request, settings, grant_path


@pytest.mark.asyncio
async def test_operator_only_conditional_schema_and_no_server_start_side_effects(configured):
    server, service, request, settings, grant_path = configured
    tools = {t.name: t for t in await server.list_tools()}
    assert len(tools) == 111 and set(tools) >= NAMES
    snapshot = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "docs/contracts/MCP_NATIVE_OPERATIONS_V1_SNAPSHOT.json"
        ).read_bytes()
    )
    assert {name: tools[name].model_dump(mode="json", by_alias=True) for name in NAMES} == snapshot[
        "tools"
    ]
    for name in NAMES:
        schema = tools[name].input_schema
        assert schema["additionalProperties"] is False
        assert not set(schema["properties"]) & {"path", "grant", "command", "host", "runner"}
    assert service.context is not None
    assert not service.context.binding.analysis_journal.exists()
    assert not service.context.lock_path.exists()
    data = json.loads(settings.read_bytes())
    for key in (
        "native_provider_binding",
        "native_provider_sha256",
        "operator_grant",
        "operator_grant_sha256",
    ):
        del data["contexts"][0][key]
    settings.write_text(json.dumps(data))
    old = create_operator_service(
        BridgeConfig(
            runtime_mode="operator",
            runtime_settings_path=settings,
            runtime_context_id=service.context.binding.context_id,
        ),
        factory=lambda _: object(),
    )
    assert old.native_operations is None
    assert len(await create_server(cast(CadenceService, old)).list_tools()) == 92


@pytest.mark.asyncio
async def test_change_readback_tool_uses_closed_local_evidence(configured, monkeypatch):
    from test_parameter_changes import _bias, _row

    from cadence_mcp_bridge.parameter_changes import verify_change_readback

    server, service, *_ = configured
    monkeypatch.setattr(wire, "run_fixed", lambda *a, **kw: pytest.fail("unexpected provider call"))
    plan = _bias()
    stages = {stage: _row(plan, stage) for stage in ("baseline", "reopened", "netlist")}
    request = {
        "plan": plan.model_dump(mode="json"),
        "expected_plan_sha256": plan.plan_sha256,
        **{stage: row.model_dump(mode="json") for stage, row in stages.items()},
    }
    name = "cadence_verify_change_readback"
    expected = verify_change_readback(plan, **stages).model_dump(mode="json")
    for _ in range(2):
        result = await server.call_tool(name, {"request": request})
        assert not result.is_error and result.structured_content == expected
    assert expected["status"] == "MATCHED" and not expected["execution_authorized"]
    for bad in (
        {**request, "expected_plan_sha256": "0" * 64},
        {**request, "path": "forbidden"},
    ):
        with pytest.raises(ToolError):
            await server.call_tool(name, {"request": bad})
    assert not service.context.binding.analysis_journal.exists()
    assert not service.context.lock_path.exists()


@pytest.mark.asyncio
async def test_research_circuit_mcp_is_local_and_rejects_missing_bulk(configured, monkeypatch):
    from test_m2_inverter import fixture
    from test_research_circuit import payload

    from cadence_mcp_bridge.research_adapters import ResearchCircuitValidation
    from cadence_mcp_bridge.variable_contracts import canonical_digest

    server, service, *_ = configured
    monkeypatch.setattr(wire, "run_fixed", lambda *a, **kw: pytest.fail("unexpected provider call"))
    plan, _ = fixture()
    definition = json.loads(json.dumps(payload(plan)))
    name = "cadence_validate_research_circuit"
    result = await server.call_tool(name, {"request": {"definition": definition}})
    assert not result.is_error
    validated = ResearchCircuitValidation.model_validate_json(json.dumps(result.structured_content))
    assert validated.definition_sha256 == canonical_digest(validated.definition)
    assert not validated.execution_authorized and not validated.remote_contact
    definition["circuits"][0]["instances"][0]["links"].pop()
    with pytest.raises(ToolError):
        await server.call_tool(name, {"request": {"definition": definition}})
    assert not service.context.binding.analysis_journal.exists()
    assert not service.context.lock_path.exists()


@pytest.mark.asyncio
async def test_research_mos_block_mcp_plans_and_checks_pinned_projections(configured, monkeypatch):
    from test_m2_inverter import fixture
    from test_research_circuit import mos_block_fixture, payload

    from cadence_mcp_bridge.research_circuit import ResearchCircuit
    from cadence_mcp_bridge.variable_contracts import canonical_digest

    server, service, *_ = configured
    monkeypatch.setattr(wire, "run_fixed", lambda *a, **kw: pytest.fail("unexpected provider call"))
    inverter, _ = fixture()
    data = payload(inverter)
    for instance, model in zip(data["circuits"][0]["instances"], ("test_n", "test_p"), strict=True):
        geometry = instance["geometry"]
        instance["spectre"] = {
            "model": model, "width": geometry["fw"], "length": geometry["length"],
            "multiplier": geometry["multiplier"], "source": geometry["source"],
        }
    definition = ResearchCircuit.model_validate_json(json.dumps(data))
    requested = {
        "definition": definition.model_dump(mode="json"),
        "expected_binding": definition.binding.model_dump(mode="json"),
        "expected_definition_sha256": canonical_digest(definition),
        "output_library": "OwnedBlock",
    }
    name = "cadence_plan_research_mos_block"
    planned = await server.call_tool(name, {"request": requested})
    assert not planned.is_error and planned.structured_content is not None
    assert planned.structured_content["plan"]["root"] == definition.dut
    assert planned.structured_content["execution_authorized"] is False
    with pytest.raises(ToolError):
        await server.call_tool(name, {"request": {**requested, "output_library": "/tmp/o"}})

    plan, evidence = mos_block_fixture()
    proof = {
        "plan": plan.model_dump(mode="json"),
        "evidence": evidence.model_dump(mode="json"),
        "expected_plan_sha256": canonical_digest(plan),
        "expected_reopened_tree_sha256": evidence.reopened_tree_sha256,
        "expected_reopen_artifact_sha256": evidence.reopen_artifact_sha256,
        "expected_netlist_artifact_sha256": evidence.netlist_artifact_sha256,
    }
    name = "cadence_verify_research_mos_block"
    verified = await server.call_tool(name, {"request": proof})
    assert not verified.is_error and verified.structured_content is not None
    assert verified.structured_content["status"] == "MATCHED"
    assert verified.structured_content["provenance"] == "LOCAL_EVIDENCE_COMPARISON"
    with pytest.raises(ToolError):
        await server.call_tool(name, {"request": {**proof, "expected_plan_sha256": "0" * 64}})
    assert not service.context.binding.analysis_journal.exists()
    assert not service.context.lock_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("with_current", [False, True])
async def test_research_transient_mcp_repeat_reads_only_retained_result(connected, with_current):
    from test_research_transient import _supplies

    from cadence_mcp_bridge.native_server import register_native_tools
    from cadence_mcp_bridge.server import DesignContractServer
    from cadence_mcp_bridge.variable_contracts import canonical_digest

    _, native, query, record, _, data = connected
    store = native.lifecycle.store = Mock()
    store.connection.side_effect = lambda **_: nullcontext()
    store._read_operation.return_value = record
    digest = None
    if with_current:
        waves = data["tran_waveforms"]
        supply = _supplies({
            key: [{"time_s": point["time_s"], "value_a": amps} for point in waves["vin"]]
            for key, amps in (("supply", -0.002), ("absorb", 0.001))
        })
        waves["pos"] = waves["vdd"]
        waves["neg"] = [{"time_s": point["time_s"], "value_v": 0} for point in waves["vin"]]
        rail = next(row for row in data["transient"] if row["logical_id"] == "vdd")
        data["transient"].extend([
            {**rail, "logical_id": "pos"},
            {**rail, "logical_id": "neg", "minimum": 0, "maximum": 0,
             "first": 0, "last": 0, "time_weighted_mean": 0},
        ])
        data["tran_supply_evidence"] = supply.model_dump(mode="json")
        digest = canonical_digest(supply)
    server = DesignContractServer("research-fixture")
    register_native_tools(server, native)
    request = {
        "operation_id": query.operation_id,
        "expected_plan_sha256": query.expected_plan_sha256,
        "window": {"start_s": 0, "stop_s": 2, "maximum_gap_s": 0.025},
        "signals": ["vin", "vout"],
        "maximum_display_points": 2,
    }
    name = "cadence_research_transient_result"
    for _ in range(2):
        response = await server.call_tool(name, {"request": request})
        result = response.structured_content
        assert not response.is_error and result is not None
        assert result["source"]["operation_id"] == query.operation_id
        assert len(result["signals"]["vout"]["points"]) == 2
        power = result["measurements"]["average_supply_power"]
        if with_current:
            assert power["value"] == pytest.approx(0.002)
        else:
            assert power["reason"] == "registered_tran_supply_current_unavailable"
            assert power["value"] is None
        assert result["tran_supply_evidence_sha256"] == digest
        assert [result[key] for key in (
            "new_simulations", "new_extractions", "new_reservations",
        )] == [0, 0, 0]
    with pytest.raises(ToolError):
        await server.call_tool(name, {"request": {**request, "waveforms": {}}})
    assert native.provider.analog_result.await_count == 2
    store.connection.assert_called_with(create=False, read_only=True)
    native.lifecycle.reconcile.assert_not_called()
    no_dispatch(native)


@pytest.mark.asyncio
async def test_research_supply_mcp_uses_signed_retained_dc(configured):
    from test_result_reports import inventory, seed

    server, *_ = configured
    native, record, source = seed(configured)
    source["sources"] = [
        {"source_id": "rail", "role": "supply", "delivered_w": 4e-6},
        {"source_id": "return", "role": "supply", "delivered_w": -1e-6},
    ]
    folder = native.context.binding.analysis_journal.parent
    before = inventory(folder)
    request = {
        "operation_id": record.operation_id,
        "expected_plan_sha256": record.plan.plan_sha256,
        "supply_ids": ["rail", "return"],
    }
    name = "cadence_research_supply_power_result"
    response = await server.call_tool(name, {"request": request})
    assert not response.is_error and response.structured_content is not None
    assert response.structured_content["measurement"]["value"] == pytest.approx(3e-6)
    with pytest.raises(ToolError):
        await server.call_tool(name, {"request": {**request, "supply_ids": ["rail", "rail"]}})
    assert native.provider.report_result.await_count == 1
    assert inventory(folder) == before


@pytest.mark.asyncio
async def test_research_ac_mcp_uses_registered_complex_transfer(configured, monkeypatch):
    from test_research_measurements import sample
    from test_result_reports import seed

    from cadence_mcp_bridge import research_measurements
    from cadence_mcp_bridge.result_reports import make_report

    server, *_ = configured
    native, record, source = seed(configured)
    plan = record.plan.model_copy(update={"analysis": "ac"})
    record = record.model_copy(update={"plan": plan})
    source.update(analysis="ac", plan_sha256=plan.plan_sha256)
    source["report_conditions"].update(
        analysis_inputs={"analysis": "ac", "start_hz": "1", "stop_hz": "100",
                         "points_per_decade": 1},
        transfer={"positive_input": "input", "negative_input": None,
                  "positive_output": "output", "negative_output": None,
                  "gain_frequencies_hz": ["1"]},
    )
    source["transfer"] = [sample(1, 0, 2)]
    report = make_report(record, source)

    async def retained_transfer(service, operation_id, plan_sha256):
        assert (service, operation_id, plan_sha256) == (
            native, record.operation_id, plan.plan_sha256,
        )
        return report, [sample(1, 0, 2), sample(100, 0.5)]

    monkeypatch.setattr(research_measurements, "_capture_retained_transfer", retained_transfer)
    result = await server.call_tool(
        "cadence_research_ac_gain_result",
        {"request": {
            "operation_id": record.operation_id,
            "expected_plan_sha256": plan.plan_sha256,
            "definition": {"reference_frequency_hz": 1.0},
        }},
    )
    assert not result.is_error and result.structured_content is not None
    measurement = result.structured_content["measurement"]
    assert measurement["reference"]["imag_v_per_v"] == 2.0
    assert measurement["unity_gain_frequency"]["value"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_public_submit_retry_restart_and_status_preserve_one_remote_accept(
    configured, monkeypatch
):
    server, service, request, settings, grant_path = configured
    calls = []
    op = str(uuid4())
    planned = await server.call_tool(
        "cadence_plan_operation", {"request": request.model_dump(mode="json")}
    )
    assert not planned.is_error
    plan_data = planned.structured_content
    assert plan_data is not None
    from cadence_mcp_bridge.operator_operations import OperationPlan

    plan = OperationPlan.model_validate_json(json.dumps(plan_data["plan"]))

    def transport(argv, raw, environment, **bounds):
        action = json.loads(raw)["action"]
        calls.append(action)
        payload = accounting(plan) if action == "authorize" else observation(op, plan)
        if action == "lookup" and len(calls) == 1:
            payload = None
        return (
            0,
            wire._canonical(
                dict(
                    schema_version=1,
                    action=action,
                    payload=payload,
                    runtime_manifest_sha256=plan.runner_sha256,
                    identity_manifest_sha256="a" * 64,
                )
            ),
            b"",
        )

    monkeypatch.setattr(wire, "run_fixed", transport)
    query = dict(operation_id=op, expected_plan_sha256=plan.plan_sha256)
    submission = dict(**query, request=request.model_dump(mode="json"))
    for selected in (
        server,
        create_server(
            cast(
                CadenceService,
                create_operator_service(
                    BridgeConfig(
                        runtime_mode="operator",
                        runtime_settings_path=settings,
                        runtime_context_id=service.context.binding.context_id,
                    ),
                    factory=lambda _: object(),
                ),
            )
        ),
    ):
        reply = await selected.call_tool("cadence_submit_operation", {"submission": submission})
        assert not reply.is_error and reply.structured_content["progress"]["phase"] == "DISPATCHED"
    reply = await server.call_tool("cadence_operation_status", {"request": query})
    assert not reply.is_error
    assert calls == ["lookup", "authorize", "accept", "lookup", "lookup"]
    assert AnalysisStore(service.context.binding.analysis_journal).operation(op).plan == plan
    assert grant_path.exists()


@pytest.mark.asyncio
async def test_injection_and_binding_drift_block_before_contact_or_journal(configured, monkeypatch):
    server, service, request, settings, grant_path = configured
    monkeypatch.setattr(wire, "run_fixed", lambda *a, **k: pytest.fail("no contact"))
    with pytest.raises(ToolError):
        await server.call_tool("cadence_plan_operation", {"request": {}, "shell": "forbidden"})
    injected = request.model_dump(mode="json")
    injected["path"] = "/forbidden"
    with pytest.raises(ToolError):
        await server.call_tool("cadence_plan_operation", {"request": injected})
    grant_path.write_bytes(b"{}")
    with pytest.raises(ConfigurationError):
        service.native_operations.current()
    denied = await server.call_tool(
        "cadence_plan_operation", {"request": request.model_dump(mode="json")}
    )
    assert denied.is_error
    assert not service.context.binding.analysis_journal.exists()
    with pytest.raises(ConfigurationError):
        NativeOperationService(load_runtime(settings)[0])


@pytest.mark.parametrize("change", ["partial", "relative", "journal-collision"])
def test_native_context_rejects_incomplete_and_colliding_bindings(configured, change):
    _, service, _, settings, _ = configured
    data = json.loads(settings.read_bytes())
    binding = data["contexts"][0]
    if change == "partial":
        del binding["operator_grant_sha256"]
    elif change == "relative":
        binding["native_provider_binding"] = "relative.json"
    else:
        binding["native_provider_binding"] = binding["analysis_journal"]
    settings.write_text(json.dumps(data))
    with pytest.raises(ConfigurationError):
        load_runtime(settings)
