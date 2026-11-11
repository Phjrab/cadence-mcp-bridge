"""Typed provider receipt/wire tests. All remote responses are synthetic."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from test_layout_engine import _orient_snapshot
from test_layout_models import fixture_snapshot, reseal
from test_layout_worker import orientation_request, request_for

from cadence_mcp_bridge import layout_native as native
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.layout_engine import predict_snapshot
from cadence_mcp_bridge.layout_models import LayoutApplyRequest, LayoutOrientationQualification


def provider(qualification=None):
    registration = native.LayoutProviderBinding(
        schema_version=1,
        resource_domain_sha256="a" * 64,
        environment_sha256="b" * 64,
        native_runtime_manifest_sha256="c" * 64,
        identity_manifest_sha256="d" * 64,
        layout_manifest_sha256="e" * 64,
        worker_sha256="f" * 64,
        orientation_qualification=qualification,
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
@pytest.mark.parametrize("orientation", [False, True])
async def test_replayed_receipt_is_verified_without_current_inspect(monkeypatch, orientation):
    before = _orient_snapshot() if orientation else fixture_snapshot()
    payload = orientation_request(before) if orientation else request_for(before)
    request = LayoutApplyRequest.model_validate_json(json.dumps(payload))
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
    qualification = (
        LayoutOrientationQualification(binding=before.binding, orientations=("R0", "R90"))
        if orientation
        else None
    )
    facade, calls = provider(qualification), []

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


def probe_registration():
    return {
        "schema_version": 1,
        "routes": [
            {
                "binding": fixture_snapshot().binding.model_dump(mode="json"),
                "cellview": {"library": "Owned", "cell": "Seed", "view": "layout"},
                "path": "/registered/managed/Owned/Seed/layout",
                "owned": True,
                "read_only": False,
            }
        ],
        "libraries": [
            {"name": name, "path": "/observed/" + name, "tree_sha256": "a" * 64}
            for name in ("Design", "Analog", "Basic", "Tech", "SourceA", "SourceB")
        ],
        "owned_libraries": [
            {"name": "Owned", "path": "/registered/managed/Owned", "tree_sha256": None}
        ],
        "protected_views": [{"path": "/observed/Design/Source/layout", "tree_sha256": "b" * 64}],
        "seed": None,
    }


def test_orientation_qualification_export_pins_same_record_and_omits_absent():
    document = probe_registration()
    args = dict(
        native_provider_sha256="c" * 64,
        identity_manifest_sha256="d" * 64,
        confirmation_sha256="e" * 64,
    )
    context = provider().context
    absent = native.build_layout_bundle(
        context, native.LayoutRegistration.model_validate_json(json.dumps(document)), **args
    )
    assert "orientation_qualification" not in json.loads(absent.assets["registration.json"])
    assert "orientation_qualification" not in json.loads(absent.provider.model_dump_json())
    qualification = {"binding": document["routes"][0]["binding"], "orientations": ["R0", "R90"]}
    document["orientation_qualification"] = qualification
    qualified = native.build_layout_bundle(
        context, native.LayoutRegistration.model_validate_json(json.dumps(document)), **args
    )
    assert qualified.manifest_sha256 != absent.manifest_sha256
    assert (
        json.loads(qualified.assets["registration.json"])["orientation_qualification"]
        == qualification
    )
    assert (
        json.loads(qualified.provider.model_dump_json())["orientation_qualification"]
        == qualification
    )
    qualification["binding"] = dict(qualification["binding"], parent_revision_sha256="e" * 64)
    with pytest.raises(ValueError, match="orientation_qualification_owned_route_required"):
        native.LayoutRegistration.model_validate_json(json.dumps(document))


@pytest.mark.parametrize("selected", [None, ["Design", "Tech"]])
def test_probe_scope_export_preserves_dependencies_and_binds_exact_bytes(selected):
    document = probe_registration()
    if selected is not None:
        document["probe_libraries"] = selected
    registration = native.LayoutRegistration.model_validate_json(json.dumps(document))
    bundle = native.build_layout_bundle(
        provider().context,
        registration,
        native_provider_sha256="c" * 64,
        identity_manifest_sha256="d" * 64,
        confirmation_sha256="e" * 64,
    )
    expected = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    assert bundle.assets["registration.json"] == expected
    exported = json.loads(expected)
    assert len(exported["libraries"]) == 6
    assert exported.get("probe_libraries") == selected
    manifest = json.loads(bundle.assets["manifest.json"])
    assert manifest["files"]["registration.json"] == {
        "sha256": hashlib.sha256(expected).hexdigest(),
        "bytes": len(expected),
    }
    assert hashlib.sha256(bundle.assets["manifest.json"]).hexdigest() == bundle.manifest_sha256
    assert bundle.provider.layout_manifest_sha256 == bundle.manifest_sha256
    default = registration.model_copy(update={"probe_libraries": None})
    default_bundle = native.build_layout_bundle(
        provider().context,
        default,
        native_provider_sha256="c" * 64,
        identity_manifest_sha256="d" * 64,
        confirmation_sha256="e" * 64,
    )
    if selected is None:
        assert default_bundle == bundle
    else:
        assert default_bundle.manifest_sha256 != bundle.manifest_sha256


@pytest.mark.parametrize(
    "selected", [[], ["Unknown"], ["Owned"], ["Tech", "Tech"], ["Tech"] * 9, "Tech"]
)
def test_invalid_operator_probe_scope_rejected_locally(selected):
    document = probe_registration()
    document["probe_libraries"] = selected
    with pytest.raises(ValueError):
        native.LayoutRegistration.model_validate_json(json.dumps(document))
