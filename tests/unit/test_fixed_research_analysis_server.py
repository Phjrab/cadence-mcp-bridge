"""The fixed research adapter uses the native service and exact host evidence."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from cadence_mcp_bridge import fixed_research_analysis_server as adapter
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.native_runtime import KIND
from cadence_mcp_bridge.native_service import (
    NativeOperationPlan,
    NativeOperationQuery,
    NativeOperationResult,
    NativeOperationStatus,
)
from cadence_mcp_bridge.operator_operations import (
    OperationPlan,
    OperationProgress,
    OperationRequest,
)

_PIN = "1" * 64
_SOURCE = "2" * 64


@pytest.fixture
def enrolled(tmp_path, monkeypatch):
    def save(name, value):
        raw = json.dumps(value).encode()
        path = tmp_path / name
        path.write_bytes(raw)
        return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}

    compiled = save(
        "registration.json",
        {
            "schema_version": 1,
            "environment_sha256": _PIN,
            "design_sha256": _PIN,
            "pdk_sha256": _PIN,
            "routes": [
                {
                    "design_id": "amp",
                    "analysis_id": "dc-transistor",
                    "analysis": "dc",
                    "source_cell": "/workspace/export/cell",
                    "source_state": "/workspace/export/ade",
                    "ade": {"source_tree_sha256": _SOURCE, "ade_state_tree_sha256": _PIN},
                }
            ],
        },
    )
    bundle = save(
        "manifest.json",
        {
            "schema_version": 3,
            "kind": KIND,
            "profile_sha256": _PIN,
            "registration_sha256": compiled["sha256"],
            "files": {
                "registration.json": {
                    "sha256": compiled["sha256"],
                    "bytes": (tmp_path / "registration.json").stat().st_size,
                }
            },
        },
    )
    plan = OperationPlan(
        resource_domain_sha256=_PIN,
        runner_sha256=bundle["sha256"],
        ledger_ref="shared-ledger",
        environment_sha256=_PIN,
        design_sha256=_PIN,
        pdk_sha256=_PIN,
        grant_sha256=_PIN,
        analysis="dc",
        request=OperationRequest(
            schema_version=1,
            design_id="amp",
            analysis_id="dc-transistor",
            values=(),
            result_reservation_bytes=1024,
        ),
    )
    query = NativeOperationQuery(
        operation_id="11111111-1111-4111-8111-111111111111",
        expected_plan_sha256=plan.plan_sha256,
    )
    receipt = save(
        "saved.json",
        {
            "operation_id": "22222222-2222-4222-8222-222222222222",
            "plan_sha256": _PIN,
            "scope_sha256": _PIN,
            "outcome": "VERIFIED",
            "replayed": False,
            "dispatched_this_call": True,
            "observed_revision_sha256": _PIN,
            "observed_testbench_revision_sha256": _PIN,
            "source_preservation_sha256": _PIN,
            "reopen_receipt_sha256": _PIN,
            "netlist_receipt_sha256": _PIN,
            "netlist_sha256": _PIN,
            "candidate_revision": {
                "workspace_id": "workspace",
                "design_id": "amp",
                "revision_id": "edited",
                "source_baseline_sha256": _PIN,
            },
        },
    )
    observed = save(
        "observed.json",
        {
            "status": "RESEARCH_1124_LIVE_READ_ONLY",
            "source": {
                "view_tree": _PIN,
                "input_sha256": _PIN,
                "view_content": "3" * 64,
                "library_content": "4" * 64,
            },
        },
    )
    export = save(
        "export.json",
        {
            "status": "RESEARCH_1124_INPUTS_EXPORTED",
            "preflight_sha256": observed["sha256"],
            "saved_view_tree_sha256": _PIN,
            "saved_view_content_sha256": "3" * 64,
            "copied_view_content_sha256": "3" * 64,
            "source_library_content_sha256": "4" * 64,
            "copied_library_content_sha256": "4" * 64,
            "source_cell": "/workspace/export/cell",
            "source_state": "/workspace/export/ade",
            "source_cell_sha256": _SOURCE,
            "source_state_sha256": _PIN,
            "ocean_calls": 0,
            "simulations": 0,
            "reservations": 0,
        },
    )
    document = {
        "schema_version": 1,
        "context_sha256": _PIN,
        "saved_apply": receipt,
        "source_observation": observed,
        "export_receipt": export,
        "revision": {
            "revision_sha256": _PIN,
            "testbench_revision_sha256": _PIN,
            "reconciled_netlist_sha256": _PIN,
            "reconciliation_receipt_sha256": _PIN,
            "registered_source_tree_sha256": _SOURCE,
            "registered_ade_state_sha256": _PIN,
        },
        "runtime_manifest": bundle,
        "runtime_registration": compiled,
        "analyses": [
            {"identity": query.model_dump(mode="json"), "plan": plan.model_dump(mode="json")}
        ],
    }
    binding = SimpleNamespace(
        runner_sha256=plan.runner_sha256,
        environment_sha256=_PIN,
        design_sha256=_PIN,
        pdk_sha256=_PIN,
        ledger_ref="shared-ledger",
        operator_grant_sha256=_PIN,
    )
    context = SimpleNamespace(context_sha256=_PIN, resource_domain_sha256=_PIN, binding=binding)
    monkeypatch.setattr(adapter, "select_context", lambda _: context)
    native = Mock()
    native.plan = AsyncMock(
        return_value=NativeOperationPlan(plan=plan, plan_sha256=plan.plan_sha256)
    )
    native.observe = AsyncMock(
        return_value=NativeOperationStatus(
            operation_id=query.operation_id,
            plan_sha256=plan.plan_sha256,
            progress=OperationProgress(phase="ADMITTED"),
            event_count=1,
        )
    )
    native.result = AsyncMock(
        return_value=NativeOperationResult(
            operation_id=query.operation_id,
            plan_sha256=plan.plan_sha256,
            result={"fixed": True},
        )
    )
    monkeypatch.setattr(adapter, "NativeOperationService", Mock(return_value=native))
    return document, save, query, plan, native


@pytest.mark.asyncio
async def test_fixed_analysis_tools_accept_only_enrolled_query(enrolled):
    draft, save, query, plan, native = enrolled
    ref = save("fixed.json", draft)
    server = adapter.create_fixed_research_analysis_server(
        BridgeConfig(runtime_mode="operator"),
        Path(ref["path"]),
        ref["sha256"],
    )
    assert {tool.name for tool in await server.list_tools()} == {
        "cadence_plan_fixed_research_analysis",
        "cadence_submit_fixed_research_analysis",
        "cadence_fixed_research_analysis_status",
        "cadence_fixed_research_analysis_result",
    }
    args = {"request": query.model_dump(mode="json")}
    submit = "cadence_submit_fixed_research_analysis"
    with pytest.raises(ToolError, match="identity_rejected"):
        await server.call_tool(
            submit, {"request": {**args["request"], "expected_plan_sha256": _PIN}}
        )
    with pytest.raises(ToolError):
        await server.call_tool(submit, {"request": {**args["request"], "path": "caller"}})
    native.observe.assert_not_called()
    response = await server.call_tool("cadence_plan_fixed_research_analysis", args)
    assert response.structured_content["revision"]["revision_sha256"] == _PIN
    await server.call_tool(submit, args)
    native.observe.assert_awaited_once_with(query, plan.request)
    native.plan.assert_awaited_once_with(plan.request)
    await server.call_tool("cadence_fixed_research_analysis_status", args)
    native.observe.assert_awaited_with(query)
    result = await server.call_tool("cadence_fixed_research_analysis_result", args)
    assert result.structured_content["result"]["operation_id"] == query.operation_id


@pytest.mark.parametrize("key", ["registered_source_tree_sha256", "reconciled_netlist_sha256"])
def test_fixed_analysis_rejects_inconsistent_saved_bindings(enrolled, key):
    draft, save, *_ = enrolled
    draft["revision"][key] = "f" * 64
    ref = save("invalid.json", draft)
    with pytest.raises(ConfigurationError, match="registration rejected"):
        adapter.create_fixed_research_analysis_server(
            BridgeConfig(runtime_mode="operator"),
            Path(ref["path"]),
            ref["sha256"],
        )
    adapter.NativeOperationService.assert_not_called()


@pytest.mark.parametrize(
    "key",
    [
        "saved_view_tree_sha256",
        "preflight_sha256",
        "copied_library_content_sha256",
        "copied_view_content_sha256",
        "source_state_sha256",
    ],
)
def test_fixed_analysis_rejects_repinned_foreign_export(enrolled, key):
    draft, save, *_ = enrolled
    export = json.loads(Path(draft["export_receipt"]["path"]).read_bytes())
    export[key] = "f" * 64
    draft["export_receipt"] = save("foreign-export.json", export)
    ref = save("invalid.json", draft)
    with pytest.raises(ConfigurationError, match="registration rejected"):
        adapter.create_fixed_research_analysis_server(
            BridgeConfig(runtime_mode="operator"),
            Path(ref["path"]),
            ref["sha256"],
        )
    adapter.NativeOperationService.assert_not_called()
