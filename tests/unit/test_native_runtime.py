"""Exported fixed-runtime contracts; fictional circuits, no EDA or VM writes."""

import hashlib
import json
import os

import pytest
from pydantic import ValidationError
from test_generic_measurements import operator as operator_fixture
from test_generic_measurements import operator_base, reader_for

from cadence_mcp_bridge import _native_dispatch as dispatch
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.native_runtime import NativeRegistration, bundle, projection
from cadence_mcp_bridge.operator_operations import OperationRejected

operator = operator_fixture
__all__ = ["operator_base"]


@pytest.fixture
def registered(operator, tmp_path):
    context, plan, ade, reader, _, _ = reader_for(operator)
    workspace = context.contracts.environment.paths.workspace_root
    profile = context.contracts.designs.profile(plan.request.design_id)
    lib = profile.binding.library
    registration = {
        "schema_version": 1,
        "identity_manifest_sha256": "a" * 64,
        "routes": [
            {
                "validation_request": plan.request.model_dump(mode="json"),
                "ade": ade.model_dump(mode="json"),
                "reader": reader.model_dump(mode="json"),
                "source_cell": workspace + "/" + lib + "/" + profile.binding.cell,
                "source_state": workspace + "/saved-state",
                "libraries": [
                    {"name": lib, "path": workspace + "/" + lib, "tree_sha256": "b" * 64}
                ],
            }
        ],
    }
    path = tmp_path / "native-registration.json"
    path.write_text(json.dumps(registration), encoding="ascii")
    return context, NativeRegistration.model_validate_json(path.read_bytes()), path


