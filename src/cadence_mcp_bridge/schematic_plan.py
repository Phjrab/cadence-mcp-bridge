"""Local, bounded logical inverter plans; no OA writer or execution authority.

The fixture's numeric/device meanings are synthetic. Nothing here establishes
production PDK/CDF, ERC, LVS, or permission to create a Cadence cellview.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal, Self, cast

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.variable_contracts import (
    Digest,
    LogicalId,
    NumberText,
    VariableModel,
    canonical_digest,
    number_text,
)

ParameterUnit = Literal["m", "um", "V", "F", "1"]
CircuitRole = Literal["dut", "testbench"]
NetRole = Literal["supply", "return", "input", "output", "internal"]
PinRole = Literal["supply", "return", "input", "output"]
EntityKind = Literal["registry", "circuit", "net", "pin", "instance", "dut-reference"]


def _unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


class RevisionBinding(VariableModel):
    workspace_id: LogicalId
    design_id: LogicalId
    revision_id: LogicalId
    parent_revision_id: LogicalId | None = None
    parent_revision_sha256: Digest | None = None
    source_baseline_sha256: Digest

    @model_validator(mode="after")
    def parent_pair(self) -> Self:
        if (self.parent_revision_id is None) != (self.parent_revision_sha256 is None):
            raise ValueError("parent revision ID and digest must occur together")
        if self.parent_revision_id == self.revision_id:
            raise ValueError("revision cannot parent itself")
        return self


class ParameterSpec(VariableModel):
    parameter_id: LogicalId
    unit: ParameterUnit
    value_type: Literal["real", "integer"] = "real"
    minimum: NumberText
    maximum: NumberText

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def canonical_number(cls, value: Any) -> str:
        return number_text(value)

    @model_validator(mode="after")
    def bounds(self) -> Self:
        lower, upper = Decimal(self.minimum), Decimal(self.maximum)
        if lower > upper:
            raise ValueError("minimum exceeds maximum")
        if self.value_type == "integer" and any(
            value != value.to_integral_value() for value in (lower, upper)
        ):
            raise ValueError("integer parameter needs integral bounds")
        return self


class DeviceRegistration(VariableModel):
    device_id: LogicalId
    kind: Literal["nmos", "pmos", "dc-source", "capacitor"]
    terminals: Annotated[tuple[LogicalId, ...], Field(min_length=2, max_length=4)]
    parameters: Annotated[tuple[ParameterSpec, ...], Field(max_length=8)]

    @model_validator(mode="after")
    def registration(self) -> Self:
        _unique(self.terminals, "registered terminal")
        _unique(tuple(item.parameter_id for item in self.parameters), "registered parameter")
        expected = {"d", "g", "s", "b"} if self.kind in ("nmos", "pmos") else {"p", "n"}
        if set(self.terminals) != expected:
            raise ValueError("device terminal set does not match the bounded logical kind")
        return self


class DeviceRegistry(VariableModel):
    schema_version: Literal[1] = 1
    registry_id: LogicalId
    provenance: Literal["synthetic_fixture", "production_cdf_unverified"]
    devices: Annotated[tuple[DeviceRegistration, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode="after")
    def registry(self) -> Self:
        _unique(tuple(device.device_id for device in self.devices), "device ID")
        if self.provenance == "production_cdf_unverified" and any(
            device.parameters for device in self.devices
        ):
            raise ValueError("unverified production CDF cannot acquire synthetic parameter bounds")
        return self

    @property
    def semantic_sha256(self) -> str:
        devices = tuple(
            device.model_copy(
                update={
                    "terminals": tuple(sorted(device.terminals)),
                    "parameters": tuple(
                        sorted(device.parameters, key=lambda item: item.parameter_id)
                    ),
                }
            )
            for device in sorted(self.devices, key=lambda item: item.device_id)
        )
        return canonical_digest(self.model_copy(update={"devices": devices}))


class ParameterValue(VariableModel):
    parameter_id: LogicalId
    unit: ParameterUnit
    value: NumberText

    @field_validator("value", mode="before")
    @classmethod
    def canonical_number(cls, value: Any) -> str:
        return number_text(value)


class TerminalConnection(VariableModel):
    terminal_id: LogicalId
    net_id: LogicalId


class Instance(VariableModel):
    instance_id: LogicalId
    device_id: LogicalId
    parameters: Annotated[tuple[ParameterValue, ...], Field(max_length=8)]
    connections: Annotated[tuple[TerminalConnection, ...], Field(min_length=2, max_length=4)]

    @model_validator(mode="after")
    def no_duplicates(self) -> Self:
        _unique(tuple(item.parameter_id for item in self.parameters), "instance parameter")
        _unique(tuple(item.terminal_id for item in self.connections), "instance terminal")
        return self


class Net(VariableModel):
    net_id: LogicalId
    role: NetRole


class Pin(VariableModel):
    pin_id: LogicalId
    net_id: LogicalId
    role: PinRole


class DutReference(VariableModel):
    instance_id: LogicalId
    dut_circuit_id: LogicalId
    connections: Annotated[tuple[TerminalConnection, ...], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def no_duplicates(self) -> Self:
        _unique(tuple(item.terminal_id for item in self.connections), "DUT port")
        return self


class CircuitPlan(VariableModel):
    circuit_id: LogicalId
    role: CircuitRole
    nets: Annotated[tuple[Net, ...], Field(min_length=4, max_length=8)]
    pins: Annotated[tuple[Pin, ...], Field(min_length=4, max_length=4)]
    instances: Annotated[tuple[Instance, ...], Field(min_length=2, max_length=8)]
    dut_reference: DutReference | None = None

    @model_validator(mode="after")
    def identities(self) -> Self:
        _unique(tuple(item.net_id for item in self.nets), "net ID")
        _unique(tuple(item.pin_id for item in self.pins), "pin ID")
        instance_ids = tuple(item.instance_id for item in self.instances)
        if self.dut_reference is not None:
            instance_ids += (self.dut_reference.instance_id,)
        _unique(instance_ids, "instance ID")
        if (self.role == "testbench") != (self.dut_reference is not None):
            raise ValueError("only testbench requires a DUT reference")
        if {pin.role for pin in self.pins} != {"supply", "return", "input", "output"}:
            raise ValueError("exactly one supply, return, input and output pin required")
        if len({pin.net_id for pin in self.pins}) != 4:
            raise ValueError("conflicting pin nets")
        nets = {net.net_id: net for net in self.nets}
        for pin in self.pins:
            if pin.net_id not in nets or nets[pin.net_id].role != pin.role:
                raise ValueError("pin must bind an existing net with matching electrical role")
        return self


class DisplayPoint(VariableModel):
    x: Annotated[int, Field(ge=-100000, le=100000)]
    y: Annotated[int, Field(ge=-100000, le=100000)]


class DisplayWire(VariableModel):
    """Presentation intent only; coordinates never join electrical terminals."""

    wire_id: LogicalId
    circuit_id: LogicalId
    net_id: LogicalId
    points: Annotated[tuple[DisplayPoint, ...], Field(min_length=2, max_length=16)]


class SchematicPlan(VariableModel):
    schema_version: Literal[1] = 1
    topology: Literal["bounded-cmos-inverter-v1"] = "bounded-cmos-inverter-v1"
    binding: RevisionBinding
    registry_sha256: Digest
    dut: CircuitPlan
    testbench: CircuitPlan
    display: Annotated[tuple[DisplayWire, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def circuit_roles(self) -> Self:
        if self.dut.role != "dut" or self.testbench.role != "testbench":
            raise ValueError("DUT and testbench roles are distinct")
        if self.dut.circuit_id == self.testbench.circuit_id:
            raise ValueError("duplicate circuit ID")
        _unique(tuple(wire.wire_id for wire in self.display), "display wire ID")
        circuits = {self.dut.circuit_id: self.dut, self.testbench.circuit_id: self.testbench}
        for wire in self.display:
            if wire.circuit_id not in circuits or wire.net_id not in {
                net.net_id for net in circuits[wire.circuit_id].nets
            }:
                raise ValueError("display wire must name an existing circuit and net")
        return self

    @property
    def semantic_sha256(self) -> str:
        return canonical_digest(_semantic(self))

    @property
    def plan_sha256(self) -> str:
        return canonical_digest(
            self.model_copy(
                update={
                    "dut": _canonical_circuit(self.dut),
                    "testbench": _canonical_circuit(self.testbench),
                    "display": tuple(sorted(self.display, key=lambda wire: wire.wire_id)),
                }
            )
        )


def _canonical_circuit(circuit: CircuitPlan) -> CircuitPlan:
    instances = tuple(
        item.model_copy(
            update={
                "parameters": tuple(sorted(item.parameters, key=lambda value: value.parameter_id)),
                "connections": tuple(sorted(item.connections, key=lambda value: value.terminal_id)),
            }
        )
        for item in sorted(circuit.instances, key=lambda value: value.instance_id)
    )
    reference = circuit.dut_reference
    if reference is not None:
        reference = reference.model_copy(
            update={
                "connections": tuple(
                    sorted(reference.connections, key=lambda value: value.terminal_id)
                )
            }
        )
    return circuit.model_copy(
        update={
            "nets": tuple(sorted(circuit.nets, key=lambda value: value.net_id)),
            "pins": tuple(sorted(circuit.pins, key=lambda value: value.pin_id)),
            "instances": instances,
            "dut_reference": reference,
        }
    )


class _SemanticPlan(VariableModel):
    topology: Literal["bounded-cmos-inverter-v1"]
    registry_sha256: Digest
    dut: CircuitPlan
    testbench: CircuitPlan


def _semantic(plan: SchematicPlan) -> _SemanticPlan:
    return _SemanticPlan(
        topology=plan.topology,
        registry_sha256=plan.registry_sha256,
        dut=_canonical_circuit(plan.dut),
        testbench=_canonical_circuit(plan.testbench),
    )


class SemanticChange(VariableModel):
    kind: EntityKind
    circuit_id: LogicalId | None
    entity_id: LogicalId
    change: Literal["added", "removed", "changed"]
    before_sha256: Digest | None
    after_sha256: Digest | None


class PlanDryRun(VariableModel):
    schema_version: Literal[1] = 1
    binding: RevisionBinding
    plan_sha256: Digest
    semantic_sha256: Digest
    registry_sha256: Digest
    display_sha256: Digest
    status: Literal["LOCAL_SYNTHETIC_PLAN_VALID", "BLOCKED_PRODUCTION_CDF_UNVERIFIED"]
    semantic_diff: tuple[SemanticChange, ...]
    electrical_validation: Literal["bounded_inverter_rules_only"] = "bounded_inverter_rules_only"
    execution_authorized: Literal[False] = False
    oa_created: Literal[False] = False
    erc_status: Literal["NOT_RUN"] = "NOT_RUN"
    lvs_status: Literal["NOT_RUN"] = "NOT_RUN"


class _Display(VariableModel):
    wires: tuple[DisplayWire, ...]


def _check_devices(circuit: CircuitPlan, registry: DeviceRegistry) -> dict[str, Instance]:
    registered = {device.device_id: device for device in registry.devices}
    nets = {net.net_id for net in circuit.nets}
    kinds: dict[str, Instance] = {}
    for instance in circuit.instances:
        device = registered.get(instance.device_id)
        if device is None:
            raise ValueError("unregistered device ID")
        if device.kind in kinds:
            raise ValueError("bounded inverter plan permits only one instance of each device kind")
        kinds[device.kind] = instance
        if {item.terminal_id for item in instance.connections} != set(device.terminals):
            raise ValueError("unknown or missing device terminal")
        if any(item.net_id not in nets for item in instance.connections):
            raise ValueError("connection references unknown electrical net")
        values = {item.parameter_id: item for item in instance.parameters}
        specs = {item.parameter_id: item for item in device.parameters}
        if set(values) != set(specs):
            raise ValueError("unknown or missing device parameter")
        for parameter_id, value in values.items():
            spec = specs[parameter_id]
            if value.unit != spec.unit:
                raise ValueError("parameter unit mismatch")
            number = Decimal(value.value)
            if not Decimal(spec.minimum) <= number <= Decimal(spec.maximum):
                raise ValueError("parameter outside registered range")
            if spec.value_type == "integer" and number != number.to_integral_value():
                raise ValueError("nonintegral parameter")
    return kinds


def _connections(instance: Instance | DutReference) -> dict[str, str]:
    return {item.terminal_id: item.net_id for item in instance.connections}


def _check_inverter(plan: SchematicPlan, registry: DeviceRegistry) -> None:
    dut = _check_devices(plan.dut, registry)
    bench = _check_devices(plan.testbench, registry)
    if set(dut) != {"nmos", "pmos"} or set(bench) != {"dc-source", "capacitor"}:
        raise ValueError("bounded topology requires complementary DUT and source/load testbench")
    pins: dict[str, str] = {pin.role: pin.net_id for pin in plan.dut.pins}
    for kind, rail in (("nmos", "return"), ("pmos", "supply")):
        if _connections(dut[kind]) != {
            "d": pins["output"],
            "g": pins["input"],
            "s": pins[rail],
            "b": pins[rail],
        }:
            raise ValueError("inverter terminal wiring rule violated")
    reference = plan.testbench.dut_reference
    if reference is None or reference.dut_circuit_id != plan.dut.circuit_id:
        raise ValueError("testbench must reference this plan's DUT")
    bench_pins = {pin.role: pin.net_id for pin in plan.testbench.pins}
    if _connections(reference) != {pin.pin_id: bench_pins[pin.role] for pin in plan.dut.pins}:
        raise ValueError("testbench DUT port wiring mismatch")
    if _connections(bench["dc-source"]) != {"p": bench_pins["supply"], "n": bench_pins["return"]}:
        raise ValueError("testbench supply source wiring rule violated")
    if _connections(bench["capacitor"]) != {"p": bench_pins["output"], "n": bench_pins["return"]}:
        raise ValueError("testbench load wiring rule violated")
    for circuit in (plan.dut, plan.testbench):
        used = {pin.net_id for pin in circuit.pins}
        used.update(item.net_id for inst in circuit.instances for item in inst.connections)
        if used != {net.net_id for net in circuit.nets}:
            raise ValueError("unused electrical net")


def _entities(plan: SchematicPlan) -> dict[tuple[str, str | None, str], str]:
    result: dict[tuple[str, str | None, str], str] = {
        ("registry", None, "device-registry"): plan.registry_sha256
    }
    for circuit in (_canonical_circuit(plan.dut), _canonical_circuit(plan.testbench)):
        # Circuit identity/role has its own digest; child changes are listed once.
        result[("circuit", circuit.circuit_id, circuit.circuit_id)] = canonical_digest(
            _CircuitIdentity(circuit_id=circuit.circuit_id, role=circuit.role)
        )
        for kind, entities in (
            ("net", circuit.nets),
            ("pin", circuit.pins),
            ("instance", circuit.instances),
        ):
            for item in entities:
                identifier = getattr(item, f"{kind}_id")
                result[(kind, circuit.circuit_id, identifier)] = canonical_digest(item)
        if circuit.dut_reference is not None:
            item_ref = circuit.dut_reference
            result[("dut-reference", circuit.circuit_id, item_ref.instance_id)] = canonical_digest(
                item_ref
            )
    return result


class _CircuitIdentity(VariableModel):
    circuit_id: LogicalId
    role: CircuitRole


def semantic_diff(before: SchematicPlan | None, after: SchematicPlan) -> tuple[SemanticChange, ...]:
    old = {} if before is None else _entities(before)
    new = _entities(after)
    changes = []
    for key in sorted(old.keys() | new.keys(), key=lambda item: (item[0], item[1] or "", item[2])):
        if old.get(key) != new.get(key):
            changes.append(
                SemanticChange(
                    kind=cast(EntityKind, key[0]),
                    circuit_id=key[1],
                    entity_id=key[2],
                    change="added"
                    if key not in old
                    else "removed"
                    if key not in new
                    else "changed",
                    before_sha256=old.get(key),
                    after_sha256=new.get(key),
                )
            )
    return tuple(changes)


def dry_run_plan(
    plan: SchematicPlan,
    registry: DeviceRegistry,
    expected_binding: RevisionBinding,
    baseline: SchematicPlan | None = None,
) -> PlanDryRun:
    """Validate a plan against independently resolved revision/registry bindings.

    A supplied parent plan is a semantic-diff input, never execution approval.
    This function neither reads nor writes files and never contacts Cadence.
    """
    # Validate again at this trust boundary: frozen pydantic model_copy/update
    # deliberately bypasses validation and must not create accepted fake plans.
    plan = SchematicPlan.model_validate_json(plan.model_dump_json())
    registry = DeviceRegistry.model_validate_json(registry.model_dump_json())
    expected_binding = RevisionBinding.model_validate_json(expected_binding.model_dump_json())
    if plan.binding != expected_binding:
        raise ValueError("target revision, parent or source baseline binding mismatch")
    if plan.registry_sha256 != registry.semantic_sha256:
        raise ValueError("registry digest mismatch")
    if plan.binding.parent_revision_id is not None and baseline is None:
        raise ValueError("child plan requires the bound parent plan for semantic diff")
    if baseline is not None:
        baseline = SchematicPlan.model_validate_json(baseline.model_dump_json())
        if (
            baseline.binding.workspace_id != plan.binding.workspace_id
            or baseline.binding.design_id != plan.binding.design_id
            or baseline.binding.revision_id != plan.binding.parent_revision_id
            or baseline.binding.source_baseline_sha256 != plan.binding.source_baseline_sha256
        ):
            raise ValueError("parent plan or source baseline mismatch")
    _check_inverter(plan, registry)
    return PlanDryRun(
        binding=plan.binding,
        plan_sha256=plan.plan_sha256,
        semantic_sha256=plan.semantic_sha256,
        registry_sha256=registry.semantic_sha256,
        display_sha256=canonical_digest(
            _Display(wires=tuple(sorted(plan.display, key=lambda wire: wire.wire_id)))
        ),
        status=(
            "LOCAL_SYNTHETIC_PLAN_VALID"
            if registry.provenance == "synthetic_fixture"
            else "BLOCKED_PRODUCTION_CDF_UNVERIFIED"
        ),
        semantic_diff=semantic_diff(baseline, plan),
    )


def synthetic_inverter_fixture(binding: RevisionBinding) -> tuple[DeviceRegistry, SchematicPlan]:
    """Package example only: units/ranges are invented fixture data, never PDK facts.

    Testbench input is an explicit external pin; this logical preview neither
    supplies a time waveform nor promises a simulator-ready autonomous testbench.
    """
    mos = (
        ParameterSpec(parameter_id="w", unit="um", minimum="0.1", maximum="10"),
        ParameterSpec(parameter_id="l", unit="um", minimum="0.1", maximum="10"),
        ParameterSpec(parameter_id="m", unit="1", value_type="integer", minimum="1", maximum="8"),
        ParameterSpec(parameter_id="nf", unit="1", value_type="integer", minimum="1", maximum="8"),
    )
    registry = DeviceRegistry(
        registry_id="synthetic-inverter-devices-v1",
        provenance="synthetic_fixture",
        devices=(
            DeviceRegistration(
                device_id="fixture-nmos",
                kind="nmos",
                terminals=("d", "g", "s", "b"),
                parameters=mos,
            ),
            DeviceRegistration(
                device_id="fixture-pmos",
                kind="pmos",
                terminals=("d", "g", "s", "b"),
                parameters=mos,
            ),
            DeviceRegistration(
                device_id="fixture-supply",
                kind="dc-source",
                terminals=("p", "n"),
                parameters=(
                    ParameterSpec(parameter_id="dc", unit="V", minimum="0.1", maximum="2"),
                ),
            ),
            DeviceRegistration(
                device_id="fixture-capacitor",
                kind="capacitor",
                terminals=("p", "n"),
                parameters=(
                    ParameterSpec(parameter_id="c", unit="F", minimum="1e-15", maximum="1e-9"),
                ),
            ),
        ),
    )
    role_names: tuple[tuple[str, PinRole], ...] = (
        ("vdd", "supply"),
        ("vss", "return"),
        ("input", "input"),
        ("output", "output"),
    )
    nets = tuple(Net(net_id=net, role=role) for net, role in role_names)
    pins = tuple(Pin(pin_id=net, net_id=net, role=role) for net, role in role_names)
    mos_values = tuple(
        ParameterValue(parameter_id=spec.parameter_id, unit=spec.unit, value="1") for spec in mos
    )

    def links(mapping: dict[str, str]) -> tuple[TerminalConnection, ...]:
        return tuple(
            TerminalConnection(terminal_id=key, net_id=value) for key, value in mapping.items()
        )

    dut = CircuitPlan(
        circuit_id="inverter-dut",
        role="dut",
        nets=nets,
        pins=pins,
        instances=tuple(
            Instance(
                instance_id=kind,
                device_id=f"fixture-{kind}",
                parameters=mos_values,
                connections=links({"d": "output", "g": "input", "s": rail, "b": rail}),
            )
            for kind, rail in (("nmos", "vss"), ("pmos", "vdd"))
        ),
    )
    bench = CircuitPlan(
        circuit_id="inverter-testbench",
        role="testbench",
        nets=nets,
        pins=pins,
        instances=(
            Instance(
                instance_id="supply",
                device_id="fixture-supply",
                parameters=(ParameterValue(parameter_id="dc", unit="V", value="1"),),
                connections=links({"p": "vdd", "n": "vss"}),
            ),
            Instance(
                instance_id="load",
                device_id="fixture-capacitor",
                parameters=(ParameterValue(parameter_id="c", unit="F", value="1e-12"),),
                connections=links({"p": "output", "n": "vss"}),
            ),
        ),
        dut_reference=DutReference(
            instance_id="dut",
            dut_circuit_id=dut.circuit_id,
            connections=links({pin.pin_id: pin.net_id for pin in pins}),
        ),
    )
    return registry, SchematicPlan(
        binding=binding, registry_sha256=registry.semantic_sha256, dut=dut, testbench=bench
    )
