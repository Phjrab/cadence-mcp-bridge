"""Pure bounded CMOS delay estimates; supplied evidence is never native attestation."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

Finite = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Time = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class DelayEvidence(VariableModel):
    """Caller-supplied identities, checked for shape only, not authenticated here."""

    operation_id: OperationId
    plan_sha256: Digest
    frame_sha256: Digest
    reader_registration_sha256: Digest
    execution_input_sha256: Digest
    static_statements_sha256: Digest


class DelayWindow(VariableModel):
    """Saved-sample plateaus enclosing exactly one input and opposite output edge."""

    start_s: Time
    initial_stop_s: Time
    final_start_s: Time
    stop_s: Time

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if not self.start_s < self.initial_stop_s < self.final_start_s < self.stop_s:
            raise ValueError("ordered nonempty plateau and transition windows required")
        return self


class DelayDefinition(VariableModel):
    input_signal: LogicalId
    output_signal: LogicalId
    vdd_v: Positive
    phl_window: DelayWindow
    plh_window: DelayWindow
    plateau_tolerance_v: Positive
    minimum_plateau_samples: Annotated[int, Field(ge=2, le=64)]
    maximum_sample_gap_s: Positive
    maximum_crossing_bracket_s: Positive
    minimum_delay_resolution_ratio: Annotated[float, Field(ge=1, allow_inf_nan=False)]

    @model_validator(mode="after")
    def resolved(self) -> Self:
        if self.input_signal == self.output_signal or self.plateau_tolerance_v >= self.vdd_v / 2:
            raise ValueError("distinct signals and resolved rail tolerance required")
        a, b = self.phl_window, self.plh_window
        if not (a.stop_s <= b.start_s or b.stop_s <= a.start_s):
            raise ValueError("two nonoverlapping observation windows required")
        return self


class TranSample(VariableModel):
    time_s: Time
    value_v: Finite


class CmosDelayRequest(VariableModel):
    evidence: DelayEvidence
    definition: DelayDefinition
    # Exact existing tran_waveforms shape, with bounded finite typed values.
    tran_waveforms: Annotated[
        dict[LogicalId, Annotated[list[TranSample], Field(min_length=2, max_length=256)]],
        Field(min_length=1, max_length=8),
    ]


class Crossing(VariableModel):
    time_s: Time
    bracket_s: tuple[Time, Time]
    direction: Literal["rising", "falling"]


Reason = Literal[
    "missing_nodes", "invalid_time_grid", "window_outside_samples", "insufficient_sampling",
    "unsettled_endpoints", "missing_crossing", "ambiguous_crossings", "output_before_input",
]


class EdgeDelay(VariableModel):
    status: Literal["OBSERVED_SAMPLED_DELAY", "NOT_EVALUATED"]
    reason: Reason | None
    delay_s: Positive | None
    # Conservative delay interval from actual sample brackets, not a statistical CI.
    delay_bracket_s: tuple[Finite, Finite] | None
    input_crossing: Crossing | None
    output_crossing: Crossing | None


class CmosDelayResult(VariableModel):
    status: Literal["OBSERVED_SAMPLED_DELAY", "NOT_EVALUATED"]
    evidence: DelayEvidence
    request_sha256: Digest
    tphl: EdgeDelay
    tplh: EdgeDelay
    qualification: Literal["LOCAL_SAMPLED_EVIDENCE_ONLY"] = "LOCAL_SAMPLED_EVIDENCE_ONLY"
    native_authentication: Literal["NOT_ATTESTED"] = "NOT_ATTESTED"
    power: Literal["UNSUPPORTED"] = "UNSUPPORTED"


def _absent(reason: Reason) -> EdgeDelay:
    return EdgeDelay(
        status="NOT_EVALUATED", reason=reason, delay_s=None, delay_bracket_s=None,
        input_crossing=None, output_crossing=None,
    )


def _crossings(times: list[float], values: list[float], threshold: float) -> list[Crossing]:
    crossings = []
    for i in range(1, len(times)):
        a, b = values[i - 1], values[i]
        # Exact hits are handled separately, avoiding double counts at a saved hit.
        if a != threshold and b != threshold and (a < threshold) != (b < threshold):
            scale = max(abs(a), abs(b), abs(threshold))
            left, right = abs(a / scale - threshold / scale), abs(b / scale - threshold / scale)
            weight = left / (left + right)
            at = times[i - 1] + weight * (times[i] - times[i - 1])
            crossings.append(Crossing(
                time_s=at, bracket_s=(times[i - 1], times[i]),
                direction="rising" if b > a else "falling",
            ))
    for i, value in enumerate(values):
        if value != threshold:
            continue
        # A threshold plateau/touch/boundary is ambiguous, never an extrapolated edge.
        if i == 0 or i == len(values) - 1 or (
            values[i - 1] == threshold or values[i + 1] == threshold
            or (values[i - 1] < threshold) == (values[i + 1] < threshold)
        ):
            raise ValueError("ambiguous_crossings")
        crossings.append(Crossing(
            time_s=times[i], bracket_s=(times[i - 1], times[i + 1]),
            direction="rising" if values[i + 1] > values[i - 1] else "falling",
        ))
    return crossings


def _edge(
    times: list[float], vin: list[float], vout: list[float], definition: DelayDefinition,
    window: DelayWindow, falling_output: bool,
) -> EdgeDelay:
    if times[0] > window.start_s or times[-1] < window.stop_s:
        return _absent("window_outside_samples")
    if any(
        b - a > definition.maximum_sample_gap_s
        for a, b in zip(times, times[1:], strict=False)
        if a < window.stop_s and b > window.start_s
    ):
        return _absent("insufficient_sampling")
    expected_input = (0.0, definition.vdd_v) if falling_output else (definition.vdd_v, 0.0)
    for series, levels in ((vin, expected_input), (vout, expected_input[::-1])):
        for start, stop, level in (
            (window.start_s, window.initial_stop_s, levels[0]),
            (window.final_start_s, window.stop_s, levels[1]),
        ):
            plateau = [v for t, v in zip(times, series, strict=True) if start <= t <= stop]
            if len(plateau) < definition.minimum_plateau_samples:
                return _absent("insufficient_sampling")
            if max(plateau) - min(plateau) > definition.plateau_tolerance_v or any(
                abs(v - level) > definition.plateau_tolerance_v for v in plateau
            ):
                return _absent("unsettled_endpoints")
    selected = [i for i, t in enumerate(times)
                if window.initial_stop_s <= t <= window.final_start_s]
    if len(selected) < 2:
        return _absent("insufficient_sampling")
    axis = [times[i] for i in selected]
    try:
        inputs = _crossings(axis, [vin[i] for i in selected], definition.vdd_v / 2)
        outputs = _crossings(axis, [vout[i] for i in selected], definition.vdd_v / 2)
    except ValueError:
        return _absent("ambiguous_crossings")
    if not inputs or not outputs:
        return _absent("missing_crossing")
    if len(inputs) != 1 or len(outputs) != 1 or (
        inputs[0].direction != ("rising" if falling_output else "falling")
        or outputs[0].direction != ("falling" if falling_output else "rising")
    ):
        return _absent("ambiguous_crossings")
    inp, out = inputs[0], outputs[0]
    delay = out.time_s - inp.time_s
    bracket = (out.bracket_s[0] - inp.bracket_s[1], out.bracket_s[1] - inp.bracket_s[0])
    widths = tuple(c.bracket_s[1] - c.bracket_s[0] for c in (inp, out))
    reason: Reason | None = None
    if delay <= 0:
        reason = "output_before_input"
    elif not math.isfinite(delay) or not all(math.isfinite(x) for x in (*bracket, *widths)) or (
        bracket[0] <= 0 or max(widths) > definition.maximum_crossing_bracket_s
        or (delay / max(widths)) / sum(w / max(widths) for w in widths)
        < definition.minimum_delay_resolution_ratio
    ):
        reason = "insufficient_sampling"
    return EdgeDelay(
        status="OBSERVED_SAMPLED_DELAY" if reason is None else "NOT_EVALUATED",
        reason=reason, delay_s=delay if reason is None else None,
        delay_bracket_s=bracket, input_crossing=inp, output_crossing=out,
    )


def evaluate_cmos_delay(request: CmosDelayRequest) -> CmosDelayResult:
    """Estimate both polarities locally; callers must authenticate evidence separately.

    JSON callers can use CmosDelayRequest.model_validate_json with the existing
    tran_waveforms {node: [{time_s, value_v}, ...]} payload. No I/O or execution.
    """
    # Frozen models still contain mutable lists/dicts; snapshot and revalidate
    # through JSON mode before evaluating or hashing any caller-supplied model.
    request = CmosDelayRequest.model_validate_json(request.model_dump_json())
    definition = request.definition
    waves = request.tran_waveforms
    reason: Reason | None = None
    if definition.input_signal not in waves or definition.output_signal not in waves:
        reason = "missing_nodes"
    elif any(
        any(a.time_s >= b.time_s for a, b in zip(wave, wave[1:], strict=False))
        for wave in waves.values()
    ):
        reason = "invalid_time_grid"
    else:
        times = [p.time_s for p in waves[definition.input_signal]]
        if any([p.time_s for p in wave] != times for wave in waves.values()):
            reason = "invalid_time_grid"
    if reason is not None:
        phl = plh = _absent(reason)
    else:
        times = [p.time_s for p in waves[definition.input_signal]]
        vin = [p.value_v for p in waves[definition.input_signal]]
        vout = [p.value_v for p in waves[definition.output_signal]]
        phl = _edge(times, vin, vout, definition, definition.phl_window, True)
        plh = _edge(times, vin, vout, definition, definition.plh_window, False)
    return CmosDelayResult(
        status=("OBSERVED_SAMPLED_DELAY" if phl.delay_s is not None and plh.delay_s is not None
                else "NOT_EVALUATED"),
        evidence=request.evidence, request_sha256=canonical_digest(request), tphl=phl, tplh=plh,
    )
