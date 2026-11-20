"""Explicit research circuit data and the bounded owned-inverter generation adapter."""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Annotated, Literal, Self

from pydantic import BeforeValidator, Field, model_validator

from cadence_mcp_bridge.m2_inverter import OwnedInverterPlan, _mos_parameters, observed_devices
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    VariableModel,
    canonical_digest,
    number_text,
)

Numeric = Annotated[str, BeforeValidator(number_text)]
PositiveInt = Annotated[int, Field(ge=1, le=100_000)]
Name = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_#!-]{0,63}$")]
Path = Annotated[tuple[Name, ...], Field(min_length=1, max_length=16)]


class Evidence(VariableModel):
    reference: Annotated[str, Field(min_length=1, max_length=256)]
    status: Literal["confirmed", "assumed", "unconfirmed"]
    sha256: Digest | None = None

    @model_validator(mode="after")
    def evidence_pin(self) -> Self:
        if self.status == "confirmed" and self.sha256 is None:
            raise ValueError("confirmed source requires an artifact digest")
        return self


class Point(VariableModel):
    x: Numeric
    y: Numeric


class Placement(VariableModel):
    """Schematic user coordinates, independent of MOS dimensions."""

    origin: Point
    orientation: Literal["R0", "R90", "R180", "R270", "MX", "MY"] = "R0"


class Port(VariableModel):
    name: Name
    net: Name
    direction: Literal["input", "output", "inputOutput"]
    origin: Point


class SymbolPin(VariableModel):
    port: Name
    origin: Point


