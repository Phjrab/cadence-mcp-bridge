"""Synthetic retained candidates only; never submit, extract or contact a VM."""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_candidate_contracts import candidate_operator, operator, planned

from cadence_mcp_bridge import candidate_reports
from cadence_mcp_bridge.candidate_contracts import CandidateBatchRequest, prepare_candidate_plan
from cadence_mcp_bridge.candidate_reports import (
    CandidateComparison,
    CandidateObservation,
    compare_candidate_reports,
    render_candidate_csv,
)
from cadence_mcp_bridge.operator_operations import (
    DurableOperation,
    OperationProgress,
    OperationRejected,
)
from cadence_mcp_bridge.result_reports import compare, make_report
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["candidate_operator", "operator"]


def succeeded(plan, *, values=(1.0, 2.0, 3.0)):
    observations = []
    evidence = plan.request.fixed_evidence
    for index, (candidate, child) in enumerate(
        zip(plan.request.candidates, plan.plans, strict=True)
    ):
        record = DurableOperation(
            operation_id=candidate.operation_id,
            plan=child,
            progress=OperationProgress(
                phase="SUCCEEDED", remote_revision=5, provider_receipt_sha256="a" * 64
            ),
            event_count=3,
        )
        report = make_report(
            record,
            {
                "status": "NATIVE_RESULT_RETRIEVED",
                "operation_id": candidate.operation_id,
                "plan_sha256": child.plan_sha256,
                "design_id": child.request.design_id,
                "analysis": child.analysis,
                "measurement_id": evidence.measurement_id,
                "reader_registration_sha256": evidence.reader_registration_sha256,
                "execution_input_sha256": hashlib.sha256(f"input-{index}".encode()).hexdigest(),
                "extraction_receipt_sha256": "e" * 64,
                "frame_sha256": "f" * 64,
                "native_provenance": "FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
                "nodes": [{"logical_id": "output", "value": values[index], "unit": "V"}],
                "report_conditions": evidence.conditions.model_dump(mode="json"),
            },
        )
        observations.append(
            CandidateObservation(
                candidate_id=candidate.candidate_id,
                record=record,
                report=report,
            )
        )
    return tuple(observations)


def test_declared_vi_compare_retains_every_input_and_legacy_comparison(candidate_operator):
    plan = planned(candidate_operator)
    observations = succeeded(plan)
    result = compare_candidate_reports(plan, plan.plan_sha256, observations)
    assert [row.status for row in result.rows] == ["SUCCEEDED"] * 3
    assert result.rows[1].metrics[0].absolute_change == 1.0
    assert result.rows[1].metrics[0].relative_change == 1.0
    assert result.rows[2].metrics[0].absolute_change == 2.0
    assert len({row.source_report.execution_input_sha256 for row in result.rows}) == 3
    assert len({row.conditions_sha256 for row in result.rows}) == 1
    assert result.rows[0].requested_values[0].value == "1.00"
    assert result.rows[0].canonical_requested_values[0].value == "1"
    assert all(row.effective_values is None for row in result.rows)
    assert result.verification_at_read == "LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"
    assert not result.remote_contact and result.new_simulations == result.new_reservations == 0
    assert result.native_candidate_qualification == "NOT_ESTABLISHED_BY_LOCAL_COMPARISON"
    assert CandidateComparison.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(OperationRejected) as failure:
        compare([o.report for o in observations])
    assert failure.value.reason == "report_conditions_mismatch"


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "ade",
        "static-load-stimulus",
        "models",
        "analysis-grid",
        "reader",
        "measurement",
        "metric-mapping",
    ],
)
def test_changed_fixed_condition_keeps_row_without_comparing_values(candidate_operator, change):
    plan = planned(candidate_operator)
    observations = list(succeeded(plan))
    payload = json.loads(observations[1].report.model_dump_json())
    if change == "source":
        payload["analysis_conditions"]["source_tree_sha256"] = "0" * 64
    elif change == "ade":
        payload["analysis_conditions"]["ade_state_tree_sha256"] = "0" * 64
    elif change == "static-load-stimulus":
        payload["analysis_conditions"]["static_statements_sha256"] = "0" * 64
    elif change == "models":
        payload["analysis_conditions"]["model_file_sha256"] = []
    elif change == "analysis-grid":
        payload["analysis_conditions"]["analysis_inputs"]["statement_sha256"] = "a" * 64
    elif change == "reader":
        payload["reader_registration_sha256"] = "0" * 64
    elif change == "measurement":
        payload["measurement_id"] = "other-output"
    else:
        payload["metrics"][0]["signal_id"] = "different-node"
    altered = type(observations[1].report).model_validate_json(json.dumps(payload))
    observations[1] = observations[1].model_copy(update={"report": altered})
    result = compare_candidate_reports(plan, plan.plan_sha256, tuple(observations))
    assert result.rows[1].status == "CONDITION_MISMATCH"
    assert result.rows[1].metrics == ()
    assert result.rows[1].source_report == altered
    assert result.rows[0].status == result.rows[2].status == "SUCCEEDED"


