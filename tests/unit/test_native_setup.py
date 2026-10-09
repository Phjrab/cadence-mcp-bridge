"""Explicit native setup: disposable records and synthetic environment probe."""

import base64
import copy
import json
import os
import subprocess
import sys
from importlib.resources import files
from types import SimpleNamespace

import pytest
from test_native_runtime import operator, operator_base, registered
from test_operator_confirmation import confirmed_domain, root

from cadence_mcp_bridge import _native_dispatch as dispatch
from cadence_mcp_bridge import _native_setup as setup
from cadence_mcp_bridge import _operator_confirmation as confirmation
from cadence_mcp_bridge import _runner_bootstrap as installer
from cadence_mcp_bridge import _shared_reservations as accounting
from cadence_mcp_bridge import native_runtime as host

__all__ = ["operator", "operator_base", "registered", "confirmed_domain", "root"]


@pytest.fixture
def prepared(confirmed_domain, monkeypatch):
    root, profile, consent = confirmed_domain
    profile["environment_id"] = "synthetic-native"
    profile_raw = setup.canonical(profile)
    assets = {
        name: files("cadence_mcp_bridge").joinpath(source).read_bytes()
        for name, source in host.SOURCES.items()
    }
    known = {name: setup.digest(raw) for name, raw in assets.items()}
    registration = {
        "schema_version": 1,
        "environment_sha256": setup.digest(profile_raw),
        "identity_manifest_sha256": consent["identity_manifest_sha256"],
        "routes": [],
    }
    assets.update({"profile.json": profile_raw, "registration.json": setup.canonical(registration)})
    manifest = {
        "schema_version": 3,
        "kind": host.KIND,
        "environment_id": profile["environment_id"],
        "profile_sha256": setup.digest(profile_raw),
        "registration_sha256": setup.digest(assets["registration.json"]),
        "files": {
            name: {"sha256": setup.digest(raw), "bytes": len(raw)} for name, raw in assets.items()
        },
    }
    raw = setup.canonical(manifest)
    assets["manifest.json"] = raw
    expected = setup.digest(raw)
    probe_stub = SimpleNamespace(validate_profile=lambda p: p, observe=lambda *args: None)
    monkeypatch.setattr(
        setup, "modules", lambda _: (accounting, installer, probe_stub, confirmation)
    )
    request = {
        "schema_version": 1,
        "action": "stage",
        "manifest_sha256": expected,
        "operator_authority": "SYNTHETIC-user-instruction",
        "files": {name: base64.b64encode(raw).decode("ascii") for name, raw in assets.items()},
    }
    return root, request, expected, known


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.skipif(os.name != "posix", reason="normal Linux operator setup")
def test_stage_activate_repeat_inspect_revoke_preserves_existing_controls(prepared):
    root, request, expected, known = prepared
    before = snapshot(root)
    first = setup.apply(request, expected, known)
    assert first["changed_files"] == len(setup.FILES) + 1 and not first["active"]
    assert setup.apply(request, expected, known)["changed_files"] == 0
    active = dict(request, action="activate")
    assert setup.apply(active, expected, known)["changed_files"] == 2
    after = snapshot(root)
    assert setup.apply(active, expected, known)["changed_files"] == 0
    assert snapshot(root) == after
    observed = setup.apply(
        dict(request, action="inspect", operator_authority=None), expected, known
    )
    assert observed["active"] and observed["changed_files"] == 0
    for name, raw in before.items():
        assert snapshot(root)[name] == raw
    revoked = dict(request, action="revoke", operator_authority="SYNTHETIC-revoke")
    assert setup.apply(revoked, expected, known)["changed_files"] == 1
    assert setup.apply(revoked, expected, known)["changed_files"] == 0
    with pytest.raises(ValueError, match="revoked"):
        setup.apply(active, expected, known)
    assert not setup.apply(
        dict(request, action="inspect", operator_authority=None), expected, known
    )["active"]
    assert first["counter"]["count"] == 82 and first["new_simulations"] == 0


@pytest.mark.skipif(os.name != "posix", reason="existing Linux lock and durability")
@pytest.mark.parametrize("phase", ["stage", "activate"])
def test_partial_setup_restarts_without_overwrite_or_new_ledger(prepared, monkeypatch, phase):
    root, request, expected, known = prepared
    if phase == "activate":
        setup.apply(request, expected, known)
        original = accounting.write_new
        calls = []

        def fail(path, value):
            original(path, value)
            calls.append(path)
            raise OSError("synthetic lost activation reply")

        monkeypatch.setattr(accounting, "write_new", fail)
    else:
        original = installer.exclusive
        calls = []

        def fail(path, data):
            original(path, data)
            calls.append(path)
            if len(calls) == 3:
                raise OSError("synthetic partial stage")

        monkeypatch.setattr(installer, "exclusive", fail)
    with pytest.raises(OSError):
        setup.apply(dict(request, action=phase), expected, known)
    after = snapshot(root)
    monkeypatch.setattr(
        accounting if phase == "activate" else installer,
        "write_new" if phase == "activate" else "exclusive",
        original,
    )
    result = setup.apply(dict(request, action=phase), expected, known)
    assert result["changed_files"] == (1 if phase == "activate" else len(setup.FILES) - 2)
    for name, raw in after.items():
        assert snapshot(root)[name] == raw
    assert accounting.read(str(root / accounting.LEDGER))["count"] == 82


