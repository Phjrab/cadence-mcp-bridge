"""Explicit sampled-transfer measurements from retained generic results, read only."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, TypeAdapter

from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.errors import BridgeError
from cadence_mcp_bridge.generic_offset import InputNullingDefinition, sampled_input_nulling
from cadence_mcp_bridge.generic_slew import SampledSlewDefinition, sampled_slew
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import NativeOperationService
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.result_reports import conditions_digest, make_report
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class SampledBandwidthDefinition(VariableModel):
    reference_frequency_hz: Positive
    drop_db: Annotated[float, Field(gt=0, le=120, allow_inf_nan=False)] = 3.0


def requirements() -> dict[str, Any]:
    return {
        "bandwidth": {
            "definition": "First downward magnitude crossing after an explicitly selected "
            "measured reference sample; interpolate dB against log10(frequency).",
            "limitations": "Sample-relative estimate, no DC plateau, continuous response or "
            "grid-convergence qualification. Never extrapolate.",
            "required": "Retained succeeded AC job, complete bounded registered complex "
            "output/input spectrum, nonzero measured input and finite nonzero transfer.",
        },
        "phase_margin": {
            "status": "BLOCKED", "reason": "qualified_loop_gain_testbench_required",
            "required": "Loop break/injection, loading, sign and actual loop-gain extraction; "
            "ordinary output/input phase cannot supply phase margin.",
        },
        "offset": {
            "status": "BLOCKED", "reason": "offset_definition_and_testbench_required",
            "experimental_operator_command": "operator-analog offset",
            "required": "Input-referred or output definition, common mode, feedback state, "
            "stimulus and threshold/zero-crossing method with actual extraction.",
        },
        "slew": {
            "status": "BLOCKED", "reason": "per_job_step_loading_window_and_resolution_required",
            "experimental_operator_command": "operator-analog slew",
            "required": "Actual step stimulus, input/output signals, load, amplitude, direction, "
            "settled endpoints, threshold window and time-resolved extraction. TRAN extrema "
            "or reference-circuit calculations are insufficient.",
        },
    }


def sampled_crossing(
    spectrum: list[dict[str, Any]], definition: SampledBandwidthDefinition,
) -> dict[str, Any]:
    """Numerical estimate only; this function makes no native-origin claim."""
    if not 2 <= len(spectrum) <= 256:
        raise OperationRejected("analog_complete_bounded_spectrum_required")
    axes: list[float] = []
    gains: list[float] = []
    for sample in spectrum:
        frequency = float(sample["frequency_hz"])
        real, imag = float(sample["real_v_per_v"]), float(sample["imag_v_per_v"])
        magnitude = math.hypot(real, imag)
        if not all(math.isfinite(v) for v in (frequency, real, imag, magnitude)) or (
            frequency <= 0 or magnitude <= 0 or (axes and frequency <= axes[-1])
        ):
            raise OperationRejected("analog_spectrum_invalid_or_zero_transfer")
        axes.append(frequency)
        gains.append(20 * math.log10(magnitude))
    matches = [i for i, f in enumerate(axes) if f == definition.reference_frequency_hz]
    if len(matches) != 1:
        raise OperationRejected("analog_reference_exact_sample_required")
    reference = matches[0]
    if reference == len(axes) - 1:
        raise OperationRejected("analog_samples_after_reference_required")
    target = gains[reference] - definition.drop_db
    output: dict[str, Any] = {
        "status": "NOT_OBSERVED_IN_SAMPLED_RANGE", "value": None, "unit": "Hz",
        "definition": definition.model_dump(mode="json"),
        "definition_sha256": canonical_digest(definition),
        "reference_gain_db": gains[reference], "threshold_gain_db": target,
        "sample_count": len(axes), "start_hz": axes[0], "stop_hz": axes[-1],
        "bracket_hz": None, "bracket_gain_db": None,
        "method": "first_downward_crossing_db_linear_log_frequency_no_extrapolation",
        "qualification": "SAMPLED_REFERENCE_ESTIMATE_NO_CONTINUOUS_OR_GRID_CONVERGENCE_CLAIM",
        "native_provenance": "NOT_ATTESTED",
    }
    for i in range(reference + 1, len(axes)):
        if gains[i - 1] > target >= gains[i]:
            fraction = (gains[i - 1] - target) / (gains[i - 1] - gains[i])
            estimate = 10 ** (
                math.log10(axes[i - 1])
                + fraction * (math.log10(axes[i]) - math.log10(axes[i - 1]))
            )
            # Keep exact sampled crossings exact and reject arithmetic outside the bracket.
            if gains[i] == target:
                estimate = axes[i]
            if not math.isfinite(estimate) or not axes[i - 1] <= estimate <= axes[i]:
                raise OperationRejected("analog_interpolation_invalid")
            output.update(
                status="OBSERVED_SAMPLED_CROSSING", value=estimate,
                bracket_hz=[axes[i - 1], axes[i]],
                bracket_gain_db=[gains[i - 1], gains[i]],
            )
            break
    return output


async def capture_bandwidth(
    native: NativeOperationService, operation_id: str, plan_sha256: str,
    definition: SampledBandwidthDefinition,
) -> dict[str, Any]:
    TypeAdapter(OperationId).validate_python(operation_id)
    TypeAdapter(Digest).validate_python(plan_sha256)
    native.current()
    store = native.lifecycle.store
    with store.connection(create=False, read_only=True) as connection:
        record = store._read_operation(connection, operation_id)
    if (
        record.operation_id != operation_id or record.plan.plan_sha256 != plan_sha256
        or record.plan.resource_domain_sha256 != native.context.resource_domain_sha256
        or record.plan.ledger_ref != native.context.binding.ledger_ref
        or record.plan.analysis != "ac" or record.progress.phase != "SUCCEEDED"
    ):
        raise OperationRejected("analog_retained_succeeded_ac_identity_required")
    observed, result = await native.provider.analog_result(operation_id, record.plan)
    observed.check(record)
    if observed.progress != record.progress:
        raise OperationRejected("analog_terminal_identity_mismatch")
    report = make_report(record, result)
    spectrum = TypeAdapter(list[dict[str, Any]]).validate_python(result["ac_spectrum"])
    estimate = sampled_crossing(spectrum, definition)
    # Provenance is attached only after the provider and retained terminal checks.
    estimate["native_provenance"] = report.source_provenance
    return {
        "measurement": estimate, "source": report.model_dump(mode="json"),
        "conditions_sha256": conditions_digest(report),
        "spectrum_sha256": hashlib.sha256(_canonical(spectrum)).hexdigest(),
        "spectrum": spectrum, "requirements": requirements(),
        "new_simulations": 0, "new_extractions": 0, "new_reservations": 0,
        "remote_contact": True,
    }


async def capture_slew(
    native: NativeOperationService, operation_id: str, plan_sha256: str,
    definition: SampledSlewDefinition,
) -> dict[str, Any]:
    TypeAdapter(OperationId).validate_python(operation_id)
    TypeAdapter(Digest).validate_python(plan_sha256)
    native.current()
    store = native.lifecycle.store
    with store.connection(create=False, read_only=True) as connection:
        record = store._read_operation(connection, operation_id)
    if (
        record.operation_id != operation_id or record.plan.plan_sha256 != plan_sha256
        or record.plan.resource_domain_sha256 != native.context.resource_domain_sha256
        or record.plan.ledger_ref != native.context.binding.ledger_ref
        or record.plan.analysis != "tran" or record.progress.phase != "SUCCEEDED"
    ):
        raise OperationRejected("analog_retained_succeeded_tran_identity_required")
    observed, result = await native.provider.analog_result(operation_id, record.plan)
    observed.check(record)
    if observed.progress != record.progress:
        raise OperationRejected("analog_terminal_identity_mismatch")
    report = make_report(record, result)
    if report.analysis_conditions.static_statements_sha256 != definition.static_statements_sha256:
        raise OperationRejected("slew_static_stimulus_and_load_binding_mismatch")
    waves = TypeAdapter(dict[str, list[dict[str, Any]]]).validate_python(result["tran_waveforms"])
    estimate = sampled_slew(waves, definition)
    estimate["native_provenance"] = report.source_provenance
    return {
        "measurement": estimate, "source": report.model_dump(mode="json"),
        "conditions_sha256": conditions_digest(report),
        "waveforms_sha256": hashlib.sha256(_canonical(waves)).hexdigest(), "waveforms": waves,
        "new_simulations": 0, "new_extractions": 0, "new_reservations": 0,
        "remote_contact": True,
    }


async def capture_offset(
    native: NativeOperationService, operations: list[dict[str, str]],
    definition: InputNullingDefinition,
) -> dict[str, Any]:
    if not 3 <= len(operations) <= 32 or len({op.get("operation_id") for op in operations}) != len(
        operations,
    ):
        raise OperationRejected("offset_distinct_bounded_operations_required")
    native.current()
    records = []
    store = native.lifecycle.store
    with store.connection(create=False, read_only=True) as connection:
        for op in operations:
            if set(op) != {"operation_id", "expected_plan_sha256"}:
                raise OperationRejected("offset_operation_identity_required")
            operation_id = TypeAdapter(OperationId).validate_python(op["operation_id"])
            plan_sha = TypeAdapter(Digest).validate_python(op["expected_plan_sha256"])
            record = store._read_operation(connection, operation_id)
            if (
                record.operation_id != operation_id or record.plan.plan_sha256 != plan_sha
                or record.plan.resource_domain_sha256 != native.context.resource_domain_sha256
                or record.plan.ledger_ref != native.context.binding.ledger_ref
                or record.plan.analysis != "dc" or record.progress.phase != "SUCCEEDED"
            ):
                raise OperationRejected("offset_retained_succeeded_dc_identity_required")
            records.append(record)
    reports, rows = [], []
    baseline = None
    for record in records:
        observed, result = await native.provider.report_result(record.operation_id, record.plan)
        observed.check(record)
        if observed.progress != record.progress:
            raise OperationRejected("analog_terminal_identity_mismatch")
        report = make_report(record, result)
        static_digest = report.analysis_conditions.static_statements_sha256
        if static_digest != definition.static_statements_sha256:
            raise OperationRejected("offset_static_testbench_binding_mismatch")
        conditions = report.conditions()
        variable_names = {definition.positive_input_variable, definition.negative_input_variable}
        conditions["values"] = [v for v in conditions["values"]
                                if v["logical_id"] not in variable_names]
        # The authenticated effective input necessarily differs at each applied
        # input point. Retain that digest in each source report, while comparing
        # the static/source/reader/analysis and every non-input variable exactly.
        conditions.pop("execution_input_sha256", None)
        if baseline is not None and conditions != baseline:
            raise OperationRejected("offset_source_or_conditions_mismatch")
        baseline = conditions
        nodes = TypeAdapter(list[dict[str, Any]]).validate_python(result["nodes"])
        measured = {node["logical_id"]: float(node["value"]) for node in nodes}
        variables = {v.logical_id: v for v in record.plan.request.values}
        for signal, logical in (
            (definition.positive_input, definition.positive_input_variable),
            (definition.negative_input, definition.negative_input_variable),
        ):
            if logical not in variables or variables[logical].unit != "V" or (
                signal not in measured
                or abs(measured[signal] - float(variables[logical].value))
                > definition.common_mode_tolerance_v
            ):
                raise OperationRejected("offset_measured_input_variable_binding_mismatch")
        rows.append(measured)
        reports.append(report.model_dump(mode="json"))
    estimate = sampled_input_nulling(rows, definition)
    estimate["native_provenance"] = reports[0]["source_provenance"]
    return {
        "measurement": estimate, "sources": reports, "measured_nodes": rows,
        "common_conditions_sha256": hashlib.sha256(_canonical(baseline)).hexdigest(),
        "new_simulations": 0, "new_extractions": 0, "new_reservations": 0,
        "remote_contact": True,
    }


def add_analog_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "operator-analog", help="Read-only experimental sampled-transfer measurements.",
    )
    actions = parser.add_subparsers(dest="analog_action", required=True)
    actions.add_parser("requirements")
    capture = actions.add_parser("bandwidth")
    capture.add_argument("--settings", type=Path, required=True)
    for name in ("context", "operation-id", "expected-plan-sha256"):
        capture.add_argument("--" + name, required=True)
    capture.add_argument("--reference-frequency-hz", type=float, required=True)
    capture.add_argument("--drop-db", type=float, default=3.0)
    capture.add_argument("--experimental-analog", action="store_true", required=True)
    slew = actions.add_parser("slew")
    slew.add_argument("--settings", type=Path, required=True)
    slew.add_argument("--definition", type=Path, required=True)
    for name in ("context", "operation-id", "expected-plan-sha256"):
        slew.add_argument("--" + name, required=True)
    slew.add_argument("--experimental-analog", action="store_true", required=True)
    offset = actions.add_parser("offset")
    offset.add_argument("--settings", type=Path, required=True)
    offset.add_argument("--definition", type=Path, required=True)
    offset.add_argument("--operations", type=Path, required=True)
    offset.add_argument("--context", required=True)
    offset.add_argument("--experimental-analog", action="store_true", required=True)


def analog_cli(arguments: argparse.Namespace) -> int:
    contact: bool | None = False
    try:
        if arguments.analog_action == "requirements":
            output = {"requirements": requirements(), "remote_contact": False,
                      "new_simulations": 0, "new_extractions": 0, "new_reservations": 0}
        else:
            definition: SampledBandwidthDefinition | SampledSlewDefinition | InputNullingDefinition
            if arguments.analog_action in ("slew", "offset"):
                from cadence_mcp_bridge.domain_provisioning import _closed_document

                with _local_path(arguments.definition).open("rb") as stream:
                    raw = stream.read(16385)
                _closed_document(raw, max_bytes=16384)
                definition = (SampledSlewDefinition.model_validate_json(raw)
                              if arguments.analog_action == "slew"
                              else InputNullingDefinition.model_validate_json(raw))
            else:
                definition = SampledBandwidthDefinition(
                    reference_frequency_hz=arguments.reference_frequency_hz,
                    drop_db=arguments.drop_db,
                )
            contexts = load_runtime(_local_path(arguments.settings))
            context = next((c for c in contexts if c.binding.context_id == arguments.context), None)
            if context is None:
                raise OperationRejected("analog_context_required")
            native = NativeOperationService(context)
            contact = None
            if isinstance(definition, InputNullingDefinition):
                with _local_path(arguments.operations).open("rb") as stream:
                    raw = stream.read(16385)
                _closed_document(raw, max_bytes=16384)
                operations = TypeAdapter(list[dict[str, str]]).validate_json(raw)
                output = asyncio.run(capture_offset(native, operations, definition))
            elif isinstance(definition, SampledSlewDefinition):
                output = asyncio.run(capture_slew(
                    native, arguments.operation_id, arguments.expected_plan_sha256, definition,
                ))
            else:
                output = asyncio.run(capture_bandwidth(
                    native, arguments.operation_id, arguments.expected_plan_sha256, definition,
                ))
        print(json.dumps(output, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, BridgeError):
        print(json.dumps({
            "status": "BLOCKED", "reason": "generic_analog_rejected",
            "guidance": "Use an existing succeeded registered AC/TRAN ID and exact plan. "
            "Confirm the bound definition and complete saved samples. No rerun occurs.",
            "remote_contact": contact, "new_simulations": 0, "new_extractions": 0,
            "new_reservations": 0,
        }))
        return 2
