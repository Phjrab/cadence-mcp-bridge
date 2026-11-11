"""Pure synthetic geometry cases; no native or PDK acceptance is implied."""

from decimal import localcontext
from hashlib import sha256
from typing import Any

import pytest
from test_layout_models import (
    box,
    fixture_correspondence,
    fixture_request,
    fixture_snapshot,
    reseal,
)

from cadence_mcp_bridge.layout_engine import (
    LayoutRejected,
    build_plan,
    compute_diff,
    dbu_to_um,
    predict_snapshot,
    um_to_dbu,
    validate_correspondence,
    validate_plan,
)
from cadence_mcp_bridge.layout_models import (
    ZERO_DIGEST,
    LayoutApplyRequest,
    LayoutCorrespondenceCheck,
    LayoutNativeEdit,
    LayoutOrientationPreview,
    LayoutOrientationQualification,
    LayoutOrientNativeEdit,
    LayoutPlan,
    LayoutPoint,
    LayoutSnapshot,
    MoveEdit,
    Orientation,
    OrientEdit,
)


def test_correspondence_matches_independent_view_bindings_without_native_claim() -> None:
    registry, schematic, layout, mapping, correspondence = fixture_correspondence()
    inputs = (registry, schematic, layout, mapping, correspondence)
    before = tuple(value.model_dump_json() for value in inputs)
    result = validate_correspondence(
        schematic,
        registry,
        layout,
        correspondence,
        mapping,
        expected_schematic_binding=schematic.binding,
        expected_layout_binding=layout.binding,
    )
    assert result.status == "LOCAL_CORRESPONDENCE_CONSISTENT"
    assert result.executed is False
    assert result.native_connectivity == result.pcell_parameters == "NOT_VERIFIED"
    assert result.schematic_check.status == "LOCAL_SYNTHETIC_PLAN_VALID"
    assert result.physical_verification.model_dump() == dict(
        drc="NOT_RUN", lvs="NOT_RUN", pex="NOT_RUN"
    )
    assert result.correspondence_sha256 == correspondence.semantic_sha256
    assert schematic.binding.source_baseline_sha256 != layout.binding.source_baseline_sha256
    assert tuple(value.model_dump_json() for value in inputs) == before
    with pytest.raises(ValueError):
        LayoutCorrespondenceCheck.model_validate_json(
            result.model_copy(update={"native_connectivity": "PASS"}).model_dump_json()
        )


@pytest.mark.parametrize("terminal", ["d", "g", "s", "b"])
def test_correspondence_wrong_terminal_net_rejects(terminal: str) -> None:
    registry, schematic, layout, mapping, correspondence = fixture_correspondence()
    device = correspondence.devices[0]
    bad = device.model_copy(
        update={
            "connections": tuple(
                c.model_copy(update={"net_id": "unknown-net"}) if c.terminal_id == terminal else c
                for c in device.connections
            )
        }
    )
    with pytest.raises(LayoutRejected, match="terminal_net_mismatch"):
        validate_correspondence(
            schematic,
            registry,
            layout,
            correspondence.model_copy(update={"devices": (bad, correspondence.devices[1])}),
            mapping,
            expected_schematic_binding=schematic.binding,
            expected_layout_binding=layout.binding,
        )


@pytest.mark.parametrize(
    "field",
    [
        "schematic_semantic_sha256",
        "layout_semantic_sha256",
        "master_mapping_sha256",
    ],
)
def test_correspondence_stale_digests_reject(field: str) -> None:
    registry, schematic, layout, mapping, correspondence = fixture_correspondence()
    with pytest.raises(LayoutRejected, match="stale_baseline|master_registration_mismatch"):
        validate_correspondence(
            schematic,
            registry,
            layout,
            correspondence.model_copy(update={field: "f" * 64}),
            mapping,
            expected_schematic_binding=schematic.binding,
            expected_layout_binding=layout.binding,
        )


@pytest.mark.parametrize("view", ["schematic", "layout"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("revision_id", "stale-revision"),
        ("source_baseline_sha256", "f" * 64),
    ],
)
def test_correspondence_independent_expected_binding_rejects_stale(
    view: str,
    field: str,
    value: str,
) -> None:
    registry, schematic, layout, mapping, correspondence = fixture_correspondence()
    expected_schematic = schematic.binding
    expected_layout = layout.binding
    if view == "schematic":
        expected_schematic = expected_schematic.model_copy(update={field: value})
    else:
        expected_layout = expected_layout.model_copy(update={field: value})
    with pytest.raises(ValueError, match="binding mismatch|revision_mismatch"):
        validate_correspondence(
            schematic,
            registry,
            layout,
            correspondence,
            mapping,
            expected_schematic_binding=expected_schematic,
            expected_layout_binding=expected_layout,
        )


