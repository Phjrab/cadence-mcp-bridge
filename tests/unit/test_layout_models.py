"""Synthetic contract fixtures only; these tests never contact Cadence."""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.layout_models import (
    ZERO_DIGEST,
    AddPinEdit,
    AddRectEdit,
    LayerPurpose,
    LayoutBBox,
    LayoutCapabilities,
    LayoutCorrespondence,
    LayoutDeviceCorrespondence,
    LayoutDeviceMaster,
    LayoutInstance,
    LayoutMasterMapping,
    LayoutPin,
    LayoutPlanRequest,
    LayoutPoint,
    LayoutResult,
    LayoutShape,
    LayoutSnapshot,
    LayoutTechnology,
    MoveEdit,
    OrientEdit,
)
from cadence_mcp_bridge.schematic_plan import (
    DeviceRegistry,
    RevisionBinding,
    SchematicPlan,
    synthetic_inverter_fixture,
)

OPERATION_ID = "37072af1-a8dc-4cb1-a6c1-d4c585baac29"


@pytest.mark.parametrize("value", ["R45", "r90", 90, None, float("nan"), float("inf")])
def test_orient_schema_rejects_unknown_or_nontext_orientation(value: Any) -> None:
    with pytest.raises(ValidationError):
        OrientEdit.model_validate({"kind": "orient", "object_id": "inst-one", "orientation": value})


