"""Exercise opt-in PM0 MCP schema, registration and invocation boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from cadence_mcp_bridge import amplifier_pm0_execution_server as adapter
from cadence_mcp_bridge.amplifier_pm0_default import RegisteredAmplifierPm0DefaultChange
from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeRequest, PmosDefaultChangeResult
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.server import create_default_server

_REQUEST = {
    "operation_id": "11111111-1111-4111-8111-111111111111",
    "expected_plan_sha256": "1" * 64,
    "expected_scope_sha256": "2" * 64,
}
_NAME = "cadence_apply_fixed_amp_pm0"


@pytest.mark.asyncio
async def test_fixed_amp_pm0_exposes_only_typed_registered_apply(monkeypatch):
    context = SimpleNamespace(context_sha256="original")
    monkeypatch.setattr(adapter, "select_context", lambda _: context)
    service = Mock(spec=RegisteredAmplifierPm0DefaultChange)
    service.apply.return_value = PmosDefaultChangeResult.model_validate({
        "operation_id": _REQUEST["operation_id"],
        "plan_sha256": _REQUEST["expected_plan_sha256"],
        "scope_sha256": _REQUEST["expected_scope_sha256"],
        "outcome": "OUTCOME_UNKNOWN",
        "replayed": True,
        "dispatched_this_call": False,
        "candidate_revision": {
            "workspace_id": "workspace",
            "design_id": "design",
            "revision_id": "candidate",
            "source_baseline_sha256": "3" * 64,
        },
    })
    monkeypatch.setattr(adapter, "registered_pmos_default_change", lambda _: service)
    server = create_default_server(operator_mode=True, fixed_amp_pm0=True)
    tool, = await server.list_tools()
    assert tool.name == _NAME
    assert tool.annotations is not None and tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is True
    result = await server.call_tool(_NAME, {"request": _REQUEST})
    assert result.structured_content == service.apply.return_value.model_dump(mode="json")
    service.apply.assert_called_once_with(PmosDefaultChangeRequest.model_validate(_REQUEST))

    with pytest.raises(ToolError):
        await server.call_tool(_NAME, {"request": {**_REQUEST, "path": "caller-path"}})
    context.context_sha256 = "changed"
    with pytest.raises(ToolError, match="registered_fixed_amp_pm0_rejected"):
        await server.call_tool(_NAME, {"request": _REQUEST})
    assert service.apply.call_count == 1


def test_fixed_amp_pm0_denies_missing_and_non_amp_registration(monkeypatch):
    config = BridgeConfig(runtime_mode="operator")
    monkeypatch.setattr(adapter, "select_context", lambda _: None)
    with pytest.raises(ConfigurationError, match="not registered"):
        adapter.create_fixed_amp_pm0_server(config)
    monkeypatch.setattr(adapter, "select_context", lambda _: SimpleNamespace(context_sha256="test"))
    monkeypatch.setattr(adapter, "registered_pmos_default_change", lambda _: object())
    with pytest.raises(ConfigurationError, match="not registered"):
        adapter.create_fixed_amp_pm0_server(config)
    with pytest.raises(ConfigurationError, match="dedicated"):
        create_default_server(fixed_amp_pm0=True)