@pytest.mark.parametrize("field", ["schematic_binding", "layout_binding"])
def test_correspondence_proposed_binding_must_match_resolved_view(field: str) -> None:
    registry, schematic, layout, mapping, correspondence = fixture_correspondence()
    wrong = correspondence.model_copy(
        update={field: getattr(correspondence, field).model_copy(update={"revision_id": "other"})}
    )
    with pytest.raises(LayoutRejected, match="revision_mismatch"):
        validate_correspondence(
            schematic,
            registry,
            layout,
            wrong,
            mapping,
            expected_schematic_binding=schematic.binding,
            expected_layout_binding=layout.binding,
        )


def test_correspondence_swapped_masters_and_unregistered_devices_reject() -> None:
    registry, schematic, layout, mapping, correspondence = fixture_correspondence()
    first, second = correspondence.devices
    swapped = correspondence.model_copy(
        update={
            "devices": (
                first.model_copy(update={"layout_object_id": second.layout_object_id}),
                second.model_copy(update={"layout_object_id": first.layout_object_id}),
            )
        }
    )
    with pytest.raises(LayoutRejected, match="device_master_mismatch"):
        validate_correspondence(
            schematic,
            registry,
            layout,
            swapped,
            mapping,
            expected_schematic_binding=schematic.binding,
            expected_layout_binding=layout.binding,
        )
    for field in ("schematic_instance_id", "layout_object_id"):
        wrong = correspondence.model_copy(
            update={
                "devices": (
                    first.model_copy(update={field: "unregistered"}),
                    second,
                )
            }
        )
        with pytest.raises(LayoutRejected, match="device_set_mismatch"):
            validate_correspondence(
                schematic,
                registry,
                layout,
                wrong,
                mapping,
                expected_schematic_binding=schematic.binding,
                expected_layout_binding=layout.binding,
            )


@pytest.mark.parametrize("extra", [False, True])
def test_correspondence_missing_or_extra_layout_instance_rejects_even_with_fresh_hash(
    extra: bool,
) -> None:
    registry, schematic, layout, mapping, correspondence = fixture_correspondence()
    instances = (
        (*layout.instances, layout.instances[0].model_copy(update={"object_id": "extra"}))
        if extra
        else layout.instances[:1]
    )
    layout = reseal(layout, instances=instances)
    correspondence = correspondence.model_copy(
        update={"layout_semantic_sha256": layout.semantic_sha256}
    )
    with pytest.raises(LayoutRejected, match="device_set_mismatch"):
        validate_correspondence(
            schematic,
            registry,
            layout,
            correspondence,
            mapping,
            expected_schematic_binding=schematic.binding,
            expected_layout_binding=layout.binding,
        )


def test_correspondence_registry_and_independent_mapping_mismatch_reject() -> None:
    registry, schematic, layout, mapping, correspondence = fixture_correspondence()
    wrong_registry = mapping.model_copy(update={"schematic_registry_sha256": "f" * 64})
    wrong_device = mapping.model_copy(
        update={
            "devices": (
                mapping.devices[0].model_copy(update={"device_id": "unregistered"}),
                mapping.devices[1],
            )
        }
    )
    for bad, reason in (
        (wrong_registry, "master_registration"),
        (wrong_device, "device_registration"),
    ):
        proposed = correspondence.model_copy(update={"master_mapping_sha256": bad.semantic_sha256})
        with pytest.raises(LayoutRejected, match=reason):
            validate_correspondence(
                schematic,
                registry,
                layout,
                proposed,
                bad,
                expected_schematic_binding=schematic.binding,
                expected_layout_binding=layout.binding,
            )


def test_correspondence_revalidates_unsafe_model_copy_and_cross_design_mapping() -> None:
    registry, schematic, layout, mapping, correspondence = fixture_correspondence()
    duplicate = correspondence.model_copy(update={"devices": (correspondence.devices[0],) * 2})
    with pytest.raises(ValueError, match="duplicate_device_correspondence"):
        validate_correspondence(
            schematic,
            registry,
            layout,
            duplicate,
            mapping,
            expected_schematic_binding=schematic.binding,
            expected_layout_binding=layout.binding,
        )
    layout = reseal(layout, binding=layout.binding.model_copy(update={"design_id": "other-design"}))
    other = correspondence.model_copy(
        update={
            "layout_binding": layout.binding,
            "layout_semantic_sha256": layout.semantic_sha256,
        }
    )
    with pytest.raises(LayoutRejected, match="design_mismatch"):
        validate_correspondence(
            schematic,
            registry,
            layout,
            other,
            mapping,
            expected_schematic_binding=schematic.binding,
            expected_layout_binding=layout.binding,
        )


