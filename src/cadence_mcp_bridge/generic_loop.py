"""Sampled return ratio of an explicitly bound ideal unilateral voltage loop.

This narrow experimental definition is not an arbitrary circuit stability solver.
"""

from __future__ import annotations

import cmath
import hashlib
import math
import re
from typing import Annotated, Any, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.generic_measurements import NodeSignal
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

Terminal = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")]
INSTANCE = re.compile(r"([A-Za-z][A-Za-z0-9_#-]*) \(([^)]+)\) ([A-Za-z][A-Za-z0-9_#-]*)(.*)")


class IdealVoltageLoopDefinition(VariableModel):
    static_statements_sha256: Digest
    static_statements: Annotated[tuple[Annotated[str, Field(max_length=2048)], ...],
                                 Field(min_length=1, max_length=256)]
    return_node: Terminal
    driven_input_node: Terminal
    fixed_input_node: Terminal
    common_node: Terminal
    output_plus_node: Terminal
    output_minus_node: Terminal
    feedback_instance: Terminal
    probe_instance: Terminal
    return_signal: LogicalId
    driven_input_signal: LogicalId
    fixed_input_signal: LogicalId
    common_signal: LogicalId
    # All independent source terminal voltages must be observed, including zero rails.
    nodes: Annotated[tuple[NodeSignal, ...], Field(min_length=4, max_length=8)]
    ac_tolerance_v: Annotated[float, Field(gt=0, le=1e-6, allow_inf_nan=False)] = 1e-9

    @model_validator(mode="after")
    def topology(self) -> Self:
        static_hash = hashlib.sha256(
            ("\n".join(self.static_statements) + "\n").encode("ascii"),
        ).hexdigest()
        if static_hash != self.static_statements_sha256:
            raise ValueError("exact effective static statements required")
        terminals = (self.return_node, self.driven_input_node, self.fixed_input_node,
                     self.common_node, self.output_plus_node, self.output_minus_node)
        if len(set(terminals)) != len(terminals):
            raise ValueError("distinct loop terminals required")
        mapping = {n.logical_id: n.selector[1:] for n in self.nodes}
        if len(mapping) != len(self.nodes) or len(set(mapping.values())) != len(mapping):
            raise ValueError("distinct loop reader mapping required")
        for logical, terminal in ((self.return_signal, self.return_node),
                                  (self.driven_input_signal, self.driven_input_node),
                                  (self.fixed_input_signal, self.fixed_input_node),
                                  (self.common_signal, self.common_node)):
            if mapping.get(logical) != terminal:
                raise ValueError("exact loop node selector binding required")
        rows = []
        for statement in self.static_statements:
            match = INSTANCE.fullmatch(statement)
            if match:
                params = dict(re.findall(r"([A-Za-z][A-Za-z0-9_#-]*)=([^\s=]+)", match[4]))
                rows.append((match[1], match[2].split(), match[3], params))
            elif re.search(r"\b" + re.escape(self.return_node) + r"\b", statement):
                raise ValueError("unrecognized return-node use")
        feedback = [r for r in rows if r[0] == self.feedback_instance]
        probe = [r for r in rows if r[0] == self.probe_instance]
        if len(feedback) != 1 or len(probe) != 1 or feedback[0][1:] != (
            [self.return_node, self.common_node, self.output_plus_node, self.output_minus_node],
            "vcvs", {"gain": "1"},
        ):
            raise ValueError("unity unilateral feedback required")
        if probe[0][1] != [self.driven_input_node, self.return_node] or (
            probe[0][2] != "vsource" or probe[0][3].get("dc") != "0"
            or probe[0][3].get("mag") != "1" or probe[0][3].get("phase") != "0"
            or set(probe[0][3]) - {"dc", "mag", "phase", "type"}
        ):
            raise ValueError("DC0 AC1 phase0 series injection required")
        incidence = [r[0] for r in rows if self.return_node in r[1]]
        if sorted(incidence) != sorted((self.feedback_instance, self.probe_instance)):
            raise ValueError("isolated return node required")
        for name, nodes, master, params in rows:
            if master == "isource":
                raise ValueError("independent current injection unsupported")
            if master != "vsource" or name == self.probe_instance:
                continue
            if len(nodes) != 2:
                raise ValueError("two voltage-source terminals required")
            # Standard-VM documented vsource mag/phase defaults are zero; actual
            # source-terminal measurements below independently check that premise.
            if params.get("mag", "0") != "0" or params.get("phase", "0") != "0":
                raise ValueError("all other independent AC sources must be zero")
            if any(node != "0" and node not in mapping.values() for node in nodes):
                raise ValueError("every independent source terminal must be saved")
        return self

    def source_terminals(self) -> list[tuple[str, str, bool]]:
        """Return bound voltage-source endpoints and the single injection role."""
        pairs = []
        for statement in self.static_statements:
            match = INSTANCE.fullmatch(statement)
            if match and match[3] == "vsource":
                nodes = match[2].split()
                if len(nodes) != 2:
                    raise OperationRejected("loop_voltage_source_terminal_count_invalid")
                pairs.append((nodes[0], nodes[1], match[1] == self.probe_instance))
        return pairs


