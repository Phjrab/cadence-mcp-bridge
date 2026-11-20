"""Research measurements over retained data and explicitly registered devices."""

from __future__ import annotations

import hashlib
import math
from itertools import pairwise
from typing import Annotated, Any, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.generic_analog import (
    Positive,
    _capture_retained_transfer,
    _interpolate_db_crossing,
)
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import NativeOperationService
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.result_reports import ResultReport, capture, conditions_digest
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

Finite = Annotated[float, Field(allow_inf_nan=False)]
DevicePath = Annotated[
    str, Field(max_length=256, pattern=r"^/?[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*$")
]
OpField = Literal["id", "gm", "gds", "vgs", "vds", "vdsat", "region"]
_OP_UNITS: dict[OpField, str] = {
    "id": "A",
    "gm": "S",
    "gds": "S",
    "vgs": "V",
    "vds": "V",
    "vdsat": "V",
    "region": "1",
}
OpResultSelector = Literal["dcOpInfo-info", "dcOpInfo"]
_OP_FRAME_LIMIT = 64 * 1024


class AcGainDefinition(VariableModel):
    reference_frequency_hz: Positive


class _TransferSample(VariableModel):
    frequency_hz: Positive
    input_real_v: Finite
    input_imag_v: Finite
    real_v_per_v: Finite
    imag_v_per_v: Finite
    gain_v_per_v: Finite
    gain_db: Finite | None
    phase_deg: Finite | None
    method: Literal["exact_sample_complex_output_over_measured_input"]


def sampled_ac_gain(
    spectrum: list[dict[str, Any]],
    definition: AcGainDefinition,
) -> dict[str, Any]:
    """Estimate the first sampled downward unity crossing at or after the reference."""
    if not 1 <= len(spectrum) <= 256:
        raise OperationRejected("research_ac_bounded_spectrum_required")
    samples = TypeAdapter(list[_TransferSample]).validate_python(spectrum)
    axes = [s.frequency_hz for s in samples]
    if any(b <= a for a, b in pairwise(axes)):
        raise OperationRejected("research_ac_axis_invalid")
    magnitudes = [math.hypot(s.real_v_per_v, s.imag_v_per_v) for s in samples]
    if any(
        not math.isfinite(magnitude)
        or not 0 < math.hypot(sample.input_real_v, sample.input_imag_v) < math.inf
        for sample, magnitude in zip(samples, magnitudes, strict=True)
    ):
        raise OperationRejected("research_ac_transfer_invalid")
    db = [20 * math.log10(value) if value else None for value in magnitudes]
    reference_index = next(
        (i for i, f in enumerate(axes) if f == definition.reference_frequency_hz),
        None,
    )
    reference = None
    if reference_index is not None:
        sample = samples[reference_index]
        reference = {
            "frequency_hz": sample.frequency_hz,
            "input_real_v": sample.input_real_v,
            "input_imag_v": sample.input_imag_v,
            "input_magnitude_v": math.hypot(sample.input_real_v, sample.input_imag_v),
            "input_phase_deg": math.degrees(math.atan2(sample.input_imag_v, sample.input_real_v)),
            "real_v_per_v": sample.real_v_per_v,
            "imag_v_per_v": sample.imag_v_per_v,
            "gain_v_per_v": magnitudes[reference_index],
            "gain_db": db[reference_index],
            "phase_deg": (
                math.degrees(math.atan2(sample.imag_v_per_v, sample.real_v_per_v))
                if magnitudes[reference_index]
                else None
            ),
        }

    crossing: dict[str, Any] = {
        "value": None,
        "unit": "Hz",
        "bracket_hz": None,
        "bracket_gain_db": None,
        "method": "first_downward_crossing_db_linear_log_frequency_no_extrapolation",
        "status": "NOT_EVALUATED",
        "reason": "reference_sample_unavailable",
    }
    if reference_index is not None and reference_index == len(samples) - 1:
        crossing["reason"] = "samples_after_reference_unavailable"
    elif reference_index is not None:
        crossing.update(status="NOT_OBSERVED_IN_SAMPLED_RANGE", reason="downward_crossing_absent")
        for i in range(reference_index + 1, len(samples)):
            left, right = db[i - 1], db[i]
            if left is None or left <= 0 or (right is not None and right > 0):
                continue
            crossing.update(bracket_hz=axes[i - 1 : i + 1], bracket_gain_db=[left, right])
            if right is None:
                crossing.update(status="NOT_EVALUATED", reason="zero_transfer_at_crossing_bracket")
            else:
                crossing.update(
                    status="OBSERVED_SAMPLED_CROSSING",
                    reason=None,
                    value=_interpolate_db_crossing(axes[i - 1], axes[i], left, right, 0),
                )
            break
    return {
        "definition": definition.model_dump(mode="json"),
        "definition_sha256": canonical_digest(definition),
        "reference": reference,
        "reference_reason": "reference_sample_unavailable" if reference is None else None,
        "unity_gain_frequency": crossing,
        "sample_count": len(samples),
        "start_hz": axes[0],
        "stop_hz": axes[-1],
    }