def test_move_rectangle_connected_pin_payload_preview_and_immutable_source() -> None:
    snapshot = fixture_snapshot()
    before = snapshot.model_dump_json()
    request = fixture_request(snapshot)
    plan = build_plan(snapshot, request)
    predicted, commands = predict_snapshot(snapshot, request)
    assert snapshot.model_dump_json() == before
    assert isinstance(commands[0], LayoutNativeEdit)
    assert isinstance(commands[1], LayoutNativeEdit)
    assert isinstance(commands[2], LayoutNativeEdit)
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


# Independent asymmetric master-local box (5,10)..(35,65), placed at (100,-50).
# These known coordinates do not use the production transform implementation.
_ORIENT_BOXES: dict[Orientation, tuple[int, int, int, int]] = {
    "R0": (105, -40, 135, 15),
    "R90": (35, -45, 90, -15),
    "R180": (65, -115, 95, -60),
    "R270": (110, -85, 165, -55),
    "MX": (105, -115, 135, -60),
    "MY": (65, -40, 95, 15),
    "MXR90": (110, -45, 165, -15),
    "MYR90": (35, -85, 90, -55),
}


def _orient_snapshot(old: Orientation = "R0") -> LayoutSnapshot:
    snapshot = fixture_snapshot()
    instance = snapshot.instances[0].model_copy(
        update={
            "origin_dbu": LayoutPoint(x=100, y=-50),
            "orientation": old,
            "bbox_dbu": box(*_ORIENT_BOXES[old]),
        }
    )
    return reseal(
        snapshot,
        instances=(instance,),
        technology=snapshot.technology.model_copy(
            update={"supported_orientations": tuple(_ORIENT_BOXES)}
        ),
        capabilities=snapshot.capabilities.model_copy(update={"rotate": "not_verified"}),
    )


@pytest.mark.parametrize("old", tuple(_ORIENT_BOXES))
@pytest.mark.parametrize("target", tuple(_ORIENT_BOXES))
def test_orient_absolute_known_asymmetric_pairs(old: Orientation, target: Orientation) -> None:
    snapshot = _orient_snapshot(old)
    original = snapshot.model_dump_json()
    request = fixture_request(snapshot).model_copy(
        update={"edits": (OrientEdit(kind="orient", object_id="inst-one", orientation=target),)}
    )
    if target == old:
        with pytest.raises(LayoutRejected, match="empty_layout_orientation"):
            build_plan(snapshot, request)
        return
    predicted, commands = predict_snapshot(snapshot, request)
    assert predicted.instances[0].bbox_dbu == box(*_ORIENT_BOXES[target])
    assert predicted.instances[0].origin_dbu == snapshot.instances[0].origin_dbu
    assert predicted.instances[0].orientation == target
    assert predicted.instances[0].master_id == snapshot.instances[0].master_id
    assert predicted.shapes == snapshot.shapes and predicted.pins == snapshot.pins
    plan = build_plan(snapshot, request)
    (command,) = commands
    assert isinstance(command, LayoutOrientNativeEdit)
    assert command.bbox_dbu == predicted.instances[0].bbox_dbu
    assert command.origin_dbu == snapshot.instances[0].origin_dbu
    assert command.before_sha256 == plan.preview.predicted_diff.changes[0].before_sha256
    assert set(command.model_dump()) == {
        "kind",
        "object_id",
        "before_sha256",
        "orientation",
        "origin_dbu",
        "bbox_dbu",
    }
    assert isinstance(plan.preview, LayoutOrientationPreview)
    assert plan.preview.oriented == 1 and plan.preview.created == plan.preview.moved == 0
    assert plan.preview.predicted_diff.changes[0].fields == ("bbox_dbu", "orientation")
    roundtrip = LayoutPlan.model_validate_json(plan.model_dump_json())
    assert roundtrip == plan and isinstance(roundtrip.preview, LayoutOrientationPreview)
    assert (
        validate_plan(
            snapshot, LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256)
        )
        == plan
    )
    assert snapshot.model_dump_json() == original


@pytest.mark.parametrize("object_id", ["rect-one", "pin-old", "missing"])
def test_orient_rejects_noninstance_or_missing(object_id: str) -> None:
    snapshot = _orient_snapshot()
    request = fixture_request(snapshot).model_copy(
        update={"edits": (OrientEdit(kind="orient", object_id=object_id, orientation="R90"),)}
    )
    with pytest.raises(LayoutRejected, match="requires_instance|unregistered_layout_object"):
        build_plan(snapshot, request)


