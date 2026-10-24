"""Synthetic host orchestration and retained reads; no VM, EDA or real authority."""

import json
from types import SimpleNamespace

import pytest
from test_binding_observation_admission import documents as synthetic_documents
from test_binding_observation_admission import encoded as synthetic_encoded
from test_binding_observation_transport import terminal as synthetic_terminal
from test_native_runtime import operator, operator_base, registered
from test_physical_metadata import current_account_owner

from cadence_mcp_bridge import binding_observation_bootstrap as factory
from cadence_mcp_bridge import binding_observation_claim as claims
from cadence_mcp_bridge import binding_observation_transport as transport
from cadence_mcp_bridge import binding_observer_operator as host
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.binding_observation import BindingScanRequest
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.native_runtime import projection
from cadence_mcp_bridge.operator_operations import OperationRejected

__all__ = ["operator", "operator_base", "registered"]


@pytest.fixture(autouse=True)
def ordinary_account_output_owner():
    with current_account_owner():
        yield


def forbidden(*args, **kwargs):
    pytest.fail("no claim, transport or simulation is permitted at this boundary")


@pytest.fixture
def case(registered, tmp_path):
    context, registration, path = registered
    route = registration.routes[0]
    design, analysis = route.ade.design_id, route.ade.analysis_id
    prepared = tmp_path / "p"
    result = host.prepare(context, path, design, analysis, prepared)
    plan = json.loads((prepared / "binding-plan.private.json").read_bytes())
    request = BindingScanRequest.model_validate_json(
        (prepared / "binding-request.private.json").read_bytes(),
    )
    pins = host.asset_pins()
    documents = host._execution_documents(
        context, projection(context, registration), request, pins, design, analysis,
    )
    worker = factory.construct_worker(*documents)
    admission, manifest_raw, closure = synthetic_documents(worker)
    admission.update(
        prepared_plan_sha256=result["plan_sha256"],
        package_sha256=host._sha(_canonical(pins)),
        resource_domain_sha256=context.resource_domain_sha256,
        identity_manifest_sha256=registration.identity_manifest_sha256,
    )
    admission_raw, manifest_raw, closure_raw = synthetic_encoded(admission, manifest_raw, closure)
    inputs = {}
    for name, raw in (("a", admission_raw), ("m", manifest_raw), ("c", closure_raw)):
        selected = tmp_path / (name + ".json")
        selected.write_bytes(raw)
        selected.chmod(0o600)
        inputs[name] = selected
    return SimpleNamespace(
        context=context, registration=path, prepared=prepared, plan=plan, request=request,
        expected_plan=result["plan_sha256"], expected_admission=host._sha(admission_raw),
        admission=admission, inputs=inputs, documents=documents, tmp=tmp_path,
    )


def execute(case, output):
    return host.run(
        case.context, case.registration, case.prepared, case.expected_plan,
        case.inputs["a"], case.expected_admission, case.inputs["m"], case.inputs["c"], output,
    )


def one_shot_dispatch(case, monkeypatch, *, response=None):
    """A disposable account claim stub, deliberately independent of output paths."""
    events = []
    marker = case.tmp / "campaign-spent.json"

    def claim(environment, predecessor, evidence):
        events.append("claim")
        assert environment == case.context.contracts.environment
        assert predecessor == case.admission["predecessor"]
        assert evidence["plan_sha256"] == case.expected_plan
        assert evidence["request_sha256"] == case.plan["request_sha256"]
        assert evidence["approval_receipt_sha256"] == case.admission["approval_receipt_sha256"]
        with marker.open("xb") as stream:
            stream.write(_canonical(evidence))

    def dispatch(environment, envelope, expected_payload, worker_sha256, helper_pins):
        events.append("dispatch")
        assert marker.is_file() and events[-2] == "claim"
        assert environment == case.context.contracts.environment
        assert expected_payload == host._sha(envelope)
        assert worker_sha256 == case.plan["package_asset_lf_sha256"]["_binding_observation.py"]
        assert helper_pins == {name: pin for name, (_, pin) in factory._HELPERS.items()}
        value = synthetic_terminal(envelope)
        return (0, _canonical(value), b"") if response is None else response(value, envelope)

    monkeypatch.setattr(claims, "claim", claim)
    monkeypatch.setattr(transport, "dispatch", dispatch)
    return events, marker


def test_pretty_originals_survive_single_dispatch_retained_reads_and_spent_retry(
    case, monkeypatch,
):
    original = case.registration.read_bytes()
    assert original != _canonical(json.loads(original))
    profile = case.context.binding.environment_profile
    profile_original = profile.read_bytes()
    events, marker = one_shot_dispatch(case, monkeypatch)
    output = case.tmp / "o"
    result = execute(case, output)
    assert result["status"] == "PROCESS_COMPLETED" and result["qualification_established"] is False
    assert events == ["claim", "dispatch"]
    spent = marker.read_bytes()
    for _ in range(2):
        assert host.read_result(output, case.expected_admission) == result
    assert events == ["claim", "dispatch"]
    with pytest.raises(FileExistsError):
        execute(case, case.tmp / "new-output")
    assert events == ["claim", "dispatch", "claim"] and marker.read_bytes() == spent
    assert case.registration.read_bytes() == original and profile.read_bytes() == profile_original
    assert not case.context.binding.analysis_journal.exists()
    assert not case.context.binding.sweep_journal.exists() and not case.context.lock_path.exists()


