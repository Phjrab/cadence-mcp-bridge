"""Local guidance is not actual VM/client qualification or permission to dispatch."""

import hashlib
import json
import subprocess
from unittest.mock import MagicMock

import pytest
from mcp import Client
from test_native_public_service import configured, operator, operator_base
from test_runtime_context import make_settings

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.designs import reference_analysis_registry
from cadence_mcp_bridge.feature_guidance import GUIDANCE_URI, guidance, service_guidance
from cadence_mcp_bridge.pdk_reference import reference_pdk_registry
from cadence_mcp_bridge.runtime_context import OperatorService, load_runtime
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.sweep_registry import fixture_sweep_registry

__all__ = ["configured", "operator", "operator_base"]


def snapshot(folder):
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in folder.rglob("*") if p.is_file()
    }


def test_local_mode_and_fixture_cannot_claim_production():
    reference = guidance(
        reference_analysis_registry(), reference_pdk_registry(), mode="legacy_reference",
    )
    assert {a["state"] for a in reference["circuits"][0]["analyses"]} == {"REFERENCE_ONLY"}
    fixture = guidance(
        fixture_sweep_registry(), reference_pdk_registry(), mode="legacy_reference",
    )
    assert any(
        a["state"] == "SYNTHETIC_ONLY" and a["route"] == "synthetic_fixture"
        for circuit in fixture["circuits"] for a in circuit["analyses"]
    )
    assert reference["execution_authorized"] is fixture["execution_authorized"] is False


@pytest.mark.asyncio
async def test_unset_resource_and_tools_preserve_contract():
    service = OperatorService(None)
    server = create_server(service)
    async with Client(server) as client:
        resources = await client.list_resources()
        assert str(resources.resources[0].uri) == GUIDANCE_URI
        result = await client.read_resource(GUIDANCE_URI)
        report = json.loads(result.contents[0].text)
        assert report["mode"] == "unconfigured" and report["circuits"] == []
        assert report["setup"]["reasons"] == ["setup_required"]
        assert len((await client.list_tools()).tools) == 85


def test_explicit_cli_settings_override_inherited_environment_and_preserve_every_file(
    tmp_path, monkeypatch, capsys,
):
    settings = make_settings(tmp_path)
    monkeypatch.setenv("CADENCE_MCP_RUNTIME_SETTINGS_PATH", "private-nonselected-settings")
    monkeypatch.setenv("CADENCE_MCP_RUNTIME_MODE", "legacy_reference")
    denied = MagicMock(side_effect=AssertionError("feature inspection must stay local"))
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    before = snapshot(tmp_path)
    assert main(["operator-features", "--settings", str(settings), "--context", "context-2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "operator" and report["context_id"] == "context-2"
    assert [c["design_id"] for c in report["circuits"]] == ["design-2"]
    assert report["native_tools_registered"] is None
    assert report["remote_contact"] is report["execution_authorized"] is False
    assert snapshot(tmp_path) == before
    assert str(tmp_path) not in json.dumps(report)
    assert main(["operator-features", "--settings", str(settings), "--context", "absent"]) == 2
    error = json.loads(capsys.readouterr().out)
    assert error["reason"] == "feature_context_invalid"
    assert str(tmp_path) not in json.dumps(error) and snapshot(tmp_path) == before


def test_description_without_binding_cannot_use_native(tmp_path):
    context = load_runtime(make_settings(tmp_path))[0]
    report = service_guidance(OperatorService(context))
    assert report["circuits"][0]["features"]["describe"]["state"] == "LOCAL_AVAILABLE"
    assert {a["state"] for a in report["circuits"][0]["analyses"]} == {"BLOCKED"}
    assert report["native_tools_registered"] is False


@pytest.mark.asyncio
async def test_loaded_native_resource_is_read_only_and_cannot_attest_live_qualification(configured):
    server, service, _, settings, _ = configured
    before = snapshot(settings.parent)
    async with Client(server) as client:
        report = json.loads((await client.read_resource(GUIDANCE_URI)).contents[0].text)
        assert len((await client.list_tools()).tools) == 96
    assert report["native_tools_registered"] is True
    assert {a["state"] for a in report["circuits"][0]["analyses"]} == {
        "REQUIRES_EXECUTION_CHECKS",
    }
    assert report["circuits"][0]["remote_route_qualification"] == "NOT_ASSESSED"
    sweep = report["circuits"][0]["features"]["native_1d_sweep"]
    assert sweep["state"] == "BLOCKED"
    assert sweep["reasons"] == ["qualified_mutable_sweep_axis_missing"]
    assert report["remaining_budget"] is None and report["execution_authorized"] is False
    assert snapshot(settings.parent) == before
    assert str(settings.parent) not in json.dumps(report)


@pytest.mark.parametrize("change", ["expired", "revoked", "scope", "tamper", "runner"])
def test_authority_and_stale_bindings_never_promote_native(configured, change):
    _, service, _, settings, grant_path = configured
    context = service.context
    if change == "runner":
        provider = context.binding.native_provider_binding
        data = json.loads(provider.read_bytes())
        data["runtime_manifest_sha256"] = "c" * 64
        provider.write_text(json.dumps(data))
        context = context.__class__(**{
            **context.__dict__,
            "binding": context.binding.model_copy(update={
                "native_provider_sha256": hashlib.sha256(provider.read_bytes()).hexdigest(),
            }),
        })
        service.context = context
    elif change == "tamper":
        grant_path.write_text("private-error-injected")
    else:
        data = json.loads(grant_path.read_bytes())
        if change == "expired":
            data["valid_until_unix"] = 2
        elif change == "revoked":
            data["status"] = "revoked"
        else:
            data["analyses"] = ["dc"]
        grant_path.write_text(json.dumps(data))
        service.context = context.__class__(**{
            **context.__dict__,
            "binding": context.binding.model_copy(update={
                "operator_grant_sha256": hashlib.sha256(grant_path.read_bytes()).hexdigest(),
            }),
        })
    before = snapshot(settings.parent)
    report = service_guidance(service)
    states = {a["analysis"]: a["state"] for a in report["circuits"][0]["analyses"]}
    assert states["ac"] == "BLOCKED"
    if change == "scope":
        assert states["dc"] == "REQUIRES_EXECUTION_CHECKS"
    if change in ("expired", "revoked"):
        assert report["circuits"][0]["features"]["native_result"]["state"] == (
            "REQUIRES_EXECUTION_CHECKS"
        )
    assert snapshot(settings.parent) == before
    assert "private-error-injected" not in json.dumps(report)


def test_malformed_catalog_never_claims_specification(configured):
    _, service, _, settings, _ = configured
    catalog = settings.parent / "spec.json"
    catalog.write_text("secret invalid content")
    context = service.context
    service.context = context.__class__(**{
        **context.__dict__, "binding": context.binding.model_copy(update={
            "native_specifications": catalog,
            "native_specifications_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        }),
    })
    report = service_guidance(service)
    assert report["circuits"][0]["features"]["native_specification"]["reasons"] == [
        "native_specifications_invalid",
    ]
    assert "secret invalid content" not in json.dumps(report)