@pytest.mark.parametrize("extra", [{"pivot": [0, 0]}, {"angle": 90}, {"dx_um": "1"}])
def test_orient_schema_rejects_free_pivot_angle_or_translation(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        OrientEdit.model_validate(
            {
                "kind": "orient",
                "object_id": "inst-one",
                "orientation": "R90",
                **extra,
            }
        )


def box(x0: int = 0, y0: int = 0, x1: int = 100, y1: int = 200) -> LayoutBBox:
    return LayoutBBox(lower_left=LayoutPoint(x=x0, y=y0), upper_right=LayoutPoint(x=x1, y=y1))


def fixture_snapshot() -> LayoutSnapshot:
    return LayoutSnapshot(
        binding=RevisionBinding(
            workspace_id="fixture-work",
            design_id="fixture-design",
            revision_id="child",
            parent_revision_id="parent",
            parent_revision_sha256="b" * 64,
            source_baseline_sha256="a" * 64,
        ),
        source_baseline_sha256="a" * 64,
        technology=LayoutTechnology(
            dbu_per_um=1000,
            manufacturing_grid_dbu=5,
            allowed_layer_purposes=(
                LayerPurpose(layer="metal1", purpose="drawing"),
                LayerPurpose(layer="metal1", purpose="pin"),
            ),
            supported_orientations=("R0", "R90"),
            provenance="synthetic_fixture",
        ),
        instances=(
            LayoutInstance(
                object_id="inst-one",
                master_id="fixture-master",
                origin_dbu=LayoutPoint(x=0, y=0),
                orientation="R0",
                bbox_dbu=box(),
            ),
        ),
        shapes=(
            LayoutShape(
                object_id="rect-one",
                kind="rect",
                layer="metal1",
                purpose="drawing",
                bbox_dbu=box(300, 0, 400, 100),
            ),
        ),
        pins=(
            LayoutPin(
                object_id="pin-old",
                layer="metal1",
                purpose="pin",
                bbox_dbu=box(0, 300, 100, 400),
                net_id="net-old",
                terminal_id="terminal-old",
            ),
        ),
        provenance="synthetic_fixture",
        owned=True,
        read_only=False,
        capabilities=LayoutCapabilities(
            move="supported", add_rect="supported", add_pin="supported"
        ),
    )


def fixture_request(snapshot: LayoutSnapshot | None = None) -> LayoutPlanRequest:
    snapshot = snapshot or fixture_snapshot()
    return LayoutPlanRequest(
        binding=snapshot.binding,
        operation_id=OPERATION_ID,
        expected_baseline_sha256=snapshot.semantic_sha256,
        edits=(
            MoveEdit(kind="move", object_id="inst-one", dx_um="0.005", dy_um="-0.010"),
            AddRectEdit(
                kind="add_rect",
                object_id="rect-new",
                layer="metal1",
                purpose="drawing",
                bbox_um=("0.5", "0", "0.6", "0.1"),
            ),
            AddPinEdit(
                kind="add_pin",
                object_id="pin-new",
                layer="metal1",
                purpose="pin",
                bbox_um=("0.5", "0.2", "0.6", "0.3"),
                net_id="net-new",
                terminal_id="terminal-new",
            ),
        ),
    )


def reseal(snapshot: LayoutSnapshot, **updates: Any) -> LayoutSnapshot:
    return LayoutSnapshot.model_validate_json(
        snapshot.model_copy(update={**updates, "semantic_sha256": ZERO_DIGEST}).model_dump_json()
    )


def fixture_correspondence() -> tuple[
    DeviceRegistry, SchematicPlan, LayoutSnapshot, LayoutMasterMapping, LayoutCorrespondence
]:
    """Independent synthetic registrations; no PDK master/parameter assertions."""
    binding = RevisionBinding(
        workspace_id="fixture-work",
        design_id="fixture-design",
        revision_id="schematic-r1",
        source_baseline_sha256="c" * 64,
    )
    registry, schematic = synthetic_inverter_fixture(binding)
    layout_binding = binding.model_copy(
        update={"revision_id": "layout-r1", "source_baseline_sha256": "d" * 64}
    )
    snapshot = fixture_snapshot()
    devices = tuple(
        LayoutInstance(
            object_id=f"layout-{device.instance_id}",
            master_id=f"master-{device.device_id}",
            origin_dbu=LayoutPoint(x=index * 200, y=0),
            orientation="R0",
            bbox_dbu=box(index * 200, 0, index * 200 + 100, 200),
            pcell_submaster=True,
        )
        for index, device in enumerate(schematic.dut.instances)
    )
    layout = reseal(
        snapshot,
        binding=layout_binding,
        source_baseline_sha256="d" * 64,
        instances=devices,
        shapes=(),
        pins=(),
    )
    mapping = LayoutMasterMapping(
        registration_id="synthetic-master-map",
        schematic_registry_sha256=registry.semantic_sha256,
        devices=tuple(
            LayoutDeviceMaster(device_id=d.device_id, layout_master_id=f"master-{d.device_id}")
            for d in schematic.dut.instances
        ),
    )
    correspondence = LayoutCorrespondence(
        schematic_binding=schematic.binding,
        schematic_semantic_sha256=schematic.semantic_sha256,
        layout_binding=layout.binding,
        layout_semantic_sha256=layout.semantic_sha256,
        master_mapping_sha256=mapping.semantic_sha256,
        devices=tuple(
            LayoutDeviceCorrespondence(
                schematic_instance_id=d.instance_id,
                layout_object_id=f"layout-{d.instance_id}",
                connections=d.connections,
            )
            for d in schematic.dut.instances
        ),
    )
    return registry, schematic, layout, mapping, correspondence


def test_correspondence_hashes_ignore_device_and_terminal_order() -> None:
    _, _, _, mapping, correspondence = fixture_correspondence()
    reordered = correspondence.model_copy(
        update={
            "devices": tuple(
                d.model_copy(update={"connections": d.connections[::-1]})
                for d in correspondence.devices[::-1]
            )
        }
    )
    assert reordered.semantic_sha256 == correspondence.semantic_sha256
    assert mapping.model_copy(update={"devices": mapping.devices[::-1]}).semantic_sha256 == (
        mapping.semantic_sha256
    )
    assert (
        LayoutCorrespondence.model_validate_json(correspondence.model_dump_json()) == correspondence
    )


@pytest.mark.parametrize("field", ["schematic_instance_id", "layout_object_id"])
def test_correspondence_duplicate_device_ids_reject(field: str) -> None:
    correspondence = fixture_correspondence()[-1]
    data = correspondence.model_dump(mode="json")
    data["devices"][1][field] = data["devices"][0][field]
    with pytest.raises(ValidationError, match="duplicate_device_correspondence"):
        LayoutCorrespondence.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("field", ["device_id", "layout_master_id"])
def test_correspondence_duplicate_registered_master_ids_reject(field: str) -> None:
    mapping = fixture_correspondence()[-2]
    data = mapping.model_dump(mode="json")
    data["devices"][1][field] = data["devices"][0][field]
    with pytest.raises(ValidationError, match="duplicate_device_master_mapping"):
        LayoutMasterMapping.model_validate_json(json.dumps(data))


def test_correspondence_missing_devices_terminals_and_extra_input_reject() -> None:
    correspondence = fixture_correspondence()[-1]
    for devices in ((), correspondence.devices[:1]):
        with pytest.raises(ValidationError):
            LayoutCorrespondence.model_validate_json(
                correspondence.model_copy(update={"devices": devices}).model_dump_json()
            )
    device = correspondence.devices[0]
    for connections in (device.connections[:3], (device.connections[0],) * 4):
        with pytest.raises(ValidationError):
            LayoutDeviceCorrespondence.model_validate_json(
                device.model_copy(update={"connections": connections}).model_dump_json()
            )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        LayoutCorrespondence.model_validate_json(
            json.dumps({**correspondence.model_dump(mode="json"), "pcell_script": "arbitrary"})
        )


def test_snapshot_json_roundtrip_digest_and_stable_order() -> None:
    snapshot = fixture_snapshot()
    assert LayoutSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    shuffled = reseal(
        snapshot,
        technology=snapshot.technology.model_copy(
            update={
                "allowed_layer_purposes": snapshot.technology.allowed_layer_purposes[::-1],
                "supported_orientations": snapshot.technology.supported_orientations[::-1],
                "provenance": "native_observed",
            }
        ),
        provenance="native_readback",
        pins=tuple(p.model_copy(update={"association": "native_verified"}) for p in snapshot.pins),
    )
    assert shuffled.semantic_sha256 == snapshot.semantic_sha256
    assert reseal(snapshot, instances=()).semantic_sha256 != snapshot.semantic_sha256


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"owned": False}, "read_only"),
        ({"source_baseline_sha256": "c" * 64}, "baseline_binding"),
        ({"semantic_sha256": "f" * 64}, "digest_mismatch"),
    ],
)
def test_snapshot_invalid_bindings_reject(updates: dict[str, Any], reason: str) -> None:
    payload = fixture_snapshot().model_dump()
    payload.update(updates)
    with pytest.raises(ValidationError, match=reason):
        LayoutSnapshot.model_validate(payload)


