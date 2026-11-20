"""Window measurements over bounded, retained registered TRAN voltage samples."""

from __future__ import annotations

import hashlib
import math
from bisect import bisect_left, bisect_right
from typing import Annotated, Any, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from cadence_mcp_bridge.cmos_delay import _crossings
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.generic_measurements import MAX_SAMPLES, SourceSignal
from cadence_mcp_bridge.native_service import NativeOperationQuery, NativeOperationService
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.result_reports import make_report
from cadence_mcp_bridge.variable_contracts import LogicalId, VariableModel

Finite = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
MAX_RESULT_BYTES = 128 * 1024


class TransientWindow(VariableModel):
    start_s: Nonnegative
    stop_s: Positive
    maximum_gap_s: Positive

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start_s >= self.stop_s:
            raise ValueError("transient window must have positive duration")
        return self


class TransientEdge(VariableModel):
    signal: LogicalId
    threshold_v: Finite
    direction: Literal["rising", "falling"]


class TransientDelay(VariableModel):
    trigger: TransientEdge
    response: TransientEdge


class TransientSlew(VariableModel):
    signal: LogicalId


class TransientSettling(VariableModel):
    signal: LogicalId
    target_v: Finite
    tolerance_v: Positive
    minimum_hold_s: Positive


class ResearchTransientQuery(NativeOperationQuery):
    window: TransientWindow
    signals: Annotated[tuple[LogicalId, ...], Field(min_length=1, max_length=6)]
    delay: TransientDelay | None = None
    slew: TransientSlew | None = None
    settling: TransientSettling | None = None
    maximum_display_points: Annotated[int, Field(ge=2, le=MAX_SAMPLES)] = MAX_SAMPLES

    @model_validator(mode="after")
    def selected(self) -> Self:
        measured: set[str] = set()
        if self.delay:
            measured.update((self.delay.trigger.signal, self.delay.response.signal))
        if self.slew:
            measured.add(self.slew.signal)
        if self.settling:
            measured.add(self.settling.signal)
        if len(set(self.signals)) != len(self.signals) or measured - set(self.signals):
            raise ValueError("measurement signals must be selected exactly once")
        return self


class _Point(VariableModel):
    time_s: Nonnegative
    value_v: Finite


class _CurrentPoint(VariableModel):
    time_s: Nonnegative
    value_a: Finite


_Wave = Annotated[list[_Point], Field(min_length=2, max_length=MAX_SAMPLES)]
_Waves = TypeAdapter(dict[LogicalId, _Wave])
_CurrentWave = Annotated[list[_CurrentPoint], Field(min_length=2, max_length=MAX_SAMPLES)]


class TransientSupplyEvidence(VariableModel):
    """Registration and saved branch-current vectors from a trusted result adapter."""

    sources: Annotated[tuple[SourceSignal, ...], Field(min_length=1, max_length=6)]
    currents: Annotated[dict[LogicalId, _CurrentWave], Field(max_length=6)]

    @model_validator(mode="after")
    def registered_supplies(self) -> Self:
        ids = {source.source_id for source in self.sources}
        if (
            len(ids) != len(self.sources)
            or any(source.role != "supply" for source in self.sources)
            or self.currents.keys() - ids
        ):
            raise ValueError("unique registered supply sources required for branch currents")
        return self


def _metric(
    unit: str, reason: str | None, value: float | None = None, **details: Any,
) -> dict[str, Any]:
    if value is not None and not math.isfinite(value):
        reason, value = "nonfinite_estimate", None
    return {"status": "ESTIMATED" if reason is None else "NOT_EVALUATED",
            "reason": reason, "value": value, "unit": unit, **details}


def _linear_at(axis: list[float], values: list[float], time: float) -> float:
    right = bisect_left(axis, time)
    if axis[right] == time:
        return values[right]
    left = right - 1
    weight = (time - axis[left]) / (axis[right] - axis[left])
    return (1 - weight) * values[left] + weight * values[right]