async def capture_ac_gain(
    native: NativeOperationService,
    operation_id: str,
    plan_sha256: str,
    definition: AcGainDefinition,
) -> dict[str, Any]:
    report, spectrum = await _capture_retained_transfer(native, operation_id, plan_sha256)
    return {
        "measurement": sampled_ac_gain(spectrum, definition),
        "source": report.model_dump(mode="json"),
        "conditions_sha256": conditions_digest(report),
        "spectrum_sha256": hashlib.sha256(_canonical(spectrum)).hexdigest(),
        "new_simulations": 0,
        "new_extractions": 0,
        "new_reservations": 0,
        "remote_contact": True,
    }


def static_supply_power(
    report: ResultReport,
    supply_ids: tuple[str, ...],
) -> dict[str, Any]:
    expected = TypeAdapter(tuple[LogicalId, ...]).validate_python(supply_ids)
    if (
        report.plan.analysis != "dc"
        or not 1 <= len(expected) <= 8
        or len(set(expected)) != len(expected)
    ):
        raise OperationRejected("research_dc_supply_definition_invalid")
    rails: dict[str, float] = {}
    for metric in report.metrics:
        if metric.kind != "delivered_power" or metric.source_role != "supply":
            continue
        if (
            metric.signal_id not in expected
            or metric.signal_id in rails
            or metric.sample_count is not None
            or metric.value is None
        ):
            raise OperationRejected("research_dc_supply_inventory_mismatch")
        assert metric.signal_id is not None
        rails[metric.signal_id] = metric.value
    missing = [name for name in expected if name not in rails]
    total = sum(rails.values()) if not missing else None
    if total is not None and not math.isfinite(total):
        raise OperationRejected("research_dc_supply_nonfinite")
    return {
        "status": "NOT_EVALUATED" if missing else "MEASURED",
        "reason": "registered_supply_measurement_missing" if missing else None,
        "value": total,
        "unit": "W",
        "missing_supply_ids": missing,
        "contributions": [{"source_id": name, "value": rails.get(name)} for name in expected],
        "definition": "sum of -(Vpositive - Vnegative) * I_into_positive_terminal",
    }


async def capture_supply_power(
    native: NativeOperationService,
    operation_id: str,
    plan_sha256: str,
    supply_ids: tuple[str, ...],
) -> dict[str, Any]:
    report = await capture(native, operation_id, plan_sha256)
    return {
        "measurement": static_supply_power(report, supply_ids),
        "source": report.model_dump(mode="json"),
        "conditions_sha256": conditions_digest(report),
        "new_simulations": 0,
        "new_extractions": 0,
        "new_reservations": 0,
        "remote_contact": True,
    }


