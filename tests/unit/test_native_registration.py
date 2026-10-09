"""Read-only enrollment provenance; synthetic transport is never actual VM proof."""

import hashlib
import json
import os
from unittest.mock import Mock

import pytest
from test_generic_measurements import operator as operator_fixture
from test_operator_operations import operator as operator_base

from cadence_mcp_bridge import _native_copy as copying
from cadence_mcp_bridge import _registration_probe as probe
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.native_registration import (
    RegistrationProbeRequest,
    assemble,
    observe,
    operator_observe,
    prepared,
)
from cadence_mcp_bridge.operator_operations import OperationRejected

operator = operator_fixture
__all__ = ["operator_base"]


@pytest.fixture
def enrollment(operator, tmp_path):
    context, _, request, _ = operator
    workspace = context.contracts.environment.paths.workspace_root
    profile = context.contracts.designs.profile(request.design_id)
    source = workspace + "/" + profile.binding.library
    baseline = tmp_path / "baseline.scs"
    baseline.write_text(
        "simulator lang=spectre\n"
        "parameters ExampleBiasN=1 ExampleBiasP=1\n"
        "R1 (n 0) resistor r=1000\n"
        'dcOp dc write="spectre.dc" annotate=status\n',
        encoding="ascii",
    )
    raw = dict(
        schema_version=1,
        validation_request=request.model_dump(mode="json"),
        source_cell=source + "/" + profile.binding.cell,
        source_state=workspace + "/saved-state",
        libraries=[dict(name=profile.binding.library, path=source)],
        model_includes=[],
        inputs=dict(analysis="dc", mode="saved_operating_point"),
        baseline_netlist=str(baseline),
    )
    return context, RegistrationProbeRequest.model_validate_json(json.dumps(raw)), baseline


def receipt(request):
    return dict(
        schema_version=1,
        status="REGISTRATION_FINGERPRINTS_OBSERVED",
        operator_uid=500,
        source_tree_sha256="a" * 64,
        ade_state_tree_sha256="b" * 64,
        libraries=[dict(name=v.name, path=v.path, tree_sha256="c" * 64) for v in request.libraries],
        model_files=[],
        entries=3,
        content_bytes=10,
        new_simulations=0,
        new_reservations=0,
        execution_authorized=False,
    )


def test_baseline_partition_and_registration_no_authority(enrollment, monkeypatch):
    context, request, baseline = enrollment
    remote, ade, sha = prepared(context, request)
    assert (
        ade["inputs"]["statement_sha256"]
        == hashlib.sha256(b'dc write="spectre.dc" annotate=status').hexdigest()
    )
    assert sha == hashlib.sha256(baseline.read_bytes()).hexdigest()
    transport = Mock(return_value=(0, json.dumps(receipt(request)).encode(), b""))
    monkeypatch.setattr("cadence_mcp_bridge.native_registration.run_fixed", transport)
    monkeypatch.setattr("cadence_mcp_bridge.native_registration._ssh", lambda _: ["fixed-ssh"])
    result = observe(context, request)
    assert result["ade"]["design_id"] == request.validation_request.design_id
    assert not result["execution_authorized"] and result["new_reservations"] == 0
    assert not context.binding.analysis_journal.exists()
    argv, raw, _ = transport.call_args.args
    payload = json.loads(raw)
    assert payload["request"] == remote and set(payload["assets"]) == {"copying", "modeltrust"}
    assert str(baseline) not in raw.decode() and "R1" not in json.dumps(result)
    assert "StrictHostKeyChecking=no" not in str(argv)


@pytest.mark.parametrize("change", ["parameters", "dc_sweep", "extra_analysis", "unsafe_static"])
def test_baseline_mismatch_never_contacts_vm(enrollment, monkeypatch, change):
    context, request, baseline = enrollment
    text = baseline.read_text(encoding="ascii")
    if change == "parameters":
        text = text.replace("ExampleBiasN=1", "ExampleBiasN=2")
    elif change == "dc_sweep":
        text = text.replace('write="spectre.dc"', "param=ExampleBiasN start=0 stop=1")
    elif change == "extra_analysis":
        text += "acAnalysis ac start=10 stop=100 dec=3\n"
    else:
        text += 'verilogA include "outside"\n'
    baseline.write_text(text, encoding="ascii")
    transport = Mock()
    monkeypatch.setattr("cadence_mcp_bridge.native_registration.run_fixed", transport)
    with pytest.raises((OperationRejected, ValueError)):
        observe(context, request)
    transport.assert_not_called()


def test_baseline_changed_during_observation_and_response_binding_reject(enrollment, monkeypatch):
    context, request, baseline = enrollment
    monkeypatch.setattr("cadence_mcp_bridge.native_registration._ssh", lambda _: ["fixed-ssh"])

    def changed(*args, **kwargs):
        baseline.write_bytes(baseline.read_bytes() + b"// drift\n")
        return 0, json.dumps(receipt(request)).encode(), b""

    monkeypatch.setattr("cadence_mcp_bridge.native_registration.run_fixed", changed)
    with pytest.raises(OperationRejected) as error:
        observe(context, request)
    assert error.value.reason == "registration_baseline_changed"