def _delay(
    axis: list[float], values: dict[str, list[float]], query: ResearchTransientQuery,
) -> dict[str, Any]:
    assert query.delay is not None
    crossings = []
    for edge in (query.delay.trigger, query.delay.response):
        try:
            eligible = [
                point for point in _crossings(axis, values[edge.signal], edge.threshold_v)
                if point.direction == edge.direction
                and query.window.start_s <= point.time_s <= query.window.stop_s
            ]
        except ValueError:
            return _metric("s", "ambiguous_threshold_contact")
        if len(eligible) != 1:
            return _metric("s", "edge_missing" if not eligible else "ambiguous_edges")
        crossings.append(eligible[0])
    trigger, response = crossings
    if response.time_s < trigger.time_s:
        return _metric("s", "response_precedes_trigger")
    return _metric(
        "s", None, response.time_s - trigger.time_s, method="linear_crossing_interpolation",
        trigger=trigger.model_dump(mode="json"), response=response.model_dump(mode="json"),
    )


def _settling(
    axis: list[float], series: list[float], window: TransientWindow, spec: TransientSettling,
) -> dict[str, Any]:
    times = [window.start_s, *(t for t in axis if window.start_s < t < window.stop_s),
             window.stop_s]
    values = [_linear_at(axis, series, time) for time in times]
    outside = [i for i, value in enumerate(values) if abs(value - spec.target_v) > spec.tolerance_v]
    if outside and outside[-1] == len(times) - 1:
        return _metric("s", "outside_tolerance_at_window_end")
    entry = times[0]
    if outside:
        i = outside[-1]
        boundary = spec.target_v + math.copysign(spec.tolerance_v, values[i] - spec.target_v)
        weight = (boundary - values[i]) / (values[i + 1] - values[i])
        entry = times[i] + weight * (times[i + 1] - times[i])
    hold = times[-1] - entry
    if hold < spec.minimum_hold_s:
        return _metric("s", "insufficient_hold_duration", observed_hold_s=hold)
    return _metric("s", None, entry - window.start_s, entry_s=entry, observed_hold_s=hold,
                   method="last_band_entry_held_through_window_end_piecewise_linear")


def _source_power(
    window: TransientWindow, waves: dict[str, list[_Point]],
    source: SourceSignal, current: list[_CurrentPoint] | None,
) -> dict[str, Any]:
    if current is None:
        return _metric("W", "missing_registered_supply_current")
    axis = [point.time_s for point in current]
    if any(a >= b for a, b in zip(axis, axis[1:], strict=False)):
        raise OperationRejected("research_transient_nonmonotonic_current_axis")
    voltages = []
    for node in (source.positive_node, source.negative_node):
        if node is None:
            voltages.append([0.0] * len(axis))
            continue
        wave = waves.get(node)
        if wave is None:
            return _metric("W", "missing_registered_supply_voltage")
        if [point.time_s for point in wave] != axis:
            return _metric("W", "supply_voltage_current_time_axes_differ")
        voltages.append([point.value_v for point in wave])
    if axis[0] > window.start_s or axis[-1] < window.stop_s:
        return _metric("W", "insufficient_observation_duration")
    gaps = [
        b - a for a, b in zip(axis, axis[1:], strict=False)
        if a < window.stop_s and b > window.start_s
    ]
    maximum_gap = max(gaps)
    if maximum_gap > window.maximum_gap_s and not math.isclose(
        maximum_gap, window.maximum_gap_s, rel_tol=1e-12,
    ):
        return _metric("W", "insufficient_time_resolution", maximum_observed_gap_s=maximum_gap)
    positive, negative = voltages
    current_values = [point.value_a for point in current]
    knots = [window.start_s, *(t for t in axis if window.start_s < t < window.stop_s),
             window.stop_s]
    voltage = [
        _linear_at(axis, positive, t) - _linear_at(axis, negative, t) for t in knots
    ]
    amperes = [_linear_at(axis, current_values, t) for t in knots]
    duration = window.stop_s - window.start_s
    try:
        # Endpoint weights integrate the quadratic product of two linear traces.
        mean = math.fsum(
            -(dt / duration) * (
                (v0 / 3) * i0 + (v0 / 6) * i1
                + (v1 / 6) * i0 + (v1 / 3) * i1
            )
            for dt, v0, v1, i0, i1 in zip(
                (b - a for a, b in zip(knots, knots[1:], strict=False)),
                voltage[:-1], voltage[1:], amperes[:-1], amperes[1:], strict=True,
            )
        )
    except (OverflowError, ValueError):
        return _metric("W", "nonfinite_estimate")
    return _metric(
        "W", None, mean, maximum_observed_gap_s=maximum_gap, saved_vector_samples=len(axis),
    )


