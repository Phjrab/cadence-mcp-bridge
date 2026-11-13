"""Pure integer DBU transforms, using an explicit mathematical convention.

Cartesian x points right, y up; R90 is counterclockwise. MX reflects in the
x axis (x, -y), MY in the y axis (-x, y). MXR90 means MX FIRST, then R90,
giving (y, x); MYR90 means MY FIRST, then R90, giving (-y, -x). These names
are mathematical candidates only: native Cadence compatibility is NOT_VERIFIED.

With column vectors, transform_point implements T(p) = o + A(p - o) + t.
The pivot o stays fixed before the final translation t. compose_orientation(a,b)
applies a FIRST, then b, so its matrix is B*A. It composes linear orientations
only. For two transforms with a shared pivot, the combined translation is
B*t_a + t_b. For different pivots, use offsets b_i = (I-A_i)*o_i + t_i;
the total offset is A_b*b_a + b_b. No implicit pivot/translation composition.
An inverse with the same pivot has orientation A^-1 and translation -A^-1*t.

Inputs and outputs use LayoutPoint's strict bounded integer coordinates. Python
integer intermediates are exact/unbounded, including p-o; no rounding or float
conversion occurs. Grid/technology validation belongs to the caller. This module
does no I/O and changes no native capability or P0 request contract.
"""

from __future__ import annotations

from cadence_mcp_bridge.layout_models import LayoutBBox, LayoutPoint, Orientation

_Matrix = tuple[int, int, int, int]
_MATRICES: dict[Orientation, _Matrix] = {
    "R0": (1, 0, 0, 1),
    "R90": (0, -1, 1, 0),
    "R180": (-1, 0, 0, -1),
    "R270": (0, 1, -1, 0),
    "MX": (1, 0, 0, -1),
    "MY": (-1, 0, 0, 1),
    "MXR90": (0, 1, 1, 0),
    "MYR90": (0, -1, -1, 0),
}
_BY_MATRIX = {matrix: orientation for orientation, matrix in _MATRICES.items()}
_ZERO = LayoutPoint(x=0, y=0)


def _matrix(orientation: Orientation) -> _Matrix:
    if type(orientation) is not str or orientation not in _MATRICES:
        raise ValueError("layout_transform_invalid_orientation")
    return _MATRICES[orientation]


def _point(point: LayoutPoint) -> LayoutPoint:
    if not isinstance(point, LayoutPoint):
        raise TypeError("layout_transform_point_required")
    # model_copy/model_construct bypass validation; nested coordinates must be
    # checked as strict Python integers, not coerced through serialization.
    return LayoutPoint.model_validate(point.model_dump(warnings=False))


def _apply(
    point: LayoutPoint,
    matrix: _Matrix,
    origin: LayoutPoint,
    translation: LayoutPoint,
) -> LayoutPoint:
    x, y = point.x - origin.x, point.y - origin.y
    a, b, c, d = matrix
    return LayoutPoint(
        x=origin.x + a * x + b * y + translation.x,
        y=origin.y + c * x + d * y + translation.y,
    )


def transform_point(
    point: LayoutPoint,
    orientation: Orientation,
    *,
    origin: LayoutPoint = _ZERO,
    translation: LayoutPoint = _ZERO,
) -> LayoutPoint:
    """Return o + A(p-o) + t, rejecting invalid inputs or out-of-range output."""
    matrix = _matrix(orientation)
    return _apply(_point(point), matrix, _point(origin), _point(translation))


def transform_bbox(
    bbox: LayoutBBox,
    orientation: Orientation,
    *,
    origin: LayoutPoint = _ZERO,
    translation: LayoutPoint = _ZERO,
) -> LayoutBBox:
    """Transform ALL four corners and recompute axis-aligned minimum/maximum."""
    matrix = _matrix(orientation)
    if not isinstance(bbox, LayoutBBox):
        raise TypeError("layout_transform_bbox_required")
    bbox = LayoutBBox.model_validate(bbox.model_dump(warnings=False))
    origin, translation = _point(origin), _point(translation)
    low, high = bbox.lower_left, bbox.upper_right
    corners = tuple(
        _apply(LayoutPoint(x=x, y=y), matrix, origin, translation)
        for x, y in ((low.x, low.y), (low.x, high.y), (high.x, low.y), (high.x, high.y))
    )
    return LayoutBBox(
        lower_left=LayoutPoint(x=min(p.x for p in corners), y=min(p.y for p in corners)),
        upper_right=LayoutPoint(x=max(p.x for p in corners), y=max(p.y for p in corners)),
    )


def compose_orientation(first: Orientation, second: Orientation) -> Orientation:
    """Return second after first (B*A); pivot/translation are not included."""
    a, b, c, d = _matrix(second)
    e, f, g, h = _matrix(first)
    return _BY_MATRIX[(a * e + b * g, a * f + b * h, c * e + d * g, c * f + d * h)]


def inverse_orientation(orientation: Orientation) -> Orientation:
    """Return the inverse orthogonal matrix (transpose), in this convention."""
    a, b, c, d = _matrix(orientation)
    return _BY_MATRIX[(a, c, b, d)]
