"""Configured public storage route with bounded synthetic wire; no EDA or deletion."""

import io
import json
import sys
from types import SimpleNamespace

import pytest
from test_generic_measurements import operator as operator
from test_generic_measurements import operator_base as operator_base
from test_native_public_service import configured as configured
from test_storage import artifact, snapshot

from cadence_mcp_bridge import _native_dispatch as dispatch
from cadence_mcp_bridge import native_storage as wire
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.errors import InvalidInputError


def envelope(provider, payload, action="storage_inventory"):
    return _canonical(dict(
        schema_version=1, runtime_manifest_sha256=provider.binding.runtime_manifest_sha256,
        identity_manifest_sha256=provider.binding.identity_manifest_sha256,
        action=action, payload=payload,
    ))


@pytest.mark.asyncio
async def test_public_storage_uses_selected_runtime_and_preserves_all_journals(
    configured, monkeypatch,
):
    server, service, _request, _settings, _grant = configured
    provider = service.native_operations.provider
    state = snapshot(artifact(2, "REPLAY_REQUIRED"))
    calls = []

    def transport(argv, data, env, **limits):
        request = json.loads(data)
        calls.append((argv, request, limits))
        assert request == dict(
            schema_version=1, action="storage_inventory", payload={},
            identity_manifest_sha256=provider.binding.identity_manifest_sha256,
        )
        assert argv[-3:] == [provider.runner, provider.binding.runtime_manifest_sha256,
                             "storage_inventory"]
        assert provider.environment.paths.managed_root in provider.runner
        assert limits == dict(timeout=60, limit=262144)
        return 0, envelope(provider, state.model_dump(mode="json")), b""

    monkeypatch.setattr(wire, "_ssh", lambda env: ["synthetic-strict-host-key", env.ssh_alias])
    monkeypatch.setattr(wire, "run_fixed", transport)
    reply = await server.call_tool("cadence_storage_summary", {})
    assert not reply.is_error
    assert reply.structured_content["total_managed_bytes"] == 200
    assert reply.structured_content["potential_reclaim_bytes"] == 0
    page = await server.call_tool("cadence_list_storage_artifacts", {"request": dict(
        snapshot_id=state.snapshot_id, offset=0, limit=20,
    )})
    assert not page.is_error
    assert len(calls) == 2
    assert not service.context.binding.analysis_journal.exists()
    assert not service.context.binding.sweep_journal.exists()
    assert not service.context.lock_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["runtime", "identity", "action", "extra", "malformed", "io", "remote"],
)
async def test_storage_rejects_unbound_or_unknown_reply_once(configured, monkeypatch, failure):
    _server, service, _request, _settings, _grant = configured
    backend = service.native_storage.backend
    state = snapshot(artifact(1, "REPLAY_REQUIRED"))
    calls = []

    def transport(*args, **kwargs):
        calls.append(1)
        if failure == "io":
            raise OSError("synthetic loss after request")
        if failure == "remote":
            return 69, b"", b"bounded rejected"
        raw = json.loads(envelope(backend.provider, state.model_dump(mode="json")))
        if failure == "runtime":
            raw["runtime_manifest_sha256"] = "f" * 64
        if failure == "identity":
            raw["identity_manifest_sha256"] = "f" * 64
        if failure == "action":
            raw["action"] = "storage_cleanup"
        if failure == "extra":
            raw["path"] = "/unregistered"
        return 0, b"{}" if failure == "malformed" else _canonical(raw), b""

    monkeypatch.setattr(wire, "_ssh", lambda env: ["synthetic"])
    monkeypatch.setattr(wire, "run_fixed", transport)
    with pytest.raises(InvalidInputError):
        await backend.storage_snapshot()
    assert calls == [1]
    assert not service.context.binding.analysis_journal.exists()


@pytest.mark.asyncio
async def test_changed_operator_binding_requires_restart_before_storage_contact(
    configured, monkeypatch,
):
    server, service, _request, _settings, grant = configured
    grant.write_bytes(b"{}")
    monkeypatch.setattr(wire, "run_fixed", lambda *a, **k: pytest.fail("no contact"))
    result = await server.call_tool("cadence_storage_summary", {})
    assert result.is_error
    assert not service.context.binding.analysis_journal.exists()


@pytest.mark.parametrize("bad", ["root", "identity", "extra", "payload"])
def test_storage_dispatch_rejects_caller_path_or_binding_before_import(monkeypatch, bad):
    request = dict(schema_version=1, action="storage_inventory",
                   identity_manifest_sha256="a" * 64, payload={})
    if bad == "root":
        request["payload"]["root"] = "/caller"
    if bad == "identity":
        request["identity_manifest_sha256"] = "b" * 64
    if bad == "extra":
        request["shell"] = "forbidden"
    if bad == "payload":
        request["payload"] = []
    assets = {"registration.json": dispatch.canonical(dict(identity_manifest_sha256="a" * 64))}
    with pytest.raises(ValueError, match="native_storage"):
        dispatch.storage_dispatch("/not-imported", "c" * 64, assets, {}, request,
                                  "storage_inventory")