@pytest.mark.parametrize("target", ["plan", "admission", "manifest", "closure", "request",
                                    "collector", "registration", "package"])
def test_every_prepared_and_external_pin_rejects_before_claim_or_contact(
    case, monkeypatch, target,
):
    monkeypatch.setattr(claims, "claim", forbidden)
    monkeypatch.setattr(transport, "dispatch", forbidden)
    if target == "package":
        pins = host.asset_pins()
        monkeypatch.setattr(
            host, "asset_pins", lambda: {**pins, "_binding_observation.py": "f" * 64},
        )
    else:
        selected = {
            "plan": case.prepared / "binding-plan.private.json",
            "admission": case.inputs["a"], "manifest": case.inputs["m"],
            "closure": case.inputs["c"],
            "request": case.prepared / "binding-request.private.json",
            "collector": case.prepared / "collector.ocn", "registration": case.registration,
        }[target]
        selected.write_bytes(selected.read_bytes() + b"\n")
    with pytest.raises((ValueError, OSError)):
        execute(case, case.tmp / "o")


@pytest.mark.parametrize("target", ["admission", "manifest", "registration", "package"])
def test_last_input_recheck_detects_drift_before_spending_claim(case, monkeypatch, target):
    monkeypatch.setattr(claims, "claim", forbidden)
    monkeypatch.setattr(transport, "dispatch", forbidden)
    original = transport.build_payload

    def changed(*arguments):
        payload = original(*arguments)
        if target == "package":
            pins = host.asset_pins()
            monkeypatch.setattr(
                host, "asset_pins", lambda: {**pins, "_binding_observation.py": "f" * 64},
            )
        else:
            selected = {"admission": case.inputs["a"], "manifest": case.inputs["m"],
                        "registration": case.registration}[target]
            selected.write_bytes(selected.read_bytes() + b"\n")
        return payload

    monkeypatch.setattr(transport, "build_payload", changed)
    with pytest.raises(OperationRejected) as failure:
        execute(case, case.tmp / "o")
    assert failure.value.reason == "binding_observation_predispatch_drift"
    assert not (case.tmp / "o" / "started.private.json").exists()


@pytest.mark.parametrize("status", ["REJECTED", "FAILED", "TIMED_OUT", "UNKNOWN"])
def test_valid_negative_terminal_is_retained_and_read_never_reexecutes(case, monkeypatch, status):
    def response(value, envelope):
        value.update(status=status, frame=None, frame_sha256=None, returncode=None,
                     originals_preserved=False, cleanup_complete=False,
                     failure_code="binding_observation_synthetic_failure")
        return 0, _canonical(value), b""

    events, marker = one_shot_dispatch(case, monkeypatch, response=response)
    output = case.tmp / "o"
    value = execute(case, output)
    assert value["status"] == status and value["retry_permitted"] is False
    assert host.read_result(output, case.expected_admission) == value
    assert events == ["claim", "dispatch"] and marker.exists()
    assert not (output / "failed.private.json").exists()


@pytest.mark.parametrize("failure", ["nonzero", "stderr", "lost_reply", "invalid_frame",
                                     "wrong_identity", "invalid_json"])
def test_failed_or_ambiguous_dispatch_preserves_spent_claim_and_all_received_bytes(
    case, monkeypatch, failure,
):
    received = {}

    def response(value, envelope):
        if failure == "lost_reply":
            raise ValueError("synthetic transport timeout unknown")
        code, stderr = (1 if failure == "nonzero" else 0), (
            b"bounded synthetic stderr" if failure == "stderr" else b""
        )
        if failure == "invalid_frame":
            value["frame"] = value["frame"].replace("COMPLETE|", "INCOMPLETE|")
            value["frame_sha256"] = host._sha(value["frame"].encode("ascii"))
        elif failure == "wrong_identity":
            value["request_sha256"] = "0" * 64
        stdout = b"{" if failure == "invalid_json" else _canonical(value)
        received.update(stdout=stdout, stderr=stderr)
        return code, stdout, stderr

    events, marker = one_shot_dispatch(case, monkeypatch, response=response)
    output = case.tmp / "o"
    with pytest.raises(OperationRejected) as error:
        execute(case, output)
    assert error.value.reason == "binding_observation_failed_or_unknown_no_retry"
    assert events == ["claim", "dispatch"] and marker.exists()
    assert json.loads((output / "started.private.json").read_bytes())["status"] == (
        "ATTEMPT_SPENT_NO_RETRY")
    failed = json.loads((output / "failed.private.json").read_bytes())
    assert failed["status"] == "FAILED_OR_UNKNOWN_NO_RETRY" and failed["retry_permitted"] is False
    assert not (output / "terminal.private.json").exists()
    if received:
        assert (output / "stdout.private.json").read_bytes() == received["stdout"]
        assert (output / "stderr.private.log").read_bytes() == received["stderr"]
    with pytest.raises(FileExistsError):
        execute(case, case.tmp / "another-output")
    assert events == ["claim", "dispatch", "claim"]


