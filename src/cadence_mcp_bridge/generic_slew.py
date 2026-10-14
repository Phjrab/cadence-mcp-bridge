"""Bounded sampled step-response slope; no execution or native-origin assertion."""

from __future__ import annotations

import math
from typing import Annotated, Any, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

Finite = Annotated[float, Field(allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class SampledSlewDefinition(VariableModel):
    """Operator-selected stimulus/load and windows, bound to exact static inputs."""

    static_statements_sha256: Digest
    input_signal: LogicalId
    output_signal: LogicalId
    # A named operator interpretation, not a claim of independently attested loading.
    load_description: Annotated[str, Field(min_length=1, max_length=200)]
    input_initial_v: Finite
    input_final_v: Finite
    initial_start_s: Nonnegative
    initial_stop_s: Positive
    final_start_s: Positive
    final_stop_s: Positive
    plateau_tolerance_v: Positive
    minimum_output_step_v: Positive
    lower_fraction: Annotated[float, Field(gt=0, lt=1, allow_inf_nan=False)] = 0.1
    upper_fraction: Annotated[float, Field(gt=0, lt=1, allow_inf_nan=False)] = 0.9
    minimum_crossing_intervals: Annotated[int, Field(ge=4, le=64)] = 4

    @model_validator(mode="after")
    def windows(self) -> Self:
        if not (
            self.initial_start_s < self.initial_stop_s < self.final_start_s < self.final_stop_s
            and self.lower_fraction < self.upper_fraction
        ) or (
            self.input_signal == self.output_signal
            or abs(self.input_final_v - self.input_initial_v) <= 2 * self.plateau_tolerance_v
            or self.minimum_output_step_v <= 2 * self.plateau_tolerance_v
        ):
            raise ValueError("distinct signals, ordered windows and resolved amplitudes required")
        return self


def sampled_slew(
    waveforms: dict[str, list[dict[str, Any]]], definition: SampledSlewDefinition,
) -> dict[str, Any]:
    """Average signed slope between first 10/90 crossings, not maximum derivative."""
    try:
        selected = [waveforms[name] for name in (definition.input_signal, definition.output_signal)]
        axes = [[float(p["time_s"]) for p in wave] for wave in selected]
        values = [[float(p["value_v"]) for p in wave] for wave in selected]
    except (KeyError, TypeError, ValueError, OverflowError):
        raise OperationRejected("slew_registered_waveforms_required") from None
    times = axes[0]
    if not 2 <= len(times) <= 256 or axes[1] != times or any(
        not math.isfinite(v) for group in (*axes, *values) for v in group
    ) or times[0] < 0 or any(a >= b for a, b in zip(times, times[1:], strict=False)):
        raise OperationRejected("slew_complete_bounded_time_grid_required")
    if times[0] > definition.initial_start_s or times[-1] < definition.final_stop_s:
        raise OperationRejected("slew_windows_outside_observed_grid")

    def plateau(series: list[float], start: float, stop: float) -> float:
        points = [v for t, v in zip(times, series, strict=True) if start <= t <= stop]
        if len(points) < 2:
            raise OperationRejected("slew_plateau_two_samples_required")
        # A range constraint is a saved-sample check, never an assertion about unseen points.
        if max(points) - min(points) > definition.plateau_tolerance_v:
            raise OperationRejected("slew_plateau_not_settled_in_saved_samples")
        return sum(v / len(points) for v in points)

    input_wave, output_wave = values
    input_initial = plateau(input_wave, definition.initial_start_s, definition.initial_stop_s)
    input_final = plateau(input_wave, definition.final_start_s, definition.final_stop_s)
    if any(abs(actual - expected) > definition.plateau_tolerance_v for actual, expected in (
        (input_initial, definition.input_initial_v), (input_final, definition.input_final_v),
    )):
        raise OperationRejected("slew_measured_input_step_mismatch")
    sign = 1 if input_final > input_initial else -1
    transition = [v for t, v in zip(times, input_wave, strict=True)
                  if definition.initial_stop_s <= t <= definition.final_start_s]
    if any(sign * (b - a) < -definition.plateau_tolerance_v for a, b in zip(
        transition, transition[1:], strict=False,
    )):
        raise OperationRejected("slew_multiple_or_reversed_input_step")
    initial = plateau(output_wave, definition.initial_start_s, definition.initial_stop_s)
    final = plateau(output_wave, definition.final_start_s, definition.final_stop_s)
    step = final - initial
    if not all(math.isfinite(v) for v in (initial, final, step)):
        raise OperationRejected("slew_nonfinite_output_step")
    output: dict[str, Any] = {
        "status": "NO_RESOLVED_OUTPUT_STEP", "value": None, "unit": "V/s",
        "definition": definition.model_dump(mode="json"),
        "definition_sha256": canonical_digest(definition), "native_provenance": "NOT_ATTESTED",
        "initial_output_v": initial, "final_output_v": final,
        "measured_input_initial_v": input_initial, "measured_input_final_v": input_final,
        "sample_count": len(times), "direction": "rising" if step > 0 else "falling",
        "method": "signed_average_first_fraction_crossings_linear_time_no_extrapolation",
        "qualification": "SAMPLED_STEP_AVERAGE_NOT_MAXIMUM_DERIVATIVE_OR_GRID_CONVERGENCE",
        "crossings": None,
    }
    if abs(step) < definition.minimum_output_step_v:
        return output
    normalized = [(v - initial) / step for v in output_wave]
    region = [i for i, t in enumerate(times)
              if definition.initial_stop_s <= t <= definition.final_start_s]
    if len(region) < 2:
        raise OperationRejected("slew_transition_window_samples_required")
    # Multiple/backwards steps or ringing across thresholds are ambiguous.
    crossings: list[dict[str, Any]] = []
    for fraction in (definition.lower_fraction, definition.upper_fraction):
        upward: list[dict[str, Any]] = []
        downward: list[int] = []
        for i in range(1, len(times)):
            if times[i - 1] < definition.initial_stop_s or times[i] > definition.final_start_s:
                continue
            a, b = normalized[i - 1], normalized[i]
            if a < fraction <= b:
                crossing = times[i - 1] + (fraction - a) / (b - a) * (times[i] - times[i - 1])
                upward.append({"time_s": crossing, "bracket_s": [times[i - 1], times[i]],
                               "bracket_index": [i - 1, i]})
            if a >= fraction > b:
                downward.append(i)
        if len(upward) != 1 or downward:
            output["status"] = "AMBIGUOUS_OR_MISSING_SAMPLED_CROSSING"
            return output
        crossings.append(upward[0])
    duration = crossings[1]["time_s"] - crossings[0]["time_s"]
    lo, hi = crossings[0]["bracket_index"][0], crossings[1]["bracket_index"][1]
    gaps = [times[i] - times[i - 1] for i in range(lo + 1, hi + 1)]
    output["crossings"] = crossings
    output["largest_crossing_sample_gap_s"] = max(gaps)
    if duration <= 0 or max(gaps) * definition.minimum_crossing_intervals > duration:
        output["status"] = "INSUFFICIENT_SAVED_TIME_RESOLUTION"
        return output
    estimate = step * (definition.upper_fraction - definition.lower_fraction) / duration
    if not math.isfinite(estimate):
        raise OperationRejected("slew_nonfinite_estimate")
    output.update(
        status="OBSERVED_SAMPLED_STEP_SLOPE", value=estimate, crossing_duration_s=duration,
    )
    return output
