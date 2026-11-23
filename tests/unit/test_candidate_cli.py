"""Synthetic operator CLI chains; no actual VM, grant or circuit qualification."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_candidate_batches import candidate_native
from test_candidate_contracts import candidate_operator, operator, planned
from test_candidate_execution import (
    amplifier_child_fixture,
    amplifier_width_evidence,
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
    "amplifier_child_fixture",
    "amplifier_width_evidence",
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


def test_apply_pmos_default_requires_context_and_request_flags(monkeypatch):
    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    with pytest.raises(SystemExit) as rejected:
        main(["operator-candidates", "apply-pmos-default"])
    assert rejected.value.code == 2


@pytest.mark.parametrize("case", ["verified", "retained-unknown", "unregistered", "wrong-context"])
def test_apply_pmos_default_uses_registered_service(
    registered_pmos_change, tmp_path, monkeypatch, capsys, case
):
    from cadence_mcp_bridge import pmos_default_service
    from cadence_mcp_bridge.candidate_execution import PmosDefaultChangeResult

    plan, request, fields = registered_pmos_change
    settings = tmp_path / "runtime.json"
    path = tmp_path / "request.json"
    raw = request.model_dump_json().encode()
    path.write_bytes(raw)
    context = SimpleNamespace(
        binding=SimpleNamespace(
            context_id="selected",
            pmos_default_change_binding=None,
            pmos_default_change_sha256=None,
        )
    )

    def load_runtime(received):
        assert received == settings
        return (context,)

    monkeypatch.setattr(cli, "load_runtime", load_runtime)
    calls = []
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

    class FixtureService:
        def apply(self, supplied):
            calls.append(supplied)
            receipt.check_registered_scope(
                supplied,
                registered_plan=plan,
                registered_scope_sha256=request.expected_scope_sha256,
            )
            return receipt

    def registered(selected):
        assert selected is context
        return FixtureService()

    if case in ("verified", "retained-unknown"):
        monkeypatch.setattr(pmos_default_service, "registered_pmos_default_change", registered)
    elif case == "wrong-context":
        monkeypatch.setattr(
            pmos_default_service,
            "registered_pmos_default_change",
            lambda _: pytest.fail("unexpected factory call"),
        )
    args = [
        "operator-candidates",
        "apply-pmos-default",
        "--settings",
        str(settings),
        "--context",
        "missing" if case == "wrong-context" else "selected",
        "--request",
        str(path),
    ]
    if case in ("unregistered", "wrong-context"):
        assert main(args) == 2
        rejected = output(capsys)
        assert rejected["status"] == "CANDIDATE_WORKFLOW_REJECTED"
        assert rejected["remote_contact"] is False
        assert not calls
    else:
        assert main(args) == 0
        assert output(capsys) == {
            **receipt.model_dump(mode="json"),
            "remote_contact": receipt.dispatched_this_call,
            "budget_reset_or_refund": False,
        }
        assert calls == [request]
    assert path.read_bytes() == raw


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


def test_observe_amplifier_pm0_request_schema(capsys):
    assert main(["operator-candidates", "schema", "--action", "observe-amplifier-pm0"]) == 0
    schema = output(capsys)["request_schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "baseline_input",
        "child_input",
        "baseline",
        "child",
        "diagnostic_receipt_sha256",
        "footprint_receipt_sha256",
        "dfm_evidence_sha256",
        "baseline_effective_dfm",
        "child_effective_dfm",
    }


@pytest.mark.parametrize(
    "case",
    [
        "matched",
        "request-hash",
        "baseline-hash",
        "child-hash",
        "output-alias",
        "missing-dfm",
        "wrong-dfm",
        "missing-geometry",
        "missing-receipt",
    ],
)
def test_observe_amplifier_pm0_retained_inputs(tmp_path, monkeypatch, capsys, case):
    from cadence_mcp_bridge import parameter_changes
    from cadence_mcp_bridge.parameter_changes import AmplifierPm0InputObservation

    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    pm0 = (
        b"PM0 (net33 Vbiasp VDD VDD) gpdk090_pmos1v w=(20u) l=1u "
        b"as=5.6p ad=5.6p ps=40.56u pd=40.56u m=(1)*(1) simM=(1)*(1)"
    )
    baseline_raw = b"simulator lang=spectre\nparameters VBIASN=0.32 VBIASP=0.702\n" + pm0 + b"\n"
    child_raw = (
        baseline_raw.replace(b"w=(20u)", b"w=(120n)")
        .replace(b"5.6p", b"69.6f")
        .replace(b"40.56u", b"1.16u")
    )
    baseline_hash = hashlib.sha256(baseline_raw).hexdigest()
    child_hash = hashlib.sha256(child_raw).hexdigest()
    monkeypatch.setattr(parameter_changes, "_AMP_CENTER_SHA256", baseline_hash)
    monkeypatch.setattr(
        parameter_changes, "_AMP_PM0_STATEMENT_SHA256", hashlib.sha256(pm0).hexdigest()
    )
    baseline_path = tmp_path / "baseline.scs"
    child_path = tmp_path / "child.scs"
    baseline_path.write_bytes(baseline_raw)
    child_path.write_bytes(child_raw)
    request = {
        "baseline_input": str(baseline_path),
        "child_input": str(child_path),
        "baseline": {
            "revision_sha256": "1" * 64,
            "testbench_revision_sha256": "2" * 64,
            "oa_cdf_sha256": "3" * 64,
            "netlist_sha256": baseline_hash,
            "width": {"value": "20", "unit": "um"},
            "geometry": [
                {"property_name": name, "value": value}
                for name, value in zip(
                    ("fw", "as", "ad", "ps", "pd"),
                    ("20u", "5.6p", "5.6p", "40.56u", "40.56u"),
                    strict=True,
                )
            ],
        },
        "child": {
            "revision_sha256": "4" * 64,
            "testbench_revision_sha256": "5" * 64,
            "oa_cdf_sha256": "6" * 64,
            "netlist_sha256": child_hash,
            "width": {"value": "120", "unit": "nm"},
            "geometry": [
                {"property_name": name, "value": value}
                for name, value in zip(
                    ("fw", "as", "ad", "ps", "pd"),
                    ("120n", "69.6f", "69.6f", "1.16u", "1.16u"),
                    strict=True,
                )
            ],
        },
        "diagnostic_receipt_sha256": "7" * 64,
        "footprint_receipt_sha256": "8" * 64,
        "dfm_evidence_sha256": "9" * 64,
        "baseline_effective_dfm": "Minimum",
        "child_effective_dfm": "DFM",
    }
    target = tmp_path / "observation.json"
    if case in ("baseline-hash", "child-hash"):
        request[case.split("-")[0]]["netlist_sha256"] = "0" * 64
    elif case == "output-alias":
        target = tmp_path / "subdir" / ".." / child_path.name
        target.parent.parent.mkdir()
    elif case == "missing-dfm":
        del request["child_effective_dfm"]
    elif case == "wrong-dfm":
        request["child_effective_dfm"] = "Minimum"
    elif case == "missing-geometry":
        request["child"]["geometry"].pop()
    elif case == "missing-receipt":
        del request["diagnostic_receipt_sha256"]
    request_path = tmp_path / "request.json"
    request_raw = json.dumps(request).encode()
    request_path.write_bytes(request_raw)
    digest = "0" * 64 if case == "request-hash" else hashlib.sha256(request_raw).hexdigest()
    args = [
        "operator-candidates",
        "observe-amplifier-pm0",
        "--request",
        str(request_path),
        digest,
        "--output",
        str(target),
    ]
    if case == "matched":
        assert main(args) == 0
        summary = output(capsys)
        raw = target.read_bytes()
        result = AmplifierPm0InputObservation.model_validate_json(raw)
        assert summary["file_sha256"] == hashlib.sha256(raw).hexdigest()
        assert summary["status"] == result.status == "OBSERVATION_ONLY"
        assert summary["scope"] == result.scope == "NETLIST_INPUT_ONLY"
        assert summary["oa_footprint"] == result.oa_footprint == "MISMATCHED"
        assert summary["oa_change_status"] == result.oa_change_status == "UNQUALIFIED_EXTRA_SETTING"
        assert (
            summary["receipt_authentication"]
            == result.receipt_authentication
            == ("NOT_VERIFIED_BY_THIS_API")
        )
        assert summary["remote_contact"] is False
        assert not any(
            summary[key]
            for key in ("execution_authorized", "admission_authorized", "selection_authorized")
        )
        assert result.netlist.artifact_sha256 == child_hash
        assert result.netlist.value.model_dump() == {"value": "120", "unit": "nm"}
        assert (result.baseline_effective_dfm, result.child_effective_dfm) == ("Minimum", "DFM")
        assert result.dfm_evidence_sha256 == request["dfm_evidence_sha256"]
        assert main(args) == 2
        assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
        assert target.read_bytes() == raw
    else:
        assert main(args) == 2
        assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
        assert target.exists() == (case == "output-alias")
    assert request_path.read_bytes() == request_raw
    assert baseline_path.read_bytes() == baseline_raw
    assert child_path.read_bytes() == child_raw


def test_amplifier_width_compare_request_schema(capsys):
    assert main(["operator-candidates", "schema", "--action", "amplifier-width-compare"]) == 0
    schema = output(capsys)["request_schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "change_plan",
        "change_plan_sha256",
        "readback",
        "baseline_input",
        "candidate_input",
        "registration_evidence",
        "dc",
        "ac",
    }


@pytest.mark.parametrize(
    "case",
    [
        "missing-historical-proof",
        "matched",
        "no-child",
        "unobserved",
        "no-report",
        "failed",
        "bad-pin",
        "bad-canonical-pin",
        "bad-terminal-pin",
        "missing-terminal-pin",
        "bad-query",
        "extra-key",
        "collision",
        "sidecar",
        "existing-wal",
    ],
)
def test_amplifier_width_compare_retained_pair(
    amplifier_width_evidence,
    amplifier_child_fixture,
    tmp_path,
    monkeypatch,
    capsys,
    case,
):
    from uuid import uuid4

    from cadence_mcp_bridge import candidate_execution, parameter_changes
    from cadence_mcp_bridge.analysis_store import AnalysisStore
    from cadence_mcp_bridge.candidate_execution import AmplifierWidthPair
    from cadence_mcp_bridge.domain_provisioning import _canonical
    from cadence_mcp_bridge.generic_ade import ModelInclude
    from cadence_mcp_bridge.operator_operations import OperationProgress

    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    change, readback, binding, dc, ac, child_raw = amplifier_width_evidence
    missing_historical_proof = case == "missing-historical-proof"
    archived = "/fixture/old/../models/root.scs"
    canonical = ModelInclude(path="/fixture/models/root.scs", section="NN", file_sha256="a" * 64)
    model_files = [{"path": canonical.path, "file_sha256": canonical.file_sha256}]
    closure = hashlib.sha256(_canonical(model_files)).hexdigest()

    if missing_historical_proof:
        archived_sha256 = hashlib.sha256(archived.encode()).hexdigest()
        monkeypatch.setattr(
            candidate_execution, "_AMP_ARCHIVED_INCLUDE_PATH_SHA256", archived_sha256
        )
        monkeypatch.setattr(
            candidate_execution,
            "_AMP_CANONICAL_INCLUDE_PATH_SHA256",
            hashlib.sha256(canonical.path.encode()).hexdigest(),
        )
        header = b"simulator lang=spectre\n"
        include = f'include "{archived}" section=NN\n'.encode()

        def archived_input(evidence):
            raw = evidence.baseline_input.replace(header, header + include, 1)
            measurements = list(evidence.baseline.measurements)
            measurements[1] = measurements[1].model_copy(
                update={"input_sha256": hashlib.sha256(raw).hexdigest()}
            )
            sweep = evidence.baseline.model_copy(update={"measurements": tuple(measurements)})
            return replace(
                evidence,
                baseline=sweep,
                baseline_input=raw,
                expected_baseline_sha256=canonical_digest(sweep),
            )

        dc, ac = archived_input(dc), archived_input(ac)
        child_raw = child_raw.replace(header, header + include, 1)
        center_sha256 = hashlib.sha256(dc.baseline_input).hexdigest()
        monkeypatch.setattr(parameter_changes, "_AMP_CENTER_SHA256", center_sha256)
        change = change.model_copy(
            update={
                "baseline": change.baseline.model_copy(update={"netlist_sha256": center_sha256}),
            }
        )
        fields = {"plan_sha256": change.plan_sha256}
        readback = parameter_changes.verify_change_readback(
            change,
            baseline=readback.baseline.model_copy(update=fields),
            reopened=readback.reopened.model_copy(update=fields),
            netlist=readback.netlist.model_copy(
                update={**fields, "artifact_sha256": hashlib.sha256(child_raw).hexdigest()},
            ),
        )
        binding = binding.model_copy(
            update={
                "change_plan_sha256": change.plan_sha256,
                "readback_sha256": canonical_digest(readback),
            }
        )
    files = {}
    journals = []

    def save(name, raw):
        path = tmp_path / name
        path.write_bytes(raw)
        files[path] = raw
        return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}

    def side(mode, evidence, registration):
        sweep_id = str(evidence.baseline.engine.sweep_id) if case != "bad-query" else str(uuid4())
        capture = {
            "query": {"design_id": change.baseline.revision.design_id, "sweep_id": sweep_id},
            "result": evidence.baseline.model_dump(mode="json"),
        }
        data = {
            "baseline_result": save(f"{mode}-result.json", json.dumps(capture).encode()),
            "baseline_result_sha256": evidence.expected_baseline_sha256,
            "baseline_input": save(f"{mode}-input.scs", evidence.baseline_input),
        }
        if case == "no-child":
            return data, registration
        evidence, registration = amplifier_child_fixture(evidence, registration, mode)
        child = evidence.child
        effective_input, report = evidence.child_input, child.report
        if missing_historical_proof:
            effective_input = effective_input.replace(archived.encode(), canonical.path.encode())
            input_sha256 = hashlib.sha256(effective_input).hexdigest()
            alias = None
            if mode == "dc":
                alias = candidate_execution.AmplifierBaselineIncludeAlias(
                    baseline_input_sha256=hashlib.sha256(evidence.baseline_input).hexdigest(),
                    archived_path_sha256=hashlib.sha256(archived.encode()).hexdigest(),
                    canonical_include=canonical,
                    historical_model_closure_sha256=closure,
                    historical_equivalence_receipt_sha256="c" * 64,
                )
            registration = registration.model_copy(
                update={
                    "model_includes": (canonical,),
                    "model_closure_sha256": closure,
                    "baseline_include_alias": alias,
                    "child_input_sha256": input_sha256,
                }
            )
            route, _, _, _ = candidate_execution._width_route(child, effective_input, mode)
            route["ade"]["model_includes"] = [canonical.model_dump(mode="json")]
            route["model_files"] = model_files
            report_data = json.loads(report)
            report_data["execution_input_sha256"] = input_sha256
            report = json.dumps(report_data).encode()
        journal = tmp_path / f"{mode}.sqlite3"
        journals.append(journal)
        store = AnalysisStore(journal)
        identity = child.query.operation_id
        assert store.admit_operation(identity, child.plan)
        failed = case == "failed" and mode == "ac"
        dispatch = OperationProgress(phase="UNKNOWN_OUTCOME")
        store.advance_operation(identity, OperationProgress(phase="ADMITTED"), dispatch)
        progress = child.record.progress
        if failed:
            progress = progress.model_copy(update={"phase": "FAILED"})
        store.advance_operation(identity, dispatch, progress)
        raw = journal.read_bytes()
        files[journal] = raw
        data["child"] = {
            "operation_id": identity,
            "plan_sha256": child.plan.plan_sha256,
            "journal": {"path": str(journal), "sha256": hashlib.sha256(raw).hexdigest()},
            "runtime_manifest": save(f"{mode}-manifest.json", b"{}"),
            "runtime_registration": save(f"{mode}-registration.json", b"{}"),
            "design_registry": save(f"{mode}-registry.json", b"{}"),
            "effective_input": save(f"{mode}-child.scs", effective_input),
        }
        if case == "unobserved" and mode == "ac":
            del data["child"]["journal"]
            data["child"]["execution_plan"] = save(
                f"{mode}-plan.json",
                child.plan.model_dump_json().encode(),
            )
        else:
            data["child"]["terminal_sha256"] = child.expected_terminal_sha256
            if not failed and (case != "no-report" or mode != "ac"):
                data["child"]["report"] = save(f"{mode}-report.json", report)
        return data, registration

    dc_request, dc_binding = side("dc", dc, binding.dc)
    ac_request, ac_binding = side("ac", ac, binding.ac)
    binding = binding.model_copy(update={"dc": dc_binding, "ac": ac_binding})
    request = {
        "change_plan": save("plan.json", change.model_dump_json().encode()),
        "change_plan_sha256": change.plan_sha256,
        "readback": save("readback.json", readback.model_dump_json().encode()),
        "baseline_input": save("center.scs", dc.baseline_input),
        "candidate_input": save("diagnostic-child.scs", child_raw),
        "registration_evidence": save("binding.json", binding.model_dump_json().encode()),
        "dc": dc_request,
        "ac": ac_request,
    }
    target = tmp_path / "comparison.json"
    if case == "bad-pin":
        request["registration_evidence"]["sha256"] = "0" * 64
    elif case == "bad-canonical-pin":
        ac_request["baseline_result_sha256"] = "0" * 64
    elif case == "bad-terminal-pin":
        ac_request["child"]["terminal_sha256"] = "0" * 64
    elif case == "missing-terminal-pin":
        del ac_request["child"]["terminal_sha256"]
    elif case == "extra-key":
        request["goals"] = []
    elif case == "collision":
        target = tmp_path / "diagnostic-child.scs"
    elif case == "sidecar":
        target = tmp_path / "ac.sqlite3-shm"
    elif case == "existing-wal":
        save("ac.sqlite3-wal", b"retained sidecar")
    request_file = save("amp-request.json", json.dumps(request).encode())
    args = [
        "operator-candidates",
        "amplifier-width-compare",
        "--request",
        request_file["path"],
        request_file["sha256"],
        "--output",
        str(target),
    ]
    if case in (
        "matched",
        "missing-historical-proof",
        "no-child",
        "unobserved",
        "no-report",
        "failed",
    ):
        assert main(args) == 0
        summary = output(capsys)
        saved_raw = target.read_bytes()
        saved = json.loads(saved_raw)
        pair = AmplifierWidthPair.model_validate_json(json.dumps(saved["association"]))
        assert summary["status"] == "AMPLIFIER_WIDTH_COMPARISON_EXPORTED"
        assert summary["remote_contact"] is False and pair.execution_authorized is False
        assert summary["file_sha256"] == hashlib.sha256(saved_raw).hexdigest()
        assert saved["request_sha256"] == request_file["sha256"]
        assert saved["requested_width"] == {"value": "19", "unit": "um"}
        assert pair.readback == readback and pair.goals == "GOALS_NOT_PROVIDED"
        assert saved["selected_candidate_id"] is None
        assert str(pair.dc.baseline.job_id) == binding.dc.baseline_operation_id
        assert str(pair.ac.baseline.job_id) == binding.ac.baseline_operation_id
        assert (pair.dc.unit, pair.ac.unit) == ("W", "dB")
        assert (pair.dc.baseline_value, pair.ac.baseline_value) == (0.002, 60.0)
        assert pair.dc.dc_output_reason == "baseline_output_scalars_not_retained"
        if case == "no-child":
            assert pair.dc.child_status == pair.ac.child_status == "NOT_RUN"
            assert saved["deltas"]["dc"] == {
                "absolute_delta": None,
                "reason": "retained_operation_not_supplied",
            }
        else:
            assert pair.dc.child_operation.operation_id == dc_request["child"]["operation_id"]
            assert pair.dc.child_report.analysis_conditions is not None
            assert saved["deltas"]["dc"]["absolute_delta"] == pytest.approx(0.001)
            assert pair.ac.child_operation.operation_id == ac_request["child"]["operation_id"]
            if missing_historical_proof:
                assert pair.dc.model_comparison == "MATCHED"
                assert pair.ac.model_comparison == "NOT_EVALUATED"
                assert pair.ac.child_status == "SUCCEEDED" and pair.ac.child_report is not None
                assert pair.ac.child_value is None
                assert saved["deltas"]["ac"] == {
                    "absolute_delta": None,
                    "reason": "historical_model_equivalence_unavailable",
                }
            elif case == "matched":
                assert pair.ac.child_value == 80.0
                assert saved["deltas"]["ac"] == {"absolute_delta": 20.0, "reason": "available"}
                assert main(args) == 2
                assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
                assert target.read_bytes() == saved_raw
            else:
                assert pair.ac.child_report is None and pair.ac.child_value is None
                status, reason = {
                    "unobserved": ("NOT_OBSERVED", "retained_operation_not_supplied"),
                    "no-report": ("SUCCEEDED", "retained_result_unavailable"),
                    "failed": ("FAILED", "retained_operation_not_succeeded"),
                }[case]
                assert pair.ac.child_status == status
                assert saved["deltas"]["ac"] == {
                    "absolute_delta": None,
                    "reason": reason,
                }
    else:
        assert main(args) == 2
        assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
        assert target.exists() == (case == "collision")
    assert all(path.read_bytes() == raw for path, raw in files.items())
    for journal in journals:
        for suffix in ("-wal", "-shm", "-journal"):
            path = journal.with_name(journal.name + suffix)
            assert path.exists() == (path in files)


def test_amplifier_fresh_width_compare_retains_registered_evidence(
    measurement_operator,
    tmp_path,
    monkeypatch,
    capsys,
):
    import test_candidate_execution as execution_fixture

    from cadence_mcp_bridge import candidate_execution
    from cadence_mcp_bridge.analysis_store import AnalysisStore
    from cadence_mcp_bridge.operator_operations import OperationProgress

    # Reuse the C7 synthetic registered-pair fixture and its compiled-route stub.
    calls = []
    associate = candidate_execution.associate_fresh_amplifier_width_pair

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return associate(*args, **kwargs)

    with monkeypatch.context() as fixture:
        fixture.setattr(execution_fixture, "associate_fresh_amplifier_width_pair", record)
        execution_fixture.test_fresh_amplifier_associates_only_bound_native_reports(
            monkeypatch,
            measurement_operator,
            "not-run",
        )

    (plan, readback), evidence = calls.pop()
    originals = {}

    def pin(path, raw):
        with path.open("xb") as output_file:
            output_file.write(raw)
        originals[path] = raw
        return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}

    def operation(label, retained):
        op = retained.operation
        journal = tmp_path / f"{label}.sqlite3"
        store = AnalysisStore(journal)
        operation_id = op.query.operation_id
        assert store.admit_operation(operation_id, op.plan)
        pending = OperationProgress(phase="UNKNOWN_OUTCOME")
        store.advance_operation(operation_id, OperationProgress(phase="ADMITTED"), pending)
        store.advance_operation(operation_id, pending, op.record.progress)
        raw = journal.read_bytes()
        originals[journal] = raw
        data = {
            "operation_id": operation_id,
            "plan_sha256": op.plan.plan_sha256,
            "journal": {"path": str(journal), "sha256": hashlib.sha256(raw).hexdigest()},
            "terminal_sha256": op.expected_terminal_sha256,
            "effective_input": pin(tmp_path / f"{label}.scs", retained.effective_input),
            "runtime_manifest": pin(tmp_path / f"{label}-manifest.json", b"{}"),
            "runtime_registration": pin(tmp_path / f"{label}-registration.json", b"{}"),
            "design_registry": pin(tmp_path / f"{label}-registry.json", b"{}"),
        }
        if op.report is not None:
            data["report"] = pin(tmp_path / f"{label}-report.json", op.report)
        return data

    request = {
        "change_plan": pin(tmp_path / "plan.json", plan.model_dump_json().encode()),
        "change_plan_sha256": evidence["expected_plan_sha256"],
        "readback": pin(tmp_path / "readback.json", readback.model_dump_json().encode()),
        "baseline_input": pin(tmp_path / "center.scs", evidence["baseline_input"]),
        "candidate_input": pin(tmp_path / "diagnostic.scs", evidence["candidate_input"]),
        "registration_evidence": pin(tmp_path / "binding.json", evidence["registration_evidence"]),
        "dc": {
            "baseline": operation("dc-baseline", evidence["dc"].baseline),
            "candidate": operation("dc-candidate", evidence["dc"].candidate),
        },
        "ac": {"baseline": operation("ac-baseline", evidence["ac"].baseline)},
    }

    def compare(label, destination):
        ref = pin(tmp_path / f"{label}.json", json.dumps(request).encode())
        return main(
            [
                "operator-candidates",
                "amplifier-fresh-width-compare",
                "--request",
                ref["path"],
                ref["sha256"],
                "--output",
                str(destination),
            ]
        )

    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    assert (
        main(
            [
                "operator-candidates",
                "schema",
                "--action",
                "amplifier-fresh-width-compare",
            ]
        )
        == 0
    )
    schema = output(capsys)["request_schema"]
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["_FreshAmplifierWidthSide"]["additionalProperties"] is False
    target = tmp_path / "comparison.json"
    assert compare("valid", target) == 0
    summary = output(capsys)
    raw = target.read_bytes()
    saved = json.loads(raw)
    pair = candidate_execution.FreshAmplifierWidthPair.model_validate_json(
        json.dumps(saved["association"])
    )
    assert summary["status"] == "AMPLIFIER_FRESH_WIDTH_COMPARISON_EXPORTED"
    assert summary["file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert summary["remote_contact"] is False and not pair.execution_authorized
    assert pair.goals == "GOALS_NOT_PROVIDED" and saved["selected_candidate_id"] is None
    assert pair.dc.candidate.operation.operation_id == request["dc"]["candidate"]["operation_id"]
    assert pair.dc.candidate.report.analysis_conditions is not None
    assert saved["deltas"]["dc"] == {"absolute_delta": 0.0, "reason": "available"}
    assert pair.ac.candidate.status == "NOT_RUN" and pair.ac.candidate.value is None
    assert saved["deltas"]["ac"] == {"absolute_delta": None, "reason": "measurement_unavailable"}

    sidecar = tmp_path / "dc-candidate.sqlite3-wal"
    assert compare("sidecar-collision", sidecar) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert compare("duplicate", target) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    request["dc"]["candidate"]["effective_input"]["sha256"] = "0" * 64
    rejected = tmp_path / "rejected.json"
    assert compare("wrong-effective-input-pin", rejected) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert not rejected.exists() and target.read_bytes() == raw
    assert all(path.read_bytes() == raw for path, raw in originals.items())
    assert not any(tmp_path.glob("*.sqlite3-*"))


@pytest.mark.parametrize("separate_baseline", [False, True])
def test_amplifier_saved_width_bias_compare_preserves_retained_and_missing_rows(
    measurement_operator,
    tmp_path,
    monkeypatch,
    capsys,
    separate_baseline,
):
    from uuid import uuid4

    import test_candidate_execution as execution_fixture
    from test_parameter_changes import BASELINE, BIAS, CHILD, VIN, _row

    from cadence_mcp_bridge import candidate_execution
    from cadence_mcp_bridge.analysis_store import AnalysisStore
    from cadence_mcp_bridge.operator_operations import ExplicitValue, OperationProgress
    from cadence_mcp_bridge.parameter_changes import (
        ChangeValue,
        plan_ade_change,
        verify_change_readback,
    )

    calls = []
    associate_width = candidate_execution.associate_fresh_amplifier_width_pair

    def capture(*args, **kwargs):
        calls.append(kwargs)
        return associate_width(*args, **kwargs)

    with monkeypatch.context() as fixture:
        fixture.setattr(execution_fixture, "associate_fresh_amplifier_width_pair", capture)
        execution_fixture.test_fresh_amplifier_associates_only_bound_native_reports(
            monkeypatch,
            measurement_operator,
            None,
        )
    evidence = calls.pop()
    width_route = candidate_execution._width_route
    routes = {}
    originals = {}

    def pin(name, raw):
        path = tmp_path / name
        with path.open("xb") as handle:
            handle.write(raw)
        originals[path] = raw
        return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}

    def stage(label, op, raw):
        store = AnalysisStore(tmp_path / f"{label}.sqlite3")
        query = op.query
        assert store.admit_operation(query.operation_id, op.plan)
        intent = OperationProgress(phase="ADMITTED")
        pending = OperationProgress(phase="UNKNOWN_OUTCOME")
        store.advance_operation(query.operation_id, intent, pending)
        store.advance_operation(query.operation_id, pending, op.record.progress)
        saved = (tmp_path / f"{label}.sqlite3").read_bytes()
        originals[tmp_path / f"{label}.sqlite3"] = saved
        return {
            "operation_id": query.operation_id,
            "plan_sha256": query.expected_plan_sha256,
            "terminal_sha256": op.expected_terminal_sha256,
            "journal": {
                "path": str(tmp_path / f"{label}.sqlite3"),
                "sha256": hashlib.sha256(saved).hexdigest(),
            },
            "runtime_manifest": pin(f"{label}-manifest.json", b"{}"),
            "runtime_registration": pin(f"{label}-registration.json", b"{}"),
            "design_registry": pin(f"{label}-registry.json", b"{}"),
            "effective_input": pin(f"{label}.scs", raw),
            "report": pin(f"{label}-report.json", op.report),
        }

    def center(mode):
        retained = evidence[mode].candidate
        op = retained.operation
        route, conditions, reader, semantics = width_route(op, retained.effective_input, mode)
        routes[op.query.operation_id] = (route, conditions, reader, semantics)
        return op, retained.effective_input

    old_dc, dc_raw = center("dc")
    old_ac, ac_raw = center("ac")
    new_raw = dc_raw.replace(b"VBIASN=0.320", b"VBIASN=0.321")
    new_ac_raw = ac_raw.replace(b"VBIASN=0.320", b"VBIASN=0.321")
    new_plan = old_dc.plan.model_copy(
        update={
            "runner_sha256": "f" * 64,
            "request": old_dc.plan.request.model_copy(
                update={
                    "design_id": "saved-width-bias321",
                    "values": (ExplicitValue(logical_id="vbiasn", value="0.321", unit="V"),),
                }
            ),
        }
    )
    new_query = old_dc.query.model_copy(
        update={
            "operation_id": str(uuid4()),
            "expected_plan_sha256": new_plan.plan_sha256,
        }
    )
    report = json.loads(old_dc.report)
    report.update(
        operation_id=new_query.operation_id,
        plan=new_plan.model_dump(mode="json"),
        execution_input_sha256=hashlib.sha256(new_raw).hexdigest(),
    )
    report_raw = json.dumps(report).encode()
    new_dc = replace(
        old_dc,
        query=new_query,
        plan=new_plan,
        report=report_raw,
        expected_report_sha256=hashlib.sha256(report_raw).hexdigest(),
        record=old_dc.record.model_copy(
            update={
                "operation_id": new_query.operation_id,
                "plan": new_plan,
            }
        ),
    )
    for op, bias in ((old_dc, "0.32"), (new_dc, "0.321")):
        route, conditions, reader, semantics = routes[old_dc.query.operation_id]
        variable = dict(
            logical_id="vbiasn",
            cadence_binding="VBIASN",
            unit="V",
            value_type="real",
            default=bias,
            mutation_policy="fixed",
            range_status="unqualified",
            minimum=None,
            maximum=None,
            step_policy="fixed",
            step=None,
            fixed_value=bias,
            review_id=None,
        )
        routes[op.query.operation_id] = (
            {**route, "variables": [variable], "source_cell": "/fixture/cell", "libraries": []},
            conditions,
            reader,
            semantics,
        )
    old_plan = old_dc.plan.model_copy(
        update={
            "request": old_dc.plan.request.model_copy(
                update={
                    "values": (ExplicitValue(logical_id="vbiasn", value="0.32", unit="V"),),
                }
            ),
        }
    )
    old_report = json.loads(old_dc.report)
    old_report["plan"] = old_plan.model_dump(mode="json")
    old_report_raw = json.dumps(old_report).encode()
    old_dc = replace(
        old_dc,
        plan=old_plan,
        report=old_report_raw,
        query=old_dc.query.model_copy(update={"expected_plan_sha256": old_plan.plan_sha256}),
        expected_report_sha256=hashlib.sha256(old_report_raw).hexdigest(),
        record=old_dc.record.model_copy(update={"plan": old_plan}),
    )
    binding = json.loads(evidence["registration_evidence"])
    binding["candidate"]["dc"]["plan_sha256"] = old_dc.plan.plan_sha256
    monkeypatch.setattr(
        candidate_execution,
        "_width_route",
        lambda op, raw, mode, *, varied_id: routes[op.query.operation_id],
    )
    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))

    action = "amplifier-saved-width-bias-compare"
    request = {
        "width_binding": pin("binding.json", json.dumps(binding).encode()),
        "requested_bias": {"value": "0.3210", "unit": "V"},
        "dc": {
            "baseline": stage("center-dc", old_dc, dc_raw),
            "candidate_query": new_query.model_dump(mode="json"),
            "candidate": stage("new-dc", new_dc, new_raw),
        },
        "ac": {
            "baseline": stage("center-ac", old_ac, ac_raw),
            "candidate_query": {"operation_id": str(uuid4()), "expected_plan_sha256": "e" * 64},
        },
    }

    def compare(label, target):
        ref = pin(f"{label}.json", json.dumps(request).encode())
        return main(
            [
                "operator-candidates",
                action,
                "--request",
                ref["path"],
                ref["sha256"],
                "--output",
                str(target),
            ]
        )

    assert main(["operator-candidates", "schema", "--action", action]) == 0
    schema = output(capsys)["request_schema"]
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["_SavedWidthBiasSide"]["additionalProperties"] is False
    target = tmp_path / "comparison.json"
    assert compare("valid", target) == 0
    summary = output(capsys)
    raw = target.read_bytes()
    saved = json.loads(raw)
    assert summary["status"] == "AMPLIFIER_SAVED_WIDTH_BIAS_COMPARISON_EXPORTED"
    assert summary["file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert summary["remote_contact"] is summary["execution_authorized"] is False
    assert (
        summary["new_simulations"] == summary["new_extractions"] == summary["new_reservations"] == 0
    )
    assert saved["association"]["goals"] == "GOALS_NOT_PROVIDED"
    assert saved["selected_candidate_id"] is None
    assert saved["requested_vbiasn"] == request["requested_bias"]
    assert saved["executed_netlist_vbiasn"]["dc"] == {
        "baseline": {"value": "0.32", "unit": "V"},
        "candidate": {"value": "0.321", "unit": "V"},
    }
    assert saved["saved_ade_bias_readback_status"] == "MISSING"
    assert "persisted_bias_readback" not in saved
    assert "export_receipt_sha256" not in saved
    assert "export_policy_receipt_sha256" not in saved
    assert saved["deltas"]["dc"] == {"absolute_delta": 0.0, "reason": "available"}
    assert saved["association"]["ac"]["baseline"]["status"] == "SUCCEEDED"
    assert saved["association"]["ac"]["candidate"]["status"] == "NOT_OBSERVED"
    assert saved["executed_netlist_vbiasn"]["ac"]["candidate"] is None
    assert saved["deltas"]["ac"]["absolute_delta"] is None

    historical_width = binding["candidate"]
    width = {
        key: historical_width[key]
        for key in (
            "revision_sha256",
            "testbench_revision_sha256",
            "source_tree_sha256",
            "ade_state_sha256",
        )
    }
    if separate_baseline:
        width["ade_state_sha256"] = "8" * 64
    change = plan_ade_change(
        BASELINE.model_copy(
            update={
                "revision_sha256": width["ade_state_sha256"],
                "testbench_revision_sha256": width["testbench_revision_sha256"],
                "netlist_sha256": hashlib.sha256(dc_raw).hexdigest(),
            }
        ),
        "saved-bias",
        CHILD.model_copy(update={"parent_revision_sha256": width["ade_state_sha256"]}),
        BIAS.model_copy(
            update={
                "logical_id": "vbiasn",
                "cadence_binding": "VBIASN",
                "default": "0.32",
                "minimum": "0.32",
                "maximum": "0.321",
                "step": "0.001",
            }
        ),
        VIN.model_copy(update={"logical_id": "vbiasn", "cadence_binding": "VBIASN"}),
        ChangeValue(value="0.32", unit="V"),
        ChangeValue(value="0.321", unit="V"),
        schematic_revision_sha256=width["revision_sha256"],
    )
    baseline, reopened, netlist = (
        _row(change, mode).model_copy(
            update={
                "schematic_revision_sha256": width["revision_sha256"],
                "testbench_revision_sha256": width["testbench_revision_sha256"],
                "revision": change.baseline.revision
                if mode == "baseline"
                else change.candidate_revision,
                **({"revision_sha256": width["ade_state_sha256"]} if mode == "baseline" else {}),
            }
        )
        for mode in ("baseline", "reopened", "netlist")
    )
    reopened = reopened.model_copy(update={"value": ChangeValue(value="0.32100", unit="V")})
    netlist = netlist.model_copy(update={"artifact_sha256": hashlib.sha256(new_raw).hexdigest()})
    readback = verify_change_readback(change, baseline=baseline, reopened=reopened, netlist=netlist)
    assert readback.status == "MATCHED"
    persistence = {
        "change_plan": pin("persisted-plan.json", change.model_dump_json().encode()),
        "change_plan_sha256": change.plan_sha256,
        "readback": pin("persisted-readback.json", readback.model_dump_json().encode()),
        "readback_sha256": canonical_digest(readback),
        "baseline_input": request["dc"]["baseline"]["effective_input"],
        "candidate_input": pin("persisted-child.scs", new_raw),
    }
    request["persisted_bias_readback"] = persistence
    persisted_target = tmp_path / "persisted.json"
    if separate_baseline:
        assert compare("without-required-persistence-baseline", persisted_target) == 2
        assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
        assert not persisted_target.exists()
        persistence["persistence_baseline"] = pin(
            "persistence-baseline.json", json.dumps(width).encode()
        )
    assert compare("with-persisted-evidence", persisted_target) == 0
    receipt = output(capsys)
    persisted_raw = persisted_target.read_bytes()
    assert receipt["file_sha256"] == hashlib.sha256(persisted_raw).hexdigest()
    persisted_saved = json.loads(persisted_raw)
    assert persisted_saved["saved_ade_bias_readback_status"] == "MATCHED"
    assert persisted_saved["association"] == saved["association"]
    assert persisted_saved["persisted_bias_readback"] == readback.model_dump(mode="json")
    assert persisted_saved["persisted_bias_readback"]["reopened"]["value"]["value"] == "0.32100"
    historical_report = saved["association"]["dc"]["candidate"]["report"]
    assert (
        historical_report["analysis_conditions"]["ade_state_tree_sha256"]
        == historical_width["ade_state_sha256"]
    )
    assert reopened.revision_sha256 != width["ade_state_sha256"]
    assert (
        persisted_saved["persisted_bias_readback"]["baseline"]["revision_sha256"]
        == width["ade_state_sha256"]
    )
    if separate_baseline:
        assert (
            persisted_saved["persistence_baseline_sha256"]
            == persistence["persistence_baseline"]["sha256"]
        )
        assert width["ade_state_sha256"] != historical_width["ade_state_sha256"]
    else:
        assert "persistence_baseline_sha256" not in persisted_saved

    assert compare("persisted-alias", tmp_path / "persisted-child.scs") == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert compare("persisted-repeat", persisted_target) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    bad = tmp_path / "persisted-rejected.json"
    sensitivity = (
        (persistence, "readback_sha256"),
        (persistence["readback"], "sha256"),
    )
    for index, (document, key) in enumerate(sensitivity):
        pin_sha = document[key]
        document[key] = "0" * 64
        assert compare(f"persisted-wrong-pin-{index}", bad) == 2
        assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
        document[key] = pin_sha
    if separate_baseline:
        baseline_ref = persistence["persistence_baseline"]
        assert compare("persistence-baseline-alias", tmp_path / "persistence-baseline.json") == 2
        assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
        persistence["persistence_baseline"] = {**baseline_ref, "sha256": "0" * 64}
        assert compare("persistence-baseline-wrong-pin", bad) == 2
        assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
        for key, value in (
            ("source_tree_sha256", "0" * 64),
            ("testbench_revision_sha256", "0" * 64),
            ("revision_sha256", "0" * 64),
            ("dc", historical_width["dc"]),
        ):
            changed = json.dumps({**width, key: value}).encode()
            persistence["persistence_baseline"] = pin(f"wrong-{key}.json", changed)
            assert compare(f"persistence-baseline-wrong-{key}", bad) == 2
            assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert not bad.exists()
    assert persisted_target.read_bytes() == persisted_raw

    if separate_baseline:
        persistence["persistence_baseline"] = baseline_ref
        ac_change = change.model_copy(
            update={
                "baseline": change.baseline.model_copy(
                    update={"netlist_sha256": hashlib.sha256(ac_raw).hexdigest()}
                )
            }
        )
        ac_readback = verify_change_readback(
            ac_change,
            baseline=baseline.model_copy(update={"plan_sha256": ac_change.plan_sha256}),
            reopened=reopened.model_copy(update={"plan_sha256": ac_change.plan_sha256}),
            netlist=netlist.model_copy(
                update={
                    "plan_sha256": ac_change.plan_sha256,
                    "artifact_sha256": hashlib.sha256(new_ac_raw).hexdigest(),
                }
            ),
        )
        ac_pins = {
            "change_plan": pin("export-ac-plan.json", ac_change.model_dump_json().encode()),
            "change_plan_sha256": ac_change.plan_sha256,
            "readback": pin("export-ac-readback.json", ac_readback.model_dump_json().encode()),
            "readback_sha256": canonical_digest(ac_readback),
            "baseline_input": pin("export-ac-baseline.scs", ac_raw),
            "candidate_input": pin("export-ac-candidate.scs", new_ac_raw),
        }
        refs = {
            name: pin(f"export-{name}.json", json.dumps({"artifact": name}).encode())
            for name in (
                "export",
                "policy_receipt",
                "baseline_profile",
                "candidate_profile",
                "reopened_receipt",
                "baseline_receipt",
            )
        }
        request["export_evidence"] = {**refs, "ac_persistence": ac_pins}
        captured = []
        associate = candidate_execution.associate_saved_width_bias_analysis

        def check_export(*args, export_evidence, **kwargs):
            captured.append(export_evidence)
            return associate(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(candidate_execution, "associate_saved_width_bias_analysis", check_export)
            export_target = tmp_path / "export-comparison.json"
            assert compare("with-export-evidence", export_target) == 0
            stdout = output(capsys)
            export_raw = export_target.read_bytes()
            assert stdout["file_sha256"] == hashlib.sha256(export_raw).hexdigest()
            assert stdout["remote_contact"] is stdout["execution_authorized"] is False
            exported = json.loads(export_raw)
            assert exported["export_receipt_sha256"] == refs["export"]["sha256"]
            assert exported["export_policy_receipt_sha256"] == refs["policy_receipt"]["sha256"]
            assert exported["persisted_bias_readback"] == persisted_saved["persisted_bias_readback"]
            assert exported["association"] == persisted_saved["association"]
            (evidence,) = captured
            assert evidence.readback == readback
            assert evidence.persistence_baseline.ade_state_sha256 == width["ade_state_sha256"]
            assert evidence.plan == change and evidence.plan_sha256 == change.plan_sha256
            assert evidence.readback_sha256 == canonical_digest(readback)
            assert evidence.baseline_input == dc_raw and evidence.candidate_input == new_raw
            assert evidence.export_sha256 == refs["export"]["sha256"]
            assert evidence.policy_receipt_sha256 == refs["policy_receipt"]["sha256"]
            for name in refs:
                assert getattr(evidence, name) == (tmp_path / f"export-{name}.json").read_bytes()

            assert compare("export-alias", tmp_path / "export-reopened_receipt.json") == 2
            assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
            assert compare("export-repeat", export_target) == 2
            assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
            assert compare("export-ac-alias", tmp_path / "export-ac-readback.json") == 2
            assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
            refs["candidate_profile"]["sha256"] = "0" * 64
            assert compare("export-wrong-pin", bad) == 2
            assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
            refs["candidate_profile"]["sha256"] = hashlib.sha256(
                (tmp_path / "export-candidate_profile.json").read_bytes()
            ).hexdigest()
            ac_pins["readback_sha256"] = "0" * 64
            assert compare("export-wrong-ac-pin", bad) == 2
            assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
            del request["persisted_bias_readback"]
            assert compare("export-missing-persistence", bad) == 2
            assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
            assert len(captured) == 1
            assert not bad.exists() and export_target.read_bytes() == export_raw
            request["persisted_bias_readback"] = persistence
        del request["export_evidence"]
    del request["persisted_bias_readback"]

    sidecar = tmp_path / "new-dc.sqlite3-wal"
    assert compare("sidecar", sidecar) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert compare("repeat", target) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    identity = dict(request["ac"]["candidate_query"])
    request["ac"]["candidate_query"] = request["dc"]["candidate_query"]
    rejected = tmp_path / "rejected.json"
    assert compare("duplicate-id", rejected) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    request["ac"]["candidate_query"] = identity
    terminal = request["ac"]["baseline"]["terminal_sha256"]
    request["ac"]["baseline"]["terminal_sha256"] = "0" * 64
    assert compare("wrong-center-terminal", rejected) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    request["ac"]["baseline"]["terminal_sha256"] = terminal
    request["dc"]["candidate"]["effective_input"]["sha256"] = "0" * 64
    assert compare("wrong-pin", rejected) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert not rejected.exists() and target.read_bytes() == raw
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert not any(tmp_path.glob("*.sqlite3-*"))


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