@pytest.mark.parametrize(
    "phase",
    [
        "ADMITTED",
        "UNKNOWN_OUTCOME",
        "RESERVED",
        "DISPATCHED",
        "RUNNING",
        "EXTRACTING",
        "FAILED",
        "EXTRACTION_FAILED",
        "CANCELLED",
    ],
)
def test_failures_unknown_and_untouched_rows_are_not_filled_from_baseline(
    candidate_operator, phase
):
    plan = planned(candidate_operator)
    observations = succeeded(plan)
    record = observations[1].record.model_copy(
        update={
            "progress": OperationProgress(
                phase=phase, remote_revision=6, provider_receipt_sha256="b" * 64
            ),
        }
    )
    result = compare_candidate_reports(
        plan,
        plan.plan_sha256,
        (
            observations[0],
            CandidateObservation(candidate_id="voltage", record=record),
        ),
    )
    assert len(result.rows) == 3
    assert result.rows[1].status == phase and result.rows[1].metrics == ()
    assert result.rows[1].source_report is None
    assert result.rows[2].status == "NOT_RUN" and result.rows[2].metrics == ()
    rows = list(csv.DictReader(io.StringIO(render_candidate_csv(result).decode("utf-8-sig"))))
    assert rows[1]["value"] == rows[2]["value"] == ""
    assert rows[1]["status"] == phase and rows[2]["status"] == "NOT_RUN"


def test_missing_report_and_missing_baseline_are_explicit(candidate_operator):
    plan = planned(candidate_operator)
    observations = succeeded(plan)
    result = compare_candidate_reports(
        plan,
        plan.plan_sha256,
        (
            CandidateObservation(candidate_id="baseline", record=observations[0].record),
            observations[1],
        ),
    )
    assert result.rows[0].status == "RESULT_UNAVAILABLE"
    assert result.rows[1].status == "SUCCEEDED"
    assert result.rows[1].metrics[0].metric.value == 2.0
    assert result.rows[1].metrics[0].absolute_change is None
    assert result.rows[1].metrics[0].delta_reason == "baseline_unavailable"
    assert result.common_conditions_sha256 is None


def test_failed_retained_read_preserves_unavailable_reason_and_csv(candidate_operator):
    plan = planned(candidate_operator)
    observations = list(succeeded(plan))
    observations[1] = CandidateObservation(
        candidate_id="voltage",
        record=observations[1].record,
        unavailable_reason="retained_report_read_failed",
    )
    result = compare_candidate_reports(plan, plan.plan_sha256, tuple(observations))
    assert result.rows[1].status == "RESULT_UNAVAILABLE"
    assert result.rows[1].reason == "retained_report_read_failed"
    assert result.rows[1].metrics == () and result.rows[1].source_report is None
    rows = list(csv.DictReader(io.StringIO(render_candidate_csv(result).decode("utf-8-sig"))))
    assert rows[1]["reason"] == "retained_report_read_failed" and rows[1]["value"] == ""
    assert result.rows[0].status == result.rows[2].status == "SUCCEEDED"


def test_unavailable_reason_cannot_label_unrun_failed_or_reported_work(candidate_operator):
    plan = planned(candidate_operator)
    observation = succeeded(plan)[1]
    failed = observation.record.model_copy(
        update={
            "progress": OperationProgress(
                phase="FAILED", remote_revision=6, provider_receipt_sha256="b" * 64
            ),
        }
    )
    for record, report in ((None, None), (failed, None), (observation.record, observation.report)):
        with pytest.raises(ValidationError):
            CandidateObservation(
                candidate_id="voltage",
                record=record,
                report=report,
                unavailable_reason="retained_report_read_failed",
            )


