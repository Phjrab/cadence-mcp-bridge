"""Generic bounded reader compiler and frame projection; native authority is external."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import deque
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, TypeAdapter, field_validator, model_validator

from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration, bind_inputs
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.operator_operations import OperationPlan, OperationRejected
from cadence_mcp_bridge.power_measurements import signed_power_totals
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)

FRAME_LIMIT = 262144
MAX_SAMPLES = 256
Selector = Annotated[str, Field(pattern=r"^/[A-Za-z0-9_#][A-Za-z0-9_#./-]{0,126}$", max_length=128)]


def _canonical_selector(value: str) -> str:
    if any(part in ("", ".", "..") for part in value[1:].split("/")):
        raise ValueError("canonical signal selector required")
    return value


class NodeSignal(VariableModel):
    logical_id: LogicalId
    selector: Selector

    @field_validator("selector")
    @classmethod
    def canonical_selector(cls, value: str) -> str:
        if value.rsplit("/", 1)[-1] in ("PLUS", "MINUS"):
            raise ValueError("branch current selector is not a node voltage")
        return _canonical_selector(value)


class SourceSignal(VariableModel):
    source_id: LogicalId
    role: Literal["supply", "bias", "stimulus"]
    positive_node: LogicalId | None
    negative_node: LogicalId | None
    current_selector: Selector
    current_convention: Literal["positive_into_source_positive_terminal_A"]

    @field_validator("current_selector")
    @classmethod
    def canonical_selector(cls, value: str) -> str:
        if not value.endswith("/PLUS"):
            raise ValueError("positive-terminal branch current selector required")
        return _canonical_selector(value)

    @model_validator(mode="after")
    def distinct_terminals(self) -> Self:
        if self.positive_node == self.negative_node:
            raise ValueError("distinct source terminals required")
        return self


class TransferSignal(VariableModel):
    positive_input: LogicalId
    negative_input: LogicalId | None
    positive_output: LogicalId
    negative_output: LogicalId | None
    gain_frequencies_hz: Annotated[tuple[NumberText, ...], Field(min_length=1, max_length=16)]

    @field_validator("gain_frequencies_hz", mode="before")
    @classmethod
    def frequencies(cls, value: Any) -> tuple[str, ...]:
        if type(value) not in (list, tuple):
            raise ValueError("frequency array required")
        return tuple(number_text(item) for item in value)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        values = tuple(Decimal(item) for item in self.gain_frequencies_hz)
        if values != tuple(sorted(set(values))) or values[0] <= 0:
            raise ValueError("unique increasing positive frequencies required")
        if (
            self.positive_input == self.negative_input
            or self.positive_output == self.negative_output
        ):
            raise ValueError("distinct differential terminals required")
        return self


class GenericReaderRegistration(VariableModel):
    schema_version: Literal[1]
    design_id: LogicalId
    analysis_id: LogicalId
    measurement_id: LogicalId
    ade_registration_sha256: Digest
    measurement_contract_sha256: Digest
    nodes: Annotated[tuple[NodeSignal, ...], Field(min_length=1, max_length=8)]
    sources: Annotated[tuple[SourceSignal, ...], Field(max_length=8)]
    transfer: TransferSignal | None
    maximum_samples: Annotated[int, Field(ge=2, le=MAX_SAMPLES)]

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: int) -> int:
        if type(value) is not int:
            raise ValueError("integer version required")
        return value

    @model_validator(mode="after")
    def inventory(self) -> Self:
        if len(self.nodes) * self.maximum_samples > 1536:
            raise ValueError("aggregate reader sample bound exceeded")
        ids = {node.logical_id for node in self.nodes}
        if len(ids) != len(self.nodes) or len({n.selector for n in self.nodes}) != len(self.nodes):
            raise ValueError("distinct signal identities required")
        if len({s.source_id for s in self.sources}) != len(self.sources) or len(
            {s.current_selector for s in self.sources}
        ) != len(self.sources):
            raise ValueError("distinct current identities required")
        if {n.selector for n in self.nodes} & {s.current_selector for s in self.sources}:
            raise ValueError("voltage and current selector inventories must be disjoint")
        refs = [
            n for s in self.sources for n in (s.positive_node, s.negative_node) if n is not None
        ]
        if self.transfer:
            refs += [
                n
                for n in (
                    self.transfer.positive_input,
                    self.transfer.negative_input,
                    self.transfer.positive_output,
                    self.transfer.negative_output,
                )
                if n is not None
            ]
        if any(n not in ids for n in refs):
            raise ValueError("signal reference outside inventory")
        if self.sources and not any(s.role == "supply" for s in self.sources):
            raise ValueError("power inventory requires an explicit supply scope")
        return self


# Proven API spellings from the retained native readers; general binding remains unqualified.
_PREAMBLE = r"""procedure(mcpGenericScalar(name)
  let((data vec)
    data=getData(name)
    cond((numberp(data) data)
      (drIsWaveform(data)
        vec=drGetWaveformYVec(data)
        if(equal(drVectorLength(vec) 1) then drGetElem(vec 0) else nil))
      (t nil))))