class Symbol(VariableModel):
    lower_left: Point
    upper_right: Point
    pins: Annotated[tuple[SymbolPin, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def ordered_box(self) -> Self:
        if Decimal(self.lower_left.x) >= Decimal(self.upper_right.x) or Decimal(
            self.lower_left.y
        ) >= Decimal(self.upper_right.y):
            raise ValueError("symbol bounds must have positive area")
        return self


class Wire(VariableModel):
    """Presentation intent for an explicit net."""

    net: Name
    points: Annotated[tuple[Point, ...], Field(min_length=2, max_length=64)]

    @model_validator(mode="after")
    def nonzero_segments(self) -> Self:
        if any(a == b for a, b in zip(self.points, self.points[1:], strict=False)):
            raise ValueError("wire segments must have nonzero length")
        return self


class Link(VariableModel):
    terminal: Name
    net: Name


class Master(VariableModel):
    library: BindingName
    cell: BindingName
    view: BindingName


class Length(VariableModel):
    value: Numeric
    unit: Literal["m", "um", "nm"]

    @model_validator(mode="after")
    def positive_length(self) -> Self:
        if Decimal(self.value) <= 0:
            raise ValueError("MOS lengths and widths must be positive")
        return self

    def metres(self) -> Decimal:
        with localcontext() as context:
            context.prec = 128
            return Decimal(self.value).scaleb({"m": 0, "um": -6, "nm": -9}[self.unit])


class MosGeometry(VariableModel):
    w: Length
    fw: Length
    length: Length
    multiplier: PositiveInt
    fingers: PositiveInt
    width_meaning: Literal["total_width", "finger_width", "cdf_defined"]
    source: Evidence

    @model_validator(mode="after")
    def width_relationship(self) -> Self:
        with localcontext() as context:
            context.prec = 128
            width, finger = self.w.metres(), self.fw.metres()
            if self.width_meaning == "total_width" and width != finger * self.fingers:
                raise ValueError("total width must equal finger width times fingers")
            if self.width_meaning == "finger_width" and width != finger:
                raise ValueError("declared finger widths must agree")
        return self


class Component(VariableModel):
    name: Name
    placement: Placement
    links: Annotated[tuple[Link, ...], Field(min_length=1, max_length=64)]

    @property
    def connections(self) -> dict[str, str]:
        return {link.terminal: link.net for link in self.links}

    @model_validator(mode="after")
    def unique_terminals(self) -> Self:
        if len(self.connections) != len(self.links):
            raise ValueError("duplicate terminal connection")
        return self


class SpectreMos(VariableModel):
    """Independently sourced expected simulator mapping for this MOS."""

    model: BindingName
    width: Length
    length: Length
    multiplier: PositiveInt
    source: Evidence


class Mos(Component):
    kind: Literal["nmos", "pmos"]
    master: Master
    master_source: Evidence
    geometry: MosGeometry
    spectre: SpectreMos | None = None

    @model_validator(mode="after")
    def four_terminals(self) -> Self:
        if set(self.connections) != {"D", "G", "S", "B"}:
            raise ValueError("MOS requires explicit D/G/S/B connections")
        return self


class Child(Component):
    kind: Literal["child"]
    circuit: Name


class Pulse(VariableModel):
    low_v: Numeric
    high_v: Numeric
    delay_s: Numeric
    rise_s: Numeric
    fall_s: Numeric
    width_s: Numeric
    period_s: Numeric

    @model_validator(mode="after")
    def timing(self) -> Self:
        with localcontext() as context:
            context.prec = 128
            rise, fall, width = map(Decimal, (self.rise_s, self.fall_s, self.width_s))
            if (
                Decimal(self.delay_s) < 0
                or min(rise, fall, width) <= 0
                or rise + fall + width > Decimal(self.period_s)
            ):
                raise ValueError("invalid pulse timing in seconds")
        return self


class VoltageSource(Component):
    kind: Literal["voltage"]
    dc_v: Numeric | None = None
    ac_magnitude_v: Numeric = "0"
    ac_phase_deg: Numeric = "0"
    pulse: Pulse | None = None
    dc_variable: BindingName | None = None

    @model_validator(mode="after")
    def source_values(self) -> Self:
        if set(self.connections) != {"PLUS", "MINUS"} or Decimal(self.ac_magnitude_v) < 0:
            raise ValueError("voltage source requires PLUS/MINUS and nonnegative AC magnitude")
        if (self.dc_v is None) == (self.dc_variable is None):
            raise ValueError("voltage source requires exactly one DC value or variable")
        return self


class Capacitor(Component):
    kind: Literal["capacitor"]
    capacitance_f: Numeric

    @model_validator(mode="after")
    def capacitor_values(self) -> Self:
        if set(self.connections) != {"PLUS", "MINUS"} or Decimal(self.capacitance_f) <= 0:
            raise ValueError("capacitor requires PLUS/MINUS and positive capacitance")
        return self


Instance = Annotated[Mos | Child | VoltageSource | Capacitor, Field(discriminator="kind")]


class Circuit(VariableModel):
    name: Name
    nets: Annotated[tuple[Name, ...], Field(min_length=1, max_length=256)]
    ports: Annotated[tuple[Port, ...], Field(max_length=64)] = ()
    instances: Annotated[tuple[Instance, ...], Field(min_length=1, max_length=128)]
    wires: Annotated[tuple[Wire, ...], Field(max_length=512)] = ()
    symbol: Symbol | None = None

    @model_validator(mode="after")
    def connectivity(self) -> Self:
        nets = set(self.nets)
        ports = {port.name for port in self.ports}
        if (
            len(nets) != len(self.nets)
            or len(ports) != len(self.ports)
            or len({inst.name for inst in self.instances}) != len(self.instances)
        ):
            raise ValueError("duplicate net, port or instance")
        used = {port.net for port in self.ports}
        used.update(link.net for inst in self.instances for link in inst.links)
        if used != nets or any(wire.net not in nets for wire in self.wires):
            raise ValueError("unknown or unused electrical net")
        if self.symbol is not None:
            pins = {pin.port for pin in self.symbol.pins}
            if pins != ports or len(pins) != len(self.symbol.pins):
                raise ValueError("symbol pins must match schematic ports")
        return self


class Analysis(VariableModel):
    kind: Literal["dc", "ac", "tran"]
    temperature_c: Numeric
    start_hz: Numeric | None = None
    stop_hz: Numeric | None = None
    points_per_decade: PositiveInt | None = None
    stop_s: Numeric | None = None
    max_step_s: Numeric | None = None

    @model_validator(mode="after")
    def analysis_bounds(self) -> Self:
        ac = (self.start_hz, self.stop_hz, self.points_per_decade)
        tran = (self.stop_s, self.max_step_s)
        if Decimal(self.temperature_c) < Decimal("-273.15"):
            raise ValueError("temperature is below absolute zero")
        if self.kind == "ac":
            if (
                self.start_hz is None
                or self.stop_hz is None
                or self.points_per_decade is None
                or not 0 < Decimal(self.start_hz) < Decimal(self.stop_hz)
            ):
                raise ValueError("AC requires ordered positive frequencies and density")
        elif any(value is not None for value in ac):
            raise ValueError("AC options require AC analysis")
        if self.kind == "tran":
            if (
                self.stop_s is None
                or self.max_step_s is None
                or not 0 < Decimal(self.max_step_s) <= Decimal(self.stop_s)
            ):
                raise ValueError("TRAN requires positive times and max step at most stop time")
        elif any(value is not None for value in tran):
            raise ValueError("TRAN options require TRAN analysis")
        return self


class NodeObservation(VariableModel):
    kind: Literal["node"]
    net: Name


class DeviceObservation(VariableModel):
    kind: Literal["device"]
    path: Path
    quantity: Literal["id", "gm", "gds", "vgs", "vds", "vdsat", "region"]


Observation = Annotated[NodeObservation | DeviceObservation, Field(discriminator="kind")]


class Measurement(VariableModel):
    name: Name
    analysis: Literal["dc", "ac", "tran"]
    quantity: Literal["voltage", "differential_gain", "supply_power", "settling"]
    nets: Annotated[tuple[Name, ...], Field(min_length=1, max_length=4)]
    supply_path: Path | None = None


class ResearchCircuit(VariableModel):
    schema_version: Literal[1] = 1
    binding: RevisionBinding
    source: Evidence
    unresolved: Annotated[tuple[Name, ...], Field(max_length=128)] = ()
    dut: Name
    bench: Name
    circuits: Annotated[tuple[Circuit, ...], Field(min_length=2, max_length=32)]
    analyses: Annotated[tuple[Analysis, ...], Field(max_length=3)] = ()
    observations: Annotated[tuple[Observation, ...], Field(max_length=256)] = ()
    measurements: Annotated[tuple[Measurement, ...], Field(max_length=128)] = ()

    @model_validator(mode="after")
    def hierarchy(self) -> Self:
        cells = {cell.name: cell for cell in self.circuits}
        if len(cells) != len(self.circuits) or self.dut not in cells or self.bench not in cells:
            raise ValueError("duplicate circuit or missing DUT/testbench")
        if self.dut == self.bench or cells[self.bench].ports or cells[self.dut].symbol is None:
            raise ValueError("testbench must be a distinct root and DUT must define a symbol")
        parents: set[str] = set()
        for cell in self.circuits:
            for inst in cell.instances:
                if not isinstance(inst, Child):
                    continue
                child = cells.get(inst.circuit)
                if (
                    child is None
                    or child.symbol is None
                    or child.name == self.bench
                    or set(inst.connections) != {port.name for port in child.ports}
                ):
                    raise ValueError("invalid child circuit or incomplete port mapping")
                if cell.name == self.bench:
                    parents.add(child.name)
        if self.dut not in parents:
            raise ValueError("testbench must instantiate the DUT")

        depths: dict[str, int] = {}
        active: set[str] = set()

        def depth(name: str) -> int:
            if name in active:
                raise ValueError("recursive circuit hierarchy")
            if name not in depths:
                active.add(name)
                depths[name] = 1 + max(
                    (
                        depth(inst.circuit)
                        for inst in cells[name].instances
                        if isinstance(inst, Child)
                    ),
                    default=0,
                )
                active.remove(name)
            return depths[name]

        if depth(self.bench) > 16 or depths.keys() != cells.keys():
            raise ValueError("unreachable circuit or hierarchy exceeds depth")
        self.validate_measurements(cells)
        return self

    def validate_measurements(self, cells: dict[str, Circuit]) -> None:
        bench = cells[self.bench]
        analysis_kinds = {analysis.kind for analysis in self.analyses}
        if len(analysis_kinds) != len(self.analyses) or len(
            {measurement.name for measurement in self.measurements}
        ) != len(self.measurements):
            raise ValueError("duplicate analysis or measurement name")

        def resolve(path: tuple[str, ...]) -> Instance:
            scope = bench
            for segment in path[:-1]:
                inst = next((item for item in scope.instances if item.name == segment), None)
                if not isinstance(inst, Child):
                    raise ValueError("invalid hierarchical observation path")
                scope = cells[inst.circuit]
            target = next((item for item in scope.instances if item.name == path[-1]), None)
            if target is None:
                raise ValueError("unknown hierarchical observation target")
            return target

        for observation in self.observations:
            if isinstance(observation, DeviceObservation):
                if not isinstance(resolve(observation.path), Mos):
                    raise ValueError("device observation requires a MOS")
            elif observation.net not in bench.nets:
                raise ValueError("unknown testbench observation net")
        for measurement in self.measurements:
            if measurement.analysis not in analysis_kinds or not set(measurement.nets) <= set(
                bench.nets
            ):
                raise ValueError("measurement requires a declared analysis and testbench nets")
            if measurement.quantity == "supply_power":
                if measurement.supply_path is None or not isinstance(
                    resolve(measurement.supply_path), VoltageSource
                ):
                    raise ValueError("power measurement requires a voltage source")
            elif measurement.supply_path is not None:
                raise ValueError("supply path requires a supply power measurement")


def validate_research_circuit(definition: ResearchCircuit) -> ResearchCircuit:
    """Validate the complete definition again at a callable boundary."""
    return ResearchCircuit.model_validate_json(definition.model_dump_json())


_SPECTRE_SCALE = {"a": -18, "f": -15, "p": -12, "n": -9, "u": -6, "m": -3}


def _cdf_length(value: str) -> Decimal:
    exponent = _SPECTRE_SCALE.get(value[-1])
    with localcontext() as context:
        context.prec = 128
        if exponent is None:
            return Decimal(value)
        return Decimal(value[:-1]).scaleb(exponent)


def _placed_at(inst: Component, x: int) -> bool:
    return inst.placement == Placement(origin=Point(x=str(x), y="0"))


def _inverter_bench(bench: Circuit, dut: str) -> bool:
    devices = {inst.name: inst for inst in bench.instances}
    if set(devices) != {"DUT", "VDD", "VIN", "CL"}:
        return False
    ref, supply, stimulus, cap = (devices[key] for key in ("DUT", "VDD", "VIN", "CL"))
    if not (
        isinstance(ref, Child)
        and ref.circuit == dut
        and ref.connections == {"vin": "vin", "vout": "vout", "vdd": "vdd", "vss": "gnd!"}
        and isinstance(supply, VoltageSource)
        and isinstance(stimulus, VoltageSource)
        and isinstance(cap, Capacitor)
        and cap.connections == {"PLUS": "vout", "MINUS": "gnd!"}
        and cap.capacitance_f == "0.000000000001"
    ):
        return False
    pulse = Pulse(
        low_v="0",
        high_v="1",
        delay_s="1e-9",
        rise_s="100e-12",
        fall_s="100e-12",
        width_s="2e-9",
        period_s="4e-9",
    )
    return (
        supply.connections == {"PLUS": "vdd", "MINUS": "gnd!"}
        and stimulus.connections == {"PLUS": "vin", "MINUS": "gnd!"}
        and supply.dc_v == "1"
        and supply.dc_variable is None
        and supply.pulse is None
        and stimulus.dc_v is None
        and stimulus.dc_variable == "m2_vin"
        and stimulus.pulse == pulse
        and all(
            source.ac_magnitude_v == "0" and source.ac_phase_deg == "0"
            for source in (supply, stimulus)
        )
        and all(
            _placed_at(inst, index * 4) for index, inst in enumerate((ref, supply, stimulus, cap))
        )
    )


def _inverter_symbol(dut: Circuit) -> bool:
    ports = {port.name: port for port in dut.ports}
    directions: dict[str, Literal["input", "output", "inputOutput"]] = {
        "vin": "input",
        "vout": "output",
        "vdd": "inputOutput",
        "vss": "inputOutput",
    }
    if ports != {
        name: Port(
            name=name, net=name, direction=direction, origin=Point(x=str(100 + 2 * i), y="100")
        )
        for i, (name, direction) in enumerate(directions.items())
    }:
        return False
    symbol = dut.symbol
    return (
        symbol is not None
        and symbol.lower_left == Point(x="-1", y="-1")
        and symbol.upper_right == Point(x="1", y="1")
        and {pin.port: pin.origin for pin in symbol.pins}
        == {
            "vin": Point(x="-1", y="0"),
            "vout": Point(x="1", y="0"),
            "vdd": Point(x="0", y="1"),
            "vss": Point(x="0", y="-1"),
        }
    )


def _generation_definition(
    definition: ResearchCircuit,
    expected_binding: RevisionBinding,
    expected_definition_sha256: Digest,
) -> ResearchCircuit:
    checked = validate_research_circuit(definition)
    if (
        checked.binding != expected_binding
        or canonical_digest(checked) != expected_definition_sha256
    ):
        raise ValueError("research definition binding or digest mismatch")
    if checked.unresolved or checked.source.status != "confirmed":
        raise ValueError("research definition has unresolved or unconfirmed inputs")
    return checked


def adapt_owned_inverter(
    definition: ResearchCircuit,
    frame: bytes,
    *,
    expected_binding: RevisionBinding,
    expected_definition_sha256: Digest,
    expected_cdf_frame_sha256: Digest,
    output_library: str,
) -> OwnedInverterPlan:
    """Bind a complete definition to the existing default inverter generator.

    The caller authenticates the independent definition and CDF pins. Analyses
    and observations are consumed separately by operation planning. The returned
    plan uses the existing owned destination, renderer and netlist verifier.
    """
    checked = _generation_definition(definition, expected_binding, expected_definition_sha256)
    cells = {cell.name: cell for cell in checked.circuits}
    dut, bench = cells[checked.dut], cells[checked.bench]
    if (
        len(cells) != 2
        or dut.wires
        or bench.wires
        or bench.symbol is not None
        or not _inverter_symbol(dut)
        or not _inverter_bench(bench, dut.name)
    ):
        raise ValueError("definition is outside the owned inverter generation profile")
    devices = {inst.name: inst for inst in dut.instances}
    mn, mp = devices.get("MN"), devices.get("MP")
    if (
        set(devices) != {"MN", "MP"}
        or not isinstance(mn, Mos)
        or not isinstance(mp, Mos)
        or (mn.kind, mp.kind) != ("nmos", "pmos")
    ):
        raise ValueError("owned inverter requires MN and MP only")
    for index, (inst, rail) in enumerate(((mn, "vss"), (mp, "vdd"))):
        if (
            inst.master.view != "symbol"
            or inst.master_source.status != "confirmed"
            or inst.master_source.sha256 != expected_cdf_frame_sha256
            or inst.geometry.source.status != "confirmed"
            or inst.geometry.source.sha256 != expected_cdf_frame_sha256
            or inst.spectre is not None
            or not _placed_at(inst, index * 4)
            or inst.connections != {"D": "vout", "G": "vin", "S": rail, "B": rail}
        ):
            raise ValueError("unconfirmed inverter device or incompatible wiring and placement")
    plan = OwnedInverterPlan(
        binding=checked.binding,
        cdf_frame_sha256=expected_cdf_frame_sha256,
        output_library=output_library,
        dut_cell=dut.name,
        testbench_cell=bench.name,
        nmos_library=mn.master.library,
        nmos_cell=mn.master.cell,
        pmos_library=mp.master.library,
        pmos_cell=mp.master.cell,
    )
    observed = observed_devices(plan, frame)
    for inst, device in zip((mn, mp), observed[:2], strict=True):
        values = _mos_parameters(device)
        geometry = inst.geometry
        if (
            (geometry.w.metres(), geometry.fw.metres(), geometry.length.metres())
            != tuple(_cdf_length(values[name]) for name in ("w", "fw", "l"))
            or geometry.multiplier != int(values["m"])
            or geometry.fingers != int(values["fingers"])
        ):
            raise ValueError("inverter geometry differs from the observed effective CDF")
    return plan


class OwnedMosBlockPlan(VariableModel):
    """Local declaration for the DUT hierarchy and its expected reopened content."""

    definition_sha256: Digest
    binding: RevisionBinding
    output_library: BindingName
    root: Name
    circuits: Annotated[tuple[Circuit, ...], Field(min_length=1, max_length=31)]


def plan_owned_mos_block(
    definition: ResearchCircuit,
    *,
    expected_binding: RevisionBinding,
    expected_definition_sha256: Digest,
    output_library: str,
) -> OwnedMosBlockPlan:
    """Resolve only the DUT closure. The bench remains operation-planning data."""
    checked = _generation_definition(definition, expected_binding, expected_definition_sha256)
    circuits = {cell.name: cell for cell in checked.circuits}
    pending = [checked.dut]
    closure: dict[str, Circuit] = {}
    while pending:
        name = pending.pop()
        if name in closure:
            continue
        cell = circuits[name]
        closure[name] = cell
        for inst in cell.instances:
            if isinstance(inst, Child):
                pending.append(inst.circuit)
            elif not isinstance(inst, Mos):
                raise ValueError("owned MOS block accepts only MOS and child cells")
            elif (
                inst.master.view != "symbol"
                or inst.master_source.status != "confirmed"
                or inst.geometry.source.status != "confirmed"
                or inst.spectre is None
                or inst.spectre.source.status != "confirmed"
                or inst.master.library == output_library
            ):
                raise ValueError(
                    "owned MOS block requires confirmed symbol, geometry and Spectre mapping"
                )
    if output_library in {"analogLib", "basic"}:
        raise ValueError("owned library collides with a primitive library")
    return OwnedMosBlockPlan(
        definition_sha256=expected_definition_sha256,
        binding=checked.binding,
        output_library=output_library,
        root=checked.dut,
        circuits=tuple(closure[name] for name in sorted(closure)),
    )


class ReopenedMos(Component):
    kind: Literal["nmos", "pmos"]
    master: Master
    w: Length
    fw: Length
    length: Length
    multiplier: PositiveInt
    fingers: PositiveInt


class ReopenedChild(Child):
    library: BindingName
    view: BindingName


class ReopenedCircuit(VariableModel):
    name: Name
    nets: Annotated[tuple[Name, ...], Field(min_length=1, max_length=256)]
    ports: Annotated[tuple[Port, ...], Field(max_length=64)]
    wires: Annotated[tuple[Wire, ...], Field(max_length=512)]
    symbol: Symbol
    instances: Annotated[
        tuple[Annotated[ReopenedMos | ReopenedChild, Field(discriminator="kind")], ...],
        Field(min_length=1, max_length=128),
    ]


class NetlistedMos(VariableModel):
    name: Name
    model: BindingName
    terminals: tuple[Name, Name, Name, Name]
    width: Length
    length: Length
    multiplier: PositiveInt


class NetlistedChild(VariableModel):
    name: Name
    circuit: Name
    terminals: Annotated[tuple[Name, ...], Field(min_length=1, max_length=64)]


class NetlistedCircuit(VariableModel):
    name: Name
    ports: Annotated[tuple[Name, ...], Field(min_length=1, max_length=64)]
    mos: Annotated[tuple[NetlistedMos, ...], Field(max_length=128)]
    children: Annotated[tuple[NetlistedChild, ...], Field(max_length=128)]


class MosBlockEvidence(VariableModel):
    """Projections from independently authenticated, complete native receipts."""

    plan_sha256: Digest
    output_library: BindingName
    reopened_tree_sha256: Digest
    netlist_source_tree_sha256: Digest
    reopen_artifact_sha256: Digest
    netlist_artifact_sha256: Digest
    reopened: Annotated[tuple[ReopenedCircuit, ...], Field(min_length=1, max_length=31)]
    netlisted: Annotated[tuple[NetlistedCircuit, ...], Field(min_length=1, max_length=31)]


def _reopened_circuit(cell: Circuit, output_library: str) -> ReopenedCircuit:
    instances: list[ReopenedMos | ReopenedChild] = []
    for inst in cell.instances:
        if isinstance(inst, Child):
            instances.append(
                ReopenedChild(**inst.model_dump(), library=output_library, view="symbol")
            )
        elif isinstance(inst, Mos):
            geometry = inst.geometry
            instances.append(
                ReopenedMos(
                    kind=inst.kind,
                    name=inst.name,
                    placement=inst.placement,
                    links=inst.links,
                    master=inst.master,
                    w=geometry.w,
                    fw=geometry.fw,
                    length=geometry.length,
                    multiplier=geometry.multiplier,
                    fingers=geometry.fingers,
                )
            )
        else:
            raise ValueError("unexpected non-MOS device in block")
    if cell.symbol is None:
        raise ValueError("generated block cell requires a symbol")
    return ReopenedCircuit(
        name=cell.name,
        nets=cell.nets,
        ports=cell.ports,
        wires=cell.wires,
        symbol=cell.symbol,
        instances=tuple(instances),
    )


def _netlisted_circuit(cell: Circuit, cells: dict[str, Circuit]) -> NetlistedCircuit:
    mos = []
    children = []
    for inst in cell.instances:
        if isinstance(inst, Child):
            links = inst.connections
            children.append(
                NetlistedChild(
                    name=inst.name,
                    circuit=inst.circuit,
                    terminals=tuple(links[port.name] for port in cells[inst.circuit].ports),
                )
            )
        elif isinstance(inst, Mos) and inst.spectre is not None:
            d, g, s, b = (inst.connections[name] for name in ("D", "G", "S", "B"))
            mos.append(
                NetlistedMos(
                    name=inst.name,
                    model=inst.spectre.model,
                    terminals=(d, g, s, b),
                    width=inst.spectre.width,
                    length=inst.spectre.length,
                    multiplier=inst.spectre.multiplier,
                )
            )
        else:
            raise ValueError("unexpected device without Spectre mapping")
    return NetlistedCircuit(
        name=cell.name,
        ports=tuple(port.net for port in cell.ports),
        mos=tuple(mos),
        children=tuple(children),
    )


def _reopened_identity(cell: ReopenedCircuit) -> tuple[object, ...]:
    def instance_identity(inst: ReopenedMos | ReopenedChild) -> tuple[object, ...]:
        common = (inst.kind, inst.name, inst.placement, inst.connections)
        if isinstance(inst, ReopenedChild):
            return (*common, inst.library, inst.circuit, inst.view)
        return (
            *common,
            inst.master,
            inst.w.metres(),
            inst.fw.metres(),
            inst.length.metres(),
            inst.multiplier,
            inst.fingers,
        )

    return (
        cell.name,
        sorted(cell.nets),
        sorted(cell.ports, key=lambda port: port.name),
        cell.symbol.lower_left,
        cell.symbol.upper_right,
        sorted(cell.symbol.pins, key=lambda pin: pin.port),
        sorted(cell.wires, key=canonical_digest),
        [instance_identity(inst) for inst in sorted(cell.instances, key=lambda inst: inst.name)],
    )


def _netlisted_identity(cell: NetlistedCircuit) -> tuple[object, ...]:
    return (
        cell.name,
        cell.ports,
        [
            (
                inst.name,
                inst.model,
                inst.terminals,
                inst.width.metres(),
                inst.length.metres(),
                inst.multiplier,
            )
            for inst in sorted(cell.mos, key=lambda inst: inst.name)
        ],
        sorted(cell.children, key=lambda inst: inst.name),
    )


def verify_owned_mos_block(
    plan: OwnedMosBlockPlan,
    evidence: MosBlockEvidence,
    *,
    expected_plan_sha256: Digest,
    expected_reopened_tree_sha256: Digest,
    expected_reopen_artifact_sha256: Digest,
    expected_netlist_artifact_sha256: Digest,
) -> None:
    """Compare complete normalized projections. The caller authenticates the raw artifacts."""
    plan = OwnedMosBlockPlan.model_validate_json(plan.model_dump_json())
    evidence = MosBlockEvidence.model_validate_json(evidence.model_dump_json())
    if (
        canonical_digest(plan) != expected_plan_sha256
        or evidence.plan_sha256 != expected_plan_sha256
        or evidence.output_library != plan.output_library
        or evidence.reopened_tree_sha256 != expected_reopened_tree_sha256
        or evidence.netlist_source_tree_sha256 != expected_reopened_tree_sha256
        or evidence.reopen_artifact_sha256 != expected_reopen_artifact_sha256
        or evidence.netlist_artifact_sha256 != expected_netlist_artifact_sha256
    ):
        raise ValueError("MOS block plan or native evidence pin mismatch")
    cells = {cell.name: cell for cell in plan.circuits}
    reopened = sorted(evidence.reopened, key=lambda cell: cell.name)
    expected = sorted(plan.circuits, key=lambda cell: cell.name)
    if [_reopened_identity(cell) for cell in reopened] != [
        _reopened_identity(_reopened_circuit(cell, plan.output_library)) for cell in expected
    ]:
        raise ValueError("reopened MOS block topology or attributes mismatch")
    netlisted = sorted(evidence.netlisted, key=lambda cell: cell.name)
    if [_netlisted_identity(cell) for cell in netlisted] != [
        _netlisted_identity(_netlisted_circuit(cell, cells)) for cell in expected
    ]:
        raise ValueError("netlisted MOS block topology or effective values mismatch")
