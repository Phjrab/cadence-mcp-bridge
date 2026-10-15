"""Nominal input-nulling interpolation from registered DC operating-point samples."""

from __future__ import annotations

import math
from typing import Annotated, Any, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

Finite = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class InputNullingDefinition(VariableModel):
    static_statements_sha256: Digest
    positive_input: LogicalId
    negative_input: LogicalId
    positive_input_variable: LogicalId
    negative_input_variable: LogicalId
    positive_output: LogicalId
    negative_output: LogicalId
    common_mode_v: Finite
    common_mode_tolerance_v: Positive
    maximum_abs_output_v: Positive
    load_and_feedback_description: Annotated[str, Field(min_length=1, max_length=200)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len({self.positive_input, self.negative_input, self.positive_output,
                self.negative_output}) != 4:
            raise ValueError("four distinct registered differential terminals required")
        if self.positive_input_variable == self.negative_input_variable:
            raise ValueError("distinct registered input-source variables required")
        return self


def sampled_input_nulling(
    nodes: list[dict[str, float]], definition: InputNullingDefinition,
) -> dict[str, Any]:
    """Signed applied Vp-Vm where Vop-Vom crosses zero; no precision claim."""
    if not 3 <= len(nodes) <= 32:
        raise OperationRejected("offset_bounded_dc_sample_set_required")
    samples = []
    try:
        for row in nodes:
            vp, vm, op, om = (float(row[name]) for name in (
                definition.positive_input, definition.negative_input,
                definition.positive_output, definition.negative_output,
            ))
            if not all(math.isfinite(v) for v in (vp, vm, op, om)) or (
                abs(vp / 2 + vm / 2 - definition.common_mode_v)
                > definition.common_mode_tolerance_v
            ):
                raise OperationRejected("offset_measured_common_mode_mismatch")
            x, y = vp - vm, op - om
            if not all(math.isfinite(v) for v in (x, y)):
                raise OperationRejected("offset_nonfinite_differential")
            if abs(y) > definition.maximum_abs_output_v:
                raise OperationRejected("offset_outside_declared_local_output_window")
            samples.append((x, y))
    except (KeyError, TypeError, ValueError, OverflowError):
        raise OperationRejected("offset_registered_dc_terminals_required") from None
    samples.sort()
    if any(a[0] >= b[0] for a, b in zip(samples, samples[1:], strict=False)):
        raise OperationRejected("offset_duplicate_measured_input")
    slopes = [(b[1] - a[1]) / (b[0] - a[0])
              for a, b in zip(samples, samples[1:], strict=False)]
    if any(not math.isfinite(s) or s == 0 for s in slopes) or (
        any(s > 0 for s in slopes) and any(s < 0 for s in slopes)
    ):
        raise OperationRejected("offset_nonmonotonic_or_zero_local_gain")
    exact = [x for x, y in samples if y == 0]
    brackets = [(a, b) for a, b in zip(samples, samples[1:], strict=False)
                if (a[1] < 0 < b[1]) or (b[1] < 0 < a[1])]
    result: dict[str, Any] = {
        "status": "NOT_OBSERVED_IN_SAMPLED_INPUT_RANGE", "value": None, "unit": "V",
        "definition": definition.model_dump(mode="json"),
        "definition_sha256": canonical_digest(definition),
        "native_provenance": "NOT_ATTESTED", "samples": [list(p) for p in samples],
        "local_gains_v_per_v": slopes, "bracket_v": None,
        "method": "signed_applied_input_differential_at_output_zero_linear_no_extrapolation",
        "qualification": "NOMINAL_SAMPLED_NULLING_NO_ABSOLUTE_PRECISION_MISMATCH_OR_PVT_CLAIM",
    }
    if len(exact) + len(brackets) > 1:
        raise OperationRejected("offset_multiple_nulling_candidates")
    if exact:
        # An endpoint zero lacks a containing two-sided local bracket.
        i = next(i for i, p in enumerate(samples) if p[0] == exact[0])
        if i == 0 or i == len(samples) - 1:
            return result
        result.update(status="OBSERVED_SAMPLED_INPUT_NULL", value=exact[0],
                      bracket_v=[samples[i - 1][0], samples[i + 1][0]])
    elif brackets:
        a, b = brackets[0]
        # Weighted sum avoids overflow in the opposite-sign difference.
        scale = max(abs(a[1]), abs(b[1]))
        ya, yb = a[1] / scale, b[1] / scale
        fraction = -ya / (yb - ya)
        estimate = (1 - fraction) * a[0] + fraction * b[0]
        if not math.isfinite(estimate) or not a[0] <= estimate <= b[0]:
            raise OperationRejected("offset_interpolation_invalid")
        result.update(status="OBSERVED_SAMPLED_INPUT_NULL", value=estimate,
                      bracket_v=[a[0], b[0]])
    return result