def sampled_loop_margin(
    waves: dict[str, list[dict[str, Any]]], definition: IdealVoltageLoopDefinition,
) -> dict[str, Any]:
    """Fixed sign L=-Vreturn/Vdriven; no extrapolation or origin claim."""
    if set(waves) != {n.logical_id for n in definition.nodes}:
        raise OperationRejected("loop_complete_registered_node_inventory_required")
    axes: list[float] | None = None
    values: dict[str, list[complex]] = {}
    for name, samples in waves.items():
        try:
            frequencies = [float(s["frequency_hz"]) for s in samples]
            phasors = [complex(float(s["real_v"]), float(s["imag_v"])) for s in samples]
        except (KeyError, TypeError, ValueError, OverflowError):
            raise OperationRejected("loop_complex_samples_required") from None
        if not 4 <= len(samples) <= 256 or any(
            not math.isfinite(f) or f <= 0 for f in frequencies
        ) or any(a >= b for a, b in zip(frequencies, frequencies[1:], strict=False)) or any(
            not math.isfinite(v.real) or not math.isfinite(v.imag) for v in phasors
        ) or (axes is not None and frequencies != axes):
            raise OperationRejected("loop_complete_finite_common_axis_required")
        axes = frequencies
        values[name] = phasors
    assert axes is not None
    selector_ids = {node.selector[1:]: node.logical_id for node in definition.nodes}
    zero = [0j] * len(axes)
    for positive, negative, injected in definition.source_terminals():
        vp = zero if positive == "0" else values[selector_ids[positive]]
        vn = zero if negative == "0" else values[selector_ids[negative]]
        target = 1 if injected else 0
        if any(abs(p - n - target) > definition.ac_tolerance_v
               for p, n in zip(vp, vn, strict=True)):
            raise OperationRejected("loop_measured_series_injection_mismatch" if injected
                                    else "loop_unexcited_source_voltage_mismatch")
    # The fixed input and feedback-reference source must also be at AC ground
    # for L=-Vreturn/Vdriven. Other floating biases and extra observations may move.
    if any(abs(v) > definition.ac_tolerance_v
           for name in (definition.fixed_input_signal, definition.common_signal)
           for v in values[name]):
        raise OperationRejected("loop_fixed_input_or_reference_ac_ground_required")
    returned, driven = values[definition.return_signal], values[definition.driven_input_signal]
    if any(abs(vm - vr - 1) > definition.ac_tolerance_v
           for vm, vr in zip(driven, returned, strict=True)):
        raise OperationRejected("loop_measured_series_injection_mismatch")
    if any(abs(v) == 0 for v in driven):
        raise OperationRejected("loop_zero_driven_voltage")
    ratios = [-vr / vm for vr, vm in zip(returned, driven, strict=True)]
    if any(not math.isfinite(z.real) or not math.isfinite(z.imag)
           or not math.isfinite(abs(z)) or abs(z) == 0 for z in ratios):
        raise OperationRejected("loop_nonfinite_or_zero_return_ratio")
    db = [20 * math.log10(abs(z)) for z in ratios]
    raw_phase = [math.degrees(cmath.phase(z)) for z in ratios]
    phase = [raw_phase[0]]
    ambiguous = False
    for previous, current in zip(raw_phase, raw_phase[1:], strict=False):
        delta = (current - previous + 180) % 360 - 180
        ambiguous |= abs(delta) >= 90
        phase.append(phase[-1] + delta)
    crossings = []
    for i in range(1, len(axes)):
        if (db[i - 1] > 0 >= db[i]) or (db[i - 1] < 0 <= db[i]):
            weight = -db[i - 1] / (db[i] - db[i - 1])
            frequency = 10 ** ((1 - weight) * math.log10(axes[i - 1])
                              + weight * math.log10(axes[i]))
            angle = (1 - weight) * phase[i - 1] + weight * phase[i]
            crossings.append({"frequency_hz": frequency, "phase_deg": angle,
                              "margin_deg": 180 + angle, "bracket_hz": axes[i - 1:i + 1],
                              "direction": "descending" if db[i] < db[i - 1] else "ascending"})
    underresolved = any(math.log10(b / a) > .15
                        for a, b in zip(axes, axes[1:], strict=False))
    eligible = (db[0] > 0 > db[-1] and abs(phase[0]) < 45 and not ambiguous
                and not underresolved and len(crossings) == 1
                and crossings[0]["direction"] == "descending" and all(v != 0 for v in db))
    return {
        "status": "OBSERVED_SINGLE_SAMPLED_MARGIN" if eligible else "UNQUALIFIED_SAMPLED_LOOP",
        "value": crossings[0]["margin_deg"] if eligible else None, "unit": "deg",
        "definition_sha256": canonical_digest(definition), "crossings": crossings,
        "sample_count": len(axes), "start_hz": axes[0], "stop_hz": axes[-1],
        "loop_ratio": [{"frequency_hz": f, "real_v_per_v": z.real, "imag_v_per_v": z.imag,
                        "gain_db": g, "unwrapped_phase_deg": p}
                       for f, z, g, p in zip(axes, ratios, db, phase, strict=True)],
        "phase_unwrap_ambiguous": ambiguous, "grid_underresolved": underresolved,
        "sign": "L=-Vreturn/Vdriven; Vm-Vreturn=1+0j",
        "qualification": ("IDEAL_UNILATERAL_DIFFERENTIAL_QA_LOOP_SAMPLED_ONLY_"
                          "NO_WHOLE_CIRCUIT_STABILITY"),
        "native_provenance": "NOT_ATTESTED",
    }