def _average_supply_power(
    window: TransientWindow, waves: dict[str, list[_Point]], supply: TransientSupplyEvidence,
) -> dict[str, Any]:
    rows = [
        {
            **source.model_dump(mode="json"),
            **_source_power(window, waves, source, supply.currents.get(source.source_id)),
        }
        for source in supply.sources
    ]
    details: dict[str, Any] = {
        "sources": rows,
        "method": "time_mean_of_negative_terminal_voltage_times_signed_current_piecewise_linear",
    }
    if any(row["value"] is None for row in rows):
        return _metric("W", "incomplete_registered_supply_evidence", **details)
    try:
        return _metric("W", None, math.fsum(row["value"] for row in rows), **details)
    except OverflowError:
        return _metric("W", "nonfinite_estimate", **details)


def evaluate_research_transient(
    query: ResearchTransientQuery, waveforms: object, *,
    sample_kind: Literal["NATIVE_SAVED_VECTOR", "DISPLAY_DOWNSAMPLED", "UNVERIFIED"],
    supply: TransientSupplyEvidence | None = None,
) -> dict[str, Any]:
    """Measure supplied samples without attesting their origin.

    The trusted adapter, not the public query, supplies resolution and optional current evidence.
    """
    query = ResearchTransientQuery.model_validate_json(query.model_dump_json())
    waves = _Waves.validate_python(waveforms)
    if sum(map(len, waves.values())) > 1536:
        raise OperationRejected("research_transient_waveforms_exceed_limit")
    window = query.window
    out: dict[str, Any] = {"signals": {}, "measurements": {}}
    series: dict[str, tuple[list[float], list[float], str | None]] = {}
    for signal in query.signals:
        wave = waves.get(signal)
        if not wave:
            out["signals"][signal] = {
                "status": "UNAVAILABLE", "reason": "missing_registered_signal",
            }
            continue
        axis = [p.time_s for p in wave]
        if any(a >= b for a, b in zip(axis, axis[1:], strict=False)):
            raise OperationRejected("research_transient_nonmonotonic_axis")
        first = max(0, bisect_right(axis, window.start_s) - 1)
        last = min(len(axis) - 1, bisect_left(axis, window.stop_s))
        saved = wave[first:last + 1]
        gaps = [b.time_s - a.time_s for a, b in zip(saved, saved[1:], strict=False)]
        maximum_gap = max(gaps, default=None)
        reason = None
        if axis[0] > window.start_s or axis[-1] < window.stop_s:
            reason = "insufficient_observation_duration"
        elif sample_kind != "NATIVE_SAVED_VECTOR":
            reason = "original_saved_resolution_unverified"
        elif maximum_gap is None or (
            maximum_gap > window.maximum_gap_s
            and not math.isclose(maximum_gap, window.maximum_gap_s, rel_tol=1e-12)
        ):
            reason = "insufficient_time_resolution"
        series[signal] = ([p.time_s for p in saved], [p.value_v for p in saved], reason)
        display = [p for p in saved if window.start_s <= p.time_s <= window.stop_s]
        display_size = min(len(display), query.maximum_display_points)
        indices = (
            [i * (len(display) - 1) // (display_size - 1) for i in range(display_size)]
            if display_size >= 2 else list(range(display_size))
        )
        out["signals"][signal] = {
            "status": "AVAILABLE" if display else "UNAVAILABLE",
            "reason": reason if display else "no_saved_points_in_window",
            "time_unit": "s", "unit": "V",
            "saved_vector_samples": len(wave), "window_samples": len(display),
            "maximum_observed_gap_s": maximum_gap,
            "display_downsampled": display_size < len(display),
            "points": [display[i].model_dump(mode="json") for i in indices],
        }

    def unavailable(signal: str) -> str | None:
        return series[signal][2] if signal in series else "missing_registered_signal"

    measurements = out["measurements"]
    if query.delay:
        a, b = query.delay.trigger.signal, query.delay.response.signal
        reason = unavailable(a) or unavailable(b)
        if reason is None and series[a][0] != series[b][0]:
            reason = "selected_time_axes_differ"
        measurements["delay"] = (
            _metric("s", reason) if reason else
            _delay(series[a][0], {a: series[a][1], b: series[b][1]}, query)
        )
    if query.slew:
        signal = query.slew.signal
        reason = unavailable(signal)
        if reason:
            measurements["slew"] = _metric("V/s", reason)
        else:
            axis, values, _ = series[signal]
            slope = (_linear_at(axis, values, window.stop_s)
                     - _linear_at(axis, values, window.start_s)) / (window.stop_s - window.start_s)
            measurements["slew"] = _metric("V/s", None, slope, method="signed_window_secant")
    if query.settling:
        signal = query.settling.signal
        reason = unavailable(signal)
        measurements["settling"] = (
            _metric("s", reason) if reason else
            _settling(series[signal][0], series[signal][1], window, query.settling)
        )
    if supply is None:
        power = _metric("W", "registered_tran_supply_current_unavailable")
    elif sample_kind != "NATIVE_SAVED_VECTOR":
        power = _metric("W", "original_saved_resolution_unverified")
    else:
        power = _average_supply_power(window, waves, supply)
    measurements["average_supply_power"] = power
    out["sample_kind"] = sample_kind
    out["qualification"] = "SAVED_SAMPLE_ESTIMATES_NO_SOLVER_GRID_CONVERGENCE"
    out["definition"] = query.model_dump(mode="json")
    return out


def research_transient_export_bytes(result: dict[str, Any]) -> bytes:
    """Serialize the selected structured result for an adapter's exclusive export."""
    raw = _canonical(result)
    if len(raw) > MAX_RESULT_BYTES:
        raise OperationRejected("research_transient_export_exceeds_limit")
    return raw


async def capture_research_transient(
    native: NativeOperationService, query: ResearchTransientQuery,
) -> dict[str, Any]:
    """Read the existing terminal journal and authenticated registered result once."""
    query = ResearchTransientQuery.model_validate_json(query.model_dump_json())
    native.current()
    with native.lifecycle.store.connection(create=False, read_only=True) as connection:
        record = native.lifecycle.store._read_operation(connection, query.operation_id)
    plan = record.plan
    context = native.context
    if (
        record.operation_id != query.operation_id or plan.plan_sha256 != query.expected_plan_sha256
        or plan.resource_domain_sha256 != context.resource_domain_sha256
        or plan.ledger_ref != context.binding.ledger_ref
        or plan.runner_sha256 != context.binding.runner_sha256
        or plan.environment_sha256 != context.binding.environment_sha256
        or plan.design_sha256 != context.binding.design_sha256
        or plan.pdk_sha256 != context.binding.pdk_sha256
        or plan.analysis != "tran" or record.progress.phase != "SUCCEEDED"
    ):
        raise OperationRejected("research_transient_succeeded_identity_required")
    observed, data = await native.provider.analog_result(query.operation_id, plan)
    observed.check(record)
    if observed.progress != record.progress:
        raise OperationRejected("research_transient_terminal_identity_mismatch")
    report = make_report(record, data)
    inputs = report.analysis_conditions.analysis_inputs
    if inputs.analysis != "tran":
        raise OperationRejected("research_transient_analysis_mismatch")
    if data.get("remote_contact") is not True or data.get("originals_preserved") is not True:
        raise OperationRejected("research_transient_provider_boundary_missing")
    waves = data.get("tran_waveforms", {})
    inventory = {metric.signal_id: metric for metric in report.metrics if metric.kind == "first"}
    parsed = _Waves.validate_python(waves)
    for signal, points in parsed.items():
        summary = inventory.get(signal)
        if summary is None or (summary.sample_count, summary.start_s, summary.stop_s) != (
            len(points), points[0].time_s, points[-1].time_s,
        ):
            raise OperationRejected("research_transient_saved_vector_inventory_mismatch")
    result = evaluate_research_transient(query, waves, sample_kind="NATIVE_SAVED_VECTOR")
    result.update(
        source=report.model_dump(mode="json"),
        declared_maxstep_s=inputs.maxstep_s,
        waveforms_sha256=hashlib.sha256(_canonical(waves)).hexdigest(),
        terminal_receipt_sha256=record.progress.provider_receipt_sha256,
        remote_contact=True, new_simulations=0, new_extractions=0, new_reservations=0,
    )
    research_transient_export_bytes(result)
    return result
