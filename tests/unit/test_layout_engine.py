"""Pure synthetic geometry cases; no native or PDK acceptance is implied."""

from decimal import localcontext
from typing import Any

import pytest
from test_layout_models import box, fixture_request, fixture_snapshot, reseal

from cadence_mcp_bridge.layout_engine import (
    LayoutRejected,
    build_plan,
    compute_diff,
    dbu_to_um,
    predict_snapshot,
    um_to_dbu,
    validate_plan,
)
from cadence_mcp_bridge.layout_models import (
    ZERO_DIGEST,
    LayoutApplyRequest,
    LayoutPlan,
    LayoutPoint,
    MoveEdit,
)


def test_move_rectangle_connected_pin_payload_preview_and_immutable_source() -> None:
    snapshot = fixture_snapshot()
    before = snapshot.model_dump_json()
    request = fixture_request(snapshot)
    plan = build_plan(snapshot, request)
    predicted, commands = predict_snapshot(snapshot, request)
    assert snapshot.model_dump_json() == before
    assert commands[0].dx_dbu == 5 and commands[0].dy_dbu == -10
    assert commands[1].shape is not None and commands[1].shape.bbox_dbu == box(500, 0, 600, 100)
    assert commands[2].pin is not None and commands[2].pin.net_id == "net-new"
    assert predicted.instances[0].origin_dbu == LayoutPoint(x=5, y=-10)
    assert plan.preview.created == 2 and plan.preview.moved == 1 and plan.preview.deleted == 0
    assert plan.preview.expected_bbox_dbu == box(0, -10, 600, 400)
    assert plan.preview.units == "DBU" and plan.preview.rounding == "reject_off_grid"
    assert plan.preview.predicted_diff.matches_plan is True
    assert len(plan.preview.predicted_diff.changes) == 3
    assert LayoutPlan.model_validate_json(plan.model_dump_json()) == plan
    assert (
        validate_plan(
            snapshot, LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256)
        )
        == plan
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("-0.005", -5),
        ("0", 0),
        ("0.005", 5),
        ("1e-2", 10),
        ("2147483.645", 2147483645),
    ],
)
def test_exact_unit_conversion_even_with_tiny_ambient_decimal_precision(
    text: str,
    expected: int,
) -> None:
    technology = fixture_snapshot().technology
    with localcontext() as context:
        context.prec = 2
        assert um_to_dbu(text, technology) == expected
        assert um_to_dbu(dbu_to_um(expected, technology), technology) == expected


@pytest.mark.parametrize(
    "value", ["NaN", "Infinity", "-Infinity", "1mm", "0.0001", "0.001", "2147483.650", 0.005, True]
)
def test_wrong_nonfinite_fractional_off_grid_and_overflow_units_reject(value: Any) -> None:
    with pytest.raises(ValueError):
        um_to_dbu(value, fixture_snapshot().technology)


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"expected_baseline_sha256": "c" * 64}, "stale_layout_baseline"),
        (
            {"edits": (MoveEdit(kind="move", object_id="missing", dx_um="0.005", dy_um="0"),)},
            "unregistered_layout_object",
        ),
        (
            {"edits": (MoveEdit(kind="move", object_id="inst-one", dx_um="0", dy_um="0"),)},
            "empty_layout_move",
        ),
    ],
)
def test_plan_rejects_stale_missing_and_empty_without_mutation(
    updates: dict[str, Any],
    reason: str,
) -> None:
    snapshot = fixture_snapshot()
    before = snapshot.model_dump_json()
    with pytest.raises(LayoutRejected, match=reason):
        build_plan(snapshot, fixture_request(snapshot).model_copy(update=updates))
    assert snapshot.model_dump_json() == before


def test_registered_target_units_layer_and_source_guard() -> None:
    snapshot = fixture_snapshot()
    request = fixture_request(snapshot)
    cases = [
        (
            request.model_copy(
                update={"binding": request.binding.model_copy(update={"revision_id": "other"})}
            ),
            "stale_revision",
        ),
        (
            request.model_copy(update={"edits": (request.edits[0], request.edits[0])}),
            "duplicate_edit_target",
        ),
        (
            request.model_copy(
                update={"edits": (request.edits[1].model_copy(update={"object_id": "inst-one"}),)}
            ),
            "already_exists",
        ),
        (
            request.model_copy(
                update={"edits": (request.edits[1].model_copy(update={"layer": "unknown"}),)}
            ),
            "unregistered_layer",
        ),
    ]
    for invalid, reason in cases:
        with pytest.raises(ValueError, match=reason):
            build_plan(snapshot, invalid)
    original = reseal(snapshot, owned=False, read_only=True)
    with pytest.raises(LayoutRejected, match="owned_working"):
        build_plan(original, fixture_request(original))


def test_tampered_plan_even_resealed_cannot_reach_worker() -> None:
    snapshot = fixture_snapshot()
    plan = build_plan(snapshot, fixture_request(snapshot))
    with pytest.raises(ValueError, match="digest_mismatch"):
        LayoutPlan.model_validate_json(
            plan.model_copy(update={"expected_semantic_sha256": "d" * 64}).model_dump_json()
        )
    malicious = LayoutPlan.model_validate_json(
        plan.model_copy(
            update={
                "normalized_edits": (
                    plan.normalized_edits[0].model_copy(update={"dx_dbu": 100}),
                    *plan.normalized_edits[1:],
                ),
                "plan_sha256": ZERO_DIGEST,
            }
        ).model_dump_json()
    )
    with pytest.raises(LayoutRejected, match="revalidation_mismatch"):
        validate_plan(
            snapshot, LayoutApplyRequest(plan=malicious, expected_plan_sha256=malicious.plan_sha256)
        )
    with pytest.raises(LayoutRejected, match="expected_plan_digest"):
        validate_plan(snapshot, LayoutApplyRequest(plan=plan, expected_plan_sha256="d" * 64))


def test_readback_diff_detects_changed_missing_extra_and_unexpected_geometry() -> None:
    before = fixture_snapshot()
    expected, _ = predict_snapshot(before, fixture_request(before))
    after = reseal(
        expected,
        shapes=(expected.shapes[-1],),
        instances=(
            expected.instances[0].model_copy(update={"origin_dbu": LayoutPoint(x=10, y=-10)}),
        ),
    )
    diff = compute_diff(before, after, expected=expected)
    assert diff.matches_plan is False
    assert diff.unexpected_object_ids == ("inst-one", "rect-one")
    assert any(c.object_id == "rect-one" and c.kind == "deleted" for c in diff.changes)
    assert any(c.object_id == "inst-one" and "origin_dbu" in c.fields for c in diff.changes)


def test_readback_evidence_flags_and_technology_inventory_order_are_not_geometry() -> None:
    before = fixture_snapshot()
    expected, _ = predict_snapshot(before, fixture_request(before))
    after = reseal(
        expected,
        provenance="native_readback",
        pins=tuple(p.model_copy(update={"association": "native_verified"}) for p in expected.pins),
        technology=expected.technology.model_copy(
            update={
                "provenance": "native_observed",
                "allowed_layer_purposes": expected.technology.allowed_layer_purposes[::-1],
            }
        ),
    )
    diff = compute_diff(before, after, expected=expected)
    assert diff.matches_plan is True and not diff.metadata_changes
    assert diff.changes == compute_diff(before, expected, expected=expected).changes