@pytest.mark.parametrize("pcell_submaster", [True, False])
def test_orient_nonpcell_scope_matches_native(pcell_submaster: bool) -> None:
    snapshot = _orient_snapshot()
    snapshot = reseal(
        snapshot,
        instances=(snapshot.instances[0].model_copy(update={"pcell_submaster": pcell_submaster}),),
    )
    original = snapshot.model_dump_json()
    request = fixture_request(snapshot).model_copy(
        update={"edits": (OrientEdit(kind="orient", object_id="inst-one", orientation="R90"),)}
    )
    if pcell_submaster:
        with pytest.raises(
            LayoutRejected, match="^layout_orientation_pcell_submaster_unsupported$"
        ):
            build_plan(snapshot, request)
    else:
        predicted, _ = predict_snapshot(snapshot, request)
        assert predicted.instances[0].orientation == "R90"
        assert predicted.instances[0].origin_dbu == snapshot.instances[0].origin_dbu
        assert predicted.instances[0].bbox_dbu == box(*_ORIENT_BOXES["R90"])
    assert snapshot.model_dump_json() == original


def test_orient_rejects_unsupported_capability_orientation_and_duplicate_target() -> None:
    snapshot = _orient_snapshot()
    edit = OrientEdit(kind="orient", object_id="inst-one", orientation="MY")
    request = fixture_request(snapshot).model_copy(update={"edits": (edit,)})
    with pytest.raises(LayoutRejected, match="layout_operation_unsupported"):
        build_plan(reseal(snapshot, capabilities=fixture_snapshot().capabilities), request)
    limited = reseal(
        snapshot,
        technology=snapshot.technology.model_copy(update={"supported_orientations": ("R0",)}),
    )
    with pytest.raises(LayoutRejected, match="unsupported_orientation"):
        build_plan(
            limited,
            request.model_copy(update={"expected_baseline_sha256": limited.semantic_sha256}),
        )
    with pytest.raises(LayoutRejected, match="duplicate_edit_target"):
        build_plan(snapshot, request.model_copy(update={"edits": (edit, request.edits[0])}))


def test_orient_rejects_offgrid_nonfinite_and_output_overflow() -> None:
    snapshot = _orient_snapshot()
    request = fixture_request(snapshot).model_copy(
        update={"edits": (OrientEdit(kind="orient", object_id="inst-one", orientation="R180"),)}
    )
    for coordinate in (101, float("nan"), float("inf")):
        bad = snapshot.instances[0].model_copy(
            update={"origin_dbu": LayoutPoint.model_construct(x=coordinate, y=-50)}
        )
        with pytest.raises(ValueError):
            build_plan(snapshot.model_copy(update={"instances": (bad,)}), request)
    extreme = snapshot.instances[0].model_copy(
        update={"origin_dbu": LayoutPoint(x=2_147_483_645, y=-50)}
    )
    snapshot = reseal(snapshot, instances=(extreme,))
    request = request.model_copy(update={"expected_baseline_sha256": snapshot.semantic_sha256})
    with pytest.raises(LayoutRejected, match="orientation_out_of_bounds"):
        build_plan(snapshot, request)


def test_orient_mixed_preview_and_tampered_native_command() -> None:
    snapshot = _orient_snapshot()
    legacy = fixture_request(snapshot)
    request = legacy.model_copy(
        update={
            "edits": (
                OrientEdit(kind="orient", object_id="inst-one", orientation="R90"),
                *legacy.edits[1:],
            )
        }
    )
    plan = build_plan(snapshot, request)
    assert isinstance(plan.preview, LayoutOrientationPreview)
    assert plan.preview.oriented == 1 and plan.preview.created == 2 and plan.preview.moved == 0
    assert all(isinstance(c, LayoutNativeEdit) for c in plan.normalized_edits[1:])
    tampered = plan.model_copy(
        update={
            "normalized_edits": (
                plan.normalized_edits[0].model_copy(update={"orientation": "MY"}),
                *plan.normalized_edits[1:],
            ),
            "plan_sha256": ZERO_DIGEST,
        }
    )
    tampered = LayoutPlan.model_validate_json(tampered.model_dump_json())
    with pytest.raises(LayoutRejected, match="revalidation_mismatch"):
        validate_plan(
            snapshot, LayoutApplyRequest(plan=tampered, expected_plan_sha256=tampered.plan_sha256)
        )