def test_dispatch_passes_only_trusted_profile_root_and_locked_guard(monkeypatch, capsys):
    root, expected = "/operator-specific/managed", "c" * 64
    profile = {"paths": {"managed_root": root}}
    assets = {"registration.json": dispatch.canonical(dict(identity_manifest_sha256="a" * 64))}
    events = []

    def execute(path, action, request, before, native_generic):
        assert (path, action, request, native_generic) == (root, "inventory", {}, True)
        before()
        events.append("inventory")
        return {"bounded": True}

    monkeypatch.setattr(dispatch, "verified_modules", lambda *_a, **_kw: {
        "storage": SimpleNamespace(execute_fixed=execute), "confirmation": object(),
    })
    monkeypatch.setattr(dispatch, "validate", lambda sha: events.append(("validate", sha)))
    monkeypatch.setattr(
        dispatch, "activation", lambda p, sha: events.append(("activation", p, sha)),
    )
    monkeypatch.setattr(dispatch, "history_guard", lambda p, sha, identity, parser: events.append(
        ("history", p, sha, identity)))
    request = dict(schema_version=1, action="storage_inventory",
                   identity_manifest_sha256="a" * 64, payload={})
    dispatch.storage_dispatch("/verified-runtime", expected, assets, profile, request,
                              "storage_inventory")
    assert [e[0] if isinstance(e, tuple) else e for e in events] == [
        "validate", "activation", "history", "inventory",
    ]
    reply = json.loads(capsys.readouterr().out)
    assert reply["runtime_manifest_sha256"] == expected
    assert reply["identity_manifest_sha256"] == "a" * 64
    assert reply["payload"] == {"bounded": True}


def test_dispatch_routes_storage_without_operation_plan_or_simulator(monkeypatch, capsys):
    request = dict(schema_version=1, action="storage_inventory",
                   identity_manifest_sha256="a" * 64, payload={})
    monkeypatch.setattr(sys, "argv", ["provider.py", "c" * 64, "storage_inventory"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(dispatch.canonical(request).decode("ascii")))
    monkeypatch.setattr(dispatch, "validate", lambda expected: ("fixed", {}, {}, {}))
    calls = []
    monkeypatch.setattr(dispatch, "storage_dispatch", lambda *args: calls.append(args))
    dispatch.main()
    assert len(calls) == 1 and calls[0][-2:] == (request, "storage_inventory")
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("names", [dispatch.MODULES, (
    "reservations", "installer", "probe", "confirmation", "storage",
)])
def test_verified_asset_modules_replace_cached_names_and_use_exact_bytes(monkeypatch, names):
    assets = {}
    for name in names:
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(
            execute_fixed=lambda *_a, **_k: pytest.fail("cached module executed"),
        ))
        assets[name + ".py"] = (
            "import sys\nassert __package__ is None\n"
            "assert sys.modules[__name__].__dict__ is globals()\n"
            f"verified_marker = {name!r}\n"
        ).encode("ascii")
    # No source path need exist: all execution uses previously authenticated bytes.
    modules = dispatch.verified_modules("/fixed/verified/runtime", assets, names)
    for name in names:
        assert modules[name] is sys.modules[name]
        assert modules[name].verified_marker == name
        assert modules[name].__file__ == "/fixed/verified/runtime/" + name + ".py"


def test_storage_dispatch_uses_authenticated_asset_not_cached_namesake(monkeypatch, capsys):
    root, expected = "/operator-specific/managed", "c" * 64
    profile = {"paths": {"managed_root": root}}
    names = ("reservations", "installer", "probe", "confirmation", "storage")
    assets = {name + ".py": b"" for name in names}
    assets["registration.json"] = dispatch.canonical(dict(identity_manifest_sha256="a" * 64))
    assets["storage.py"] = b"""
def execute_fixed(root, action, request, before, native_generic):
    assert root == '/operator-specific/managed'
    assert action == 'inventory' and request == {} and native_generic
    before()
    return {'verified_asset': True}
"""
    for name in names:
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(
            execute_fixed=lambda *_a, **_k: pytest.fail("cached storage bypass"),
        ))
    monkeypatch.setattr(dispatch, "validate", lambda _sha: None)
    monkeypatch.setattr(dispatch, "activation", lambda *_a: None)
    monkeypatch.setattr(dispatch, "history_guard", lambda *_a: None)
    request = dict(schema_version=1, action="storage_inventory",
                   identity_manifest_sha256="a" * 64, payload={})
    dispatch.storage_dispatch("/verified-runtime", expected, assets, profile, request,
                              "storage_inventory")
    reply = json.loads(capsys.readouterr().out)
    assert reply["payload"] == {"verified_asset": True}
