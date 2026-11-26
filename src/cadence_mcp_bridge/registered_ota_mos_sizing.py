"""Verify a single-axis edit of one MOS in the registered 17-device OTA."""

from __future__ import annotations

import re
from decimal import localcontext
from typing import Annotated, Literal, Self, cast

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from cadence_mcp_bridge._native_rendering import statements as netlist_statements
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.ota_reopen_evidence import parse_ota_reopen_properties
from cadence_mcp_bridge.parameter_changes import _checked, mos_multiplicity_factors
from cadence_mcp_bridge.registered_mos_edit import (
    _GEOMETRY,
    MosProperty,
    MosPropertyValue,
    RegisteredMosEditBinding,
    RegisteredMosEditProvider,
)
from cadence_mcp_bridge.registered_mos_sizing import (
    _NETLIST_KEYS,
    MosSizingDimensions,
    MosSizingLength,
    MosSizingPlan,
    MosSizingValues,
    RegisteredMosSizingRoute,
    RegisteredMosSizingService,
    _check_input,
    _engineering,
    _NetlistControls,
    _observed_dimensions,
)
from cadence_mcp_bridge.research_circuit import MosBlockStageReceipt
from cadence_mcp_bridge.research_generation_ota_recovery import RecoveredOtaGenerationAnalysisSource
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    VariableModel,
    canonical_digest,
)

_SPECTRE_MOS = re.compile(r"([^ ]+) \(([^()]+)\) (gpdk090_[np]mos1v) (.+)")


class OtaMosInstance(VariableModel):
    """One row of independent baseline OA/CDF readback, ordered D/G/S/B."""

    name: BindingName
    master_cell: Literal["nmos1v", "pmos1v"]
    terminals: tuple[str, str, str, str]
    dimensions: MosSizingDimensions
    finger_width: MosSizingLength
    fingers: Literal[1]

    @model_validator(mode="after")
    def single_finger(self) -> Self:
        if self.dimensions.m is None or self.finger_width.in_nm() != self.dimensions.w.in_nm():
            raise ValueError("OTA requires an observed multiplier and equal single-finger W/FW")
        return self


