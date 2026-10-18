"""Local preparation with fictional registrations; no VM, claim or EDA action."""

import hashlib
import json
import os
from dataclasses import replace

import pytest
from test_native_runtime import operator, operator_base, registered

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.binding_observation import BindingScanRequest, render_collector
from cadence_mcp_bridge.binding_observer_operator import ASSETS, BLOCKERS, prepare
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.operator_operations import OperationRejected

__all__ = ["operator", "operator_base", "registered"]


def selection(registered):
    context, registration, path = registered
    route = registration.routes[0]
    return context, path, route.ade.design_id, route.ade.analysis_id


def test_preparation_binds_exact_registration_and_all_variables_without_execution(
    registered, tmp_path, monkeypatch,
):
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail("local preparation must not launch any process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    context, path, design, analysis = selection(registered)
    original = path.read_bytes()
    output = tmp_path / "private-plan"
    receipt = prepare(context, path, design, analysis, output)
    raw = (output / "binding-plan.private.json").read_bytes()
    plan = json.loads(raw)
    request = BindingScanRequest.model_validate_json(
        (output / "binding-request.private.json").read_bytes()
    )
    assert plan["request"] == request.model_dump(mode="json")
    assert receipt["plan_sha256"] == hashlib.sha256(raw).hexdigest()
    assert plan["request_sha256"] == hashlib.sha256(
        _canonical(request.model_dump(mode="json"))
    ).hexdigest()
    assert plan["registration_input_sha256"] == hashlib.sha256(original).hexdigest()
    assert plan["collector_sha256"] == hashlib.sha256(render_collector(request)).hexdigest()
    assert (output / "collector.ocn").read_bytes() == render_collector(request)
    assert set(plan["package_asset_lf_sha256"]) == set(ASSETS)
    variables = context.contracts.designs.variable_set(design).variables
    assert {(v.logical_id, v.cadence_binding) for v in request.variables} == {
        (v.logical_id, v.cadence_binding) for v in variables
    }
    assert plan["blockers"] == list(BLOCKERS)
    assert plan["limits"]["new_simulations"] == plan["limits"]["new_extractions"] == 0
    assert not plan["claim_spent"] and not plan["remote_contact"]
    assert not plan["execution_authorized"] and not plan["qualification_established"]
    assert path.read_bytes() == original
    assert not context.binding.analysis_journal.exists()
    assert not context.binding.sweep_journal.exists() and not context.lock_path.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "reserved_journal"])
def test_exclusive_output_never_replaces_existing_or_reserved_state(registered, tmp_path, kind):
    context, path, design, analysis = selection(registered)
    output = tmp_path / "retained"
    if kind == "file":
        output.write_bytes(b"existing operator evidence")
    elif kind == "directory":
        output.mkdir()
        (output / "existing.txt").write_bytes(b"existing operator evidence")
    else:
        output = context.binding.analysis_journal
    with pytest.raises(OperationRejected) as failure:
        prepare(context, path, design, analysis, output)
    assert failure.value.reason == "binding_observation_exclusive_output_required"
    if kind == "file":
        assert output.read_bytes() == b"existing operator evidence"
    elif kind == "directory":
        assert (output / "existing.txt").read_bytes() == b"existing operator evidence"
        assert len(list(output.iterdir())) == 1
    else:
        assert not output.exists()


@pytest.mark.parametrize("field", ["design", "analysis"])
def test_missing_selected_route_rejects_before_output(registered, tmp_path, field):
    context, path, design, analysis = selection(registered)
    with pytest.raises(OperationRejected) as failure:
        prepare(
            context, path, "unregistered" if field == "design" else design,
            "unregistered" if field == "analysis" else analysis, tmp_path / "output",
        )
    assert failure.value.reason == "binding_observation_registered_route_required"
    assert not (tmp_path / "output").exists()


def test_registration_drift_before_publication_leaves_no_output(registered, tmp_path, monkeypatch):
    from cadence_mcp_bridge import binding_observer_operator as host

    context, path, design, analysis = selection(registered)
    read = host.read_candidate_document
    calls = []

    def changed(selected):
        raw = read(selected)
        calls.append(selected)
        return raw if len(calls) == 1 else raw + b"\n"

    monkeypatch.setattr(host, "read_candidate_document", changed)
    with pytest.raises(OperationRejected) as failure:
        prepare(context, path, design, analysis, tmp_path / "output")
    assert failure.value.reason == "binding_observation_preparation_drift"
    assert not (tmp_path / "output").exists()


def test_changed_package_pin_rejects_before_publication(registered, tmp_path, monkeypatch):
    from cadence_mcp_bridge import binding_observer_operator as host

    context, path, design, analysis = selection(registered)
    pins = host.asset_pins()
    calls = []

    def changed():
        calls.append(None)
        return pins if len(calls) == 1 else {**pins, ASSETS[0]: "0" * 64}

    monkeypatch.setattr(host, "asset_pins", changed)
    with pytest.raises(OperationRejected) as failure:
        prepare(context, path, design, analysis, tmp_path / "output")
    assert failure.value.reason == "binding_observation_preparation_drift"
    assert not (tmp_path / "output").exists()