def test_private_exclusive_output_preserved(enrollment, tmp_path, monkeypatch):
    context, request, _ = enrollment
    path = tmp_path / "request.json"
    path.write_text(request.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(
        "cadence_mcp_bridge.native_registration.observe",
        lambda *_: dict(
            receipt(request), status="REGISTRATION_FINGERPRINTS_PREPARED_NOT_AUTHORIZED"
        ),
    )
    output = tmp_path / "private.json"
    result = operator_observe(context, path, output)
    assert result["new_simulations"] == 0 and str(output) not in json.dumps(result)
    before = output.read_bytes()
    with pytest.raises(OperationRejected):
        operator_observe(context, path, output)
    assert output.read_bytes() == before


def test_schema_and_bad_cli_are_safe(capsys):
    assert main(["native-registration", "schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["additionalProperties"] is False


@pytest.mark.skipif(os.name != "posix", reason="actual POSIX source/no-follow observation")
def test_fixed_collector_preserves_content_metadata_and_rejects_busy_source(tmp_path, monkeypatch):
    import pwd
    import socket

    from cadence_mcp_bridge import _installation_repair as modeltrust

    monkeypatch.setattr(os, "getuid", lambda: 500)
    monkeypatch.setattr(pwd, "getpwuid", lambda _: Mock(pw_name="qa"))
    library = tmp_path / "Lib"
    library.mkdir()
    source = library / "Cell"
    source.mkdir()
    (source / "sch.oa").write_bytes(b"synthetic")
    state = tmp_path / "State"
    state.mkdir()
    (state / "state").write_bytes(b"synthetic")
    request = dict(
        hostname=socket.gethostname(),
        user="qa",
        workspace_root=str(tmp_path),
        managed_root=str(tmp_path / "managed"),
        protected_roots=[],
        source_cell=str(source),
        source_state=str(state),
        libraries=[dict(name="Lib", path=str(library))],
        model_includes=[],
    )
    before = copying.snapshot(str(source))
    result = probe.collect(request, copying, modeltrust)
    assert result["source_tree_sha256"] == before["tree_sha256"]
    assert copying.snapshot(str(source)) == before
    (source / "sch.oa.cdslck").write_bytes(b"held")
    with pytest.raises(ValueError, match="active_or_recovery"):
        probe.collect(request, copying, modeltrust)
    assert (source / "sch.oa.cdslck").read_bytes() == b"held"


@pytest.fixture
def assembly(enrollment, tmp_path, monkeypatch):
    context, request, _ = enrollment
    monkeypatch.setattr("cadence_mcp_bridge.native_registration._ssh", lambda _: ["fixed-ssh"])
    monkeypatch.setattr(
        "cadence_mcp_bridge.native_registration.run_fixed",
        lambda *args, **kwargs: (0, json.dumps(receipt(request)).encode(), b""),
    )
    record = observe(context, request)
    definition = dict(
        measurement_id="dc-output",
        nodes=[dict(logical_id="out", selector="/out")],
        sources=[],
        transfer=None,
        maximum_samples=10,
    )
    paths = [tmp_path / (name + ".json") for name in ("request", "record", "reader")]
    for path, value in zip(
        paths, (request.model_dump(mode="json"), record, definition), strict=True
    ):
        path.write_text(json.dumps(value), encoding="utf-8")
    return context, paths, tmp_path / "registration.json"


def test_assemble_binds_all_contracts_and_preserves_private_output(assembly):
    from cadence_mcp_bridge.native_runtime import NativeRegistration, projection
    from cadence_mcp_bridge.variable_contracts import canonical_digest

    context, paths, target = assembly
    result = assemble(context, [paths[0]], [paths[1]], [paths[2]], "d" * 64, target)
    registration = NativeRegistration.model_validate_json(target.read_bytes())
    route = registration.routes[0]
    assert route.reader.ade_registration_sha256 == canonical_digest(route.ade)
    assert len(projection(context, registration)["routes"]) == 1
    assert result["routes"] == 1 and result["remote_contact"] is False
    assert result["new_reservations"] == 0 and not context.binding.analysis_journal.exists()
    before = target.read_bytes()
    with pytest.raises(OperationRejected):
        assemble(context, [paths[0]], [paths[1]], [paths[2]], "d" * 64, target)
    assert target.read_bytes() == before


@pytest.mark.parametrize(
    "change", ["baseline", "source", "profile", "authority", "reader", "extra", "bool"]
)
def test_assemble_rejects_mismatched_observations_before_output(assembly, change):
    context, paths, target = assembly
    record = json.loads(paths[1].read_bytes())
    if change == "baseline":
        record["baseline_input_sha256"] = "e" * 64
    elif change == "source":
        record["source_cell"] += "-other"
    elif change == "profile":
        record["ade"]["design_profile_sha256"] = "e" * 64
    elif change == "authority":
        record["execution_authorized"] = True
    elif change == "extra":
        record["ignored_content"] = "unregistered"
    elif change == "bool":
        record["new_simulations"] = False
    else:
        reader = json.loads(paths[2].read_bytes())
        reader["measurement_id"] = "ac-gain"
        paths[2].write_text(json.dumps(reader), encoding="utf-8")
    paths[1].write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError):
        assemble(context, [paths[0]], [paths[1]], [paths[2]], "d" * 64, target)
    assert not target.exists()
