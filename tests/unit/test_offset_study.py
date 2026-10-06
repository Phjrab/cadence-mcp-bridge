"""Synthetic numerical checks, not real offset qualification or user selection."""

import math

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.offset_study import (
    OffsetDefinition,
    OffsetPoint,
    input_nulling_estimate,
    output_difference_at_zero_input,
)


def point(x: float, y: float, **changes: bool) -> OffsetPoint:
    return OffsetPoint(
        input_differential_v=x,
        output_differential_v=y,
        valid_dc=changes.get("valid_dc", True),
        effective_input_verified=changes.get("effective_input_verified", True),
        local_output_window_reviewed=changes.get("local_output_window_reviewed", True),
    )


def test_requires_explicit_scientific_method() -> None:
    with pytest.raises(ValidationError):
        OffsetDefinition.model_validate({})
    for method in ("nominal-open-loop-input-nulling-v1", "nominal-open-loop-output-v1"):
        d = OffsetDefinition.model_validate({"definition_id": method})
        assert d.specification == "not_evaluated" and d.mismatch == "not_simulated"
    with pytest.raises(ValidationError):
        OffsetDefinition.model_validate({"definition_id": "input", "path": "/tmp/input"})


@pytest.mark.parametrize("sign", [1, -1])
def test_bracketed_nulling_sign_is_applied_input_not_negated(sign: int) -> None:
    # Synthetic root +0.25uV; the negative-gain case preserves that same sign.
    p = tuple(point(x, sign * 1000 * (x - 0.25e-6)) for x in (-1e-6, 0.0, 1e-6))
    r = input_nulling_estimate(p)
    assert r.status == "BRACKETED_ZERO" and r.nulling_input_v == pytest.approx(0.25e-6)
    assert r.input_bracket_v == (0, 1e-6)
    assert r.qualification == "UNQUALIFIED" and r.spec_evaluation == "not_evaluated"


def test_exact_zero_needs_opposed_neighbors() -> None:
    r = input_nulling_estimate((point(-1e-6, -0.01), point(0, 0), point(1e-6, 0.01)))
    assert r.status == "EXACT_SAMPLED_ZERO" and r.nulling_input_v == 0
    assert r.local_gain_v_per_v == (10000, 10000)


@pytest.mark.parametrize(
    "values,status",
    [
        ((-0.03, -0.02, -0.01), "NO_CROSSING"),
        ((0.0, 0.0, 0.01), "FLAT_ZERO_INTERVAL"),
        ((0.0, 0.01, 0.02), "ENDPOINT_ONLY_ZERO"),
        ((-0.01, 0.01, -0.01), "MULTIPLE_CROSSINGS"),
        ((-0.02, -0.01, -0.015, 0.01), "NON_MONOTONIC"),
        ((-0.99, 0.0, 0.99), "BRACKET_OUTSIDE_LOCAL_OUTPUT_WINDOW"),
    ],
)
def test_unqualified_shapes_return_no_value(values: tuple[float, ...], status: str) -> None:
    r = input_nulling_estimate(tuple(point(i * 1e-6, v) for i, v in enumerate(values)))
    assert r.status == status and r.nulling_input_v is None


@pytest.mark.parametrize(
    "flag", ["valid_dc", "effective_input_verified", "local_output_window_reviewed"]
)
def test_missing_qualification_denied(flag: str) -> None:
    r = input_nulling_estimate(
        (point(-1e-6, -0.01), point(0, 0, **{flag: False}), point(1e-6, 0.01))
    )
    assert r.status == "UNQUALIFIED_POINTS" and r.nulling_input_v is None


def test_bounds_duplicate_unsorted_and_insufficient_inputs() -> None:
    assert input_nulling_estimate(()).status == "INSUFFICIENT_POINTS"
    for inputs in ((-1e-6, -1e-6, 1e-6), (1e-6, 0.0, -1e-6)):
        with pytest.raises(ValueError, match="increasing"):
            input_nulling_estimate(tuple(point(x, x) for x in inputs))
    with pytest.raises(ValueError, match="bounded"):
        input_nulling_estimate(tuple(point(i * 1e-6, i * 1e-6) for i in range(18)))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 0.02])
def test_nonfinite_or_unbounded_inputs_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        point(value, 0)


def test_output_candidate_requires_equal_effective_inputs() -> None:
    assert output_difference_at_zero_input(point(0, 1e-6)) == 1e-6
    with pytest.raises(ValueError, match="equal"):
        output_difference_at_zero_input(point(1e-6, 0))
    with pytest.raises(ValueError, match="qualified"):
        output_difference_at_zero_input(point(0, 0, local_output_window_reviewed=False))
