"""Synthetic candidate selections, using the existing retained-report path."""

from __future__ import annotations

import csv
import io
import json

import pytest
from pydantic import ValidationError
from test_candidate_contracts import candidate_operator, operator, planned
from test_candidate_execution import analysis_batch
from test_candidate_reports import succeeded

from cadence_mcp_bridge.candidate_contracts import CandidateBatchPlan
from cadence_mcp_bridge.candidate_execution import CandidateAnalysisManifest
from cadence_mcp_bridge.candidate_reports import CandidateObservation, compare_candidate_reports
from cadence_mcp_bridge.candidate_selection import (
    CandidateGoal,
    CandidateLimit,
    CandidateMeasurement,
    CandidateSelectionRequest,
    render_candidate_selection_csv,
    select_candidate_analyses,
    select_candidates,
)
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.result_reports import ReportMetric, ResultReport, make_report
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["candidate_operator", "operator"]

OUTPUT = CandidateMeasurement(metric_id="output", kind="node_voltage", signal_id="output")
POWER = CandidateMeasurement(
    metric_id="rail-power",
    kind="supply_power",
    supply_source_ids=("vdd",),
)


def _comparison(candidate_operator, *, values=(1.0, 2.0, 3.0), power=None, alter=None):
    plan = planned(candidate_operator)
    observations = list(succeeded(plan, values=values))
    if power is not None:
        for index, (observation, delivered) in enumerate(zip(observations, power, strict=True)):
            report = observation.report
            observations[index] = observation.model_copy(
                update={
                    "report": report.model_copy(
                        update={
                            "metrics": report.metrics
                            + (
                                ReportMetric(
                                    kind="delivered_power",
                                    signal_id="vdd",
                                    unit="W",
                                    source_role="supply",
                                    value=delivered,
                                ),
                            )
                        },
                    )
                }
            )
    if alter is not None:
        alter(observations)
    return compare_candidate_reports(plan, plan.plan_sha256, tuple(observations))


def _evaluate(comparison, measurements=(OUTPUT,), goals=()):
    return select_candidates(
        comparison,
        canonical_digest(comparison),
        CandidateSelectionRequest(measurements=measurements, goals=goals),
    )


def test_no_goal_shows_measurements_and_deltas_without_pass_or_winner(candidate_operator):
    comparison = _comparison(candidate_operator, values=(0.0, 1.0, 2.0))
    result = _evaluate(comparison)
    assert result.status == "GOALS_NOT_PROVIDED" and result.selected_candidate_id is None
    assert all(row.status == "NOT_EVALUATED" and row.goals == () for row in result.rows)
    delta = result.rows[2].metrics[0]
    assert (delta.value, delta.unit, delta.absolute_change) == (2, "V", 2)
    assert delta.relative_change is None and delta.delta_reason == "zero_baseline"
    assert result.comparison == comparison


def test_required_limit_filters_before_explicit_power_objective(candidate_operator):
    comparison = _comparison(candidate_operator, power=(0.0, 0.002, 0.003))
    result = _evaluate(
        comparison,
        (OUTPUT, POWER),
        (
            CandidateGoal(
                metric_id="output",
                unit="V",
                required=CandidateLimit(
                    comparison=">=",
                    target="1.5",
                ),
            ),
            CandidateGoal(metric_id="rail-power", unit="W", objective="minimize"),
        ),
    )
    assert result.status == "SELECTED" and result.selected_candidate_id == "voltage"
    assert [row.status for row in result.rows] == ["INELIGIBLE", "SELECTED", "DOMINATED"]
    assert [row.goals[0].status for row in result.rows] == ["FAIL", "PASS", "PASS"]
    assert result.rows[2].dominated_by == ("voltage",)
    assert result.rows[1].metrics[1].value == 0.002
    assert result.layout_handoff == "EFFECTIVE_VALUES_AND_LAYOUT_BINDING_UNVERIFIED"
    assert all(row.effective_values is None for row in result.comparison.rows)
    records = csv.DictReader(
        io.StringIO(render_candidate_selection_csv(result).decode("utf-8-sig"))
    )
    selected = next(row for row in records if row["candidate_id"] == "voltage")
    assert selected["source_revision_sha256"] == "4" * 64
    assert selected["candidate_revision_sha256"] == selected["effective_values_json"] == ""
    assert selected["layout_handoff"] == result.layout_handoff


@pytest.mark.parametrize("equal", [False, True])
def test_pareto_tradeoff_and_exact_tie_keep_all_nondominated_candidates(candidate_operator, equal):
    comparison = _comparison(
        candidate_operator,
        values=(1.0, 2.0, 2.0 if equal else 3.0),
        power=(0.001, 0.001, 0.001 if equal else 0.003),
    )
    result = _evaluate(
        comparison,
        (OUTPUT, POWER),
        (
            CandidateGoal(metric_id="output", unit="V", objective="maximize"),
            CandidateGoal(metric_id="rail-power", unit="W", objective="minimize"),
        ),
    )
    assert result.selected_candidate_id is None
    assert result.status == "MULTIPLE_ELIGIBLE_CANDIDATES"
    assert [row.status for row in result.rows] == ["DOMINATED", "ON_FRONTIER", "ON_FRONTIER"]


