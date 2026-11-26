"""Three disposable MOS points through original edit and DC receipt projections."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_generic_measurements import frame_for, reader_for
from test_generic_measurements import operator as measurement_operator  # noqa: F401
from test_operator_operations import operator as operator_base  # noqa: F401
from test_registered_mos_edit import _cdf_frame
from test_registered_mos_sizing import _fixture, _length, _Provider

from cadence_mcp_bridge._native_rendering import partition_input, static_fingerprint
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.authenticated_provider import (
    ExtractionReceipt,
    NativeResultPayload,
    TerminalEvent,
    verify_native_result,
)
from cadence_mcp_bridge.candidate_execution import PmosDcOperation
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.environments import EnvironmentProfile
from cadence_mcp_bridge.generic_ade import ModelInclude
from cadence_mcp_bridge.generic_measurements import render_reader
from cadence_mcp_bridge.mos_dc_evaluation import (
    MosDcEvidence,
    MosDcRoute,
    capture_mos_dc,
    read_mos_dc,
    submit_mos_dc,
    validate_mos_dc_batch,
)
from cadence_mcp_bridge.native_runtime import KIND
from cadence_mcp_bridge.native_service import NativeOperationQuery
from cadence_mcp_bridge.operator_operations import OperationProgress
from cadence_mcp_bridge.registered_mos_sizing import (
    MosSizingValues,
    RegisteredMosSizingService,
    plan_registered_mos_sizing,
)
from cadence_mcp_bridge.result_reports import make_report
from cadence_mcp_bridge.variable_contracts import canonical_digest


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _dc_input(raw, model_path):
    return (
        raw.replace(b"VDD=1", b"ExampleBiasN=1 ExampleBiasP=1")
        + f'include "{model_path}" section=nn\n'.encode()
        + b"VDD (vdd 0) vsource dc=1\nsimulatorOptions options temp=27\n"
        + b"analysis0 dc save=all\n"
    )


def _electrical_drift(raw, drift):
    changes = {
        "temperature": (b"temp=27", b"temp=50"),
        "supply": (b"vsource dc=1", b"vsource dc=1.2"),
        "input": (b"ExampleBiasN=1", b"ExampleBiasN=0"),
    }
    if drift in changes:
        before, after = changes[drift]
        assert raw.count(before) == 1
        return raw.replace(before, after)
    return raw


def _point(registered, length, index, *, baseline_route=False, drift=None):
    context, plan, ade, reader, _, _ = registered
    sizing, child, _, _, original_binding, before, capture = _fixture()
    model_path = context.contracts.environment.paths.protected_roots[0] + "/model.scs"
    model = ModelInclude(
        path=model_path, section="nn", file_sha256=("c" if drift == "model" else "b") * 64
    )
    old, new = _dc_input(before, model_path), _dc_input(capture.netlist, model_path)
    new = new.replace(b"l=2.5e-7", f"l={length}n".encode())
    revision = _sha(f"synthetic revision {index}".encode())
    child = child.model_copy(update={"revision_id": f"edit-{index}"})
    sizing = sizing.model_copy(
        update={
            "baseline": sizing.baseline.model_copy(update={"netlist_sha256": _sha(old)}),
        }
    )
    requested = MosSizingValues(l=_length(length))
    change = plan_registered_mos_sizing(sizing, child, requested)
    binding = original_binding.model_copy(
        update={
            "operation_id": str(uuid4()),
            "owned_copy_operation_id": str(uuid4()),
            "plan_sha256": change.plan_sha256,
            "route_sha256": change.route_sha256,
        }
    )
    properties = capture.readback.reopened.properties.copy()
    properties["l"] = properties["l"].model_copy(
        update={"oa_value": f"{length}n", "cdf_value": f"{length}n"}
    )
    frame = _cdf_frame("nmos1v", properties, "MN")
    snapshot = {"revision_sha256": revision, "properties": properties}
    observed = capture.readback.model_copy(
        update={
            "operation_id": binding.operation_id,
            "plan_sha256": binding.plan_sha256,
            "saved": capture.readback.saved.model_copy(update=snapshot),
            "reopened": capture.readback.reopened.model_copy(update=snapshot),
            "netlisted_revision_sha256": revision,
            "netlist_sha256": _sha(new),
            "cdf_frame_sha256": _sha(frame),
        }
    )
    provider = _Provider(replace(capture, readback=observed, netlist=new, cdf_frame=frame))
    service = RegisteredMosSizingService(
        binding,
        sizing,
        child,
        requested,
        old,
        provider,
        expected_binding_sha256=canonical_digest(binding),
    )
    assert service.apply(service.identity).outcome == "VERIFIED"
    replay = service.lookup(service.identity)
    assert replay.outcome == "VERIFIED" and provider.dispatches == 1
    raw_edit = replay.model_dump_json().encode()

    profile = context.contracts.designs.profile(plan.request.design_id)
    variables = context.contracts.designs.variable_set(plan.request.design_id)
    assert variables is not None
    ade = ade.model_copy(
        update={
            "static_statements_sha256": static_fingerprint(
                partition_input(_electrical_drift(old, drift) if baseline_route else new)[3]
            ),
            "model_includes": (model,),
            "source_tree_sha256": _sha(f"owned bench {index}".encode()),
            "ade_state_tree_sha256": "2" * 64
            if baseline_route
            else _sha(f"copied ADE {index}".encode()),
        }
    )
    reader = reader.model_copy(update={"ade_registration_sha256": canonical_digest(ade)})
    if drift == "reader":
        reader = reader.model_copy(
            update={
                "nodes": (
                    reader.nodes[0],
                    reader.nodes[1].model_copy(update={"selector": "/other"}),
                ),
            }
        )
    library = f"/synthetic/owned-{index}"
    export = dict(
        status="OWNED_INPUT_COPY_VERIFIED",
        edit_operation_id=binding.operation_id,
        edit_scope_sha256=binding.scope_sha256,
        owned_copy_operation_id=binding.owned_copy_operation_id,
        source_preservation_sha256=binding.source_preservation_sha256,
        source_revision_sha256=revision,
        testbench_revision_sha256=observed.netlisted_testbench_revision_sha256,
        reopen_receipt_sha256=observed.reopened.receipt_sha256,
        netlist_receipt_sha256=observed.netlist_receipt_sha256,
        netlist_sha256=_sha(new),
        source_cell=library + "/" + profile.binding.cell,
        source_state=library + "/ade",
        library_path=library,
        dependency_tree_sha256=_sha(library.encode()),
        source_cell_sha256=ade.source_tree_sha256,
        source_state_sha256=ade.ade_state_tree_sha256,
        source_ade_sha256="2" * 64,
    )
    route = dict(
        analysis="dc",
        design_id=plan.request.design_id,
        analysis_id=plan.request.analysis_id,
        source_cell=export["source_cell"],
        source_state=export["source_state"],
        libraries=[
            dict(
                name=profile.binding.library,
                path=library,
                tree_sha256=export["dependency_tree_sha256"],
            )
        ],
        model_files=[{"path": model.path, "file_sha256": model.file_sha256}],
        profile=profile.model_dump(mode="json"),
        variables=[item.model_dump(mode="json") for item in variables.variables],
        ade=ade.model_dump(mode="json"),
        reader=reader.model_dump(mode="json"),
    )
    registration = _canonical(
        dict(
            schema_version=1,
            environment_sha256=plan.environment_sha256,
            design_sha256=plan.design_sha256,
            pdk_sha256=plan.pdk_sha256,
            routes=[route],
        )
    )
    runtime = _canonical(
        dict(
            schema_version=3,
            kind=KIND,
            profile_sha256=plan.environment_sha256,
            registration_sha256=_sha(registration),
            files={"registration.json": dict(sha256=_sha(registration), bytes=len(registration))},
        )
    )
    plan = plan.model_copy(update={"runner_sha256": _sha(runtime)})
    context = replace(
        context, binding=context.binding.model_copy(update={"runner_sha256": _sha(runtime)})
    )
    query = NativeOperationQuery(operation_id=str(uuid4()), expected_plan_sha256=plan.plan_sha256)
    operation = PmosDcOperation(
        query, plan, runtime, registration, context.binding.design_registry.read_bytes()
    )
    exported = _canonical(export)
    evidence = MosDcEvidence(
        change,
        binding,
        raw_edit,
        _sha(raw_edit),
        old,
        new,
        MosDcRoute(context, operation, exported, _sha(exported)),
    )
    return evidence, ade, reader


def _baseline(registered, *, drift=None):
    evidence, ade, reader = _point(registered, "250", 99, baseline_route=True, drift=drift)
    original = b"// original baseline native capture\n" + _electrical_drift(
        evidence.baseline_input, drift
    )
    raw = _terminal((replace(evidence, confirmed_input=original), ade, reader), "SUCCEEDED", "1")
    context, operation = evidence.route.context, evidence.route.operation
    identity = operation.query.operation_id
    store = AnalysisStore(context.binding.analysis_journal)
    with store.connection(read_only=True, create=False) as connection:
        record = store._read_operation(connection, identity)
    data = NativeResultPayload.model_validate_json(raw)
    _, view = verify_native_result(
        context, record.plan, identity, data, include_report_conditions=True
    )
    report = make_report(record, view).model_dump_json().encode()
    return replace(
        operation,
        record=record,
        report=report,
        expected_report_sha256=_sha(report),
        expected_terminal_sha256=record.progress.provider_receipt_sha256,
        environment_profile=context.binding.environment_profile.read_bytes(),
    ), original


@pytest.mark.parametrize(
    "drift", [None, "temperature", "supply", "input", "model", "reader", "tool", "floor"]
)
def test_storage_successor_matches_only_unchanged_dc_conditions(
    measurement_operator,  # noqa: F811
    tmp_path,
    drift,
):
    registered = reader_for(measurement_operator)
    baseline, baseline_input = _baseline(registered, drift=drift)
    context, plan, *reader = registered
    document = json.loads(context.binding.environment_profile.read_bytes())
    document["limits"]["result_reserved_bytes"] += 4194304
    if drift == "floor":
        document["limits"]["disk_floor_percent"] += 1
    if drift == "tool":
        document["tools"]["spectre"]["sha256"] = "f" * 64
    raw = _canonical(document)
    path = tmp_path / "storage-successor.json"
    path.write_bytes(raw)
    new_sha = _sha(raw)
    updated = replace(
        context,
        binding=context.binding.model_copy(
            update={"environment_profile": path, "environment_sha256": new_sha}
        ),
        contracts=replace(
            context.contracts,
            environment=EnvironmentProfile.model_validate_json(raw),
            environment_sha256=new_sha,
        ),
    )
    point = _point(
        (updated, plan.model_copy(update={"environment_sha256": new_sha}), *reader), "200", 0
    )
    evidence, _, _ = point
    result = _terminal(point, "SUCCEEDED", "0.8")

    if drift in ("temperature", "supply", "input"):
        with pytest.raises(
            ValueError, match="spectre_(static_inputs|explicit_parameters)_mismatch"
        ):
            read_mos_dc(
                evidence,
                executed_input=evidence.confirmed_input,
                native_result=result,
                baseline=baseline,
                baseline_executed_input=baseline_input,
            )
        return
    comparison = read_mos_dc(
        evidence,
        executed_input=evidence.confirmed_input,
        native_result=result,
        baseline=baseline,
    )
    if drift is not None:
        assert comparison.comparison_status == "CONDITION_MISMATCH"
        assert all(item.absolute_change is None for item in comparison.metrics)
        return
    assert comparison.comparison_status == "COMPARABLE"
    assert comparison.baseline_operation_id == baseline.query.operation_id
    (output,) = (item for item in comparison.metrics if item.metric.signal_id == "output")
    assert output.absolute_change == pytest.approx(-0.2)

    with pytest.raises(ValueError, match="evidence digest mismatch"):
        read_mos_dc(
            evidence,
            executed_input=evidence.confirmed_input,
            native_result=result,
            baseline=replace(baseline, environment_profile=raw),
        )


def _terminal(point, phase, voltage):
    evidence, ade, reader = point
    source = evidence.route
    operation = source.operation
    context, plan, identity = source.context, operation.plan, operation.query.operation_id
    store = AnalysisStore(context.binding.analysis_journal)
    assert store.admit_operation(identity, plan, dispatch_intent=True)
    if phase == "UNKNOWN_OUTCOME":
        return None
    progress = OperationProgress(
        phase="FAILED", remote_revision=1, provider_receipt_sha256="a" * 64
    )
    if phase == "FAILED":
        store.advance_operation(identity, OperationProgress(phase="UNKNOWN_OUTCOME"), progress)
        return None
    input_sha = _sha(evidence.confirmed_input)
    frame = frame_for(
        (context, plan, ade, reader, identity, input_sha),
        f"V|input|1\nV|output|{voltage}\nI|rail|-0.001",
    )
    receipt = ExtractionReceipt(
        schema_version=1,
        operation_id=identity,
        plan_sha256=plan.plan_sha256,
        native_input_sha256=input_sha,
        reader_registration_sha256=canonical_digest(reader),
        reader_script_sha256=_sha(render_reader(context, plan, ade, reader, identity, input_sha)),
        frame_sha256=_sha(frame),
        psf_tree_fingerprint="a" * 64,
        pre_receipt_tree_fingerprint="b" * 64,
        logical_bytes=128,
        allocated_bytes=256,
        originals_preserved=True,
    )
    terminal = TerminalEvent(
        schema_version=1,
        operation_id=identity,
        plan_sha256=plan.plan_sha256,
        revision=1,
        previous_sha256="c" * 64,
        phase="SUCCEEDED",
        evidence_sha256=canonical_digest(receipt),
    )
    progress = OperationProgress(
        phase="SUCCEEDED",
        remote_revision=1,
        provider_receipt_sha256=canonical_digest(terminal),
    )
    store.advance_operation(identity, OperationProgress(phase="UNKNOWN_OUTCOME"), progress)
    return _canonical(
        dict(
            observation=dict(
                operation_id=identity,
                plan_sha256=plan.plan_sha256,
                ledger_ref=plan.ledger_ref,
                resource_domain_sha256=plan.resource_domain_sha256,
                progress=progress.model_dump(mode="json"),
            ),
            terminal_event=terminal.model_dump(mode="json"),
            receipt=receipt.model_dump(mode="json"),
            ade=ade.model_dump(mode="json"),
            reader=reader.model_dump(mode="json"),
            frame=frame.decode("ascii"),
            completed_size=dict(logical_bytes=256, allocated_bytes=512, tree_fingerprint="d" * 64),
        )
    )


def test_three_points_preserve_dc_outcomes_and_reject_cross_candidate_evidence(
    measurement_operator,  # noqa: F811
):
    registered = reader_for(measurement_operator)
    points = tuple(
        _point(registered, length, index) for index, length in enumerate(("200", "250", "300"))
    )
    candidates = tuple(item[0] for item in points)
    reservation = sum(
        row.route.operation.plan.request.result_reservation_bytes for row in candidates
    )
    assert (
        validate_mos_dc_batch(
            candidates,
            max_attempts=3,
            max_reservation_bytes=reservation,
        )
        == reservation
    )
    with pytest.raises(ValueError, match="budget"):
        validate_mos_dc_batch(candidates, max_attempts=2, max_reservation_bytes=reservation)
    with pytest.raises(ValueError, match="physical revision"):
        validate_mos_dc_batch(candidates[:1] * 2, max_attempts=3, max_reservation_bytes=reservation)
    assert [read_mos_dc(point).analysis_status for point in candidates] == ["NOT_RUN"] * 3

    first, second, third = candidates
    baseline, original = _baseline(registered)
    frame_one = _terminal(points[0], "SUCCEEDED", "0.8")
    frame_two = _terminal(points[1], "SUCCEEDED", "0.8")
    _terminal(points[2], "UNKNOWN_OUTCOME", None)
    journal = first.route.context.binding.analysis_journal
    retained = journal.read_bytes()
    for evidence, frame in ((first, frame_one), (second, frame_two)):
        row = read_mos_dc(evidence, executed_input=evidence.confirmed_input, native_result=frame)
        assert (
            row.analysis_status == "SUCCEEDED" and row.comparison_status == "BASELINE_UNAVAILABLE"
        )
        assert row.analysis_operation_id == evidence.route.operation.query.operation_id
        assert row.report is not None
        assert all(m.absolute_change is None for m in row.metrics)
    unknown = read_mos_dc(third)
    assert unknown.analysis_status == "UNKNOWN_OUTCOME" and not unknown.metrics
    compared = read_mos_dc(
        first,
        executed_input=first.confirmed_input,
        native_result=frame_one,
        baseline=baseline,
        baseline_executed_input=original,
    )
    assert compared.comparison_status == "COMPARABLE"
    assert compared.baseline_operation_id == baseline.query.operation_id
    (output,) = (m for m in compared.metrics if m.metric.signal_id == "output")
    assert output.absolute_change == pytest.approx(-0.2)
    with pytest.raises(ValueError, match="baseline report"):
        read_mos_dc(
            first,
            executed_input=first.confirmed_input,
            native_result=frame_one,
            baseline=baseline,
            baseline_executed_input=first.confirmed_input,
        )
    with pytest.raises(ValueError, match="terminal"):
        read_mos_dc(first, executed_input=first.confirmed_input, native_result=frame_two)
    with pytest.raises(ValueError, match="static"):
        read_mos_dc(first, executed_input=second.confirmed_input, native_result=frame_two)
    assert journal.read_bytes() == retained
    AnalysisStore(journal).advance_operation(
        third.route.operation.query.operation_id,
        OperationProgress(phase="UNKNOWN_OUTCOME"),
        OperationProgress(phase="FAILED", remote_revision=1, provider_receipt_sha256="a" * 64),
    )
    failed = read_mos_dc(third)
    assert failed.analysis_status == "FAILED" and not failed.metrics


@pytest.mark.asyncio
async def test_capture_uses_only_original_report_action(measurement_operator):  # noqa: F811
    point = _point(reader_for(measurement_operator), "250", 0)
    evidence, _, _ = point
    source = evidence.route
    store = AnalysisStore(source.context.binding.analysis_journal)
    calls = []

    async def report_result(identity, plan):
        calls.append((identity, plan))
        return verify_native_result(
            source.context,
            plan,
            identity,
            data,
            include_report_conditions=True,
        )

    service = SimpleNamespace(
        context=source.context,
        current=lambda: None,
        lifecycle=SimpleNamespace(store=store),
        provider=SimpleNamespace(report_result=report_result),
    )
    assert (await capture_mos_dc(evidence, service)).analysis_status == "NOT_RUN"
    assert not calls
    data = NativeResultPayload.model_validate_json(_terminal(point, "SUCCEEDED", "0.9"))
    before = store.path.read_bytes()
    first = await capture_mos_dc(evidence, service)
    replay = await capture_mos_dc(evidence, service)
    assert first.metrics == replay.metrics and first.terminal_receipt_sha256 == (
        replay.terminal_receipt_sha256
    )
    op = source.operation
    assert calls == [(op.query.operation_id, op.plan)] * 2
    assert store.path.read_bytes() == before


@pytest.mark.asyncio
async def test_submit_delegates_same_uuid_and_blocks_foreign_registration(
    measurement_operator,  # noqa: F811
):
    point, _, _ = _point(reader_for(measurement_operator), "250", 0)

    class Service:
        context = point.route.context
        calls = []

        async def observe(self, query, submission):
            self.calls.append((query, submission))

    service = Service()
    await submit_mos_dc(point, service)
    await submit_mos_dc(point, service)
    operation = point.route.operation
    assert service.calls == [(operation.query, operation.plan.request)] * 2
    with pytest.raises(ValueError, match="evidence digest mismatch"):
        await submit_mos_dc(
            replace(point, route=replace(point.route, export_sha256="0" * 64)), service
        )
    assert len(service.calls) == 2
