"""Research measurements over retained data and explicitly registered devices."""

from __future__ import annotations

import hashlib
import math
import os
import stat
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.generic_analog import (
    Positive,
    _capture_retained_transfer,
    _interpolate_db_crossing,
)
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import NativeOperationQuery, NativeOperationService
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.result_reports import REPORT_LIMIT, ResultReport, capture, conditions_digest
from cadence_mcp_bridge.runtime_context import ExecutionContext
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
_AC_AXIS_REL_TOL = 1e-12


class AcGainDefinition(VariableModel):
    reference_frequency_hz: Positive
    bandwidth_drop_db: Positive | None = None
    minimum_search_stop_hz: Positive | None = None
    maximum_adjacent_frequency_ratio: Annotated[float, Field(gt=1, allow_inf_nan=False)] | None = (
        None
    )

    @model_validator(mode="after")
    def ordered_search(self) -> Self:
        if self.minimum_search_stop_hz is not None and (
            self.minimum_search_stop_hz <= self.reference_frequency_hz
        ):
            raise ValueError("minimum search stop must exceed the reference frequency")
        return self


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


def _research_crossing(
    axes: list[float],
    db: list[float | None],
    reference: int | None,
    threshold_db: float | None,
    definition: AcGainDefinition,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "value": None,
        "unit": "Hz",
        "threshold_gain_db": threshold_db,
        "bracket_hz": None,
        "bracket_gain_db": None,
        "method": "first_downward_crossing_db_linear_log_frequency_no_extrapolation",
        "status": "NOT_EVALUATED",
        "reason": "reference_sample_unavailable",
    }
    if reference is None:
        return result
    if threshold_db is None:
        return {**result, "reason": "reference_gain_db_unavailable"}
    if reference == len(axes) - 1:
        return {**result, "reason": "samples_after_reference_unavailable"}
    ratio_limit = definition.maximum_adjacent_frequency_ratio
    threshold_hit: int | None = None
    for i in range(reference + 1, len(axes)):
        left, right = db[i - 1], db[i]
        if ratio_limit is not None and axes[i] / axes[i - 1] > ratio_limit:
            return {
                **result,
                "reason": "insufficient_frequency_resolution",
                "gap_hz": axes[i - 1 : i + 1],
            }
        if right == threshold_db:
            if left is not None and left > threshold_db:
                threshold_hit = i
            continue
        if right is not None and right > threshold_db:
            threshold_hit = None
            continue
        if threshold_hit is None and (left is None or left <= threshold_db):
            continue
        if right is None:
            return {
                **result,
                "bracket_hz": axes[i - 1 : i + 1],
                "bracket_gain_db": [left, right],
                "reason": "zero_transfer_at_crossing_bracket",
            }
        if threshold_hit is not None:
            return {
                **result,
                "bracket_hz": axes[threshold_hit - 1 : threshold_hit + 1],
                "bracket_gain_db": db[threshold_hit - 1 : threshold_hit + 1],
                "falling_confirmation_hz": axes[i],
                "falling_confirmation_gain_db": right,
                "status": "OBSERVED_SAMPLED_CROSSING",
                "reason": None,
                "value": axes[threshold_hit],
            }
        assert left is not None
        return {
            **result,
            "bracket_hz": axes[i - 1 : i + 1],
            "bracket_gain_db": [left, right],
            "status": "OBSERVED_SAMPLED_CROSSING",
            "reason": None,
            "value": _interpolate_db_crossing(axes[i - 1], axes[i], left, right, threshold_db),
        }
    minimum_stop = definition.minimum_search_stop_hz
    if (
        minimum_stop is not None
        and axes[-1] < minimum_stop
        and not math.isclose(axes[-1], minimum_stop, rel_tol=_AC_AXIS_REL_TOL)
    ):
        return {**result, "reason": "insufficient_frequency_range"}
    if threshold_hit is not None:
        return {**result, "reason": "crossing_direction_unconfirmed_at_range_end"}
    return {
        **result,
        "status": "NOT_OBSERVED_IN_SAMPLED_RANGE",
        "reason": "downward_crossing_absent",
    }