def test_missing_failed_and_mismatched_rows_keep_null_values_and_original_evidence(
    candidate_operator,
):
    def alter(observations):
        bad = observations[1]
        report = json.loads(bad.report.model_dump_json())
        report["analysis_conditions"]["static_statements_sha256"] = "0" * 64
        observations[1] = bad.model_copy(
            update={
                "report": ResultReport.model_validate_json(json.dumps(report)),
            }
        )
        failed = observations[2]
        record = failed.record.model_copy(
            update={
                "progress": failed.record.progress.model_copy(
                    update={"phase": "FAILED"},
                )
            }
        )
        observations[2] = CandidateObservation(candidate_id=failed.candidate_id, record=record)

    comparison = _comparison(candidate_operator, alter=alter)
    result = _evaluate(
        comparison,
        (OUTPUT, POWER),
        (
            CandidateGoal(metric_id="output", unit="V", objective="maximize"),
            CandidateGoal(metric_id="rail-power", unit="W", objective="minimize"),
        ),
    )
    assert result.status == "NO_ELIGIBLE_CANDIDATE" and result.selected_candidate_id is None
    assert [row.status for row in result.comparison.rows] == [
        "SUCCEEDED",
        "CONDITION_MISMATCH",
        "FAILED",
    ]
    assert result.rows[0].goals[1].reason == "required_supply_source_unavailable"
    assert result.rows[1].goals[0].status == "CONDITION_MISMATCH"
    assert result.rows[2].goals[0].status == "MISSING_MEASUREMENT"
    for row in result.rows[1:]:
        assert all(item.value is None and item.absolute_change is None for item in row.metrics)


@pytest.mark.parametrize("field", ["metric", "status", "conditions_sha256"])
def test_rebuild_rejects_tampered_comparison_even_with_matching_supplied_digest(
    candidate_operator,
    field,
):
    comparison = _comparison(candidate_operator)
    row = comparison.rows[1]
    if field == "metric":
        metric = row.metrics[0]
        edit = {
            "metrics": (
                metric.model_copy(
                    update={
                        "metric": metric.metric.model_copy(update={"value": 99.0}),
                    }
                ),
            )
        }
    elif field == "status":
        edit = {"status": "FAILED"}
    else:
        edit = {"conditions_sha256": "f" * 64}
    altered = comparison.model_copy(
        update={
            "rows": (comparison.rows[0], row.model_copy(update=edit), comparison.rows[2]),
        }
    )
    with pytest.raises(OperationRejected) as failure:
        _evaluate(altered)
    assert failure.value.reason == "candidate_comparison_content_mismatch"


def test_bad_expected_digest_and_goal_unit_fail_closed(candidate_operator):
    comparison = _comparison(candidate_operator)
    with pytest.raises(OperationRejected) as failure:
        select_candidates(comparison, "0" * 64, CandidateSelectionRequest(measurements=(OUTPUT,)))
    assert failure.value.reason == "candidate_selection_comparison_digest_mismatch"
    with pytest.raises(ValidationError, match="exact unit"):
        _evaluate(
            comparison, goals=(CandidateGoal(metric_id="output", unit="W", objective="maximize"),)
        )


def test_missing_baseline_cannot_rank_incomparable_transient_records(candidate_operator):
    dc = planned(candidate_operator)
    manifest = dc.model_dump(mode="json")
    request = manifest["request"]
    conditions = request["fixed_evidence"]["conditions"]
    conditions["analysis_inputs"] = {
        "analysis": "tran",
        "stop_s": "1e-9",
        "maxstep_s": "1e-11",
        "method": "trap",
    }
    for candidate, child in zip(request["candidates"], manifest["plans"], strict=True):
        candidate["analysis_id"] = child["request"]["analysis_id"] = "synthetic-tran"
        child["analysis"] = "tran"
    plan = CandidateBatchPlan.model_validate_json(json.dumps(manifest))

    observations = []
    for index, prior in enumerate(succeeded(dc)[1:], 1):
        child = plan.plans[index]
        report = prior.report.model_dump(mode="json")
        report.update(
            plan=child.model_dump(mode="json"),
            analysis_conditions=conditions,
            metrics=[
                dict(
                    kind="maximum",
                    signal_id="output",
                    value=index,
                    unit="V",
                    start_s=0,
                    stop_s=1e-9,
                    sample_count=2 + index,
                )
            ],
        )
        observations.append(
            CandidateObservation(
                candidate_id=prior.candidate_id,
                record=prior.record.model_copy(update={"plan": child}),
                report=ResultReport.model_validate_json(json.dumps(report)),
            )
        )
    comparison = compare_candidate_reports(plan, plan.plan_sha256, tuple(observations))
    assert comparison.common_conditions_sha256 is None
    assert comparison.rows[1].conditions_sha256 != comparison.rows[2].conditions_sha256
    result = _evaluate(
        comparison,
        (CandidateMeasurement(metric_id="peak", kind="maximum", signal_id="output"),),
        (CandidateGoal(metric_id="peak", unit="V", objective="maximize"),),
    )
    assert result.status == "NO_ELIGIBLE_CANDIDATE"
    assert result.selected_candidate_id is None
    assert all(row.metrics[0].value is None for row in result.rows)
    assert result.rows[1].goals[0].reason == "common_conditions_unverified"