def test_zero_baseline_keeps_absolute_difference_and_null_relative(candidate_operator):
    plan = planned(candidate_operator)
    result = compare_candidate_reports(
        plan, plan.plan_sha256, succeeded(plan, values=(0.0, 2.0, 3.0))
    )
    item = result.rows[1].metrics[0]
    assert item.metric.value == 2.0 and item.baseline_value == 0.0
    assert item.absolute_change == 2.0 and item.relative_change is None
    assert item.delta_reason == "zero_baseline"


@pytest.mark.parametrize(
    "change",
    [
        "manifest",
        "unknown-id",
        "duplicate-id",
        "operation-id",
        "plan",
        "recordless-report",
        "failed-report",
        "nonfinite-model-copy",
    ],
)
def test_retained_identity_and_model_copy_cannot_bypass_validation(candidate_operator, change):
    plan = planned(candidate_operator)
    observations = list(succeeded(plan))
    digest = plan.plan_sha256
    if change == "manifest":
        digest = "0" * 64
    elif change == "unknown-id":
        observations[1] = observations[1].model_copy(update={"candidate_id": "unknown"})
    elif change == "duplicate-id":
        observations[1] = observations[0]
    elif change in ("operation-id", "plan"):
        if change == "operation-id":
            record = observations[1].record.model_copy(update={"operation_id": str(uuid4())})
        else:
            child = observations[1].record.plan.model_copy(update={"grant_sha256": "0" * 64})
            record = observations[1].record.model_copy(update={"plan": child})
        observations[1] = CandidateObservation(candidate_id="voltage", record=record)
    elif change == "recordless-report":
        observations[1] = observations[1].model_copy(update={"record": None})
    elif change == "failed-report":
        record = observations[1].record.model_copy(
            update={
                "progress": OperationProgress(
                    phase="FAILED", remote_revision=6, provider_receipt_sha256="b" * 64
                ),
            }
        )
        observations[1] = observations[1].model_copy(update={"record": record})
    else:
        metric = observations[1].report.metrics[0].model_copy(update={"value": float("inf")})
        report = observations[1].report.model_copy(update={"metrics": (metric,)})
        observations[1] = observations[1].model_copy(update={"report": report})
    with pytest.raises((OperationRejected, ValidationError)):
        compare_candidate_reports(plan, digest, tuple(observations))


@pytest.mark.parametrize(
    "label",
    [
        "=SUM(1,2)",
        "+cmd",
        "-cmd",
        "@SUM(1)",
        ' \t\ufeff=HYPERLINK("x")',
        "\x01\n+cmd",
    ],
)
def test_csv_bom_quoting_korean_and_formula_prefixes(candidate_operator, label):
    context, grant, request, _ = candidate_operator
    payload = json.loads(request.model_dump_json())
    payload["candidates"][1]["label"] = label
    payload["candidates"][2]["label"] = '한글 "후보",\n두 번째 줄'
    request = CandidateBatchRequest.model_validate_json(json.dumps(payload))
    plan = prepare_candidate_plan(context, grant, canonical_digest(grant), request, 100)
    result = compare_candidate_reports(plan, plan.plan_sha256, succeeded(plan))
    raw = render_candidate_csv(result)
    assert raw.startswith(codecs.BOM_UTF8)
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert rows[1]["label"] == "'" + label
    assert result.rows[1].label == label
    assert rows[2]["label"] == payload["candidates"][2]["label"]
    assert rows[1]["unit"] == "V" and rows[1]["value"] == "2.0"
    assert rows[1]["execution_input_sha256"] == result.rows[1].source_report.execution_input_sha256
    assert rows[1]["effective_values_verification"] == "NOT_PRESENT_IN_RETAINED_SCALAR_REPORT"


def test_csv_recomputes_derived_fields_and_bounds_output(candidate_operator, monkeypatch):
    plan = planned(candidate_operator)
    result = compare_candidate_reports(plan, plan.plan_sha256, succeeded(plan))
    fake_metric = result.rows[1].metrics[0].model_copy(update={"absolute_change": 100.0})
    fake_row = result.rows[1].model_copy(update={"metrics": (fake_metric,)})
    fake = result.model_copy(update={"rows": (result.rows[0], fake_row, result.rows[2])})
    with pytest.raises(OperationRejected) as error:
        render_candidate_csv(fake)
    assert error.value.reason == "candidate_comparison_content_mismatch"
    monkeypatch.setattr(candidate_reports, "CSV_LIMIT", 50)
    with pytest.raises(OperationRejected) as error:
        render_candidate_csv(result)
    assert error.value.reason == "candidate_csv_capacity_exceeded"
