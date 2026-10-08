"""Configured MCP lifecycle with a synthetic wire; no VM or approval creation."""

import hashlib
import json
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_authenticated_provider import accounting, observation
from test_generic_measurements import operator, operator_base

from cadence_mcp_bridge import authenticated_provider as wire
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.native_service import NativeOperationService
from cadence_mcp_bridge.runtime_context import create_operator_service, load_runtime
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService

__all__ = ["operator", "operator_base"]
NAMES = {
    "cadence_plan_operation",
    "cadence_submit_operation",
    "cadence_operation_status",
    "cadence_operation_result",
    "cadence_cancel_pending_operation",
}


@pytest.fixture
def configured(operator, tmp_path):
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
    service = create_operator_service(config)
    assert not context.binding.analysis_journal.exists()
    return create_server(cast(CadenceService, service)), service, request, settings, grant_path


@pytest.mark.asyncio
async def test_operator_only_conditional_schema_and_no_server_start_side_effects(configured):
    server, service, request, settings, grant_path = configured
    tools = {t.name: t for t in await server.list_tools()}
    assert len(tools) == 90 and set(tools) >= NAMES
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
        )
    )
    assert old.native_operations is None
    assert len(await create_server(cast(CadenceService, old)).list_tools()) == 85


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
                    )
                ),
            )
        ),
    ):
        reply = await selected.call_tool("cadence_submit_operation", {"submission": submission})
        assert not reply.is_error and reply.structured_content["progress"]["phase"] == "DISPATCHED"
    reply = await server.call_tool("cadence_operation_status", {"request": query})
    assert not reply.is_error
    assert calls == ["authorize", "accept", "lookup", "lookup"]
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
