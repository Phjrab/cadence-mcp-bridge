"""Synthetic fixtures for the retained finite-grid comparison adapter."""

from __future__ import annotations

from uuid import uuid4

import pytest
from test_amplifier_specifications import source

from cadence_mcp_bridge.amplifier_candidate_selection import (
    GAIN,
    AmplifierCandidateSelectionRequest,
    select_retained_amplifier_candidates,
)
from cadence_mcp_bridge.candidate_selection import CandidateGoal, CandidateLimit
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.resource_policy import FreshResourceCounter, FreshResourcePolicy
from cadence_mcp_bridge.variable_contracts import canonical_digest


@pytest.fixture
async def sweeps(tmp_path):
    roots = {mode: tmp_path / mode for mode in ("dc", "ac")}
    for root in roots.values():
        root.mkdir()
    return tuple([(await source(roots[mode], mode))[2] for mode in roots])


def evaluate(dc, ac, *, dc_pin=None, goals=()):
    return select_retained_amplifier_candidates(
        dc,
        ac,
        expected_dc_sha256=dc_pin or canonical_digest(dc),
        expected_ac_sha256=canonical_digest(ac),
        request=AmplifierCandidateSelectionRequest(
            candidate_values_v=("0.320", "0.321"),
            baseline_vbiasn_v="0.320",
            goals=goals,
        ),
    )


def test_no_goal_preserves_exact_old_points_and_signed_sources(sweeps):
    dc, ac = sweeps
    result = evaluate(dc, ac)
    assert result.selected_candidate_id is None and result.status == "GOALS_NOT_PROVIDED"
    assert [row.requested_vbiasn_v for row in result.rows] == ["0.32", "0.321"]
    assert result.dc.source == dc and result.ac.source == ac
    assert len(result.dc.source.measurements[1].signed_sources) == 6
    for index, row in enumerate(result.rows, 1):
        assert row.dc_point == dc.engine.points[index]
        assert row.ac_point == ac.engine.points[index]
        assert all(point.child_job_id.version == 5 for point in (row.dc_point, row.ac_point))
        assert row.dc_point.applied_value == row.ac_point.applied_value == row.requested_vbiasn_v
        assert [item.value for item in row.metrics] == [0.002, 60.0]
        assert row.status == "NOT_EVALUATED" and row.goals == ()


def test_explicit_unmet_goal_leaves_no_eligible_candidate(sweeps):
    dc, ac = sweeps
    result = evaluate(
        dc,
        ac,
        goals=(
            CandidateGoal(
                metric_id=GAIN.metric_id,
                unit="dB",
                required=CandidateLimit(comparison=">", target="60"),
            ),
        ),
    )
    assert result.status == "NO_ELIGIBLE_CANDIDATE"
    assert [row.goals[0].status for row in result.rows] == ["FAIL", "FAIL"]


@pytest.mark.parametrize("drift", ["capture", "plan", "point", "effective", "definition"])
def test_retained_amplifier_rejects_wrong_digest_or_source_binding(sweeps, drift):
    dc, ac = sweeps
    point = dc.engine.points[1]
    if drift == "capture":
        with pytest.raises(OperationRejected) as failure:
            evaluate(dc, ac, dc_pin="0" * 64)
        assert failure.value.reason == "amplifier_candidate_capture_digest_mismatch"
    elif drift == "definition":
        dc = dc.model_copy(update={"definition_sha256": "0" * 64})
        with pytest.raises(InvalidInputError):
            evaluate(dc, ac)
    else:
        if drift == "plan":
            engine = dc.engine.model_copy(update={"plan_hash": "0" * 64})
            reason = "amplifier_candidate_plan_identity_mismatch"
        else:
            changed = point.model_copy(
                update=(
                    {"operation_key": uuid4()} if drift == "point" else {"applied_value": "0.319"}
                )
            )
            engine = dc.engine.model_copy(
                update={
                    "points": (dc.engine.points[0], changed, dc.engine.points[2]),
                }
            )
            reason = "amplifier_candidate_point_identity_mismatch"
        with pytest.raises(OperationRejected) as failure:
            evaluate(dc.model_copy(update={"engine": engine}), ac)
        assert failure.value.reason == reason


def test_individually_valid_captures_cannot_mix_resource_domains(sweeps):
    dc, ac = sweeps
    domain = str(uuid4())
    policy = FreshResourcePolicy(campaign_id=domain, attempt_ceiling=10, result_ceiling_bytes=5000)
    measurements = tuple(
        metric.model_copy(
            update={
                "counter": FreshResourceCounter(
                    campaign_id=domain,
                    policy=policy,
                    count=index,
                    result_reserved_bytes=1000 * index,
                )
            }
        )
        for index, metric in enumerate(ac.measurements, 1)
    )
    foreign = type(ac).model_validate_json(
        ac.model_copy(
            update={
                "measurements": measurements,
            }
        ).model_dump_json()
    )
    with pytest.raises(OperationRejected) as failure:
        evaluate(dc, foreign)
    assert failure.value.reason == "amplifier_candidate_resource_policy_mismatch"