def test_orient_preserves_exact_legacy_plan_and_normalized_bytes() -> None:
    # Captured from unchanged867797f before this additive contract implementation.
    snapshot = fixture_snapshot()
    request = fixture_request(snapshot)
    plan = build_plan(snapshot, request)
    expected = {
        "snapshot": "c53fa48ed69aad2b8845bc7eeedcbd6afcbcfaa62a6a9544fa8c2c45892f126a",
        "request": "a86ff90e1e8abae85bd40c1f447fe2f075c54978163fe6177dccc5ba1c59f9e2",
        "plan": "037f52479247e446cfcbc987c90a7568c4fd42e7cb9c6ddbee089a7ac2709333",
        "preview": "447858bac7d1fbbf8d11364c757010dd0789345a686b9fc0f5351bd39b479bf0",
    }
    for name, value in {
        "snapshot": snapshot,
        "request": request,
        "plan": plan,
        "preview": plan.preview,
    }.items():
        assert sha256(value.model_dump_json().encode()).hexdigest() == expected[name]
    assert sha256(
        "".join(e.model_dump_json() for e in plan.normalized_edits).encode()
    ).hexdigest() == ("92c5256f6ac446ab2980e938b25e6b04c247979ca7a4e5557c5d30a2d293840a")
    assert plan.plan_sha256 == "865eeeb090317f1b7eb9c6ed9bf9bae715d939dc722381920768a09bd38c3bbe"


def _qualification_fixture(old: Orientation = "R0") -> LayoutSnapshot:
    snapshot = _orient_snapshot(old)
    return reseal(
        snapshot,
        provenance="native_readback",
        technology=snapshot.technology.model_copy(
            update={"provenance": "native_observed", "supported_orientations": ("R0", "R90", "MX")}
        ),
    )


def test_orientation_qualification_binds_plan_and_stable_readback() -> None:
    before = _qualification_fixture()
    qualification = LayoutOrientationQualification(
        binding=before.binding, orientations=("R0", "R90")
    )
    request = fixture_request(before).model_copy(
        update={
            "edits": (OrientEdit(kind="orient", object_id="inst-one", orientation="R90"),),
        }
    )
    with pytest.raises(LayoutRejected, match="layout_orientation_qualification_required"):
        build_plan(before, request)
    plan = build_plan(before, request, orientation_qualification=qualification)
    apply = LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256)
    assert validate_plan(before, apply, orientation_qualification=qualification) == plan
    predicted, _ = predict_snapshot(before, request, orientation_qualification=qualification)
    after = _qualification_fixture("R90")
    assert after.technology.supported_orientations == before.technology.supported_orientations
    assert after.capabilities.rotate == before.capabilities.rotate == "not_verified"
    assert before.semantic_sha256 != after.semantic_sha256 == plan.expected_semantic_sha256
    diff = compute_diff(before, after, expected=predicted)
    assert diff.matches_plan is True and diff.metadata_changes == ()


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("mirror_target", "unsupported_orientation"),
        ("mirror_source", "unsupported_orientation"),
        ("pcell", "layout_orientation_pcell_submaster_unsupported"),
        ("other_revision", "layout_orientation_qualification_binding_mismatch"),
        ("unprojected", "layout_orientation_qualification_snapshot_mismatch"),
        ("unsupported", "layout_orientation_qualification_snapshot_mismatch"),
    ],
)
def test_orientation_qualification_rejects_unqualified_plan(case: str, reason: str) -> None:
    before = _qualification_fixture("MX" if case == "mirror_source" else "R0")
    binding = before.binding
    if case == "other_revision":
        binding = binding.model_copy(update={"revision_id": "other-child"})
    elif case == "pcell":
        before = reseal(
            before, instances=(before.instances[0].model_copy(update={"pcell_submaster": True}),)
        )
    elif case == "unprojected":
        before = reseal(
            before,
            technology=before.technology.model_copy(update={"supported_orientations": ("R0",)}),
        )
    elif case == "unsupported":
        before = reseal(before, capabilities=fixture_snapshot().capabilities)
    qualification = LayoutOrientationQualification(binding=binding, orientations=("R0", "R90"))
    target: Orientation = "MX" if case == "mirror_target" else "R90"
    request = fixture_request(before).model_copy(
        update={
            "edits": (OrientEdit(kind="orient", object_id="inst-one", orientation=target),),
        }
    )
    with pytest.raises(LayoutRejected, match=f"^{reason}$"):
        build_plan(before, request, orientation_qualification=qualification)


def test_orientation_qualification_cannot_expand_registered_pair() -> None:
    before = _qualification_fixture()
    with pytest.raises(ValueError):
        LayoutOrientationQualification.model_validate(
            {
                "binding": before.binding,
                "orientations": ("R0", "R45"),
            }
        )