def sampled_ac_gain(
    spectrum: list[dict[str, Any]],
    definition: AcGainDefinition,
) -> dict[str, Any]:
    """Estimate sampled unity and optional relative-bandwidth crossings."""
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
    if reference_index is None:
        # The authenticated reader permits roundoff in the observed frequency axis.
        nearby = [
            i
            for i, frequency in enumerate(axes)
            if math.isclose(frequency, definition.reference_frequency_hz, rel_tol=_AC_AXIS_REL_TOL)
        ]
        if len(nearby) == 1:
            reference_index = nearby[0]
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

    definition_data = definition.model_dump(mode="json", exclude_none=True)
    result = {
        "definition": definition_data,
        "definition_sha256": hashlib.sha256(_canonical(definition_data)).hexdigest(),
        "reference": reference,
        "reference_reason": "reference_sample_unavailable" if reference is None else None,
        "unity_gain_frequency": _research_crossing(axes, db, reference_index, 0, definition),
        "sample_count": len(samples),
        "start_hz": axes[0],
        "stop_hz": axes[-1],
        "qualification": "SAMPLED_REFERENCE_ESTIMATE_NO_CONTINUOUS_OR_GRID_CONVERGENCE_CLAIM",
    }
    if definition.bandwidth_drop_db is not None:
        reference_db = db[reference_index] if reference_index is not None else None
        threshold = (
            reference_db - definition.bandwidth_drop_db if reference_db is not None else None
        )
        result["bandwidth"] = _research_crossing(axes, db, reference_index, threshold, definition)
    return result


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
            if kind == "missing" and raw in ("nil", "instance"):
                rows.append(
                    DeviceOpRow(
                        instance_path=path,
                        field=field,
                        value=None,
                        reason=(
                            "instance_not_available" if raw == "instance" else "field_not_available"
                        ),
                    )
                )
            elif kind == "value" and len(raw) <= 48:
                value = float(raw)
                if not math.isfinite(value) or abs(value) > 1e12:
                    raise ValueError("bounded OP frame value required")
                rows.append(DeviceOpRow(instance_path=path, field=field, value=value))
            else:
                raise ValueError("OP frame value")
        absent_paths = {row.instance_path for row in rows if row.reason == "instance_not_available"}
        if any(
            row.instance_path in absent_paths and row.reason != "instance_not_available"
            for row in rows
        ):
            raise ValueError("OP instance availability changed within its rows")
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


class DeviceOpQuery(NativeOperationQuery):
    registration_id: LogicalId


class DeviceOpSourceBinding(VariableModel):
    """Trusted local operator setting; public requests never supply this value."""

    catalog_path: Path
    catalog_sha256: Digest


class _DeviceOpArtifact(VariableModel):
    path: Path
    sha256: Digest


class _DeviceOpRecord(VariableModel):
    registration_id: LogicalId
    operation_id: OperationId
    plan_sha256: Digest
    execution_input_sha256: Digest
    terminal_sha256: Digest
    registration: DeviceOpRegistration
    registration_sha256: Digest
    report: _DeviceOpArtifact
    frame: _DeviceOpArtifact


