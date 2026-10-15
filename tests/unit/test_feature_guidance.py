"""Local guidance is not actual VM/client qualification or permission to dispatch."""

import hashlib
import json
import subprocess
from unittest.mock import MagicMock

import pytest
from mcp import Client
from test_native_public_service import configured, operator, operator_base
from test_native_specifications import contract as specification_contract
from test_runtime_context import make_settings

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.designs import reference_analysis_registry
from cadence_mcp_bridge.feature_guidance import GUIDANCE_URI, guidance, service_guidance
from cadence_mcp_bridge.native_specifications import NativeSpecificationCatalog
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


@pytest.mark.parametrize("catalog_state", ["registered", "empty", "missing", "invalid", "changed"])
@pytest.mark.parametrize("route_state", ["available", "no_binding", "not_loaded", "inactive"])
def test_specification_reasons_distinguish_registration_from_result_route(
    configured, catalog_state, route_state,
):
    _, service, _, settings, grant_path = configured
    context = service.context
    design_id = context.contracts.designs.designs[0].design_id
    updates = {}
    if catalog_state != "missing":
        catalog = settings.parent / "guidance-spec.json"
        spec = specification_contract(design_id=design_id)
        raw = NativeSpecificationCatalog(
            specifications=() if catalog_state == "empty" else (spec,),
        ).model_dump_json().encode()
        if catalog_state == "invalid":
            raw = b'{"private-invalid":true}'
        catalog.write_bytes(raw)
        updates.update(
            native_specifications=catalog,
            native_specifications_sha256="f" * 64 if catalog_state == "changed"
            else hashlib.sha256(raw).hexdigest(),
        )
    if route_state == "no_binding":
        updates.update(native_provider_binding=None, native_provider_sha256=None,
                       operator_grant=None, operator_grant_sha256=None)
    elif route_state == "inactive":
        grant = json.loads(grant_path.read_bytes())
        grant["valid_until_unix"] = 2
        grant_path.write_text(json.dumps(grant))
        updates["operator_grant_sha256"] = hashlib.sha256(grant_path.read_bytes()).hexdigest()
    context = context.__class__(**{
        **context.__dict__, "binding": context.binding.model_copy(update=updates),
    })
    before = snapshot(settings.parent)
    report = guidance(
        context.contracts.designs, context.contracts.pdks, mode="operator", context=context,
        native_tools_registered=route_state != "not_loaded",
    )
    feature = report["circuits"][0]["features"]["native_specification"]
    if catalog_state == "registered":
        reasons = [] if route_state in ("available", "inactive") else [
            "native_result_route_unavailable",
        ]
    else:
        reasons = [{
            "empty": "native_specification_not_registered_for_design",
            "missing": "native_specifications_missing",
            "invalid": "native_specifications_invalid",
            "changed": "native_specifications_invalid",
        }[catalog_state]]
    assert feature["reasons"] == reasons
    assert feature["state"] == ("BLOCKED" if reasons else "REQUIRES_EXECUTION_CHECKS")
    assert report["remote_contact"] is False and report["new_reservations"] == 0
    assert snapshot(settings.parent) == before


@pytest.mark.parametrize("document", ["specifications", "provider", "grant"])
@pytest.mark.asyncio
async def test_deeply_nested_bound_document_returns_closed_resource_and_cli_guidance(
    configured, document, capsys,
):
    server, service, _, settings, grant_path = configured
    context = service.context
    field, digest_field, path = {
        "specifications": ("native_specifications", "native_specifications_sha256",
                           settings.parent / "spec.json"),
        "provider": ("native_provider_binding", "native_provider_sha256",
                     context.binding.native_provider_binding),
        "grant": ("operator_grant", "operator_grant_sha256", grant_path),
    }[document]
    raw = b'{"nested":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}'
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    service.context = context.__class__(**{
        **context.__dict__, "binding": context.binding.model_copy(update={
            field: path, digest_field: digest,
        }),
    })
    runtime = json.loads(settings.read_bytes())
    runtime["contexts"][0].update({field: str(path), digest_field: digest})
    settings.write_text(json.dumps(runtime))
    before = snapshot(settings.parent)
    async with Client(server) as client:
        report = json.loads((await client.read_resource(GUIDANCE_URI)).contents[0].text)
    if document == "specifications":
        assert report["circuits"][0]["features"]["native_specification"]["reasons"] == [
            "native_specifications_invalid",
        ]
    else:
        assert {a["state"] for a in report["circuits"][0]["analyses"]} == {"BLOCKED"}
        assert all("native_binding_invalid" in a["reasons"]
                   for a in report["circuits"][0]["analyses"])
    assert main([
        "operator-features", "--settings", str(settings),
        "--context", context.binding.context_id,
    ]) in (0, 2)
    cli = json.loads(capsys.readouterr().out)
    assert cli["status"] in ("LOCAL_FEATURE_GUIDANCE", "BLOCKED")
    assert snapshot(settings.parent) == before
    assert str(settings.parent) not in json.dumps(report) + json.dumps(cli)