class DeviceOpRegistration(VariableModel):
    """Device inventory independent of the waveform node limit."""

    instance_paths: Annotated[tuple[DevicePath, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len({path.lstrip("/") for path in self.instance_paths}) != len(self.instance_paths):
            raise ValueError("distinct registered device paths required")
        return self


class DeviceOpRow(VariableModel):
    instance_path: DevicePath
    field: OpField
    value: Finite | None
    reason: Literal["field_not_available", "instance_not_available"] | None = None

    @model_validator(mode="after")
    def observed_or_missing(self) -> Self:
        if (self.value is None) != (self.reason is not None):
            raise ValueError("missing OP values require an explicit reason")
        return self


class DeviceOpPayload(VariableModel):
    operation_id: OperationId
    plan_sha256: Digest
    execution_input_sha256: Digest
    registration_sha256: Digest
    op_frame_sha256: Digest
    rows: Annotated[tuple[DeviceOpRow, ...], Field(max_length=64 * len(_OP_UNITS))]


def project_device_operating_points(
    report: ResultReport,
    registration: DeviceOpRegistration,
    payload: DeviceOpPayload,
) -> dict[str, Any]:
    """Project already collected rows. Frame authenticity belongs to the caller."""
    if (
        report.plan.analysis != "dc"
        or payload.operation_id != report.operation_id
        or payload.plan_sha256 != report.plan.plan_sha256
        or payload.execution_input_sha256 != report.execution_input_sha256
        or payload.registration_sha256 != canonical_digest(registration)
    ):
        raise OperationRejected("research_op_identity_mismatch")
    rows: dict[tuple[str, OpField], DeviceOpRow] = {}
    for row in payload.rows:
        key = (row.instance_path, row.field)
        if row.instance_path not in registration.instance_paths or key in rows:
            raise OperationRejected("research_op_inventory_mismatch")
        rows[key] = row
    measurements = []
    for path in registration.instance_paths:
        for field, unit in _OP_UNITS.items():
            entry = rows.get((path, field))
            measurements.append(
                {
                    "instance_path": path,
                    "field": field,
                    "unit": unit,
                    "value": entry.value if entry else None,
                    "reason": entry.reason if entry else "field_not_retained",
                    "interpretation_reason": (
                        "registered_model_region_meaning_unavailable"
                        if field == "region" and entry is not None and entry.value is not None
                        else None
                    ),
                }
            )
    return {
        "operation_id": payload.operation_id,
        "plan_sha256": payload.plan_sha256,
        "execution_input_sha256": payload.execution_input_sha256,
        "registration_sha256": payload.registration_sha256,
        "op_frame_sha256": payload.op_frame_sha256,
        "verification_at_read": "LOCAL_OP_PAYLOAD_IDENTITY_ONLY",
        "measurements": measurements,
    }


def _op_read_order(registration: DeviceOpRegistration) -> list[tuple[str, str, OpField]]:
    return [
        (path, f"mos{index:02d}", field)
        for index, path in enumerate(registration.instance_paths, 1)
        for field in _OP_UNITS
    ]


def render_device_op_reads(
    registration: DeviceOpRegistration,
    selector: OpResultSelector,
) -> str:
    """Render only calls to the existing diagnostic mcpReadOp function."""
    registration = DeviceOpRegistration.model_validate_json(registration.model_dump_json())
    selector = TypeAdapter(OpResultSelector).validate_python(selector)
    return "\n".join(
        f'  mcpReadOp(port "registered" "{alias}" "{path}" "{field}" "{selector}")'
        for path, alias, field in _op_read_order(registration)
    )


def parse_device_op_frame(
    report: ResultReport,
    registration: DeviceOpRegistration,
    frame: bytes,
    *,
    expected_frame_sha256: str,
) -> DeviceOpPayload:
    """Parse one bounded instance-ordered OP frame pinned by its collector."""
    if report.plan.analysis != "dc":
        raise OperationRejected("research_op_requires_dc_report")
    if len(frame) > _OP_FRAME_LIMIT or hashlib.sha256(frame).hexdigest() != expected_frame_sha256:
        raise OperationRejected("research_op_frame_size_or_digest_mismatch")
    try:
        lines = frame.decode("ascii").splitlines()
        order = _op_read_order(registration)
        if len(lines) != len(order) + 2 or lines[0] != "BEGIN" or lines[-1] != "END":
            raise ValueError("OP frame envelope")
        rows = []
        for line, (path, alias, field) in zip(lines[1:-1], order, strict=True):
            parts = line.split("|")
            if len(parts) != 6 or parts[:4] != ["OP", "registered", alias, field]:
                raise ValueError("OP frame identity")
            kind, raw = parts[4:]
            if kind == "missing" and raw == "nil":
                rows.append(
                    DeviceOpRow(
                        instance_path=path,
                        field=field,
                        value=None,
                        reason="field_not_available",
                    )
                )
            elif kind == "value" and len(raw) <= 48:
                value = float(raw)
                if not math.isfinite(value) or abs(value) > 1e12:
                    raise ValueError("bounded OP frame value required")
                rows.append(DeviceOpRow(instance_path=path, field=field, value=value))
            else:
                raise ValueError("OP frame value")
    except ValueError:
        raise OperationRejected("research_op_frame_invalid") from None
    return DeviceOpPayload(
        operation_id=report.operation_id,
        plan_sha256=report.plan.plan_sha256,
        execution_input_sha256=report.execution_input_sha256,
        registration_sha256=canonical_digest(registration),
        op_frame_sha256=expected_frame_sha256,
        rows=tuple(rows),
    )
