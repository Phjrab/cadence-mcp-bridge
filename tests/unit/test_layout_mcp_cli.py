"""Adapter evidence only: synthetic fixtures never stand for a native edit."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from mcp import Client
from mcp.types import TextContent
from pydantic import BaseModel

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import BackendUnavailableError, ConfigurationError
from cadence_mcp_bridge.layout_cli import dispatch_layout
from cadence_mcp_bridge.layout_models import (
    LayerPurpose,
    LayoutApplyRequest,
    LayoutBBox,
    LayoutDiff,
    LayoutDiffRequest,
    LayoutForkRequest,
    LayoutInspectRequest,
    LayoutNativeEdit,
    LayoutPlan,
    LayoutPlanRequest,
    LayoutPoint,
    LayoutPreview,
    LayoutResult,
    LayoutSelectRequest,
    LayoutShape,
    LayoutSnapshot,
    LayoutTechnology,
    MoveEdit,
)
from cadence_mcp_bridge.layout_server import LAYOUT_ACTIONS, LAYOUT_TOOLS, LazyLayoutService
from cadence_mcp_bridge.layout_service import LayoutService
from cadence_mcp_bridge.runtime_context import OperatorService
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService


def binding() -> RevisionBinding:
    return RevisionBinding(
        workspace_id="fixture-work", design_id="fixture-layout", revision_id="working-one",
        parent_revision_id="source", parent_revision_sha256="b" * 64,
        source_baseline_sha256="a" * 64,
    )


def route_data() -> dict[str, tuple[BaseModel, BaseModel]]:
    target = binding()
    snapshot = LayoutSnapshot(
        binding=target, source_baseline_sha256="a" * 64,
        technology=LayoutTechnology(
            dbu_per_um=1000, manufacturing_grid_dbu=5,
            allowed_layer_purposes=(LayerPurpose(layer="M1", purpose="drawing"),),
            provenance="synthetic_fixture",
        ),
        shapes=(LayoutShape(
            object_id="shape-one", kind="rect", layer="M1", purpose="drawing",
            bbox_dbu=LayoutBBox(
                lower_left=LayoutPoint(x=0, y=0), upper_right=LayoutPoint(x=10, y=10),
            ),
        ),),
        provenance="synthetic_fixture", owned=True, read_only=False,
    )
    request = LayoutPlanRequest(
        binding=target, operation_id=str(uuid4()),
        expected_baseline_sha256=snapshot.semantic_sha256,
        edits=(MoveEdit(kind="move", object_id="shape-one", dx_um="0.005", dy_um="0"),),
    )
    plan = LayoutPlan(
        request=request, baseline_sha256=snapshot.semantic_sha256,
        normalized_edits=(LayoutNativeEdit(
            kind="move", object_id="shape-one", before_sha256="c" * 64, dx_dbu=5, dy_dbu=0,
        ),),
        expected_semantic_sha256="d" * 64,
        preview=LayoutPreview(
            target_object_ids=("shape-one",), created=0, moved=1,
            expected_bbox_dbu=LayoutBBox(
                lower_left=LayoutPoint(x=5, y=0), upper_right=LayoutPoint(x=15, y=10),
            ),
            predicted_diff=LayoutDiff(
                before_sha256=snapshot.semantic_sha256, after_sha256="d" * 64,
            ),
        ),
    )
    result = LayoutResult(status="NOT_VERIFIED", binding=target, snapshot=snapshot)
    return {
        "inspect": (LayoutInspectRequest(binding=target), snapshot),
        "fork": (LayoutForkRequest(
            binding=target, operation_id=str(uuid4()), expected_baseline_sha256="b" * 64,
        ), result),
        "plan": (request, plan),
        "apply": (LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256), result),
        "diff": (LayoutDiffRequest(
            binding=target, before_revision_id="source", expected_before_sha256="b" * 64,
        ), result),
        "select": (LayoutSelectRequest(
            binding=target, expected_baseline_sha256=snapshot.semantic_sha256,
        ), result),
    }


def server() -> Any:
    return create_server(cast(CadenceService, OperatorService(None)))


async def test_unconfigured_discovery_and_explicit_denial() -> None:
    async with Client(server()) as client:
        listing = await client.list_tools()
        tools = {tool.name: tool for tool in listing.tools}
        assert tools.keys() >= LAYOUT_TOOLS
        for name in LAYOUT_TOOLS:
            tool = tools[name]
            assert tool.input_schema["additionalProperties"] is False
            assert tool.input_schema["required"] == ["request"]
            assert tool.output_schema and tool.annotations
        for action, (request, _) in route_data().items():
            response = await client.call_tool(
                "cadence_layout_" + action, {"request": request.model_dump(mode="json")},
            )
            assert response.is_error
            data = cast(dict[str, Any], response.structured_content)
            assert data["error"]["code"] == "invalid_configuration"
            assert data["error"]["details"]["reason"] == "layout_development_context_required"


@pytest.mark.parametrize("action", LAYOUT_ACTIONS)
async def test_mcp_and_cli_dispatch_identical_typed_requests(
    action: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, expected = route_data()[action]
    service = AsyncMock(spec=LayoutService)
    method = getattr(service, action)
    method.return_value = expected
    monkeypatch.setattr(LazyLayoutService, "get", lambda self: service)
    async with Client(server()) as client:
        response = await client.call_tool(
            "cadence_layout_" + action, {"request": request.model_dump(mode="json")},
        )
    assert not response.is_error
    assert response.structured_content == expected.model_dump(mode="json")
    cli_result = await dispatch_layout(
        LazyLayoutService(None), action, request.model_dump_json().encode(),
    )
    assert cli_result == expected
    assert method.await_count == 2
    assert all(call.args == (request,) for call in method.await_args_list)


@pytest.mark.parametrize("arguments", [
    {"request": {"binding": {}}, "command": "injected"},
    {"request": {"binding": {}, "path": "/arbitrary"}},
    {"request": "not-an-object"},
])
async def test_mcp_invalid_envelopes_reject_before_provider(
    arguments: dict[str, Any], monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(self: LazyLayoutService) -> LayoutService:
        pytest.fail("invalid request reached provider")

    monkeypatch.setattr(LazyLayoutService, "get", unexpected)
    async with Client(server()) as client:
        response = await client.call_tool("cadence_layout_inspect", arguments)
    assert response.is_error


def test_cli_schema_without_native_settings(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["layout", "schema", "--action", "apply"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert set(schema["required"]) == {"plan", "expected_plan_sha256"}
    assert schema["additionalProperties"] is False


def test_cli_unconfigured_rejection(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "inspect.json"
    path.write_text(LayoutInspectRequest(binding=binding()).model_dump_json(), encoding="utf-8")
    assert main(["layout", "inspect", "--request", str(path)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["error"]["details"]["reason"] == "layout_development_context_required"


@pytest.mark.parametrize(
    "payload", [b"not-json", b'{"command":"raw"}', b"x" * 1_048_577],
    ids=["malformed", "raw-command", "oversized"],
)
def test_cli_bad_request_is_sanitized(
    payload: bytes, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(payload)
    assert main(["layout", "apply", "--request", str(path)]) == 1
    output = capsys.readouterr().out
    assert json.loads(output)["error"]["code"] == "invalid_input"
    assert str(path) not in output


def test_legacy_settings_cannot_enable_layout() -> None:
    with pytest.raises(ConfigurationError, match="explicitly configured development context"):
        LazyLayoutService(BridgeConfig(runtime_mode="legacy_reference")).get()


async def test_real_engine_plan_and_rejections_through_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = route_data()
    provider = AsyncMock()
    provider.inspect.return_value = data["inspect"][1]
    service = LayoutService(provider)
    monkeypatch.setattr(LazyLayoutService, "get", lambda self: service)
    plan_request = data["plan"][0].model_dump(mode="json")
    async with Client(server()) as client:
        response = await client.call_tool("cadence_layout_plan", {"request": plan_request})
        assert not response.is_error
        plan = LayoutPlan.model_validate_json(json.dumps(response.structured_content))
        assert plan.normalized_edits[0].dx_dbu == 5
        assert plan.preview.moved == 1
        for dx in ("0.001", "NaN"):
            reads_before = provider.inspect.await_count
            bad = {**plan_request, "edits": [dict(
                kind="move", object_id="shape-one", dx_um=dx, dy_um="0",
            )]}
            response = await client.call_tool("cadence_layout_plan", {"request": bad})
            assert response.is_error
            if dx == "NaN":
                # The corrected typed model rejects before the SDK calls our tool.
                assert provider.inspect.await_count == reads_before
                assert response.structured_content is None
                message = cast(TextContent, response.content[0]).text
                assert "bounded decimal text required" in message
            else:
                data_out = cast(dict[str, Any], response.structured_content)
                assert data_out["error"]["code"] == "invalid_input"
        response = await client.call_tool("cadence_layout_apply", {"request": {
            "plan": plan.model_dump(mode="json"), "expected_plan_sha256": "f" * 64,
        }})
        assert response.is_error
        assert cast(dict[str, Any], response.structured_content)["error"]["details"]["reason"] == (
            "layout_expected_plan_digest_mismatch"
        )
    provider.apply.assert_not_awaited()


@pytest.mark.parametrize("reason", ["vm_disconnected", "license_unavailable", "layout_locked",
                                  "revision_conflict", "unsupported_layer_purpose"])
def test_cli_preserves_safe_backend_error_reason(
    reason: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject(self: LazyLayoutService) -> LayoutService:
        raise BackendUnavailableError("Layout provider unavailable", details={"reason": reason})

    monkeypatch.setattr(LazyLayoutService, "get", reject)
    path = tmp_path / "inspect.json"
    path.write_text(LayoutInspectRequest(binding=binding()).model_dump_json(), encoding="utf-8")
    assert main(["layout", "inspect", "--request", str(path)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["error"]["details"]["reason"] == reason


def test_lazy_fixed_native_factory_receives_explicit_settings_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    settings = BridgeConfig(
        runtime_mode="operator", runtime_settings_path=tmp_path / "settings.json",
        runtime_context_id="development",
    )
    service = LayoutService(AsyncMock())
    calls: list[BridgeConfig] = []

    def factory(config: BridgeConfig) -> LayoutService:
        calls.append(config)
        return service

    module = ModuleType("cadence_mcp_bridge.layout_native")
    monkeypatch.setattr(module, "create_layout_service", factory, raising=False)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    lazy = LazyLayoutService(settings)
    assert not calls
    assert lazy.get() is service
    assert lazy.get() is service
    assert calls == [settings]


async def test_pin_label_is_rejected_before_native_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(self: LazyLayoutService) -> LayoutService:
        pytest.fail("unsupported pin label reached native factory")

    monkeypatch.setattr(LazyLayoutService, "get", unexpected)
    request = route_data()["plan"][0].model_dump(mode="json")
    request["edits"] = [{
        "kind": "add_pin", "object_id": "pin-one", "layer": "M1", "purpose": "drawing",
        "bbox_um": ["0", "0", "0.01", "0.01"], "net_id": "net-one",
        "terminal_id": "term-one", "label": "OUT",
    }]
    async with Client(server()) as client:
        response = await client.call_tool("cadence_layout_plan", {"request": request})
    assert response.is_error
    message = cast(TextContent, response.content[0]).text
    assert "request.edits.0.add_pin.label" in message