@pytest.mark.parametrize("value", [True, 1.0, float("nan"), float("inf"), "5", 2**31])
def test_dbu_must_be_bounded_strict_integer(value: Any) -> None:
    with pytest.raises(ValidationError):
        LayoutPoint(x=value, y=0)


def test_bbox_grid_layers_orientation_and_duplicate_ids_reject() -> None:
    snapshot = fixture_snapshot()
    with pytest.raises(ValidationError, match="positive_area"):
        box(100, 0, 0, 10)
    cases: list[tuple[dict[str, Any], str]] = [
        ({"origin_dbu": LayoutPoint(x=1, y=0)}, "off_grid"),
        ({"orientation": "R180"}, "unsupported_orientation"),
    ]
    for update, reason in cases:
        with pytest.raises(ValidationError, match=reason):
            reseal(snapshot, instances=(snapshot.instances[0].model_copy(update=update),))
    with pytest.raises(ValidationError, match="unregistered_layer"):
        reseal(snapshot, shapes=(snapshot.shapes[0].model_copy(update={"layer": "unknown"}),))
    with pytest.raises(ValidationError, match="duplicate_layout"):
        reseal(snapshot, shapes=(snapshot.shapes[0], snapshot.shapes[0]))


def test_arbitrary_code_paths_parameters_and_operations_are_not_inputs() -> None:
    request = fixture_request()
    for payload in (
        {**request.model_dump(), "path": "/tmp/arbitrary"},
        {**request.model_dump(), "skill": "dbSave(cv)"},
        {**request.model_dump(), "operation_id": "not-a-uuid"},
        {**request.model_dump(), "edits": ({"kind": "delete_hierarchy", "object_id": "all"},)},
    ):
        with pytest.raises(ValidationError):
            LayoutPlanRequest.model_validate(payload)
    for object_id in ("../secret", "x;system", "$(whoami)", "0x1234"):
        with pytest.raises(ValidationError):
            MoveEdit(kind="move", object_id=object_id, dx_um="0", dy_um="1")


def test_fixture_cannot_claim_native_edit_verification() -> None:
    snapshot = fixture_snapshot()
    with pytest.raises(ValidationError, match="native_reopen"):
        LayoutResult(
            status="EDIT_VERIFIED",
            binding=snapshot.binding,
            snapshot=snapshot,
            saved=True,
            reopened=True,
            source_unchanged=True,
        )
    with pytest.raises(ValidationError, match="replay_cannot_execute"):
        LayoutResult(status="NOT_VERIFIED", binding=snapshot.binding, executed=True, replayed=True)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1mm", "1e100"])
def test_nonfinite_and_wrong_units_reject_at_typed_boundary(value: str) -> None:
    with pytest.raises(ValidationError):
        MoveEdit(kind="move", object_id="inst-one", dx_um=value, dy_um="0")
    with pytest.raises(ValidationError):
        AddRectEdit(
            kind="add_rect",
            object_id="new",
            layer="metal1",
            purpose="drawing",
            bbox_um=("0", "0", value, "1"),
        )
    with pytest.raises(ValidationError):
        AddPinEdit(
            kind="add_pin",
            object_id="new",
            layer="metal1",
            purpose="pin",
            bbox_um=("0", "0", "1", value),
            net_id="net",
            terminal_id="term",
        )
