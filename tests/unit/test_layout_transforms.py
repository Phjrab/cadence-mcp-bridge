"""Mathematical DBU cases only; no Cadence/native orientation qualification."""

from itertools import product
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.layout_models import LayoutBBox, LayoutPoint, Orientation
from cadence_mcp_bridge.layout_transforms import (
    compose_orientation,
    inverse_orientation,
    transform_bbox,
    transform_point,
)

ORIENTATIONS: tuple[Orientation, ...] = get_args(Orientation)
PIVOT = LayoutPoint(x=10, y=-4)
SHIFT = LayoutPoint(x=-5, y=7)
BOUND = 2_147_483_647


@pytest.mark.parametrize(
    "orientation,point,bounds",
    [
        ("R0", (8, 5), (6, 4, 10, 6)),
        ("R90", (3, 6), (2, 4, 4, 8)),
        ("R180", (2, 1), (0, 0, 4, 2)),
        ("R270", (7, 0), (6, -2, 8, 2)),
        ("MX", (8, 1), (6, 0, 10, 2)),
        ("MY", (2, 5), (0, 4, 4, 6)),
        ("MXR90", (7, 6), (6, 4, 8, 8)),
        ("MYR90", (3, 0), (2, -2, 4, 2)),
    ],
)
def test_asymmetric_known_values_around_nonzero_pivot(
    orientation: Orientation,
    point: tuple[int, int],
    bounds: tuple[int, int, int, int],
) -> None:
    source = LayoutPoint(x=13, y=-2)
    bbox = LayoutBBox(lower_left=LayoutPoint(x=11, y=-3), upper_right=LayoutPoint(x=15, y=-1))
    before = (source.model_dump_json(), bbox.model_dump_json(), PIVOT.model_dump_json())
    assert transform_point(source, orientation, origin=PIVOT, translation=SHIFT) == LayoutPoint(
        x=point[0],
        y=point[1],
    )
    assert transform_bbox(bbox, orientation, origin=PIVOT, translation=SHIFT) == LayoutBBox(
        lower_left=LayoutPoint(x=bounds[0], y=bounds[1]),
        upper_right=LayoutPoint(x=bounds[2], y=bounds[3]),
    )
    assert before == (source.model_dump_json(), bbox.model_dump_json(), PIVOT.model_dump_json())


def test_composition_is_ordered_and_closes_for_all_orientation_pairs() -> None:
    assert compose_orientation("MX", "R90") == "MXR90"
    assert compose_orientation("R90", "MX") == "MYR90"
    point = LayoutPoint(x=13, y=-2)
    other_shift = LayoutPoint(x=2, y=-3)
    for first, second in product(ORIENTATIONS, repeat=2):
        sequential = transform_point(
            transform_point(point, first, origin=PIVOT, translation=SHIFT),
            second,
            origin=PIVOT,
            translation=other_shift,
        )
        # For a shared pivot: combined shift is B*t_first + t_second.
        combined_shift = transform_point(SHIFT, second, translation=other_shift)
        assert sequential == transform_point(
            point,
            compose_orientation(first, second),
            origin=PIVOT,
            translation=combined_shift,
        )


@pytest.mark.parametrize("orientation", ORIENTATIONS)
def test_inverse_roundtrip_for_point_and_bbox_with_translation(orientation: Orientation) -> None:
    inverse = inverse_orientation(orientation)
    assert compose_orientation(orientation, inverse) == "R0"
    assert compose_orientation(inverse, orientation) == "R0"
    rotated_shift = transform_point(SHIFT, inverse)
    reverse_shift = LayoutPoint(x=-rotated_shift.x, y=-rotated_shift.y)
    point = LayoutPoint(x=-7, y=9)
    bbox = LayoutBBox(lower_left=LayoutPoint(x=-7, y=3), upper_right=LayoutPoint(x=2, y=9))
    assert (
        transform_point(
            transform_point(point, orientation, origin=PIVOT, translation=SHIFT),
            inverse,
            origin=PIVOT,
            translation=reverse_shift,
        )
        == point
    )
    assert (
        transform_bbox(
            transform_bbox(bbox, orientation, origin=PIVOT, translation=SHIFT),
            inverse,
            origin=PIVOT,
            translation=reverse_shift,
        )
        == bbox
    )


def test_integer_intermediates_can_exceed_dbu_but_absolute_outputs_cannot() -> None:
    point = LayoutPoint(x=BOUND, y=-BOUND)
    origin = LayoutPoint(x=-BOUND, y=BOUND)
    assert transform_point(point, "R0", origin=origin) == point
    assert transform_point(LayoutPoint(x=BOUND, y=BOUND), "R180") == LayoutPoint(x=-BOUND, y=-BOUND)
    with pytest.raises(ValidationError):
        transform_point(point, "R0", translation=LayoutPoint(x=1, y=0))
    bbox = LayoutBBox(lower_left=LayoutPoint(x=0, y=0), upper_right=LayoutPoint(x=BOUND, y=2))
    with pytest.raises(ValidationError):
        transform_bbox(bbox, "R0", translation=LayoutPoint(x=1, y=0))


@pytest.mark.parametrize("value", [True, 1.0, "1", float("nan"), float("inf"), BOUND + 1])
@pytest.mark.parametrize("role", ["point", "origin", "translation"])
def test_raw_point_model_bypasses_reject_before_transform(value: Any, role: str) -> None:
    bad = LayoutPoint.model_construct(x=value, y=0)
    point, origin, translation = LayoutPoint(x=1, y=2), PIVOT, SHIFT
    if role == "point":
        point = bad
    elif role == "origin":
        origin = bad
    else:
        translation = bad
    with pytest.raises(ValidationError):
        transform_point(point, "R90", origin=origin, translation=translation)


def test_raw_bbox_model_bypass_and_wrong_object_types_reject() -> None:
    bbox = LayoutBBox(lower_left=LayoutPoint(x=0, y=0), upper_right=LayoutPoint(x=2, y=3))
    invalid = bbox.model_copy(update={"lower_left": LayoutPoint(x=4, y=4)})
    with pytest.raises(ValidationError):
        transform_bbox(invalid, "MX")
    invalid = bbox.model_copy(update={"upper_right": LayoutPoint.model_construct(x=1.0, y=3)})
    with pytest.raises(ValidationError):
        transform_bbox(invalid, "R90")
    with pytest.raises(TypeError, match="point_required"):
        transform_point({"x": 1, "y": 2}, "R0")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="bbox_required"):
        transform_bbox(None, "R0")  # type: ignore[arg-type]


@pytest.mark.parametrize("orientation", ["R45", "r90", "", "R0\n", None, True, 90, []])
def test_unsupported_orientation_rejected_by_every_entry(orientation: Any) -> None:
    point = LayoutPoint(x=1, y=2)
    bbox = LayoutBBox(lower_left=LayoutPoint(x=0, y=0), upper_right=point)
    for call in (
        lambda: transform_point(point, orientation),
        lambda: transform_bbox(bbox, orientation),
        lambda: inverse_orientation(orientation),
        lambda: compose_orientation(orientation, "R0"),
        lambda: compose_orientation("R0", orientation),
    ):
        with pytest.raises(ValueError, match="invalid_orientation"):
            call()
