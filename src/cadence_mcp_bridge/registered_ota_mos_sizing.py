"""Verify a single-axis edit of one MOS in the registered 17-device OTA."""

from __future__ import annotations

import re
from decimal import localcontext
from typing import Annotated, Literal, Self, cast

from pydantic import Field, model_validator

from cadence_mcp_bridge._native_rendering import partition_input
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.parameter_changes import mos_multiplicity_factors
from cadence_mcp_bridge.registered_mos_edit import MosProperty, MosPropertyValue
from cadence_mcp_bridge.registered_mos_sizing import (
    _NETLIST_KEYS,
    MosSizingDimensions,
    MosSizingLength,
    MosSizingPlan,
    RegisteredMosSizingRoute,
    RegisteredMosSizingService,
    _check_input,
    _engineering,
    _NetlistControls,
    _observed_dimensions,
)
from cadence_mcp_bridge.variable_contracts import BindingName, Digest, VariableModel

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
    netlist_receipt_sha256: Digest
    baseline_dc_op_receipt_sha256: Digest
    baseline_ac_receipt_sha256: Digest
    symbol_tree_sha256: Digest
    ade_state_tree_sha256: Digest
    dut_instance: BindingName
    devices: Annotated[tuple[OtaMosInstance, ...], Field(min_length=17, max_length=17)]

    @model_validator(mode="after")
    def independent_receipts(self) -> Self:
        if (
            len({row.name for row in self.devices}) != 17
            or len(
                {
                    self.reopen_receipt_sha256,
                    self.netlist_receipt_sha256,
                    self.baseline_dc_op_receipt_sha256,
                    self.baseline_ac_receipt_sha256,
                }
            )
            != 4
        ):
            raise ValueError("OTA baseline devices and phase receipts must be distinct")
        return self


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
        fixed = _ota_fixed_statements(route, self.plan, raw)
        return controls, fixed, options


def _check_ota_plan(route: RegisteredOtaMosSizingRoute, plan: MosSizingPlan) -> None:
    axis = route.target.instance.property_name
    if (
        plan.changed != (axis,)
        or plan.requested.m is not None
        or (plan.requested.w is None) == (plan.requested.l is None)
    ):
        raise ValueError("OTA sizing request must change only the registered W/L axis")


def _ota_fixed_statements(
    route: RegisteredOtaMosSizingRoute, plan: MosSizingPlan, raw: bytes
) -> list[str]:
    """Permit only device order and numeric spelling inside the registered OTA block."""
    _, _, _, static = partition_input(raw)  # type: ignore[no-untyped-call]
    statements = cast(list[str], static)
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
        with localcontext() as context:
            context.prec = 128
            unchanged = sorted(
                (key, str(value.normalize()))
                for key, value in numbers.items()
                if name != target or key not in permitted
            )
        fixed.append(f"{name} ({nodes}) {model} {count} {unchanged}")
    return statements[:start] + sorted(fixed) + statements[end:]