@pytest.mark.skipif(os.name != "posix", reason="private Linux runtime inventory")
@pytest.mark.parametrize("failure", ["source", "partial", "link", "unknown", "lock", "authority"])
def test_invalid_setup_retains_evidence_and_accounting(prepared, failure):
    root, request, expected, known = prepared
    target = root / "runtime" / expected
    if failure in ("partial", "link", "unknown"):
        setup.apply(request, expected, known)
        if failure == "partial":
            (target / "worker.py").write_bytes(b"retained invalid bytes")
        elif failure == "link":
            (target / "worker.py").unlink()
            (target / "worker.py").symlink_to(target / "gate.py")
        else:
            (target / "unknown.py").write_bytes(b"retained")
    wrong = copy.deepcopy(request)
    if failure == "source":
        wrong["files"]["worker.py"] = base64.b64encode(b"unbound program").decode("ascii")
    elif failure == "authority":
        wrong["operator_authority"] = ""
    before = snapshot(root)
    if failure == "lock":
        with accounting.ReservationSession(str(root)), pytest.raises((OSError, ValueError)):
            setup.apply(wrong, expected, known)
    else:
        with pytest.raises(ValueError):
            setup.apply(wrong, expected, known)
    assert snapshot(root) == before


def test_host_rejects_source_drift_before_contact(registered, tmp_path, monkeypatch):
    context, _, registration = registered
    output = tmp_path / "export"
    expected = host.bundle(context, registration, output)["manifest_sha256"]
    (output / "worker.py").write_bytes(b"invalid")
    monkeypatch.setattr(host, "run_fixed", lambda *args, **kwargs: pytest.fail("must not contact"))
    with pytest.raises(ValueError, match="package_asset"):
        host.setup_runtime(output, expected, "stage", "SYNTHETIC-authority")


def test_host_fixed_setup_transport_and_closed_receipt(registered, tmp_path, monkeypatch):
    context, _, registration = registered
    output = tmp_path / "export"
    expected = host.bundle(context, registration, output)["manifest_sha256"]
    monkeypatch.setattr(host, "_ssh", lambda env: ["fixed-ssh", env.ssh_alias, "python", "-B"])
    calls = []

    def transport(argv, payload, environment, **bounds):
        value = json.loads(payload)
        calls.append((argv, value, bounds))
        return (
            0,
            setup.canonical(
                {
                    "schema_version": 1,
                    "status": "NATIVE_RUNTIME_STAGE",
                    "manifest_sha256": expected,
                    "identity_manifest_sha256": "a" * 64,
                    "changed_files": 14,
                    "active": False,
                    "counter": {"campaign_id": "synthetic", "count": 0, "result_reserved_bytes": 0},
                    "operator_uid": 500,
                    "execution_authorized": False,
                    "new_reservations": 0,
                    "new_simulations": 0,
                }
            ),
            b"",
        )

    monkeypatch.setattr(host, "run_fixed", transport)
    result = host.setup_runtime(output, expected, "stage", "SYNTHETIC-authority")
    assert result["remote_contact"] and not result["execution_authorized"]
    assert calls[0][0][-1] == expected and calls[0][0][-3] == "-c"
    assert calls[0][2] == {"timeout": 60, "limit": 1048576}
    assert set(calls[0][1]["files"]) == set(dispatch.FILES + ("manifest.json",))
    assert "grant_json" not in calls[0][1]


def test_standalone_memory_helpers_load_only_verified_fixed_package_assets():
    source = files("cadence_mcp_bridge").joinpath("_native_setup.py").read_text("utf-8")
    assets = {
        name: files("cadence_mcp_bridge").joinpath(host.SOURCES[name]).read_bytes()
        for name in ("installer.py", "probe.py", "reservations.py", "confirmation.py")
    }
    code = (
        source
        + """
data = json.loads(sys.stdin.read())
assets = dict((name, base64.b64decode(raw)) for name, raw in data.items())
accounting, installer, probe, confirmation = modules(assets)
assert confirmation.helpers() == (accounting, installer, probe)
sys.stdout.write("FIXED_MEMORY_MODULES_OK")
"""
    )
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        input=json.dumps(
            {name: base64.b64encode(raw).decode("ascii") for name, raw in assets.items()}
        ).encode("ascii"),
        capture_output=True,
        timeout=10,
        check=True,
    )
    assert result.stdout == b"FIXED_MEMORY_MODULES_OK" and not result.stderr