def test_export_has_exact_fixed_assets_bound_hashes_and_no_authority(registered, tmp_path):
    context, registration, path = registered
    output = tmp_path / "export"
    result = bundle(context, path, output)
    manifest_raw = (output / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    assert result["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
    assert set(manifest["files"]) == set(dispatch.FILES)
    assert result["asset_count"] == len(dispatch.FILES)
    assert set(p.name for p in output.iterdir()) == set(dispatch.FILES + ("manifest.json",))
    for name, entry in manifest["files"].items():
        data = (output / name).read_bytes()
        assert entry == {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    compiled = json.loads((output / "registration.json").read_bytes())
    assert compiled == projection(context, registration)
    assert "validation_request" not in compiled["routes"][0]
    assert not result["execution_authorized"] and not result["remote_contact"]
    assert not context.binding.analysis_journal.exists() and not context.lock_path.exists()
    retained = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(OperationRejected) as failure:
        bundle(context, path, output)
    assert failure.value.reason == "native_runtime_exclusive_output_required"
    assert retained == {p.name: p.read_bytes() for p in output.iterdir()}


def test_crlf_package_exports_same_authenticated_bytes_and_installer_hashes(
    registered, tmp_path, monkeypatch
):
    from cadence_mcp_bridge import native_runtime as host

    context, _, path = registered
    first = tmp_path / "lf"
    receipt = bundle(context, path, first)
    real_files = host.files

    class CrLfResource:
        def __init__(self, resource):
            self.resource = resource

        def joinpath(self, name):
            return CrLfResource(self.resource.joinpath(name))

        def read_bytes(self):
            raw = self.resource.read_bytes().replace(b"\r\n", b"\n")
            return raw.replace(b"\n", b"\r\n")

        def read_text(self, encoding):
            return self.resource.read_text(encoding)

    monkeypatch.setattr(host, "files", lambda package: CrLfResource(real_files(package)))
    second = tmp_path / "crlf"
    assert bundle(context, path, second) == receipt
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }
    assert all(b"\r\n" not in (second / name).read_bytes() for name in host.SOURCES)
    contacts = []

    def transport(*args, **kwargs):
        contacts.append(args)
        raise OSError("synthetic transport boundary")

    monkeypatch.setattr(host, "run_fixed", transport)
    monkeypatch.setattr(host, "_ssh", lambda environment: ["synthetic-ssh", "python"])
    with pytest.raises(host.NativeSetupRemoteRejected) as failure:
        host.setup_runtime(second, receipt["manifest_sha256"], "stage", "SYNTHETIC-authority")
    assert failure.value.reason == "native_setup_transport_ambiguous"
    assert len(contacts) == 1  # The installed-package hash check accepted the same projection.


@pytest.mark.parametrize("analysis", ["ac", "tran"])
def test_native_large_waveform_registration_keeps_existing_sample_contract(registered, analysis):
    context, _, path = registered
    data = json.loads(path.read_bytes())
    route = data["routes"][0]
    route["ade"]["inputs"] = (
        {"analysis": "ac", "start_hz": "1", "stop_hz": "1000", "points_per_decade": 64}
        if analysis == "ac"
        else {"analysis": "tran", "stop_s": "0.001", "maxstep_s": "0.00001", "method": "trap"}
    )
    route["reader"].update(
        nodes=[
            {"logical_id": "n" + str(i) + "x" * 60, "selector": "/n" + str(i)} for i in range(6)
        ],
        sources=[],
        transfer=None,
        maximum_samples=256,
    )
    assert (
        NativeRegistration.model_validate_json(json.dumps(data)).routes[0].reader.maximum_samples
        == 256
    )
    assert not context.binding.analysis_journal.exists()


@pytest.mark.parametrize(
    "failure", ["source", "state", "managed", "library", "reader", "extra", "duplicate"]
)
def test_bad_route_rejected_before_output_creation(registered, tmp_path, failure):
    context, _, path = registered
    data = json.loads(path.read_bytes())
    route = data["routes"][0]
    if failure == "source":
        route["source_cell"] += "/different"
    elif failure == "state":
        route["source_state"] = "/outside/state"
    elif failure == "managed":
        route["source_state"] = context.contracts.environment.paths.managed_root + "/state"
    elif failure == "library":
        route["libraries"].append(
            {"name": "OutsideLib", "path": "/outside/library", "tree_sha256": "b" * 64}
        )
    elif failure == "reader":
        route["reader"]["ade_registration_sha256"] = "9" * 64
    elif failure == "extra":
        route["shell"] = "unused"
    else:
        data["routes"].append(route.copy())
    path.write_text(json.dumps(data), encoding="ascii")
    output = tmp_path / "invalid"
    with pytest.raises((OperationRejected, ValidationError)):
        bundle(context, path, output)
    assert not output.exists()


def test_native_schema_and_unknown_context_cli_are_bounded(registered, capsys, tmp_path):
    context, _, path = registered
    assert main(["native-runtime", "schema"]) == 0
    assert json.loads(capsys.readouterr().out)["additionalProperties"] is False
    settings = tmp_path / "runtime.json"
    assert (
        main(
            [
                "native-runtime",
                "bundle",
                "--settings",
                str(settings),
                "--context",
                "missing",
                "--registration",
                str(path),
                "--output",
                str(tmp_path / "unused"),
            ]
        )
        == 1
    )
    denied = json.loads(capsys.readouterr().out)
    assert denied["reason"] == "native_runtime_unknown_context"
    assert not denied["execution_authorized"] and not denied["remote_contact"]


def test_dispatch_closed_wire_rejects_duplicates_noncanonical_and_nonfinite():
    for raw in (b'{"a":1,"a":1}', b'{ "a":1}', b'{"a":NaN}'):
        with pytest.raises(ValueError):
            dispatch.closed(raw)


@pytest.mark.skipif(os.name != "posix", reason="native runtime requires normal Linux uid")
def test_dispatch_private_pointer_and_revocation_binding(tmp_path):
    root = str(tmp_path.resolve())
    profile = {"paths": {"managed_root": root}}
    pointer = tmp_path / "active-native-provider.json"
    pointer.write_bytes(dispatch.canonical({"schema_version": 1, "manifest_sha256": "a" * 64}))
    pointer.chmod(0o600)
    dispatch.activation(profile, "a" * 64)
    with pytest.raises(ValueError, match="activation_mismatch"):
        dispatch.activation(profile, "b" * 64)
    (tmp_path / "native-provider-revoked.json").write_bytes(b"retained revocation")
    with pytest.raises(ValueError, match="revoked"):
        dispatch.activation(profile, "a" * 64)


@pytest.mark.skipif(os.name != "posix", reason="private normal-user runtime tree")
@pytest.mark.parametrize("failure", [None, "asset", "extra", "permissions", "linked"])
def test_dispatch_validates_exact_immutable_bundle_before_import(
    registered, tmp_path, monkeypatch, failure
):
    context, _, path = registered
    exported = tmp_path / "export"
    bundle(context, path, exported)
    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    profile = json.loads((exported / "profile.json").read_bytes())
    profile["paths"]["managed_root"] = str(root.resolve())
    assets = {name: (exported / name).read_bytes() for name in dispatch.FILES}
    assets["profile.json"] = dispatch.canonical(profile)
    manifest = json.loads((exported / "manifest.json").read_bytes())
    manifest["profile_sha256"] = dispatch.digest(assets["profile.json"])
    manifest["files"] = {
        name: {"sha256": dispatch.digest(raw), "bytes": len(raw)} for name, raw in assets.items()
    }
    raw = dispatch.canonical(manifest)
    expected = dispatch.digest(raw)
    target = runtime / expected
    target.mkdir(mode=0o700)
    for name, data in {**assets, "manifest.json": raw}.items():
        (target / name).write_bytes(data)
        (target / name).chmod(0o600)
    monkeypatch.setattr(dispatch, "__file__", str(target / "provider.py"))
    if failure == "asset":
        (target / "worker.py").write_bytes(b"invalid worker")
    elif failure == "extra":
        (target / "unexpected.py").write_bytes(b"never import")
    elif failure == "permissions":
        (target / "worker.py").chmod(0o620)
    elif failure == "linked":
        (target / "worker.py").unlink()  # Disposable fault injection only.
        (target / "worker.py").symlink_to(exported / "worker.py")
    if failure is None:
        here, _, retained, _ = dispatch.validate(expected)
        assert here == str(target) and retained == assets
    else:
        with pytest.raises(ValueError):
            dispatch.validate(expected)