def test_linked_dc_ac_selection_preserves_each_operation_and_missing_analysis(candidate_operator):
    dc, ac, tran = (analysis_batch(candidate_operator, name) for name in ("dc", "ac", "tran"))
    dc_rows = succeeded(dc)
    ac_rows = []
    for index, (prior, candidate, child) in enumerate(
        zip(
            dc_rows,
            ac.request.candidates,
            ac.plans,
            strict=True,
        )
    ):
        record = prior.record.model_copy(
            update={"operation_id": candidate.operation_id, "plan": child}
        )
        evidence = ac.request.fixed_evidence
        ac_rows.append(
            CandidateObservation(
                candidate_id=candidate.candidate_id,
                record=record,
                report=make_report(
                    record,
                    dict(
                        status="NATIVE_RESULT_RETRIEVED",
                        operation_id=candidate.operation_id,
                        plan_sha256=child.plan_sha256,
                        design_id=candidate.design_id,
                        analysis="ac",
                        measurement_id=evidence.measurement_id,
                        reader_registration_sha256=evidence.reader_registration_sha256,
                        execution_input_sha256="1" * 64,
                        extraction_receipt_sha256="2" * 64,
                        frame_sha256="3" * 64,
                        native_provenance="FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
                        report_conditions=evidence.conditions.model_dump(mode="json"),
                        transfer=[
                            dict(
                                frequency_hz=1000.0,
                                gain_v_per_v=3.0 - index,
                                gain_db=8.0 - index,
                                phase_deg=0.0,
                            )
                        ],
                    ),
                ),
            )
        )
    manifest = CandidateAnalysisManifest(batches=(dc, ac, tran))
    observations = {dc.request.batch_id: dc_rows, ac.request.batch_id: tuple(ac_rows)}
    request = CandidateSelectionRequest(
        measurements=(
            OUTPUT,
            CandidateMeasurement(metric_id="gain", kind="voltage_gain_db", frequency_hz=1000.0),
            CandidateMeasurement(metric_id="peak", kind="maximum", signal_id="output"),
        ),
        goals=(
            CandidateGoal(
                metric_id="output",
                unit="V",
                required=CandidateLimit(
                    comparison=">=",
                    target="2",
                ),
            ),
            CandidateGoal(metric_id="gain", unit="dB", objective="maximize"),
        ),
    )
    result = select_candidate_analyses(manifest, manifest.manifest_sha256, observations, request)
    assert result.selected_candidate_id is None
    assert result.rows[1].goals[1].reason == "cross_analysis_conditions_unverified"
    candidate = result.candidates[1]
    assert candidate.revision.values == dc.plans[1].request.values == ac.plans[1].request.values
    assert [analysis.operation_id for analysis in candidate.analyses] == [
        batch.request.candidates[1].operation_id for batch in (dc, ac, tran)
    ]
    assert [analysis.status for analysis in candidate.analyses] == [
        "SUCCEEDED",
        "SUCCEEDED",
        "NOT_OBSERVED",
    ]
    assert [metric.value for metric in result.rows[1].metrics] == [2.0, 7.0, None]
    assert result.rows[1].metrics[1].absolute_change == -1.0
    assert result.rows[1].metrics[2].reason == "retained_observation_not_supplied"
    csv_data = render_candidate_selection_csv(result).decode("utf-8-sig")
    records = list(csv.DictReader(io.StringIO(csv_data)))
    item = next(
        row for row in records if row["candidate_id"] == "voltage" and row["metric_id"] == "gain"
    )
    assert item["operation_id"] == ac.request.candidates[1].operation_id
    assert item["source_revision_sha256"] == candidate.revision.source_revision_sha256
    assert item["candidate_revision_sha256"] == candidate.revision_sha256
    assert item["value"] == "7.0" and item["unit"] == "dB"
    assert item["goal_reason"] == "cross_analysis_conditions_unverified"
    gain_only = request.model_copy(update={"goals": (request.goals[1],)})
    ranked = select_candidate_analyses(manifest, manifest.manifest_sha256, observations, gain_only)
    assert ranked.selected_candidate_id == "baseline"
