"""Explicit sampled-transfer measurements from retained generic results, read only."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from typing import Annotated, Any

from pydantic import Field, TypeAdapter

from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.errors import BridgeError
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
            "required": "Input-referred or output definition, common mode, feedback state, "
            "stimulus and threshold/zero-crossing method with actual extraction.",
        },
        "slew": {
            "status": "BLOCKED", "reason": "qualified_step_loading_and_window_required",
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


def add_analog_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "operator-analog", help="Read-only experimental sampled-transfer measurements.",
    )
    actions = parser.add_subparsers(dest="analog_action", required=True)
    actions.add_parser("requirements")
    capture = actions.add_parser("bandwidth")
    for name in ("settings", "context", "operation-id", "expected-plan-sha256"):
        capture.add_argument("--" + name, required=True)
    capture.add_argument("--reference-frequency-hz", type=float, required=True)
    capture.add_argument("--drop-db", type=float, default=3.0)
    capture.add_argument("--experimental-analog", action="store_true", required=True)


def analog_cli(arguments: argparse.Namespace) -> int:
    contact: bool | None = False
    try:
        if arguments.analog_action == "requirements":
            output = {"requirements": requirements(), "remote_contact": False,
                      "new_simulations": 0, "new_extractions": 0, "new_reservations": 0}
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
            output = asyncio.run(capture_bandwidth(
                native, arguments.operation_id, arguments.expected_plan_sha256, definition,
            ))
        print(json.dumps(output, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, BridgeError):
        print(json.dumps({
            "status": "BLOCKED", "reason": "generic_analog_rejected",
            "guidance": "Use an existing succeeded registered AC ID and exact plan; confirm "
            "nonzero complete transfer and a measured reference frequency. No rerun occurs.",
            "remote_contact": contact, "new_simulations": 0, "new_extractions": 0,
            "new_reservations": 0,
        }))
        return 2
