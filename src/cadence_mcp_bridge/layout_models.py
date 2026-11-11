"""Bounded layout contract v1. Coordinates are integers in observed technology DBU.

Opaque object IDs are revision-scoped collector identities, never OA pointers.
No model establishes native authority or electrical/manufacturing qualification.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.schematic_plan import PlanDryRun, RevisionBinding, TerminalConnection
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)

ZERO_DIGEST = "0" * 64
DBU = Annotated[int, Field(ge=-2_147_483_647, le=2_147_483_647)]
PositiveDBU = Annotated[int, Field(gt=0, le=2_147_483_647)]
Orientation = Literal["R0", "R90", "R180", "R270", "MX", "MY", "MXR90", "MYR90"]


class LayoutPoint(VariableModel):
    x: DBU
    y: DBU


class LayoutBBox(VariableModel):
    lower_left: LayoutPoint
    upper_right: LayoutPoint

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.lower_left.x >= self.upper_right.x or self.lower_left.y >= self.upper_right.y:
            raise ValueError("layout_bbox_must_have_positive_area")
        return self


class LayerPurpose(VariableModel):
    layer: BindingName
    purpose: BindingName


class LayoutTechnology(VariableModel):
    dbu_per_um: Annotated[int, Field(gt=0, le=1_000_000_000)]
    manufacturing_grid_dbu: PositiveDBU
    allowed_layer_purposes: Annotated[tuple[LayerPurpose, ...], Field(max_length=256)]
    supported_orientations: Annotated[tuple[Orientation, ...], Field(max_length=8)] = ("R0",)
    provenance: Literal["synthetic_fixture", "native_observed"]

    @model_validator(mode="after")
    def unique(self) -> Self:
        pairs = [(item.layer, item.purpose) for item in self.allowed_layer_purposes]
        if len(pairs) != len(set(pairs)) or len(set(self.supported_orientations)) != len(
            self.supported_orientations
        ):
            raise ValueError("duplicate_technology_registration")
        return self

    def semantic_model(self) -> Self:
        return self.model_copy(
            update={
                "provenance": "synthetic_fixture",
                "allowed_layer_purposes": tuple(
                    sorted(self.allowed_layer_purposes, key=lambda p: (p.layer, p.purpose))
                ),
                "supported_orientations": tuple(sorted(self.supported_orientations)),
            }
        )

    @property
    def semantic_sha256(self) -> str:
        return canonical_digest(self.semantic_model())


class LayoutInstance(VariableModel):
    object_id: LogicalId
    master_id: LogicalId
    origin_dbu: LayoutPoint
    orientation: Orientation
    bbox_dbu: LayoutBBox
    pcell_submaster: bool = False


class LayoutShape(VariableModel):
    object_id: LogicalId
    kind: Literal["rect", "path"]
    layer: BindingName
    purpose: BindingName
    bbox_dbu: LayoutBBox
    points_dbu: Annotated[tuple[LayoutPoint, ...], Field(max_length=256)] = ()
    width_dbu: PositiveDBU | None = None

    @model_validator(mode="after")
    def geometry(self) -> Self:
        if self.kind == "rect":
            if self.points_dbu or self.width_dbu is not None:
                raise ValueError("rectangle_has_no_path_parameters")
        elif len(self.points_dbu) < 2 or self.width_dbu is None:
            raise ValueError("path_requires_points_and_positive_width")
        return self


class LayoutPin(VariableModel):
    object_id: LogicalId
    layer: BindingName
    purpose: BindingName
    bbox_dbu: LayoutBBox
    net_id: LogicalId
    terminal_id: LogicalId
    label: BindingName | None = None
    association: Literal["requested", "native_verified", "not_verified"] = "not_verified"


class LayoutCapabilities(VariableModel):
    move: Literal["supported", "not_verified", "unsupported"] = "not_verified"
    add_rect: Literal["supported", "not_verified", "unsupported"] = "not_verified"
    add_pin: Literal["supported", "not_verified", "unsupported"] = "not_verified"
    rotate: Literal["supported", "not_verified", "unsupported"] = "unsupported"
    edit_path: Literal["unsupported"] = "unsupported"
    delete: Literal["unsupported"] = "unsupported"
    pcell_parameters: Literal["unsupported"] = "unsupported"
    via: Literal["unsupported"] = "unsupported"
    auto_route: Literal["unsupported"] = "unsupported"


class LayoutOrientationQualification(VariableModel):
    """Operator-pinned input for the private R0/R90 qualification route."""

    binding: RevisionBinding
    orientations: tuple[Literal["R0"], Literal["R90"]]

    @model_validator(mode="after")
    def child_required(self) -> Self:
        if self.binding.parent_revision_id is None:
            raise ValueError("layout_orientation_qualification_child_required")
        return self


LayoutObject = LayoutInstance | LayoutShape | LayoutPin


class LayoutSnapshot(VariableModel):
    schema_version: Literal[1] = 1
    binding: RevisionBinding
    source_baseline_sha256: Digest
    technology: LayoutTechnology
    instances: Annotated[tuple[LayoutInstance, ...], Field(max_length=4096)] = ()
    shapes: Annotated[tuple[LayoutShape, ...], Field(max_length=4096)] = ()
    pins: Annotated[tuple[LayoutPin, ...], Field(max_length=1024)] = ()
    provenance: Literal["synthetic_fixture", "native_readback", "plan_prediction"]
    owned: bool = False
    read_only: bool = True
    capabilities: LayoutCapabilities = LayoutCapabilities()
    semantic_sha256: Digest = ZERO_DIGEST

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.source_baseline_sha256 != self.binding.source_baseline_sha256:
            raise ValueError("source_baseline_binding_mismatch")
        objects: tuple[LayoutObject, ...] = (*self.instances, *self.shapes, *self.pins)
        ids = [item.object_id for item in objects]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_layout_object_id")
        if not self.owned and not self.read_only:
            raise ValueError("source_snapshot_must_be_read_only")
        grid = self.technology.manufacturing_grid_dbu
        allowed = {(p.layer, p.purpose) for p in self.technology.allowed_layer_purposes}
        for item in objects:
            points = [item.bbox_dbu.lower_left, item.bbox_dbu.upper_right]
            if isinstance(item, LayoutInstance):
                points.append(item.origin_dbu)
                if item.orientation not in self.technology.supported_orientations:
                    raise ValueError("unsupported_orientation")
            else:
                if (item.layer, item.purpose) not in allowed:
                    raise ValueError("unregistered_layer_purpose")
                if isinstance(item, LayoutShape):
                    points.extend(item.points_dbu)
                    if item.width_dbu is not None and item.width_dbu % grid:
                        raise ValueError("path_width_off_grid")
            if any(p.x % grid or p.y % grid for p in points):
                raise ValueError("layout_coordinate_off_grid")
        # Hash actual geometry and technology, excluding evidence labels/capability
        # claims. Ordering/native database handles do not define semantic identity.
        normalized = self.model_copy(
            update={
                "technology": self.technology.semantic_model(),
                "instances": tuple(sorted(self.instances, key=lambda o: o.object_id)),
                "shapes": tuple(sorted(self.shapes, key=lambda o: o.object_id)),
                "pins": tuple(
                    p.model_copy(update={"association": "not_verified"})
                    for p in sorted(self.pins, key=lambda o: o.object_id)
                ),
                "provenance": "plan_prediction",
                "semantic_sha256": ZERO_DIGEST,
                "capabilities": LayoutCapabilities(),
            }
        )
        digest = canonical_digest(normalized)
        if self.semantic_sha256 not in (ZERO_DIGEST, digest):
            raise ValueError("layout_semantic_digest_mismatch")
        object.__setattr__(self, "semantic_sha256", digest)
        return self


class MoveEdit(VariableModel):
    kind: Literal["move"]
    object_id: LogicalId
    dx_um: NumberText
    dy_um: NumberText

    @field_validator("dx_um", "dy_um", mode="before")
    @classmethod
    def finite_decimal(cls, value: str) -> str:
        return number_text(value)


class AddRectEdit(VariableModel):
    kind: Literal["add_rect"]
    object_id: LogicalId
    layer: BindingName
    purpose: BindingName
    bbox_um: tuple[NumberText, NumberText, NumberText, NumberText]

    @field_validator("bbox_um")
    @classmethod
    def finite_decimal_bbox(cls, value: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
        a, b, c, d = (number_text(v) for v in value)
        return a, b, c, d


class AddPinEdit(VariableModel):
    kind: Literal["add_pin"]
    object_id: LogicalId
    layer: BindingName
    purpose: BindingName
    bbox_um: tuple[NumberText, NumberText, NumberText, NumberText]
    net_id: LogicalId
    terminal_id: LogicalId
    label: None = None

    @field_validator("label", mode="before")
    @classmethod
    def label_unsupported(cls, value: object) -> None:
        if value is not None:
            raise ValueError("layout_pin_label_not_supported")
        return None

    @field_validator("bbox_um")
    @classmethod
    def finite_decimal_bbox(cls, value: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
        a, b, c, d = (number_text(v) for v in value)
        return a, b, c, d


class OrientEdit(VariableModel):
    """Absolute instance orientation about its unchanged placement origin."""

    kind: Literal["orient"]
    object_id: LogicalId
    orientation: Orientation


LayoutEdit = Annotated[
    MoveEdit | AddRectEdit | AddPinEdit | OrientEdit, Field(discriminator="kind")
]


class LayoutInspectRequest(VariableModel):
    binding: RevisionBinding


class LayoutForkRequest(VariableModel):
    binding: RevisionBinding
    operation_id: OperationId
    expected_baseline_sha256: Digest

    @model_validator(mode="after")
    def parent_required(self) -> Self:
        if self.binding.parent_revision_id is None:
            raise ValueError("fork_requires_preserved_parent")
        return self


class LayoutPlanRequest(VariableModel):
    binding: RevisionBinding
    operation_id: OperationId
    expected_baseline_sha256: Digest
    edits: Annotated[tuple[LayoutEdit, ...], Field(min_length=1, max_length=128)]


class LayoutNativeEdit(VariableModel):
    """Fixed worker command; geometry is complete, no arbitrary parameters/code."""

    kind: Literal["move", "add_rect", "add_pin"]
    object_id: LogicalId
    before_sha256: Digest | None = None
    dx_dbu: DBU | None = None
    dy_dbu: DBU | None = None
    shape: LayoutShape | None = None
    pin: LayoutPin | None = None

    @model_validator(mode="after")
    def command_shape(self) -> Self:
        if self.kind == "move":
            if (
                self.before_sha256 is None
                or self.dx_dbu is None
                or self.dy_dbu is None
                or self.shape is not None
                or self.pin is not None
            ):
                raise ValueError("invalid_move_command")
        elif self.kind == "add_rect":
            if (
                self.shape is None
                or self.shape.kind != "rect"
                or self.pin is not None
                or self.before_sha256 is not None
                or self.dx_dbu is not None
                or self.dy_dbu is not None
            ):
                raise ValueError("invalid_rectangle_command")
            if self.shape.object_id != self.object_id:
                raise ValueError("command_object_id_mismatch")
        else:
            if (
                self.pin is None
                or self.shape is not None
                or self.before_sha256 is not None
                or self.dx_dbu is not None
                or self.dy_dbu is not None
            ):
                raise ValueError("invalid_pin_command")
            if self.pin.object_id != self.object_id:
                raise ValueError("command_object_id_mismatch")
        return self


class LayoutOrientNativeEdit(VariableModel):
    """Candidate fixed orientation command; native execution is not implemented."""

    kind: Literal["orient"]
    object_id: LogicalId
    before_sha256: Digest
    orientation: Orientation
    origin_dbu: LayoutPoint
    bbox_dbu: LayoutBBox


LayoutNativeCommand = Annotated[
    LayoutNativeEdit | LayoutOrientNativeEdit, Field(discriminator="kind")
]


class LayoutChange(VariableModel):
    object_id: LogicalId
    kind: Literal["created", "modified", "deleted"]
    before_sha256: Digest | None = None
    after_sha256: Digest | None = None
    fields: tuple[str, ...] = ()


class LayoutDiff(VariableModel):
    before_sha256: Digest
    after_sha256: Digest
    changes: Annotated[tuple[LayoutChange, ...], Field(max_length=9216)] = ()
    unexpected_object_ids: tuple[LogicalId, ...] = ()
    metadata_changes: tuple[str, ...] = ()
    matches_plan: bool | None = None


class LayoutPreview(VariableModel):
    units: Literal["DBU"] = "DBU"
    display_units: Literal["um"] = "um"
    rounding: Literal["reject_off_grid"] = "reject_off_grid"
    target_object_ids: tuple[LogicalId, ...]
    created: Annotated[int, Field(ge=0)]
    moved: Annotated[int, Field(ge=0)]
    deleted: Literal[0] = 0
    expected_bbox_dbu: LayoutBBox | None
    predicted_diff: LayoutDiff


class LayoutOrientationPreview(LayoutPreview):
    """Only orientation plans gain this field; legacy preview bytes stay fixed."""

    oriented: Annotated[int, Field(ge=1, le=128)]


class LayoutPlan(VariableModel):
    schema_version: Literal[1] = 1
    request: LayoutPlanRequest
    baseline_sha256: Digest
    normalized_edits: Annotated[
        tuple[LayoutNativeCommand, ...], Field(min_length=1, max_length=128)
    ]
    expected_semantic_sha256: Digest
    preview: LayoutOrientationPreview | LayoutPreview
    plan_sha256: Digest = ZERO_DIGEST

    @model_validator(mode="after")
    def sealed(self) -> Self:
        digest = canonical_digest(self.model_copy(update={"plan_sha256": ZERO_DIGEST}))
        if self.plan_sha256 not in (ZERO_DIGEST, digest):
            raise ValueError("layout_plan_digest_mismatch")
        object.__setattr__(self, "plan_sha256", digest)
        return self


class LayoutApplyRequest(VariableModel):
    plan: LayoutPlan
    expected_plan_sha256: Digest


class LayoutDiffRequest(VariableModel):
    binding: RevisionBinding
    before_revision_id: LogicalId
    expected_before_sha256: Digest


class LayoutSelectRequest(VariableModel):
    binding: RevisionBinding
    expected_baseline_sha256: Digest


class LayoutPhysicalVerification(VariableModel):
    drc: Literal["NOT_RUN", "UNAVAILABLE"] = "NOT_RUN"
    lvs: Literal["NOT_RUN", "UNAVAILABLE"] = "NOT_RUN"
    pex: Literal["NOT_RUN", "UNAVAILABLE"] = "NOT_RUN"


class LayoutResult(VariableModel):
    executed: bool = False
    status: Literal[
        "FORK_VERIFIED",
        "EDIT_VERIFIED",
        "SELECTED",
        "DIFF",
        "NOT_VERIFIED",
        "REJECTED",
        "OUTCOME_UNKNOWN",
    ]
    operation_id: OperationId | None = None
    binding: RevisionBinding
    new_revision: RevisionBinding | None = None
    diff: LayoutDiff | None = None
    snapshot: LayoutSnapshot | None = None
    saved: bool = False
    reopened: bool = False
    source_unchanged: bool = False
    replayed: bool = False
    physical_verification: LayoutPhysicalVerification = LayoutPhysicalVerification()

    @model_validator(mode="after")
    def evidence_required(self) -> Self:
        if self.status in ("EDIT_VERIFIED", "FORK_VERIFIED") and (
            not self.saved
            or not self.reopened
            or not self.source_unchanged
            or self.snapshot is None
            or self.snapshot.provenance != "native_readback"
            or self.snapshot.technology.provenance != "native_observed"
            or self.snapshot.binding != (self.new_revision or self.binding)
        ):
            raise ValueError("native_reopen_evidence_required")
        if self.status == "EDIT_VERIFIED" and (
            self.diff is None or self.diff.matches_plan is not True
        ):
            raise ValueError("matching_native_diff_required")
        if self.replayed and self.executed:
            raise ValueError("replay_cannot_execute_again")
        return self


class LayoutDeviceMaster(VariableModel):
    """Operator-registered logical symbol/device to layout-master relationship."""

    device_id: LogicalId
    layout_master_id: LogicalId


class LayoutMasterMapping(VariableModel):
    """Resolved independently of the candidate; this record grants no authority."""

    registration_id: LogicalId
    schematic_registry_sha256: Digest
    devices: Annotated[tuple[LayoutDeviceMaster, ...], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def unique(self) -> Self:
        if (
            len({d.device_id for d in self.devices}) != 2
            or len({d.layout_master_id for d in self.devices}) != 2
        ):
            raise ValueError("layout_duplicate_device_master_mapping")
        return self

    @property
    def semantic_sha256(self) -> str:
        return canonical_digest(
            self.model_copy(
                update={"devices": tuple(sorted(self.devices, key=lambda d: d.device_id))}
            )
        )


class LayoutDeviceCorrespondence(VariableModel):
    """Proposed logical terminal intent, not observed instance connectivity."""

    schematic_instance_id: LogicalId
    layout_object_id: LogicalId
    connections: Annotated[tuple[TerminalConnection, ...], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def terminals(self) -> Self:
        if {c.terminal_id for c in self.connections} != {"d", "g", "s", "b"}:
            raise ValueError("layout_cmos_terminal_set_mismatch")
        return self


class LayoutCorrespondence(VariableModel):
    """Explicit pair of independently registered schematic/layout revisions."""

    schematic_binding: RevisionBinding
    schematic_semantic_sha256: Digest
    layout_binding: RevisionBinding
    layout_semantic_sha256: Digest
    master_mapping_sha256: Digest
    devices: Annotated[tuple[LayoutDeviceCorrespondence, ...], Field(min_length=2, max_length=2)]

    @model_validator(mode="after")
    def unique(self) -> Self:
        if (
            len({d.schematic_instance_id for d in self.devices}) != 2
            or len({d.layout_object_id for d in self.devices}) != 2
        ):
            raise ValueError("layout_duplicate_device_correspondence")
        return self

    @property
    def semantic_sha256(self) -> str:
        devices = tuple(
            device.model_copy(
                update={
                    "connections": tuple(sorted(device.connections, key=lambda c: c.terminal_id))
                }
            )
            for device in sorted(self.devices, key=lambda d: d.schematic_instance_id)
        )
        return canonical_digest(self.model_copy(update={"devices": devices}))


class LayoutCorrespondenceCheck(VariableModel):
    status: Literal["LOCAL_CORRESPONDENCE_CONSISTENT"] = "LOCAL_CORRESPONDENCE_CONSISTENT"
    executed: Literal[False] = False
    schematic_check: PlanDryRun
    layout_binding: RevisionBinding
    layout_semantic_sha256: Digest
    master_mapping_sha256: Digest
    correspondence_sha256: Digest
    native_connectivity: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    pcell_parameters: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    physical_verification: LayoutPhysicalVerification = LayoutPhysicalVerification()
