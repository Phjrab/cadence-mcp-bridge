"""Synthetic operator CLI chains; no actual VM, grant or circuit qualification."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace

import pytest
from test_candidate_batches import candidate_native
from test_candidate_contracts import candidate_operator, operator, planned
from test_candidate_execution import (
    measurement_operator,
    operator_base,
    pmos_pair,
    registered_pmos_change,
)
from test_candidate_reports import succeeded

from cadence_mcp_bridge import candidate_cli as cli
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.candidate_batches import CandidateBatchSupervisor
from cadence_mcp_bridge.candidate_contracts import CandidateBatchPlan
from cadence_mcp_bridge.candidate_reports import CandidateComparison
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = [
    "candidate_native",
    "candidate_operator",
    "measurement_operator",
    "operator",
    "operator_base",
    "pmos_pair",
    "registered_pmos_change",
]


def output(capsys):
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("case", ["verified", "retained-unknown", "wrong-scope", "missing-netlist"])
def test_dispatch_pmos_default_change_preserves_typed_boundary(
    registered_pmos_change, tmp_path, case
):
    from pydantic import ValidationError

    from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeResult

    plan, request, fields = registered_pmos_change
    path = tmp_path / "request.json"
    raw = request.model_dump_json().encode()
    path.write_bytes(raw)
    if case == "retained-unknown":
        fields.update(
            outcome="OUTCOME_UNKNOWN",
            replayed=True,
            dispatched_this_call=False,
            netlist_receipt_sha256=None,
            netlist_sha256=None,
            reason="netlist_receipt_unavailable",
        )
    receipt = PmosDefaultChangeResult.model_validate(fields)
    calls = []

    class FixtureService:
        def apply(self, supplied):
            calls.append(supplied)
            receipt.check_registered_scope(
                supplied,
                registered_plan=plan,
                registered_scope_sha256=request.expected_scope_sha256,
            )
            if case == "wrong-scope":
                return receipt.model_copy(update={"scope_sha256": "0" * 64})
            if case == "missing-netlist":
                return receipt.model_copy(
                    update={"netlist_receipt_sha256": None, "netlist_sha256": None}
                )
            return receipt

    service = FixtureService()
    if case == "wrong-scope":
        with pytest.raises(OperationRejected) as rejected:
            cli.dispatch_pmos_default_change(path, service)
        assert rejected.value.reason == "pmos_default_change_identity_mismatch"
    elif case == "missing-netlist":
        with pytest.raises(ValidationError, match="verified change requires netlist evidence"):
            cli.dispatch_pmos_default_change(path, service)
    else:
        assert cli.dispatch_pmos_default_change(path, service) == receipt
    assert calls == [request]
    assert path.read_bytes() == raw


@pytest.mark.parametrize("case", ["extra-field", "over-limit"])
def test_dispatch_pmos_default_change_rejects_before_apply(registered_pmos_change, tmp_path, case):
    _, request, _ = registered_pmos_change
    path = tmp_path / "request.json"
    if case == "extra-field":
        path.write_text(json.dumps({**request.model_dump(), "callback": "other"}), encoding="utf-8")
    else:
        path.write_bytes(b" " * (cli.DOCUMENT_LIMIT + 1))

    class UnusedService:
        def apply(self, _request):
            pytest.fail("invalid request reached apply")

    with pytest.raises(ValueError):
        cli.dispatch_pmos_default_change(path, UnusedService())


def test_pmos_default_command_waits_for_registered_factory(monkeypatch):
    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    with pytest.raises(SystemExit) as rejected:
        main(["operator-candidates", "apply-pmos-default"])
    assert rejected.value.code == 2


def test_schema_and_missing_opt_in_never_load_context(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    assert main(["operator-candidates", "schema"]) == 0
    assert output(capsys)["wl"] == "UNSUPPORTED"
    with pytest.raises(SystemExit):
        main(
            [
                "operator-candidates",
                "advance",
                "--settings",
                "missing",
                "--context",
                "missing",
                "--plan",
                "missing",
                "--expected-plan-sha256",
                "0" * 64,
            ]
        )


@pytest.fixture
def change_readback_case(tmp_path, monkeypatch):
    from test_parameter_changes import _bias, _row

    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    plan = _bias()
    plan_path = tmp_path / "change-plan.json"
    plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
    args = [
        "operator-candidates",
        "verify-change-readback",
        "--plan",
        str(plan_path),
        "--expected-plan-sha256",
        plan.plan_sha256,
    ]
    stages = {stage: _row(plan, stage) for stage in ("baseline", "reopened", "netlist")}
    return plan, args, stages


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("MATCHED", "local_projections_match"),
        ("MISSING", "baseline_reopened_and_netlist_readbacks_required"),
        ("STALE", "reopened_and_netlist_revisions_differ"),
        ("CONFLICT", "netlist_fixed_conditions_changed"),
    ],
)
def test_verify_change_readback_exports_typed_status(
    change_readback_case, tmp_path, capsys, status, reason
):
    from cadence_mcp_bridge.parameter_changes import ChangeReadback

    plan, args, stages = change_readback_case
    if status == "MISSING":
        del stages["netlist"]
    elif status in ("STALE", "CONFLICT"):
        field = "revision_sha256" if status == "STALE" else "fixed_conditions_sha256"
        stages["netlist"] = stages["netlist"].model_copy(update={field: "8" * 64})
    for stage, row in stages.items():
        path = tmp_path / f"{stage}.json"
        raw = row.model_dump_json().encode()
        path.write_bytes(raw)
        args.extend([f"--{stage}", str(path), hashlib.sha256(raw).hexdigest()])
    target = tmp_path / "readback.json"

    assert main([*args, "--output", str(target)]) == 0
    summary = output(capsys)
    raw = target.read_bytes()
    saved = ChangeReadback.model_validate_json(raw)
    assert (saved.plan_sha256, saved.status, saved.reason) == (plan.plan_sha256, status, reason)
    assert (saved.baseline, saved.reopened, saved.netlist) == (
        stages.get("baseline"),
        stages.get("reopened"),
        stages.get("netlist"),
    )
    assert saved.execution_authorized is summary["execution_authorized"] is False
    assert saved.provenance == "LOCAL_EVIDENCE_COMPARISON"
    assert summary["readback_status"] == status and summary["remote_contact"] is False
    assert summary["file_sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("failure", ["plan_pin", "stage_pin", "malformed", "extra", "collision"])
def test_verify_change_readback_rejects_invalid_inputs_without_overwrite(
    change_readback_case, tmp_path, capsys, failure
):
    _, args, stages = change_readback_case
    path = tmp_path / "baseline.json"
    stage = stages["baseline"].model_dump(mode="json")
    if failure == "extra":
        stage["extra"] = True
    raw = b"{" if failure == "malformed" else json.dumps(stage).encode()
    path.write_bytes(raw)
    target = path if failure == "collision" else tmp_path / "readback.json"
    if failure == "plan_pin":
        args[-1] = "0" * 64
    pin = "0" * 64 if failure == "stage_pin" else hashlib.sha256(raw).hexdigest()

    assert main([*args, "--baseline", str(path), pin, "--output", str(target)]) == 2
    summary = output(capsys)
    assert summary["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert summary["remote_contact"] is False
    assert path.read_bytes() == raw
    assert target.exists() == (failure == "collision")


@pytest.mark.parametrize("case", ["matched", "missing-power", "bad-pin", "collision", "sidecar"])
def test_pmos_dc_compare_retained_pair(pmos_pair, tmp_path, monkeypatch, capsys, case):
    from cadence_mcp_bridge.analysis_store import AnalysisStore
    from cadence_mcp_bridge.candidate_execution import PmosDcPair
    from cadence_mcp_bridge.operator_operations import OperationProgress

    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    change, readback, baseline_input, candidate_input, copy, operation = pmos_pair
    pinned = {}

    def save(name, raw):
        path = tmp_path / name
        path.write_bytes(raw)
        pinned[path] = raw
        return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}

    def side(label, bound):
        journal = tmp_path / f"{label}.sqlite3"
        store = AnalysisStore(journal)
        identity = bound.query.operation_id
        assert store.admit_operation(identity, bound.plan)
        dispatch = OperationProgress(phase="UNKNOWN_OUTCOME")
        store.advance_operation(identity, OperationProgress(phase="ADMITTED"), dispatch)
        store.advance_operation(identity, dispatch, bound.record.progress)
        journal_raw = journal.read_bytes()
        pinned[journal] = journal_raw
        return {
            "operation_id": identity,
            "plan_sha256": bound.plan.plan_sha256,
            "terminal_sha256": bound.expected_terminal_sha256,
            "journal": {"path": str(journal), "sha256": hashlib.sha256(journal_raw).hexdigest()},
            "runtime_manifest": save(f"{label}-manifest.json", bound.runtime_manifest),
            "runtime_registration": save(f"{label}-registration.json", bound.runtime_registration),
            "design_registry": save(f"{label}-registry.json", bound.design_registry),
            "report": save(f"{label}-report.json", bound.report),
        }

    request = {
        "change_plan": save("plan.json", change.model_dump_json().encode()),
        "change_plan_sha256": change.plan_sha256,
        "readback": save("readback.json", readback.model_dump_json().encode()),
        "baseline_input": save("baseline.scs", baseline_input),
        "candidate_input": save("candidate.scs", candidate_input),
        "copy_receipt": save("copy.json", json.dumps(copy).encode()),
        "copy_scope_sha256": "d" * 64,
        "copy_id": copy["copy_id"],
        "reopen_receipt_sha256": "a" * 64,
        "baseline": side("baseline", operation(False)),
        "candidate": side(
            "candidate", operation(True, "power-missing" if case == "missing-power" else None)
        ),
    }
    if case == "bad-pin":
        request["candidate"]["report"]["sha256"] = "0" * 64
    request_file = save("request.json", json.dumps(request).encode())
    target = tmp_path / "result.json"
    if case == "collision":
        target = tmp_path / "baseline-report.json"
    elif case == "sidecar":
        target = tmp_path / "candidate.sqlite3-wal"

    args = [
        "operator-candidates",
        "pmos-dc-compare",
        "--request",
        request_file["path"],
        request_file["sha256"],
        "--output",
        str(target),
    ]
    if case in ("bad-pin", "collision", "sidecar"):
        assert main(args) == 2
        assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
        assert target.exists() == (case == "collision")
    else:
        assert main(args) == 0
        summary = output(capsys)
        saved_raw = target.read_bytes()
        saved = json.loads(saved_raw)
        pair = PmosDcPair.model_validate_json(json.dumps(saved["association"]))
        assert summary["status"] == "PMOS_DC_COMPARISON_EXPORTED"
        assert summary["file_sha256"] == hashlib.sha256(saved_raw).hexdigest()
        assert summary["remote_contact"] is False and pair.execution_authorized is False
        assert pair.goals == "GOALS_NOT_PROVIDED" and saved["selected_candidate_id"] is None
        assert saved["deltas"][0]["absolute_delta"] == pytest.approx(-0.2)
        assert saved["deltas"][1]["absolute_delta"] == (None if case == "missing-power" else 0.0)
        assert [row.operation.operation_id for row in pair.rows] == [
            request[key]["operation_id"] for key in ("baseline", "candidate")
        ]
    assert all(path.read_bytes() == raw for path, raw in pinned.items())


def test_local_plan_exports_full_vector_without_journal(
    candidate_operator, tmp_path, monkeypatch, capsys
):
    context, grant, request, settings = candidate_operator
    grant_path = tmp_path / "cli-grant.json"
    grant_path.write_text(grant.model_dump_json(), encoding="utf-8")
    digest = canonical_digest(grant)
    context = replace(
        context,
        binding=context.binding.model_copy(
            update={
                "operator_grant": grant_path,
                "operator_grant_sha256": digest,
            }
        ),
    )
    monkeypatch.setattr(cli, "load_runtime", lambda _: (context,))
    monkeypatch.setattr(cli, "load_grant", lambda *args: (grant, digest))
    monkeypatch.setattr(cli.time, "time", lambda: 100)
    source, target = tmp_path / "request.json", tmp_path / "plan.json"
    source.write_text(request.model_dump_json(), encoding="utf-8")
    args = [
        "operator-candidates",
        "plan",
        "--settings",
        str(settings),
        "--context",
        context.binding.context_id,
        "--request",
        str(source),
        "--output",
        str(target),
    ]
    assert main(args) == 0
    receipt = output(capsys)
    plan = CandidateBatchPlan.model_validate_json(target.read_bytes())
    assert receipt["plan_sha256"] == plan.plan_sha256
    assert plan.request.candidates == request.candidates and plan.expected_executions == 3
    assert not context.binding.analysis_journal.exists() and not context.lock_path.exists()
    assert main(args) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert CandidateBatchPlan.model_validate_json(target.read_bytes()) == plan
    args[-1] = str(context.binding.analysis_journal)
    assert main(args) == 2
    output(capsys)
    assert not context.binding.analysis_journal.exists()


def test_compare_csv_cli_chain_retains_all_rows(candidate_operator, tmp_path, capsys):
    plan = planned(candidate_operator)
    source, observations = tmp_path / "plan.json", tmp_path / "observations.json"
    comparison, csv = tmp_path / "comparison.json", tmp_path / "comparison.csv"
    source.write_text(plan.model_dump_json(), encoding="utf-8")
    observations.write_bytes(cli.OBSERVATIONS.dump_json(succeeded(plan)))
    args = [
        "operator-candidates",
        "compare",
        "--plan",
        str(source),
        "--expected-plan-sha256",
        plan.plan_sha256,
        "--observations",
        str(observations),
        "--output",
        str(comparison),
    ]
    assert main(args) == 0
    assert output(capsys)["new_simulations"] == 0
    report = CandidateComparison.model_validate_json(comparison.read_bytes())
    assert len(report.rows) == 3 and all(row.status == "SUCCEEDED" for row in report.rows)
    assert (
        main(["operator-candidates", "csv", "--comparison", str(comparison), "--output", str(csv)])
        == 0
    )
    assert output(capsys)["remote_contact"] is False
    assert csv.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "기준 회로" in csv.read_text(encoding="utf-8-sig")
    observations.write_bytes(b"[]")
    args[-1] = str(tmp_path / "not-run.json")
    assert main(args) == 0
    output(capsys)
    missing = CandidateComparison.model_validate_json((tmp_path / "not-run.json").read_bytes())
    assert all(row.status == "NOT_RUN" and not row.metrics for row in missing.rows)


def test_local_selection_checks_comparison_pin_and_exports_typed_result(
    candidate_operator,
    tmp_path,
    monkeypatch,
    capsys,
):
    from cadence_mcp_bridge.candidate_selection import CandidateSelection, CandidateSelectionRequest

    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    plan = planned(candidate_operator)
    plan_file, observations = tmp_path / "plan.json", tmp_path / "observations.json"
    comparison, request, target = (
        tmp_path / "comparison.json",
        tmp_path / "selection-request.json",
        tmp_path / "selection.json",
    )
    plan_file.write_text(plan.model_dump_json(), encoding="utf-8")
    observations.write_bytes(cli.OBSERVATIONS.dump_json(succeeded(plan)))
    assert (
        main(
            [
                "operator-candidates",
                "compare",
                "--plan",
                str(plan_file),
                "--expected-plan-sha256",
                plan.plan_sha256,
                "--observations",
                str(observations),
                "--output",
                str(comparison),
            ]
        )
        == 0
    )
    digest = output(capsys)["comparison_sha256"]
    assert digest == canonical_digest(
        CandidateComparison.model_validate_json(comparison.read_bytes())
    )
    assert main(["operator-candidates", "schema", "--action", "select"]) == 0
    assert output(capsys)["request_schema"] == CandidateSelectionRequest.model_json_schema()
    request.write_text(
        json.dumps(
            {
                "measurements": [
                    {"metric_id": "output-voltage", "kind": "node_voltage", "signal_id": "output"}
                ],
                "goals": [{"metric_id": "output-voltage", "unit": "V", "objective": "maximize"}],
            }
        ),
        encoding="utf-8",
    )
    args = [
        "operator-candidates",
        "select",
        "--comparison",
        str(comparison),
        "--request",
        str(request),
        "--output",
        str(target),
        "--expected-comparison-sha256",
    ]
    assert main([*args, "0" * 64]) == 2
    assert output(capsys)["remote_contact"] is False and not target.exists()
    assert main([*args, digest]) == 0
    receipt = output(capsys)
    raw = target.read_bytes()
    selection = CandidateSelection.model_validate_json(raw)
    assert selection.selected_candidate_id == receipt["selected_candidate_id"] == "mixed"
    assert selection.comparison_sha256 == digest
    assert selection.layout_handoff == "EFFECTIVE_VALUES_AND_LAYOUT_BINDING_UNVERIFIED"
    assert receipt["file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["remote_contact"] is False and receipt["new_reservations"] == 0
    assert main([*args, digest]) == 2
    output(capsys)
    assert target.read_bytes() == raw


def test_local_compose_and_collect_preserve_plan_and_capture_identity(
    candidate_operator,
    tmp_path,
    monkeypatch,
    capsys,
):
    from pydantic import TypeAdapter

    from cadence_mcp_bridge.candidate_execution import (
        CandidateAnalysisManifest,
        CandidateRevisionResult,
    )
    from cadence_mcp_bridge.candidate_reports import CandidateObservation

    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    plan = planned(candidate_operator)
    plan_file, manifest_file = tmp_path / "plan.json", tmp_path / "manifest.json"
    capture_file, target = tmp_path / "capture.json", tmp_path / "analysis-results.json"
    plan_file.write_text(plan.model_dump_json(), encoding="utf-8")
    first = succeeded(plan)[0]
    capture_file.write_bytes(
        cli.OBSERVATIONS.dump_json(
            (
                first,
                CandidateObservation(candidate_id=plan.request.candidates[1].candidate_id),
            )
        )
    )
    compose = [
        "operator-candidates",
        "compose",
        "--output",
        str(manifest_file),
        "--batch",
        str(plan_file),
    ]
    assert main([*compose, "0" * 64]) == 2
    assert output(capsys)["remote_contact"] is False and not manifest_file.exists()
    assert main([*compose, plan.plan_sha256]) == 0
    receipt = output(capsys)
    manifest = CandidateAnalysisManifest.model_validate_json(manifest_file.read_bytes())
    assert manifest.batches == (plan,) and receipt["manifest_sha256"] == manifest.manifest_sha256
    assert receipt["planned_result_reservation_bytes"] == plan.result_reservation_bytes
    batch_id = plan.request.batch_id
    collect = [
        "operator-candidates",
        "collect",
        "--manifest",
        str(manifest_file),
        "--expected-manifest-sha256",
        manifest.manifest_sha256,
        "--output",
        str(target),
        "--capture",
        batch_id,
        str(capture_file),
    ]
    assert main([*collect, "--capture", batch_id, str(capture_file)]) == 2
    assert output(capsys)["remote_contact"] is False and not target.exists()
    assert main(collect) == 0
    receipt = output(capsys)
    raw = target.read_bytes()
    results = TypeAdapter(tuple[CandidateRevisionResult, ...]).validate_json(raw)
    analyses = [result.analyses[0] for result in results]
    assert [analysis.operation_id for analysis in analyses] == [
        candidate.operation_id for candidate in plan.request.candidates
    ]
    assert [analysis.status for analysis in analyses] == ["SUCCEEDED", "NOT_RUN", "NOT_OBSERVED"]
    assert analyses[0].row is not None and analyses[0].row.source_report == first.report
    assert receipt["manifest_sha256"] == manifest.manifest_sha256
    assert receipt["file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["remote_contact"] is False and receipt["new_simulations"] == 0


def test_retained_amplifier_cli_preserves_original_point_and_intent_bindings(
    tmp_path,
    monkeypatch,
    capsys,
):
    from uuid import uuid4

    from test_amplifier_specifications import source
    from test_amplifier_sweeps import request as sweep_request

    from cadence_mcp_bridge.amplifier_candidate_selection import (
        AmplifierCandidateSelection,
        AmplifierCandidateSelectionRequest,
    )
    from cadence_mcp_bridge.amplifier_specifications import (
        AmplifierSpecificationRegistry,
        evaluate_source,
    )
    from cadence_mcp_bridge.amplifier_sweeps import (
        AmplifierPrepared,
        AmplifierSubmission,
        make_amplifier_plan,
    )

    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    assert main(["operator-candidates", "schema", "--action", "amplifier-select"]) == 0
    assert (
        output(capsys)["request_schema"] == AmplifierCandidateSelectionRequest.model_json_schema()
    )

    def save_document(name, document):
        path = tmp_path / f"{name}.json"
        raw = json.dumps(document).encode("utf-8")
        path.write_bytes(raw)
        return [str(path), hashlib.sha256(raw).hexdigest()]

    captures, spec, original, intents = {}, {}, {}, {}
    for mode in ("dc", "ac"):
        folder = tmp_path / mode
        folder.mkdir()
        _, query, result = asyncio.run(source(folder, mode))
        original[mode] = result
        request = sweep_request(mode)
        plan = make_amplifier_plan(request)
        submission = AmplifierSubmission(
            request=request,
            expected_plan_hash=plan.plan_hash,
            experiment_key=result.engine.experiment_key,
        )
        intents[mode] = {
            "prepared": AmplifierPrepared(engine_plan=plan).model_dump(mode="json"),
            "submission": submission.model_dump(mode="json"),
        }
        captures[f"{mode}-intent"] = save_document(f"{mode}-intent", intents[mode])
        captures[f"{mode}-result"] = save_document(
            f"{mode}-result",
            {
                "query": query.model_dump(mode="json"),
                "result": result.model_dump(mode="json"),
            },
        )
        evaluation = evaluate_source(
            result, AmplifierSpecificationRegistry(), request.measurement_id
        )
        spec[mode] = {
            "request": {
                **query.model_dump(mode="json"),
                "expected_sweep_result_sha256": evaluation.source_result_sha256,
                "expected_specification_registry_sha256": evaluation.specification_registry_sha256,
            },
            "evaluation": evaluation.model_dump(mode="json"),
        }
    captures["specification"] = save_document("specification", {"outputs": spec})
    request_path, _ = save_document(
        "selection-request",
        {
            "candidate_values_v": ["0.320", "0.321"],
            "baseline_vbiasn_v": "0.320",
        },
    )
    target = tmp_path / "amplifier-selection.json"
    args = [
        "operator-candidates",
        "amplifier-select",
        "--request",
        request_path,
        "--output",
        str(target),
    ]
    for name, pair in captures.items():
        args.extend([f"--{name}", *pair])
    dc_intent = args.index("--dc-intent") + 1
    wrong_hash = args.copy()
    wrong_hash[dc_intent + 1] = "0" * 64
    assert main(wrong_hash) == 2
    assert output(capsys)["remote_contact"] is False and not target.exists()
    wrong_intent = args.copy()
    wrong_intent[dc_intent : dc_intent + 2] = save_document(
        "wrong-intent",
        {
            **intents["dc"],
            "submission": {**intents["dc"]["submission"], "experiment_key": str(uuid4())},
        },
    )
    assert main(wrong_intent) == 2
    assert output(capsys)["remote_contact"] is False and not target.exists()
    wrong_evaluation = args.copy()
    spec_arg = args.index("--specification") + 1
    wrong_evaluation[spec_arg : spec_arg + 2] = save_document(
        "wrong-evaluation",
        {
            "outputs": {
                **spec,
                "dc": {
                    **spec["dc"],
                    "evaluation": {**spec["dc"]["evaluation"], "target_status": "not_selected"},
                },
            }
        },
    )
    assert main(wrong_evaluation) == 2
    assert output(capsys)["remote_contact"] is False and not target.exists()
    assert main(args) == 0
    receipt = output(capsys)
    raw = target.read_bytes()
    selection = AmplifierCandidateSelection.model_validate_json(raw)
    assert selection.status == "GOALS_NOT_PROVIDED" and selection.selected_candidate_id is None
    assert selection.dc.source == original["dc"] and selection.ac.source == original["ac"]
    for index, row in enumerate(selection.rows, 1):
        assert row.dc_point == original["dc"].engine.points[index]
        assert row.ac_point == original["ac"].engine.points[index]
    assert receipt["file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["remote_contact"] is False and receipt["new_simulations"] == 0
    assert main(args) == 2
    output(capsys)
    assert target.read_bytes() == raw


def test_read_rejects_duplicate_keys_and_oversized_files(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(b'{"x":1,"x":2}')
    with pytest.raises(ValueError):
        cli.read_candidate_document(path)
    path.write_bytes(b" " * (cli.DOCUMENT_LIMIT + 1))
    with pytest.raises(OperationRejected):
        cli.read_candidate_document(path)


def test_publication_failure_preserves_complete_pending_file(tmp_path, monkeypatch):
    target = tmp_path / "new.json"

    def fail(*_):
        raise OSError("synthetic interrupted publication")

    monkeypatch.setattr(cli, "_publish_report", fail)
    with pytest.raises(OSError):
        cli._export(target, b'{"synthetic":true}')
    assert not target.exists()
    pending = tuple(tmp_path.glob(".cadence-candidates-*.pending"))
    assert len(pending) == 1 and pending[0].read_bytes() == b'{"synthetic":true}'


@pytest.mark.parametrize("read_fails", [False, True])
def test_submit_advance_capture_compare_chain_without_retry(
    candidate_native,
    candidate_operator,
    tmp_path,
    monkeypatch,
    capsys,
    read_fails,
):
    make_native, provider, request = candidate_native
    context = make_native().context
    settings = candidate_operator[3]
    monkeypatch.setattr(cli, "load_runtime", lambda _: (context,))
    monkeypatch.setattr(cli.time, "time", lambda: 100)
    monkeypatch.setattr(
        "cadence_mcp_bridge.native_service.NativeOperationService", lambda _: make_native()
    )
    plan = asyncio.run(CandidateBatchSupervisor(make_native()).plan(request))
    source = tmp_path / "plan.json"
    source.write_text(plan.model_dump_json(), encoding="utf-8")
    shared = [
        "--settings",
        str(settings),
        "--context",
        context.binding.context_id,
        "--plan",
        str(source),
        "--expected-plan-sha256",
        plan.plan_sha256,
    ]
    assert main(["operator-candidates", "submit", *shared, "--experimental-candidates"]) == 0
    assert output(capsys)["state"] == "PLANNED" and provider.calls == []
    assert main(["operator-candidates", "advance", *shared, "--experimental-candidates"]) == 0
    assert output(capsys)["state"] == "PARTIAL" and len(provider.calls) == 1
    assert main(["operator-candidates", "submit", *shared, "--experimental-candidates"]) == 0
    output(capsys)
    assert len(provider.calls) == 1
    reports = {o.record.operation_id: o.report for o in succeeded(plan)}
    reads = []

    async def read(_native, operation_id, digest):
        reads.append(operation_id)
        assert digest == reports[operation_id].plan.plan_sha256
        if read_fails:
            raise OperationRejected("synthetic_report_read_failed")
        return reports[operation_id]

    monkeypatch.setattr(cli, "capture_report", read)
    observations = tmp_path / "observations.json"
    assert main(["operator-candidates", "capture", *shared, "--output", str(observations)]) == 0
    captured = output(capsys)
    assert captured["new_simulations"] == 0 and captured["unavailable_reports"] == int(read_fails)
    assert reads == [request.candidates[0].operation_id] and len(provider.calls) == 1
    comparison = tmp_path / "comparison.json"
    assert (
        main(
            [
                "operator-candidates",
                "compare",
                "--plan",
                str(source),
                "--expected-plan-sha256",
                plan.plan_sha256,
                "--observations",
                str(observations),
                "--output",
                str(comparison),
            ]
        )
        == 0
    )
    output(capsys)
    rows = CandidateComparison.model_validate_json(comparison.read_bytes()).rows
    assert [row.status for row in rows] == [
        "RESULT_UNAVAILABLE" if read_fails else "SUCCEEDED",
        "NOT_RUN",
        "NOT_RUN",
    ]
    assert rows[0].reason == ("retained_report_read_failed" if read_fails else None)
    assert len(provider.calls) == 1