def replacement(prepared):
    root, original, previous, known = prepared
    setup.apply(original, previous, known)
    setup.apply(dict(original, action="activate"), previous, known)
    assets = {name: base64.b64decode(raw) for name, raw in original["files"].items()}
    profile = setup.closed(assets["profile.json"])
    profile["environment_id"] = "synthetic-native-update"
    assets["profile.json"] = setup.canonical(profile)
    registration = setup.closed(assets["registration.json"])
    registration["environment_sha256"] = setup.digest(assets["profile.json"])
    assets["registration.json"] = setup.canonical(registration)
    manifest = setup.closed(assets["manifest.json"])
    manifest.update(
        environment_id=profile["environment_id"],
        profile_sha256=setup.digest(assets["profile.json"]),
        registration_sha256=setup.digest(assets["registration.json"]),
    )
    manifest["files"] = {
        name: {"sha256": setup.digest(raw), "bytes": len(raw)}
        for name, raw in assets.items()
        if name != "manifest.json"
    }
    assets["manifest.json"] = setup.canonical(manifest)
    expected = setup.digest(assets["manifest.json"])
    request = dict(
        original,
        manifest_sha256=expected,
        files={name: base64.b64encode(raw).decode("ascii") for name, raw in assets.items()},
    )
    setup.apply(request, expected, known)
    return (
        root,
        dict(request, action="update", previous_manifest_sha256=previous),
        expected,
        previous,
        known,
    )


@pytest.mark.skipif(os.name != "posix", reason="normal Linux atomic update")
def test_update_preserves_old_assets_history_and_counters_and_repeats(prepared):
    root, request, expected, previous, known = replacement(prepared)
    before = snapshot(root)
    old_metadata = setup.metadata(str(root / "active-native-provider.json"))
    result = setup.apply(request, expected, known)
    assert result["active"] and result["changed_files"] == 3
    assert result["counter"]["count"] == 82 and result["new_reservations"] == 0
    after = snapshot(root)
    for name, raw in before.items():
        if name != "active-native-provider.json":
            assert after[name] == raw
    record = setup.closed(
        (root / "native-provider-updates" / f"{previous}-{expected}.json").read_bytes()
    )
    assert record["previous_metadata"] == old_metadata
    assert record["replacement_metadata"] == setup.metadata(
        str(root / "active-native-provider.json")
    )
    assert record["replacement_metadata"]["inode"] != old_metadata["inode"]
    assert setup.apply(request, expected, known)["changed_files"] == 0
    assert snapshot(root) == after
    old = prepared[1]
    assert not setup.apply(dict(old, action="inspect", operator_authority=None), previous, known)[
        "active"
    ]
    with pytest.raises(ValueError, match="other_active_runtime"):
        setup.apply(dict(old, action="activate"), previous, known)


@pytest.mark.skipif(os.name != "posix", reason="durable Linux partial update")
@pytest.mark.parametrize("failure", ["pending", "receipt", "history", "rename"])
def test_partial_update_resumes_without_spend(prepared, monkeypatch, failure):
    root, request, expected, previous, known = replacement(prepared)
    original = (
        installer.exclusive
        if failure == "pending"
        else os.rename
        if failure == "rename"
        else accounting.write_new
    )
    module = installer if failure == "pending" else os if failure == "rename" else accounting
    name = "exclusive" if failure == "pending" else "rename" if failure == "rename" else "write_new"

    def interrupted(path, value):
        original(path, value)
        if (
            failure in ("pending", "rename")
            or failure == "receipt"
            and "native-provider-updates" in path
            or failure == "history"
            and "native-provider-history" in path
        ):
            raise OSError("synthetic lost update reply")

    monkeypatch.setattr(module, name, interrupted)
    with pytest.raises(OSError):
        setup.apply(request, expected, known)
    monkeypatch.setattr(module, name, original)
    result = setup.apply(request, expected, known)
    assert result["active"] and result["counter"]["count"] == 82
    assert result["new_reservations"] == result["new_simulations"] == 0
    assert setup.apply(request, expected, known)["changed_files"] == 0
    assert (root / "runtime" / previous / "manifest.json").is_file()


