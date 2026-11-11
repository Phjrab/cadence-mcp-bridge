"""Typed provider receipt/wire tests. All remote responses are synthetic."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from test_layout_models import fixture_snapshot, reseal
from test_layout_worker import request_for

from cadence_mcp_bridge import layout_native as native
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.layout_engine import predict_snapshot
from cadence_mcp_bridge.layout_models import LayoutApplyRequest


def provider():
    registration = native.LayoutProviderBinding(
        schema_version=1,
        resource_domain_sha256="a" * 64,
        environment_sha256="b" * 64,
        native_runtime_manifest_sha256="c" * 64,
        identity_manifest_sha256="d" * 64,
        layout_manifest_sha256="e" * 64,
        worker_sha256="f" * 64,
    )
    context = SimpleNamespace(
        resource_domain_sha256="a" * 64,
        binding=SimpleNamespace(environment_sha256="b" * 64, runner_sha256="c" * 64),
        contracts=SimpleNamespace(environment=None),
        transport=SimpleNamespace(remote_root="/registered/managed"),
    )
    return native.NativeLayoutProvider(context, registration)


def test_unconfigured_factory_has_precise_setup_error_and_no_remote_contact():
    with pytest.raises(ConfigurationError, match="LAYOUT_SETUP_REQUIRED"):
        native.create_layout_service(BridgeConfig())


@pytest.mark.asyncio
async def test_replayed_receipt_is_verified_without_current_inspect(monkeypatch):
    before = fixture_snapshot()
    request = LayoutApplyRequest.model_validate_json(json.dumps(request_for(before)))
    expected, _ = predict_snapshot(before, request.plan.request)
    after = reseal(
        expected,
        provenance="native_readback",
        technology=expected.technology.model_copy(update={"provenance": "native_observed"}),
        pins=tuple(p.model_copy(update={"association": "native_verified"}) for p in expected.pins),
    )
    receipt = {
        "operation_id": request.plan.request.operation_id,
        "state": "SUCCEEDED",
        "before": before.model_dump(mode="json"),
        "snapshot": after.model_dump(mode="json"),
        "executed": False,
        "replayed": True,
        "saved": True,
        "reopened": True,
        "source_unchanged": True,
    }
    facade, calls = provider(), []

    async def invoke(action, payload):
        calls.append(action)
        assert action == "lookup"
        return receipt

    monkeypatch.setattr(facade, "_invoke", invoke)
    result = await facade.apply(request)
    assert result.status == "EDIT_VERIFIED" and result.replayed and not result.executed
    assert calls == ["lookup"]
    receipt["saved"] = False
    with pytest.raises(RemoteFailureError, match="readback"):
        await facade.apply(request)


@pytest.mark.asyncio
async def test_unknown_receipt_never_inspects_or_reexecutes(monkeypatch):
    facade = provider()
    request = LayoutApplyRequest.model_validate_json(json.dumps(request_for(fixture_snapshot())))

    async def invoke(action, payload):
        assert action == "lookup"
        return {
            "state": "OUTCOME_UNKNOWN",
            "operation_id": request.plan.request.operation_id,
            "executed": False,
            "replayed": True,
        }

    monkeypatch.setattr(facade, "_invoke", invoke)
    assert (await facade.apply(request)).status == "OUTCOME_UNKNOWN"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason,error",
    [
        ("layout_setup_required", ConfigurationError),
        ("layout_revision_conflict", InvalidInputError),
        ("layout_resource_lock_busy", RemoteFailureError),
        ("layout_outcome_unknown", RemoteFailureError),
    ],
)
async def test_only_closed_worker_error_codes_are_preserved(monkeypatch, reason, error):
    facade = provider()
    monkeypatch.setattr(native, "_ssh", lambda env: ["fixed-ssh"])

    def transport(*args, **kwargs):
        assert "shell" not in kwargs
        return 1, b"", ("LAYOUT_FIXED_WORKER_REJECTED:" + reason + "\n").encode()

    monkeypatch.setattr(native, "run_fixed", transport)
    with pytest.raises(error) as failure:
        await facade._invoke("inspect", {})
    assert failure.value.details == {"reason": reason}


@pytest.mark.asyncio
async def test_arbitrary_remote_error_is_not_echoed(monkeypatch):
    facade = provider()
    monkeypatch.setattr(native, "_ssh", lambda env: ["fixed-ssh"])
    monkeypatch.setattr(native, "run_fixed", lambda *a, **k: (1, b"", b"private PDK /path secret"))
    with pytest.raises(RemoteFailureError) as failure:
        await facade._invoke("inspect", {})
    assert failure.value.details == {"reason": "layout_transport_unavailable"}
    assert "private PDK" not in str(failure.value)


def test_bundle_export_has_exact_asset_pins_and_observed_seed_only():
    reference = fixture_snapshot()

    def registration_from(value):
        return native.LayoutRegistration.model_validate_json(json.dumps(value))

    registration = registration_from(
        {
            "routes": [
                {
                    "binding": reference.binding.model_dump(mode="json"),
                    "cellview": {"library": "Owned", "cell": "Seed", "view": "layout"},
                    "path": "/registered/managed/Owned/Seed/layout",
                    "owned": True,
                    "read_only": False,
                }
            ],
            "libraries": [{"name": "Tech", "path": "/observed/Tech", "tree_sha256": "a" * 64}],
            "owned_libraries": [{"name": "Owned", "path": "/registered/managed/Owned"}],
            "protected_views": [{"path": "/observed/Tech/Source/layout", "tree_sha256": "b" * 64}],
        }
    )
    bundle = native.build_layout_bundle(
        provider().context,
        registration,
        native_provider_sha256="c" * 64,
        identity_manifest_sha256="d" * 64,
        confirmation_sha256="e" * 64,
    )
    assert set(bundle.assets) == {"worker.py", "rendering.py", "registration.json", "manifest.json"}
    manifest = json.loads(bundle.assets["manifest.json"])
    for name, pin in manifest["files"].items():
        assert pin == {
            "sha256": hashlib.sha256(bundle.assets[name]).hexdigest(),
            "bytes": len(bundle.assets[name]),
        }
        assert b"\r\n" not in bundle.assets[name]
    assert hashlib.sha256(bundle.assets["manifest.json"]).hexdigest() == bundle.manifest_sha256
    assert bundle.provider.worker_sha256 == manifest["files"]["worker.py"]["sha256"]
    raw = registration.model_dump(mode="json")
    raw["seed"] = {
        "revision_id": reference.binding.revision_id,
        "technology_library": "Tech",
        "master_cell": "RectMaster",
        "technology": reference.technology.model_dump(mode="json"),
        "layer_purpose": {"layer": "metal1", "purpose": "drawing"},
    }
    with pytest.raises(ValueError, match="observation_required"):
        registration_from(raw)
    raw["seed"]["technology"]["provenance"] = "native_observed"
    assert registration_from(raw).seed is not None
    raw["routes"][0]["path"] = "/registered/managed/Owned/../Seed/layout"
    with pytest.raises(ValueError, match="path_shape"):
        registration_from(raw)