def test_retained_read_rejects_wrong_external_admission_without_any_execution(case, monkeypatch):
    events, _ = one_shot_dispatch(case, monkeypatch)
    output = case.tmp / "o"
    execute(case, output)
    monkeypatch.setattr(claims, "claim", forbidden)
    monkeypatch.setattr(transport, "dispatch", forbidden)
    with pytest.raises(OperationRejected) as failure:
        host.read_result(output, "0" * 64)
    assert failure.value.reason == "binding_observation_external_approval_digest"
    assert events == ["claim", "dispatch"]


@pytest.mark.parametrize("target", ["terminal", "payload"])
def test_retained_read_authenticates_terminal_and_payload_without_new_execution(
    case, monkeypatch, target,
):
    events, _ = one_shot_dispatch(case, monkeypatch)
    output = case.tmp / "o"
    execute(case, output)
    selected = output / (target + ".private.json")
    value = json.loads(selected.read_bytes())
    if target == "terminal":
        value["request_sha256"] = "0" * 64
    else:
        request = json.loads(value["documents"]["request"])
        request["cell"] = "DifferentCell"
        value["documents"]["request"] = _canonical(request).decode("ascii")
    selected.write_bytes(_canonical(value))
    monkeypatch.setattr(claims, "claim", forbidden)
    monkeypatch.setattr(transport, "dispatch", forbidden)
    monkeypatch.setattr(factory, "construct_worker", forbidden)
    with pytest.raises(ValueError):
        host.read_result(output, case.expected_admission)
    assert events == ["claim", "dispatch"]


def test_retained_read_does_not_depend_on_current_package_or_runtime(case, monkeypatch):
    events, _ = one_shot_dispatch(case, monkeypatch)
    output = case.tmp / "o"
    result = execute(case, output)
    monkeypatch.setattr(claims, "claim", forbidden)
    monkeypatch.setattr(transport, "dispatch", forbidden)
    monkeypatch.setattr(transport, "_installed", forbidden)
    monkeypatch.setattr(factory, "construct_worker", forbidden)
    monkeypatch.setattr(host, "load_runtime", forbidden)
    assert host.read_result(output, case.expected_admission) == result
    assert events == ["claim", "dispatch"]


def cli_base(case, action, output):
    return [
        "operator-binding-observation", action, "--settings", str(case.tmp / "runtime.json"),
        "--context", case.context.binding.context_id, "--registration", str(case.registration),
        "--output", str(output),
    ]


def test_schema_and_prepare_cli_never_claim_or_dispatch(case, monkeypatch, capsys):
    monkeypatch.setattr(claims, "claim", forbidden)
    monkeypatch.setattr(transport, "dispatch", forbidden)
    monkeypatch.setattr(host, "load_runtime", lambda path: (case.context,))
    assert main(["operator-binding-observation", "schema"]) == 0
    assert json.loads(capsys.readouterr().out)["remote_contact"] is False
    assert main([
        *cli_base(case, "prepare", case.tmp / "cli-plan"), "--design-id", case.plan["design_id"],
        "--analysis-id", case.plan["analysis_id"],
    ]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["remote_contact"] is False and value["claim_spent"] is False


def test_cli_run_uses_same_once_only_operation_and_result_needs_no_runtime(
    case, monkeypatch, capsys,
):
    monkeypatch.setattr(host, "load_runtime", lambda path: (case.context,))
    events, _ = one_shot_dispatch(case, monkeypatch)
    output = case.tmp / "cli-output"
    assert main([
        *cli_base(case, "run", output), "--prepared", str(case.prepared),
        "--expected-plan", case.expected_plan, "--admission", str(case.inputs["a"]),
        "--expected-admission", case.expected_admission, "--manifest", str(case.inputs["m"]),
        "--attestation", str(case.inputs["c"]),
    ]) == 0
    executed = json.loads(capsys.readouterr().out)
    assert executed["status"] == "PROCESS_COMPLETED" and events == ["claim", "dispatch"]
    monkeypatch.setattr(host, "load_runtime", forbidden)
    monkeypatch.setattr(claims, "claim", forbidden)
    monkeypatch.setattr(transport, "dispatch", forbidden)
    assert main([
        "operator-binding-observation", "result", "--output", str(output),
        "--expected-admission", case.expected_admission,
    ]) == 0
    assert json.loads(capsys.readouterr().out) == executed


def test_run_cli_requires_exact_inputs_instead_of_implying_prepare_authority(capsys):
    with pytest.raises(SystemExit) as failure:
        main(["operator-binding-observation", "run"])
    assert failure.value.code == 2
    assert "--expected-admission" in capsys.readouterr().err