class _DeviceOpCatalog(VariableModel):
    schema_version: Literal[1]
    records: Annotated[tuple[_DeviceOpRecord, ...], Field(max_length=64)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        ids = {(row.operation_id, row.registration_id) for row in self.records}
        if len(ids) != len(self.records):
            raise ValueError("distinct device OP lookup keys required")
        return self


def _read_op_artifact(path: Path, digest: str, *, limit: int) -> bytes:
    if not path.is_absolute() or path.drive.startswith("\\"):
        raise OperationRejected("research_op_local_absolute_path_required")
    try:
        source = _local_path(path)
        before = source.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise OperationRejected("research_op_artifact_invalid")
        fd = os.open(
            source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise OperationRejected("research_op_artifact_changed")
            raw = stream.read(limit + 1)
    except OperationRejected:
        raise
    except (OSError, ValueError):
        raise OperationRejected("research_op_artifact_unreadable") from None
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != digest:
        raise OperationRejected("research_op_artifact_digest_or_size_mismatch")
    return raw


def capture_device_operating_points(
    native: NativeOperationService,
    query: DeviceOpQuery,
    *,
    source: DeviceOpSourceBinding | None,
) -> dict[str, Any]:
    """Validate retained DC operation identity and read an operator-pinned OP frame."""
    return _read_device_operating_points(native.context, query, source, native.current)


def read_retained_device_operating_points(
    context: ExecutionContext,
    query: DeviceOpQuery,
    *,
    source: DeviceOpSourceBinding | None,
) -> dict[str, Any]:
    """Read the same pinned evidence in a context with no native execution authority."""
    if (
        context.binding.native_provider_binding is not None
        or context.binding.operator_grant is not None
    ):
        raise OperationRejected("retained_op_context_has_native_authority")
    return _read_device_operating_points(context, query, source)


def _read_device_operating_points(
    context: ExecutionContext,
    query: DeviceOpQuery,
    source: DeviceOpSourceBinding | None,
    check_native_binding: Callable[[], None] | None = None,
) -> dict[str, Any]:
    effects = {
        "remote_contact": False,
        "new_simulations": 0,
        "new_extractions": 0,
        "new_reservations": 0,
    }
    if source is None:
        return {"status": "NOT_AVAILABLE", "reason": "device_op_source_not_configured", **effects}
    raw = _read_op_artifact(source.catalog_path, source.catalog_sha256, limit=REPORT_LIMIT)
    try:
        _closed_document(raw, max_bytes=REPORT_LIMIT)
        catalog = _DeviceOpCatalog.model_validate_json(raw)
    except ValueError:
        raise OperationRejected("research_op_catalog_invalid") from None
    evidence = next(
        (
            row
            for row in catalog.records
            if (row.operation_id, row.registration_id)
            == (query.operation_id, query.registration_id)
        ),
        None,
    )
    if evidence is None:
        return {"status": "NOT_AVAILABLE", "reason": "registered_op_record_unavailable", **effects}
    if evidence.plan_sha256 != query.expected_plan_sha256 or (
        canonical_digest(evidence.registration) != evidence.registration_sha256
    ):
        raise OperationRejected("research_op_registration_or_plan_mismatch")

    if check_native_binding is not None:
        check_native_binding()
    store = AnalysisStore(context.binding.analysis_journal)
    with store.connection(create=False, read_only=True) as connection:
        record = store._read_operation(connection, query.operation_id)
    plan = record.plan
    if (
        record.operation_id != query.operation_id
        or plan.plan_sha256 != evidence.plan_sha256
        or plan.resource_domain_sha256 != context.resource_domain_sha256
        or plan.ledger_ref != context.binding.ledger_ref
        or plan.runner_sha256 != context.binding.runner_sha256
        or plan.environment_sha256 != context.binding.environment_sha256
        or plan.design_sha256 != context.binding.design_sha256
        or plan.pdk_sha256 != context.binding.pdk_sha256
        or plan.analysis != "dc"
        or record.progress.phase != "SUCCEEDED"
        or record.progress.provider_receipt_sha256 != evidence.terminal_sha256
    ):
        raise OperationRejected("research_op_retained_terminal_mismatch")

    report_raw = _read_op_artifact(evidence.report.path, evidence.report.sha256, limit=REPORT_LIMIT)
    try:
        _closed_document(report_raw, max_bytes=REPORT_LIMIT)
        report = ResultReport.model_validate_json(report_raw)
    except ValueError:
        raise OperationRejected("research_op_source_report_invalid") from None
    if (
        report.operation_id != record.operation_id
        or report.plan != record.plan
        or report.execution_input_sha256 != evidence.execution_input_sha256
    ):
        raise OperationRejected("research_op_source_report_mismatch")

    frame = _read_op_artifact(evidence.frame.path, evidence.frame.sha256, limit=_OP_FRAME_LIMIT)
    payload = parse_device_op_frame(
        report,
        evidence.registration,
        frame,
        expected_frame_sha256=evidence.frame.sha256,
    )
    measurement = project_device_operating_points(report, evidence.registration, payload)
    return {
        "status": "AVAILABLE",
        "registration_id": query.registration_id,
        "measurement": measurement,
        "source": report.model_dump(mode="json"),
        "source_report_sha256": evidence.report.sha256,
        "terminal_sha256": evidence.terminal_sha256,
        "catalog_sha256": source.catalog_sha256,
        "verification_at_read": "OPERATOR_PINNED_ARTIFACT_AND_RETAINED_TERMINAL_VERIFIED",
        **effects,
    }