@pytest.mark.skipif(os.name != "posix", reason="Linux predecessor binding")
@pytest.mark.parametrize("failure", ["missing", "wrong", "asset", "revoked", "lock", "same"])
def test_update_rejects_unknown_drift_revocation_and_live_worker(prepared, failure):
    root, request, expected, previous, known = replacement(prepared)
    if failure == "missing":
        request.pop("previous_manifest_sha256")
    elif failure == "wrong":
        request["previous_manifest_sha256"] = "a" * 64
    elif failure == "same":
        request["previous_manifest_sha256"] = expected
    elif failure == "asset":
        (root / "runtime" / previous / "worker.py").write_bytes(b"retained drift")
    elif failure == "revoked":
        accounting.write_new(
            str(root / "native-provider-history" / (previous + ".revoked.json")), {}
        )
    before = snapshot(root)
    if failure == "lock":
        with accounting.ReservationSession(str(root)), pytest.raises((OSError, ValueError)):
            setup.apply(request, expected, known)
    else:
        with pytest.raises((OSError, ValueError)):
            setup.apply(request, expected, known)
    assert snapshot(root) == before


@pytest.mark.parametrize("previous", [None, "not-a-sha", "b" * 64])
def test_host_update_requires_exact_distinct_predecessor(tmp_path, monkeypatch, previous):
    monkeypatch.setattr(host, "run_fixed", lambda *a, **k: pytest.fail("no contact"))
    with pytest.raises(host.OperationRejected) as error:
        host.setup_runtime(tmp_path, "b" * 64, "update", "SYNTHETIC", previous)
    assert error.value.reason == "native_update_exact_predecessor_required"


@pytest.mark.skipif(os.name != "posix", reason="read-only Linux fixed preflight")
def test_native_preflight_has_no_writes_or_execution_authority(prepared):
    root, request, expected, known = prepared
    setup.apply(request, expected, known)
    _, _, probe, _ = setup.modules({})
    calls = []
    probe.observe = lambda *args: calls.append(args) or {"synthetic_only": True}
    before = snapshot(root)
    result = setup.apply(
        dict(request, action="preflight", operator_authority=None, nonce="1" * 32), expected, known
    )
    assert len(calls) == 1 and calls[0][-1] == "1" * 32
    assert result["environment_observation"] == {"synthetic_only": True}
    assert not result["execution_authorized"] and result["changed_files"] == 0
    assert snapshot(root) == before


@pytest.mark.parametrize("drift", [None, "nonce", "clock", "executable", "disk", "mutation"])
def test_host_preflight_verifies_exact_fresh_package_observation(
    registered, tmp_path, monkeypatch, drift
):
    from datetime import UTC, datetime

    from test_environments import observation

    from cadence_mcp_bridge.environments import load_environment

    context, _, registration = registered
    monkeypatch.setattr(host, "_ssh", lambda environment: ["synthetic-ssh", "python", "-B"])
    output = tmp_path / "preflight-bundle"
    receipt = host.bundle(context, registration, output)
    expected = receipt["manifest_sha256"]
    environment, raw = load_environment(output / "profile.json")

    def transport(argv, payload, environment_variables, **bounds):
        request = json.loads(payload)
        assert request["action"] == "preflight" and request["operator_authority"] is None
        observed = observation(environment, raw)
        observed.update(nonce=request["nonce"], observed_at=datetime.now(UTC).isoformat())
        for name in ("virtuoso", "spectre", "ocean"):
            binding = getattr(environment.tools, name)
            observed["tools"][name].update(
                sha256=binding.sha256, version=None if name == "ocean" else binding.version
            )
        if drift == "nonce":
            observed["nonce"] = "f" * 32
        elif drift == "clock":
            observed["observed_at"] = "2026-01-01T00:00:00Z"
        elif drift == "executable":
            observed["tools"]["spectre"]["sha256"] = "f" * 64
        elif drift == "disk":
            observed["free_bytes"] = 0
        value = {
            "schema_version": 1,
            "status": "NATIVE_RUNTIME_PREFLIGHT",
            "manifest_sha256": expected,
            "identity_manifest_sha256": receipt["provider_binding"]["identity_manifest_sha256"],
            "changed_files": 1 if drift == "mutation" else 0,
            "active": True,
            "counter": {"campaign_id": "synthetic", "count": 0, "result_reserved_bytes": 0},
            "operator_uid": 500,
            "execution_authorized": False,
            "new_reservations": 0,
            "new_simulations": 0,
            "environment_observation": observed,
        }
        return 0, setup.canonical(value), b""

    monkeypatch.setattr(host, "run_fixed", transport)
    if drift:
        with pytest.raises(host.NativeSetupRemoteRejected):
            host.setup_runtime(output, expected, "preflight")
    else:
        result = host.setup_runtime(output, expected, "preflight")
        assert result["environment_preflight"]["status"] == "qualified_environment_preflight"
        assert result["new_reservations"] == result["new_simulations"] == 0
        assert "environment_observation" not in result