class OtaMosBaseline(VariableModel):
    """Operator-pinned provenance and readback from the generated OTA baseline."""

    generation_operation_id: OperationId
    reopen_receipt_sha256: Digest
    reopen_stdout_sha256: Digest
    dut_plan_sha256: Digest
    netlist_receipt_sha256: Digest | None = None
    recovered_source_sha256: Digest | None = None
    baseline_dc_op_receipt_sha256: Digest
    baseline_ac_receipt_sha256: Digest
    symbol_tree_sha256: Digest
    ade_state_tree_sha256: Digest
    dut_instance: BindingName
    devices: Annotated[tuple[OtaMosInstance, ...], Field(min_length=17, max_length=17)]

    @model_validator(mode="after")
    def independent_receipts(self) -> Self:
        if (self.netlist_receipt_sha256 is None) == (self.recovered_source_sha256 is None):
            raise ValueError("OTA baseline requires exactly one native or recovered Netlist source")
        if (
            len({row.name for row in self.devices}) != 17
            or len(
                {
                    self.reopen_receipt_sha256,
                    self.netlist_receipt_sha256 or self.recovered_source_sha256,
                    self.baseline_dc_op_receipt_sha256,
                    self.baseline_ac_receipt_sha256,
                }
            )
            != 4
        ):
            raise ValueError("OTA baseline devices and phase receipts must be distinct")
        return self

    @model_serializer(mode="wrap")
    def omit_absent_netlist_evidence(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        for name in ("netlist_receipt_sha256", "recovered_source_sha256"):
            if result.get(name) is None:
                result.pop(name, None)
        return result


class RegisteredOtaMosSizingRoute(RegisteredMosSizingRoute):
    ota: OtaMosBaseline

    @model_validator(mode="after")
    def measured_target(self) -> Self:
        target, support = self.target, self.support
        axis = target.instance.property_name
        if (
            support.lifecycle != "headless_wlm_v1"
            or support.m is not None
            or (axis == "w" and (support.w is None or support.l is not None))
            or (axis == "l" and (support.l is None or support.w is not None))
            or axis not in ("w", "l")
            or self.testbench_cell == self.source_cell
        ):
            raise ValueError("OTA route admits one W/L axis on one nested single-finger MOS")
        dut, _, instance = target.netlist_path.partition("/")
        row = next((row for row in self.ota.devices if row.name == instance), None)
        observed = _observed_dimensions(self.before, include_m=True)
        if (
            dut != self.ota.dut_instance
            or row is None
            or (
                target.instance.master_cell,
                target.netlist_terminals,
                observed.w,
                observed.l,
                observed.m,
            )
            != (
                row.master_cell,
                row.terminals,
                row.dimensions.w.in_nm(),
                row.dimensions.l.in_nm(),
                row.dimensions.m,
            )
        ):
            raise ValueError("OTA target differs from the independently reopened baseline")
        return self


class RegisteredOtaMosSizingService(RegisteredMosSizingService):
    """Use the same durable edit protocol with an OTA-specific Netlist projection."""

    def __init__(
        self,
        binding: RegisteredMosEditBinding,
        route: RegisteredOtaMosSizingRoute,
        child: RevisionBinding,
        requested: MosSizingValues,
        baseline_input: bytes,
        provider: RegisteredMosEditProvider,
        *,
        expected_binding_sha256: str,
        baseline_reopen_stdout: bytes,
        baseline_recovery: RecoveredOtaGenerationAnalysisSource | None = None,
        baseline_reopen_receipt: MosBlockStageReceipt | None = None,
    ) -> None:
        route = _checked(route)
        ota = route.ota
        if ota.recovered_source_sha256 is not None:
            if baseline_recovery is None or baseline_reopen_receipt is None:
                raise ValueError("OTA recovery requires the verified source and original reopen")
            verify_ota_recovered_generation(route, baseline_recovery, baseline_reopen_receipt)
        elif baseline_recovery is not None or baseline_reopen_receipt is not None:
            raise ValueError("unexpected recovery evidence on a native OTA baseline")
        self._baseline_properties = parse_ota_reopen_properties(
            baseline_reopen_stdout,
            stdout_sha256=ota.reopen_stdout_sha256,
            plan_sha256=ota.dut_plan_sha256,
            cell=route.source_cell,
            instance_names=tuple(device.name for device in ota.devices),
        )
        target_name = route.target.netlist_path.split("/")[1]
        if route.before != self._baseline_properties[target_name]:
            raise ValueError("OTA registered target differs from original detached OA/CDF readback")
        for row in ota.devices:
            props = self._baseline_properties[row.name]
            dimensions = _observed_dimensions(props, include_m=True)
            if (dimensions.w, dimensions.l, dimensions.m, props["model"].cdf_value) != (
                row.dimensions.w.in_nm(),
                row.dimensions.l.in_nm(),
                row.dimensions.m,
                f"gpdk090_{row.master_cell}",
            ):
                raise ValueError("OTA device differs from original detached OA/CDF readback")
        super().__init__(
            binding,
            route,
            child,
            requested,
            baseline_input,
            provider,
            expected_binding_sha256=expected_binding_sha256,
        )

    def _project_input(
        self, raw: bytes, properties: dict[MosProperty, MosPropertyValue]
    ) -> tuple[_NetlistControls, list[str], dict[str, str]]:
        route = self._route
        if not isinstance(route, RegisteredOtaMosSizingRoute):
            raise ValueError("OTA sizing requires its separately registered baseline")
        _check_ota_plan(route, self.plan)
        if route.ota.generation_operation_id in (
            self._binding.operation_id,
            self._binding.owned_copy_operation_id,
        ):
            raise ValueError("OTA sizing operation and copy must be distinct from generation")
        controls, _, options = _check_input(route.target, raw, properties)
        fixed = _ota_fixed_statements(route, self.plan, raw, self._baseline_properties)
        return controls, fixed, options


def verify_ota_recovered_generation(
    route: RegisteredOtaMosSizingRoute,
    source: RecoveredOtaGenerationAnalysisSource,
    reopen: MosBlockStageReceipt,
) -> None:
    """Join a separately verified recovery export to the original detached reopen."""
    source = RecoveredOtaGenerationAnalysisSource.model_validate_json(source.model_dump_json())
    reopen = _checked(reopen)
    ota, baseline = route.ota, route.baseline
    if (
        ota.recovered_source_sha256 != canonical_digest(source)
        or ota.reopen_receipt_sha256 != canonical_digest(reopen)
        or source.reopen_receipt_sha256 != ota.reopen_receipt_sha256
        or source.operation_id != ota.generation_operation_id
        or (source.dut_plan_sha256, source.reopen_stdout_sha256, source.symbol_tree_sha256)
        != (ota.dut_plan_sha256, ota.reopen_stdout_sha256, ota.symbol_tree_sha256)
        or (reopen.phase, reopen.operation_id, reopen.plan_sha256, reopen.artifact_sha256)
        != ("reopen", ota.generation_operation_id, ota.dut_plan_sha256, ota.reopen_stdout_sha256)
        or source.library != reopen.library
        or reopen.library.name != route.source_library
        or reopen.source_cell != f"{reopen.library.path}/{route.source_cell}"
        or reopen.bench_cell != f"{reopen.library.path}/{route.testbench_cell}"
        or (source.dut_cell, source.dut_tree_sha256)
        != (reopen.source_cell, reopen.source_tree_sha256)
        or reopen.source_tree_sha256 != baseline.revision_sha256
        or (source.source_cell, source.source_tree_sha256)
        != (reopen.bench_cell, reopen.bench_tree_sha256)
        or reopen.bench_tree_sha256 != baseline.testbench_revision_sha256
        or source.full_netlist_sha256 != baseline.netlist_sha256
        or source.conditions_sha256 != baseline.fixed_conditions_sha256
        or source.ade_state_tree_sha256 != ota.ade_state_tree_sha256
    ):
        raise ValueError("OTA recovery differs from the original source, reopen or conditions")


def _check_ota_plan(route: RegisteredOtaMosSizingRoute, plan: MosSizingPlan) -> None:
    axis = route.target.instance.property_name
    if (
        plan.changed != (axis,)
        or plan.requested.m is not None
        or (plan.requested.w is None) == (plan.requested.l is None)
    ):
        raise ValueError("OTA sizing request must change only the registered W/L axis")


def _ota_fixed_statements(
    route: RegisteredOtaMosSizingRoute,
    plan: MosSizingPlan,
    raw: bytes,
    baseline_properties: dict[str, dict[MosProperty, MosPropertyValue]],
) -> list[str]:
    """Project the registered OTA devices and the two observed bench orders."""
    statements = cast(list[str], netlist_statements(raw))  # type: ignore[no-untyped-call]
    benches = [line for line in statements if line.startswith(route.ota.dut_instance + " ")]
    if len(benches) != 1 or not benches[0].endswith(" " + route.source_cell):
        raise ValueError("OTA Netlist bench does not reference the registered DUT")
    starts = [
        idx
        for idx, line in enumerate(statements)
        if line.split()[:2] == ["subckt", route.source_cell]
    ]
    if len(starts) != 1:
        raise ValueError("OTA Netlist requires one registered DUT definition")
    start = starts[0] + 1
    end = start + 17
    if end >= len(statements) or statements[end] not in ("ends", f"ends {route.source_cell}"):
        raise ValueError("OTA Netlist requires a contiguous block of seventeen MOS instances")
    devices = {device.name: device for device in route.ota.devices}
    target = route.target.netlist_path.split("/")[1]
    permitted = set(plan.changed).union(plan.allowed_derived)
    fixed: list[str] = []
    for line in statements[start:end]:
        match = _SPECTRE_MOS.fullmatch(line)
        if match is None:
            raise ValueError("unsupported statement inside the registered OTA DUT")
        name, nodes, model, raw_options = match.groups()
        device = devices.pop(name, None)
        if device is None or (tuple(nodes.split()), model) != (
            device.terminals,
            f"gpdk090_{device.master_cell}",
        ):
            raise ValueError("OTA Netlist differs from the observed device model or terminals")
        pairs = [token.split("=", 1) for token in raw_options.split()]
        if any(len(pair) != 2 for pair in pairs):
            raise ValueError("invalid OTA MOS option")
        options = dict(pairs)
        if options.keys() != _NETLIST_KEYS or len(options) != len(pairs):
            raise ValueError("unexpected, duplicate or missing OTA MOS option")
        count = (str(device.dimensions.m), str(device.fingers))
        if any(mos_multiplicity_factors(options[key]) != count for key in ("m", "simM")):
            raise ValueError("OTA Netlist changed a multiplier or finger factor")
        numbers = {
            key: _engineering(value) for key, value in options.items() if key not in {"m", "simM"}
        }
        for axis, length in (("w", device.dimensions.w), ("l", device.dimensions.l)):
            if (name != target or axis not in permitted) and numbers[axis] != _engineering(
                f"{length.in_nm().value}n"
            ):
                raise ValueError("OTA Netlist differs from a held W/L dimension")
        if name != target and any(
            numbers[key] != _engineering(baseline_properties[name][key].cdf_value)
            for key in _GEOMETRY
        ):
            raise ValueError("OTA Netlist changed a sibling junction geometry")
        with localcontext() as context:
            context.prec = 128
            unchanged = sorted(
                (key, str(value.normalize()))
                for key, value in numbers.items()
                if name != target or key not in permitted
            )
        fixed.append(f"{name} ({nodes}) {model} {count} {unchanged}")
    bench = statements[end:]
    if route.baseline.revision.design_id == "ota17-baseline" and route.ota.dut_instance == "DUT":
        bench = _project_ota_bench_order(bench)
    return statements[:start] + sorted(fixed) + bench


def _project_ota_bench_order(after_dut: list[str]) -> list[str]:
    """Compare the observed HNL DUT-last variant to the original DUT-first block."""
    dut_last = ("VSUP", "VINN", "VINP", "CL", "DUT")
    block = after_dut[1:6]
    if (
        len(after_dut) > 6
        and tuple(line.split(" ", 1)[0] for line in block) == dut_last
        and after_dut[6].startswith("simulatorOptions options ")
        and not any(line.split(" ", 1)[0] in dut_last for line in after_dut[6:])
    ):
        # Preserve the complete statement bytes in the projected comparison.
        return after_dut[:1] + block[-1:] + block[:-1] + after_dut[6:]
    return after_dut