"""


def bind_reader(
    context: ExecutionContext,
    plan: OperationPlan,
    ade: AdeExecutionRegistration,
    reader: GenericReaderRegistration,
) -> None:
    bind_inputs(context, plan, ade)
    if (reader.design_id, reader.analysis_id, reader.ade_registration_sha256) != (
        plan.request.design_id,
        plan.request.analysis_id,
        canonical_digest(ade),
    ) or reader.measurement_id not in context.contracts.designs.profile(
        reader.design_id
    ).allowed_measurements:
        raise OperationRejected("reader_registration_binding_mismatch")
    measurement = next(
        (
            m
            for m in context.contracts.designs.measurements_for(reader.design_id)
            if m.measurement_id == reader.measurement_id
        ),
        None,
    )
    if measurement is None or (
        measurement.analysis_id != reader.analysis_id
        or canonical_digest(measurement) != reader.measurement_contract_sha256
    ):
        raise OperationRejected("reader_measurement_analysis_binding_mismatch")
    if measurement.reader != "unqualified":
        raise OperationRejected("reader_legacy_definition_protected")
    if (plan.analysis == "ac") != (reader.transfer is not None) or (
        plan.analysis != "dc" and reader.sources
    ):
        raise OperationRejected("reader_analysis_inventory_mismatch")
    if reader.transfer:
        if ade.inputs.analysis != "ac":
            raise OperationRejected("reader_analysis_inventory_mismatch")
        for frequency in reader.transfer.gain_frequencies_hz:
            if (
                not Decimal(ade.inputs.start_hz)
                <= Decimal(frequency)
                <= Decimal(ade.inputs.stop_hz)
            ):
                raise OperationRejected("reader_gain_frequency_outside_analysis")


def _header(
    operation_id: str,
    plan: OperationPlan,
    reader: GenericReaderRegistration,
    execution_input_sha256: str,
) -> str:
    TypeAdapter(OperationId).validate_python(operation_id)
    TypeAdapter(Digest).validate_python(execution_input_sha256)
    return "|".join(
        (
            "MCP_GREL_FRAME",
            "1",
            operation_id,
            plan.plan_sha256,
            execution_input_sha256,
            canonical_digest(reader),
        )
    )


def render_reader(
    context: ExecutionContext,
    plan: OperationPlan,
    ade: AdeExecutionRegistration,
    reader: GenericReaderRegistration,
    operation_id: str,
    execution_input_sha256: str,
) -> bytes:
    bind_reader(context, plan, ade, reader)
    header = _header(operation_id, plan, reader, execution_input_sha256)
    # Paths come only from the immutable operator environment and validated UUID.
    job = context.contracts.environment.paths.job_root + "/" + operation_id + "/work"
    result = "dcOp" if plan.analysis == "dc" else plan.analysis
    lines = [
        _PREAMBLE,
        "let((port data wave xVec yVec count index sample axis)",
        f'  port=outfile("{job}/generic-frame.txt")',
        "  unless(port exit(1))",
        f'  unless(openResults("{job}/psf") close(port) exit(1))',
        f"  unless(selectResult('{result}) close(port) exit(1))",
        f'  fprintf(port "{header}\\n")',
    ]
    if plan.analysis == "dc":
        for node in reader.nodes:
            lines += [
                f'  data=mcpGenericScalar("{node.selector}")',
                "  unless(numberp(data) close(port) exit(1))",
                f'  fprintf(port "V|{node.logical_id}|%.16g\\n" data)',
            ]
        for source in reader.sources:
            lines += [
                f'  data=mcpGenericScalar("{source.current_selector}")',
                "  unless(numberp(data) close(port) exit(1))",
                f'  fprintf(port "I|{source.source_id}|%.16g\\n" data)',
            ]
    else:
        for node in reader.nodes:
            lines += [
                f'  wave=getData("{node.selector}")',
                "  unless(wave && drIsWaveform(wave) close(port) exit(1))",
                "  xVec=drGetWaveformXVec(wave) yVec=drGetWaveformYVec(wave)",
                "  count=drVectorLength(xVec)",
                f"  unless(count>=2 && count<={reader.maximum_samples} && "
                "count==drVectorLength(yVec) close(port) exit(1))",
                "  for(index 0 sub1(count)",
                "    axis=drGetElem(xVec index) sample=drGetElem(yVec index)",
                f'    fprintf(port "P|{node.logical_id}|%d|%.16g|%.16g|%.16g\\n" '
                "index axis real(sample) imag(sample)))",
            ]
    lines += ['  fprintf(port "END\\n")', "  close(port))", "exit(0)", ""]
    return "\n".join(lines).encode("ascii")


def _finite(text: str) -> float:
    if (
        len(text) > 48
        or re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text) is None
    ):
        raise OperationRejected("reader_frame_number_invalid")
    try:
        value = float(number_text(text))
    except ValueError:
        raise OperationRejected("reader_frame_number_invalid") from None
    if not math.isfinite(value):
        raise OperationRejected("reader_frame_number_invalid")
    return value


def project_frame(
    context: ExecutionContext,
    plan: OperationPlan,
    ade: AdeExecutionRegistration,
    reader: GenericReaderRegistration,
    operation_id: str,
    execution_input_sha256: str,
    frame: bytes,
) -> dict[str, object]:
    """Validate mathematical data only. A future provider must authenticate its origin."""
    script = render_reader(context, plan, ade, reader, operation_id, execution_input_sha256)
    if len(frame) > FRAME_LIMIT:
        raise OperationRejected("reader_frame_limit")
    try:
        lines = frame.decode("ascii").splitlines()
    except UnicodeDecodeError:
        raise OperationRejected("reader_frame_invalid") from None
    if (
        not lines
        or lines[0] != _header(operation_id, plan, reader, execution_input_sha256)
        or lines[-1] != "END"
    ):
        raise OperationRejected("reader_frame_identity_or_completion_invalid")
    rows = deque(lines[1:-1])
    scalar: dict[str, float] = {}
    waves: dict[str, tuple[tuple[float, complex], ...]] = {}
    currents: dict[str, float] = {}
    try:
        for node in reader.nodes:
            if plan.analysis == "dc":
                row = rows.popleft().split("|")
                if len(row) != 3 or row[:2] != ["V", node.logical_id]:
                    raise ValueError
                scalar[node.logical_id] = _finite(row[2])
            else:
                samples: list[tuple[float, complex]] = []
                # Read a contiguous block with explicit monotonically increasing indices.
                while True:
                    row = rows.popleft().split("|")
                    if (
                        len(row) != 6
                        or row[:2] != ["P", node.logical_id]
                        or row[2] != str(len(samples))
                    ):
                        raise ValueError
                    samples.append((_finite(row[3]), complex(_finite(row[4]), _finite(row[5]))))
                    if len(samples) > reader.maximum_samples:
                        raise ValueError
                    if not rows or not rows[0].startswith("P|" + node.logical_id + "|"):
                        break
                if len(samples) < 2 or any(
                    a[0] >= b[0] for a, b in zip(samples, samples[1:], strict=False)
                ):
                    raise ValueError
                waves[node.logical_id] = tuple(samples)
        for source in reader.sources:
            row = rows.popleft().split("|")
            if len(row) != 3 or row[:2] != ["I", source.source_id]:
                raise ValueError
            currents[source.source_id] = _finite(row[2])
        if rows:
            raise ValueError
    except (ValueError, IndexError):
        raise OperationRejected("reader_frame_inventory_invalid") from None
    output: dict[str, object] = {
        "status": "BOUNDED_FRAME_VALIDATED_NATIVE_UNATTESTED",
        "operation_id": operation_id,
        "design_id": reader.design_id,
        "measurement_id": reader.measurement_id,
        "analysis": plan.analysis,
        "plan_sha256": plan.plan_sha256,
        "execution_input_sha256": execution_input_sha256,
        "reader_registration_sha256": canonical_digest(reader),
        "reader_script_sha256": hashlib.sha256(script).hexdigest(),
        "frame_sha256": hashlib.sha256(frame).hexdigest(),
        "native_provenance": "NOT_ATTESTED",
        "spec_evaluation": "not_evaluated",
        "execution_authorized": False,
        "remote_contact": False,
    }
    if plan.analysis == "dc":
        output["nodes"] = [{"logical_id": n, "value": v, "unit": "V"} for n, v in scalar.items()]
        if reader.sources:
            contributions = tuple(
                (
                    s.role,
                    (scalar[s.positive_node] if s.positive_node else 0.0)
                    - (scalar[s.negative_node] if s.negative_node else 0.0),
                    currents[s.source_id],
                )
                for s in reader.sources
            )
            totals = signed_power_totals(contributions)
            output["power"] = dict(
                zip(
                    ("supply_w", "bias_w", "stimulus_w", "all_registered_sources_w"),
                    totals,
                    strict=True,
                )
            )
            output["sources"] = [
                {
                    "source_id": s.source_id,
                    "role": role,
                    "voltage_v": v,
                    "signed_current_a": i,
                    "delivered_w": -v * i,
                }
                for s, (role, v, i) in zip(reader.sources, contributions, strict=True)
            ]
    else:
        axes = tuple(x for x, _ in next(iter(waves.values())))
        if any(tuple(x for x, _ in wave) != axes for wave in waves.values()):
            raise OperationRejected("reader_frame_axes_mismatch")
        if plan.analysis == "ac":
            output["transfer"] = _transfer(ade, reader, axes, waves)
        else:
            output["transient"] = _transient(ade, axes, waves)
    return output


def _transfer(
    ade: AdeExecutionRegistration,
    reader: GenericReaderRegistration,
    axes: tuple[float, ...],
    waves: dict[str, tuple[tuple[float, complex], ...]],
) -> list[dict[str, object]]:
    inputs = ade.inputs
    if (
        inputs.analysis != "ac"
        or axes[0] < float(inputs.start_hz)
        or axes[-1] > float(inputs.stop_hz)
    ):
        raise OperationRejected("reader_ac_interval_invalid")
    assert reader.transfer is not None
    transfer = reader.transfer
    results: list[dict[str, object]] = []
    for text in transfer.gain_frequencies_hz:
        freq = float(text)
        matches = [i for i, x in enumerate(axes) if math.isclose(x, freq, rel_tol=1e-12, abs_tol=0)]
        if len(matches) != 1:
            raise OperationRejected("reader_gain_sample_unavailable")
        i = matches[0]

        def differential(positive: str, negative: str | None, index: int) -> complex:
            return waves[positive][index][1] - (waves[negative][index][1] if negative else 0j)

        vin = differential(transfer.positive_input, transfer.negative_input, i)
        vout = differential(transfer.positive_output, transfer.negative_output, i)
        if vin == 0:
            raise OperationRejected("reader_ac_input_zero")
        value = vout / vin
        gain = abs(value)
        if not all(math.isfinite(v) for v in (value.real, value.imag, gain)):
            raise OperationRejected("reader_transfer_nonfinite")
        results.append(
            {
                "frequency_hz": axes[i],
                "input_real_v": vin.real,
                "input_imag_v": vin.imag,
                "real_v_per_v": value.real,
                "imag_v_per_v": value.imag,
                "gain_v_per_v": gain,
                "gain_db": 20 * math.log10(gain) if gain else None,
                "phase_deg": math.degrees(math.atan2(value.imag, value.real)) if gain else None,
                "method": "exact_sample_complex_output_over_measured_input",
            }
        )
    return results


def _transient(
    ade: AdeExecutionRegistration,
    axes: tuple[float, ...],
    waves: dict[str, tuple[tuple[float, complex], ...]],
) -> list[dict[str, object]]:
    inputs = ade.inputs
    if (
        inputs.analysis != "tran"
        or axes[0] != 0
        or not math.isclose(axes[-1], float(inputs.stop_s), rel_tol=1e-12)
    ):
        raise OperationRejected("reader_tran_interval_invalid")
    summaries = []
    steps = tuple(b - a for a, b in zip(axes, axes[1:], strict=False))
    for logical_id, wave in waves.items():
        if any(value.imag != 0 for _, value in wave):
            raise OperationRejected("reader_tran_complex_invalid")
        values = tuple(value.real for _, value in wave)
        mean = math.fsum(
            (a / 2 + b / 2) * dt for a, b, dt in zip(values[:-1], values[1:], steps, strict=True)
        ) / (axes[-1] - axes[0])
        if not math.isfinite(mean):
            raise OperationRejected("reader_tran_summary_nonfinite")
        summaries.append(
            {
                "logical_id": logical_id,
                "unit": "V",
                "minimum": min(values),
                "maximum": max(values),
                "first": values[0],
                "last": values[-1],
                "time_weighted_mean": mean,
                "sample_count": len(values),
                "start_s": axes[0],
                "stop_s": axes[-1],
                "minimum_step_s": min(steps),
                "maximum_step_s": max(steps),
                "method": "all_saved_samples_trapezoidal_mean_no_resampling",
            }
        )
    return summaries


def operator_reader(
    settings: Path,
    context_id: str,
    plan_path: Path,
    expected_plan_sha256: str,
    ade_path: Path,
    expected_ade_sha256: str,
    reader_path: Path,
    expected_reader_sha256: str,
    operation_id: str,
    execution_input_sha256: str,
    output: Path | None = None,
    frame_path: Path | None = None,
) -> dict[str, object]:
    from cadence_mcp_bridge.generic_ade import _read_input
    from cadence_mcp_bridge.onboarding import _local_path
    from cadence_mcp_bridge.operator_operations import bounded_document
    from cadence_mcp_bridge.runtime_context import load_runtime

    context = next((c for c in load_runtime(settings) if c.binding.context_id == context_id), None)
    if context is None:
        raise OperationRejected("unknown_context_id")
    plan = OperationPlan.model_validate_json(bounded_document(plan_path))
    if plan.plan_sha256 != expected_plan_sha256:
        raise OperationRejected("stale_operation_plan")
    ade = AdeExecutionRegistration.model_validate_json(bounded_document(ade_path))
    reader = GenericReaderRegistration.model_validate_json(bounded_document(reader_path))
    if (
        canonical_digest(ade) != expected_ade_sha256
        or canonical_digest(reader) != expected_reader_sha256
    ):
        raise OperationRejected("stale_reader_registration")
    script = render_reader(context, plan, ade, reader, operation_id, execution_input_sha256)
    if frame_path is not None:
        return project_frame(
            context,
            plan,
            ade,
            reader,
            operation_id,
            execution_input_sha256,
            _read_input(frame_path),
        )
    if output is None:
        raise OperationRejected("reader_output_required")
    manifest = {
        "status": "LOCAL_READER_PREPARED_NATIVE_UNQUALIFIED",
        "schema_version": 1,
        "operation_id": operation_id,
        "plan_sha256": plan.plan_sha256,
        "execution_input_sha256": execution_input_sha256,
        "reader_registration_sha256": canonical_digest(reader),
        "ade_registration_sha256": canonical_digest(ade),
        "reader_script_sha256": hashlib.sha256(script).hexdigest(),
        "native_provenance": "NOT_ATTESTED",
        "execution_authorized": False,
        "remote_contact": False,
        "provider_required": True,
    }
    target = _local_path(output)
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, data in (
        ("extract.ocn", script),
        ("registration.json", reader.model_dump_json().encode("ascii")),
        ("manifest.json", json.dumps(manifest, sort_keys=True).encode("ascii")),
    ):
        descriptor = os.open(target / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return manifest