def test_new_local_id_does_not_claim_an_additional_attempt(registered, tmp_path):
    context, path, design, analysis = selection(registered)
    first = prepare(context, path, design, analysis, tmp_path / "first")
    second = prepare(context, path, design, analysis, tmp_path / "second")
    assert first["request_sha256"] != second["request_sha256"]
    assert not first["claim_spent"] and not second["claim_spent"]
    assert not context.lock_path.exists()


def test_cli_exposes_local_preparation_only_and_does_not_construct_backend(monkeypatch, capsys):
    import subprocess

    from cadence_mcp_bridge.runtime_context import ExecutionContext

    def forbidden(*args, **kwargs):
        pytest.fail("schema must not contact an execution backend")

    monkeypatch.setattr(ExecutionContext, "backend", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert main(["operator-binding-observation", "schema"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["operational_status"] == "CAPABILITY_NOT_QUALIFIED"
    assert report["blockers"] == list(BLOCKERS)
    assert not report["remote_contact"] and not report["execution_authorized"]
    with pytest.raises(SystemExit) as failure:
        main(["operator-binding-observation", "observe"])
    assert failure.value.code == 2


def test_no_variables_cannot_generate_a_meaningless_observation(registered, tmp_path):
    context, path, design, analysis = selection(registered)
    registry = context.contracts.designs
    # Projection is separately tested against real closed contracts. This seam
    # targets the observer's complete inventory check before any output write.
    class MissingVariables:
        def variable_set(self, _):
            return None

        def profile(self, selected):
            return registry.profile(selected)

    from unittest.mock import patch

    import cadence_mcp_bridge.binding_observer_operator as host

    altered = replace(context, contracts=replace(context.contracts, designs=MissingVariables()))
    with (
        patch.object(host, "projection", return_value={}),
        pytest.raises(OperationRejected) as failure,
    ):
        prepare(altered, path, design, analysis, tmp_path / "output")
    assert failure.value.reason == "binding_observation_complete_va_inventory_required"
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("kind", ["analysis_journal", "sweep_journal", "lock_path"])
def test_cli_rejects_other_context_reserved_missing_paths(
    registered, tmp_path, monkeypatch, capsys, kind,
):
    from cadence_mcp_bridge import binding_observer_operator as host

    context, path, design, analysis = selection(registered)
    other = replace(
        context,
        binding=context.binding.model_copy(update={
            "context_id": "other-context",
            "analysis_journal": tmp_path / "other-analysis.sqlite",
            "sweep_journal": tmp_path / "other-sweep.sqlite",
        }),
        resource_domain_sha256="d" * 64,
    )
    output = other.lock_path if kind == "lock_path" else getattr(other.binding, kind)
    assert not output.exists()
    monkeypatch.setattr(host, "load_runtime", lambda _: (context, other))
    assert main([
        "operator-binding-observation", "prepare", "--settings", str(tmp_path / "runtime.json"),
        "--context", context.binding.context_id, "--registration", str(path),
        "--design-id", design, "--analysis-id", analysis, "--output", str(output),
    ]) == 1
    result = json.loads(capsys.readouterr().out)
    assert not result["remote_contact"] and not output.exists()


def test_output_names_are_pinned_or_replacement_is_rejected(tmp_path):
    from cadence_mcp_bridge import binding_observer_operator as host

    output = tmp_path / "exclusive-output"
    output.mkdir(mode=0o700)
    parents = {path: host._directory_identity(path) for path in output.parents}
    detached = tmp_path / "retained-detached"
    if os.name == "nt":
        with host._held_output(output, parents) as (_, guard):
            with pytest.raises(PermissionError):
                output.rename(detached)
            guard()
        assert output.is_dir() and not detached.exists()
    else:
        with (
            pytest.raises(OperationRejected) as failure,
            host._held_output(output, parents) as (_, guard),
        ):
            output.rename(detached)
            output.mkdir(mode=0o700)
            guard()
        assert failure.value.reason == "binding_observation_output_namespace_drift"
        assert not list(output.iterdir()) and detached.is_dir()


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory-fd anchored creation")
def test_detached_output_cannot_redirect_file_creation(registered, tmp_path, monkeypatch):
    from cadence_mcp_bridge import binding_observer_operator as host

    context, path, design, analysis = selection(registered)
    output, detached = tmp_path / "output", tmp_path / "detached"
    real_open = os.open
    attacked = []

    def exchange(name, flags, mode=0o777, **kwargs):
        if name == "binding-plan.private.json" and not attacked:
            attacked.append(True)
            output.rename(detached)
            output.mkdir(mode=0o700)
        return real_open(name, flags, mode, **kwargs)

    monkeypatch.setattr(host.os, "open", exchange)
    with pytest.raises(OperationRejected) as failure:
        prepare(context, path, design, analysis, output)
    assert failure.value.reason == "binding_observation_output_namespace_drift"
    assert not list(output.iterdir())
    assert (detached / "binding-plan.private.json").read_bytes() == b""
