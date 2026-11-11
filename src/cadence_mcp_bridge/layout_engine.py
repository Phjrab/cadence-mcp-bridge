"""Pure layout planning and native read-back comparison, without I/O.

Decimal micrometres convert exactly to DBU. There is no implicit rounding:
fractional DBU and manufacturing-grid violations reject before dispatch.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Literal

from cadence_mcp_bridge.layout_models import (
    ZERO_DIGEST,
    AddPinEdit,
    AddRectEdit,
    LayoutApplyRequest,
    LayoutBBox,
    LayoutChange,
    LayoutCorrespondence,
    LayoutCorrespondenceCheck,
    LayoutDiff,
    LayoutInstance,
    LayoutMasterMapping,
    LayoutNativeCommand,
    LayoutNativeEdit,
    LayoutObject,
    LayoutOrientationPreview,
    LayoutOrientNativeEdit,
    LayoutPin,
    LayoutPlan,
    LayoutPlanRequest,
    LayoutPoint,
    LayoutPreview,
    LayoutShape,
    LayoutSnapshot,
    LayoutTechnology,
    MoveEdit,
    OrientEdit,
)
from cadence_mcp_bridge.layout_transforms import (
    compose_orientation,
    inverse_orientation,
    transform_bbox,
)
from cadence_mcp_bridge.schematic_plan import (
    DeviceRegistry,
    RevisionBinding,
    SchematicPlan,
    dry_run_plan,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest, number_text


class LayoutRejected(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def validate_correspondence(
    schematic: SchematicPlan,
    registry: DeviceRegistry,
    layout: LayoutSnapshot,
    correspondence: LayoutCorrespondence,
    master_mapping: LayoutMasterMapping,
    *,
    expected_schematic_binding: RevisionBinding,
    expected_layout_binding: RevisionBinding,
    schematic_baseline: SchematicPlan | None = None,
) -> LayoutCorrespondenceCheck:
    """Check bounded logical intent against independently resolved registrations.

    The caller resolves both expected bindings and master_mapping independently
    of the proposed correspondence. No PCell arguments, instance-terminal readback
    or physical continuity are inferred from matching IDs or net names.
    """
    schematic = SchematicPlan.model_validate_json(schematic.model_dump_json())
    registry = DeviceRegistry.model_validate_json(registry.model_dump_json())
    layout = LayoutSnapshot.model_validate_json(layout.model_dump_json())
    correspondence = LayoutCorrespondence.model_validate_json(correspondence.model_dump_json())
    master_mapping = LayoutMasterMapping.model_validate_json(master_mapping.model_dump_json())
    expected_layout_binding = RevisionBinding.model_validate_json(
        expected_layout_binding.model_dump_json()
    )
    schematic_check = dry_run_plan(
        schematic, registry, expected_schematic_binding, schematic_baseline
    )
    if (
        correspondence.schematic_binding != schematic.binding
        or correspondence.layout_binding != layout.binding
        or layout.binding != expected_layout_binding
    ):
        raise LayoutRejected("layout_correspondence_revision_mismatch")
    if (schematic.binding.workspace_id, schematic.binding.design_id) != (
        layout.binding.workspace_id,
        layout.binding.design_id,
    ):
        raise LayoutRejected("layout_correspondence_design_mismatch")
    if (
        correspondence.schematic_semantic_sha256 != schematic.semantic_sha256
        or correspondence.layout_semantic_sha256 != layout.semantic_sha256
    ):
        raise LayoutRejected("layout_correspondence_stale_baseline")
    if (
        master_mapping.schematic_registry_sha256 != registry.semantic_sha256
        or correspondence.master_mapping_sha256 != master_mapping.semantic_sha256
    ):
        raise LayoutRejected("layout_correspondence_master_registration_mismatch")
    schematic_devices = {d.instance_id: d for d in schematic.dut.instances}
    layout_devices = {d.object_id: d for d in layout.instances}
    masters = {d.device_id: d.layout_master_id for d in master_mapping.devices}
    if set(masters) != {d.device_id for d in schematic_devices.values()}:
        raise LayoutRejected("layout_correspondence_device_registration_mismatch")
    if {d.schematic_instance_id for d in correspondence.devices} != set(schematic_devices) or {
        d.layout_object_id for d in correspondence.devices
    } != set(layout_devices):
        raise LayoutRejected("layout_correspondence_device_set_mismatch")
    for device in correspondence.devices:
        source = schematic_devices[device.schematic_instance_id]
        target = layout_devices[device.layout_object_id]
        if target.master_id != masters[source.device_id]:
            raise LayoutRejected("layout_correspondence_device_master_mismatch")
        if {c.terminal_id: c.net_id for c in device.connections} != {
            c.terminal_id: c.net_id for c in source.connections
        }:
            raise LayoutRejected("layout_correspondence_terminal_net_mismatch")
    return LayoutCorrespondenceCheck(
        schematic_check=schematic_check,
        layout_binding=layout.binding,
        layout_semantic_sha256=layout.semantic_sha256,
        master_mapping_sha256=master_mapping.semantic_sha256,
        correspondence_sha256=correspondence.semantic_sha256,
    )


def um_to_dbu(value: str, technology: LayoutTechnology) -> int:
    with localcontext() as context:
        context.prec = 128
        scaled = Decimal(number_text(value)) * technology.dbu_per_um
        if scaled != scaled.to_integral_value():
            raise LayoutRejected("fractional_dbu")
        if abs(scaled) > 2_147_483_647:
            raise LayoutRejected("dbu_coordinate_out_of_bounds")
        result = int(scaled)
    if result % technology.manufacturing_grid_dbu:
        raise LayoutRejected("layout_coordinate_off_grid")
    return result


def dbu_to_um(value: int, technology: LayoutTechnology) -> str:
    if type(value) is not int or abs(value) > 2_147_483_647:
        raise LayoutRejected("invalid_dbu_integer")
    with localcontext() as context:
        context.prec = 128
        number = Decimal(value) / technology.dbu_per_um
        # Non-terminating decimal technology scales cannot be displayed exactly.
        text = format(number, "f")
        if Decimal(text) * technology.dbu_per_um != value:
            raise LayoutRejected("nonterminating_display_unit")
        return number_text(text)


def object_digest(item: LayoutObject) -> str:
    if isinstance(item, LayoutPin):
        item = item.model_copy(update={"association": "not_verified"})
    return canonical_digest(item)


def snapshot_objects(snapshot: LayoutSnapshot) -> dict[str, LayoutObject]:
    objects: tuple[LayoutObject, ...] = (*snapshot.instances, *snapshot.shapes, *snapshot.pins)
    return {o.object_id: o for o in objects}


def _fields(item: LayoutObject) -> dict[str, object]:
    data = item.model_dump(mode="json")
    data.pop("association", None)
    return data


def compute_diff(
    before: LayoutSnapshot,
    after: LayoutSnapshot,
    *,
    expected: LayoutSnapshot | None = None,
) -> LayoutDiff:
    before = LayoutSnapshot.model_validate_json(before.model_dump_json())
    after = LayoutSnapshot.model_validate_json(after.model_dump_json())
    if (before.binding.workspace_id, before.binding.design_id) != (
        after.binding.workspace_id,
        after.binding.design_id,
    ):
        raise LayoutRejected("layout_diff_design_mismatch")
    old, new = snapshot_objects(before), snapshot_objects(after)
    changes: list[LayoutChange] = []
    for object_id in sorted(old.keys() | new.keys()):
        a, b = old.get(object_id), new.get(object_id)
        old_hash = object_digest(a) if a is not None else None
        new_hash = object_digest(b) if b is not None else None
        if old_hash == new_hash:
            continue
        kind: Literal["created", "modified", "deleted"] = (
            "created" if a is None else "deleted" if b is None else "modified"
        )
        fields: tuple[str, ...] = ()
        if a is not None and b is not None:
            left, right = _fields(a), _fields(b)
            fields = tuple(
                sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k))
            )
        changes.append(
            LayoutChange(
                object_id=object_id,
                kind=kind,
                before_sha256=old_hash,
                after_sha256=new_hash,
                fields=fields,
            )
        )
    metadata = tuple(
        k
        for k in ("source_baseline_sha256", "technology", "owned", "read_only")
        if (
            before.technology.semantic_sha256 != after.technology.semantic_sha256
            if k == "technology"
            else getattr(before, k) != getattr(after, k)
        )
    )
    unexpected: tuple[str, ...] = ()
    matches = None
    if expected is not None:
        expected = LayoutSnapshot.model_validate_json(expected.model_dump_json())
        wanted = snapshot_objects(expected)
        unexpected = tuple(
            sorted(
                key
                for key in new.keys() | wanted.keys()
                if (object_digest(new[key]) if key in new else None)
                != (object_digest(wanted[key]) if key in wanted else None)
            )
        )
        matches = after.semantic_sha256 == expected.semantic_sha256 and not unexpected
    return LayoutDiff(
        before_sha256=before.semantic_sha256,
        after_sha256=after.semantic_sha256,
        changes=tuple(changes),
        unexpected_object_ids=unexpected,
        metadata_changes=metadata,
        matches_plan=matches,
    )


def _translated(point: LayoutPoint, dx: int, dy: int) -> LayoutPoint:
    return LayoutPoint(x=point.x + dx, y=point.y + dy)


def _move(item: LayoutObject, dx: int, dy: int) -> LayoutObject:
    box = LayoutBBox(
        lower_left=_translated(item.bbox_dbu.lower_left, dx, dy),
        upper_right=_translated(item.bbox_dbu.upper_right, dx, dy),
    )
    changes: dict[str, object] = {"bbox_dbu": box}
    if isinstance(item, LayoutInstance):
        changes["origin_dbu"] = _translated(item.origin_dbu, dx, dy)
    if isinstance(item, LayoutShape) and item.kind == "path":
        changes["points_dbu"] = tuple(_translated(p, dx, dy) for p in item.points_dbu)
    return item.model_copy(update=changes)


def _bbox(edit: AddRectEdit | AddPinEdit, technology: LayoutTechnology) -> LayoutBBox:
    x0, y0, x1, y1 = (um_to_dbu(value, technology) for value in edit.bbox_um)
    return LayoutBBox(lower_left=LayoutPoint(x=x0, y=y0), upper_right=LayoutPoint(x=x1, y=y1))


def _union_bbox(objects: dict[str, LayoutObject]) -> LayoutBBox | None:
    if not objects:
        return None
    boxes = [item.bbox_dbu for item in objects.values()]
    return LayoutBBox(
        lower_left=LayoutPoint(
            x=min(b.lower_left.x for b in boxes), y=min(b.lower_left.y for b in boxes)
        ),
        upper_right=LayoutPoint(
            x=max(b.upper_right.x for b in boxes), y=max(b.upper_right.y for b in boxes)
        ),
    )


def predict_snapshot(
    snapshot: LayoutSnapshot, request: LayoutPlanRequest
) -> tuple[LayoutSnapshot, tuple[LayoutNativeCommand, ...]]:
    snapshot = LayoutSnapshot.model_validate_json(snapshot.model_dump_json())
    request = LayoutPlanRequest.model_validate_json(request.model_dump_json())
    if snapshot.binding != request.binding:
        raise LayoutRejected("stale_revision_binding")
    if snapshot.semantic_sha256 != request.expected_baseline_sha256:
        raise LayoutRejected("stale_layout_baseline")
    if not snapshot.owned or snapshot.read_only or snapshot.binding.parent_revision_id is None:
        raise LayoutRejected("owned_working_revision_required")
    objects = snapshot_objects(snapshot)
    selected: set[str] = set()
    terminals = {pin.terminal_id for pin in snapshot.pins}
    commands: list[LayoutNativeCommand] = []
    allowed = {(p.layer, p.purpose) for p in snapshot.technology.allowed_layer_purposes}
    for edit in request.edits:
        if edit.object_id in selected:
            raise LayoutRejected("duplicate_edit_target")
        selected.add(edit.object_id)
        capability = "rotate" if isinstance(edit, OrientEdit) else edit.kind
        if getattr(snapshot.capabilities, capability) == "unsupported":
            raise LayoutRejected("layout_operation_unsupported")
        if isinstance(edit, OrientEdit):
            item = objects.get(edit.object_id)
            if item is None:
                raise LayoutRejected("unregistered_layout_object")
            if not isinstance(item, LayoutInstance):
                raise LayoutRejected("layout_orientation_requires_instance")
            if item.pcell_submaster:
                raise LayoutRejected("layout_orientation_pcell_submaster_unsupported")
            if edit.orientation not in snapshot.technology.supported_orientations:
                raise LayoutRejected("unsupported_orientation")
            if edit.orientation == item.orientation:
                raise LayoutRejected("empty_layout_orientation")
            # One composite matrix avoids spurious out-of-range intermediates
            # while undoing the old orientation then applying the new one.
            relative = compose_orientation(inverse_orientation(item.orientation), edit.orientation)
            try:
                box = transform_bbox(item.bbox_dbu, relative, origin=item.origin_dbu)
            except ValueError as error:
                raise LayoutRejected("layout_orientation_out_of_bounds") from error
            objects[edit.object_id] = item.model_copy(
                update={"orientation": edit.orientation, "bbox_dbu": box}
            )
            commands.append(
                LayoutOrientNativeEdit(
                    kind="orient",
                    object_id=edit.object_id,
                    before_sha256=object_digest(item),
                    orientation=edit.orientation,
                    origin_dbu=item.origin_dbu,
                    bbox_dbu=box,
                )
            )
        elif isinstance(edit, MoveEdit):
            item = objects.get(edit.object_id)
            if item is None:
                raise LayoutRejected("unregistered_layout_object")
            dx = um_to_dbu(edit.dx_um, snapshot.technology)
            dy = um_to_dbu(edit.dy_um, snapshot.technology)
            if dx == dy == 0:
                raise LayoutRejected("empty_layout_move")
            objects[edit.object_id] = _move(item, dx, dy)
            commands.append(
                LayoutNativeEdit(
                    kind="move",
                    object_id=edit.object_id,
                    before_sha256=object_digest(item),
                    dx_dbu=dx,
                    dy_dbu=dy,
                )
            )
        else:
            if edit.object_id in objects:
                raise LayoutRejected("layout_object_already_exists")
            if (edit.layer, edit.purpose) not in allowed:
                raise LayoutRejected("unregistered_layer_purpose")
            box = _bbox(edit, snapshot.technology)
            if isinstance(edit, AddRectEdit):
                shape = LayoutShape(
                    object_id=edit.object_id,
                    kind="rect",
                    layer=edit.layer,
                    purpose=edit.purpose,
                    bbox_dbu=box,
                )
                objects[edit.object_id] = shape
                commands.append(
                    LayoutNativeEdit(kind="add_rect", object_id=edit.object_id, shape=shape)
                )
            else:
                if edit.terminal_id in terminals:
                    raise LayoutRejected("layout_pin_terminal_conflict")
                terminals.add(edit.terminal_id)
                pin = LayoutPin(
                    object_id=edit.object_id,
                    layer=edit.layer,
                    purpose=edit.purpose,
                    bbox_dbu=box,
                    net_id=edit.net_id,
                    terminal_id=edit.terminal_id,
                    label=edit.label,
                    association="requested",
                )
                objects[edit.object_id] = pin
                commands.append(LayoutNativeEdit(kind="add_pin", object_id=edit.object_id, pin=pin))
    values = tuple(objects.values())
    predicted = LayoutSnapshot.model_validate(
        {
            **snapshot.model_dump(),
            "instances": tuple(o for o in values if isinstance(o, LayoutInstance)),
            "shapes": tuple(o for o in values if isinstance(o, LayoutShape)),
            "pins": tuple(o for o in values if isinstance(o, LayoutPin)),
            "provenance": "plan_prediction",
            "semantic_sha256": ZERO_DIGEST,
        }
    )
    return predicted, tuple(commands)


def build_plan(snapshot: LayoutSnapshot, request: LayoutPlanRequest) -> LayoutPlan:
    predicted, commands = predict_snapshot(snapshot, request)
    diff = compute_diff(snapshot, predicted, expected=predicted)
    preview = LayoutPreview(
        target_object_ids=tuple(e.object_id for e in request.edits),
        created=sum(e.kind in ("add_rect", "add_pin") for e in request.edits),
        moved=sum(e.kind == "move" for e in request.edits),
        expected_bbox_dbu=_union_bbox(snapshot_objects(predicted)),
        predicted_diff=diff,
    )
    oriented = sum(e.kind == "orient" for e in request.edits)
    if oriented:
        preview = LayoutOrientationPreview(**preview.model_dump(), oriented=oriented)
    return LayoutPlan(
        request=request,
        baseline_sha256=snapshot.semantic_sha256,
        normalized_edits=commands,
        expected_semantic_sha256=predicted.semantic_sha256,
        preview=preview,
    )


def validate_plan(snapshot: LayoutSnapshot, request: LayoutApplyRequest) -> LayoutPlan:
    """Provider calls this AFTER durable replay lookup, under its existing lock."""
    request = LayoutApplyRequest.model_validate_json(request.model_dump_json())
    if request.expected_plan_sha256 != request.plan.plan_sha256:
        raise LayoutRejected("layout_expected_plan_digest_mismatch")
    rebuilt = build_plan(snapshot, request.plan.request)
    if rebuilt != request.plan:
        raise LayoutRejected("layout_plan_revalidation_mismatch")
    return rebuilt
