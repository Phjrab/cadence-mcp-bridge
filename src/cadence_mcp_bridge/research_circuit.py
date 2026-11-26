"""Explicit research circuit data and the bounded owned-inverter generation adapter."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, localcontext
from hashlib import sha256
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import BeforeValidator, ConfigDict, Field, model_validator

from cadence_mcp_bridge._native_rendering import partition_input, static_fingerprint
from cadence_mcp_bridge.domain_provisioning import _closed_document
from cadence_mcp_bridge.generic_ade import LIMIT as ADE_INPUT_LIMIT
from cadence_mcp_bridge.m2_cdf import parse_frame
from cadence_mcp_bridge.m2_inverter import (
    _PRELUDE,
    OwnedInverterPlan,
    _mos_parameters,
    _quote,
    observed_devices,
)
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_registration import RegistrationObservation
from cadence_mcp_bridge.native_runtime import NativeLibrary, RemotePath
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    VariableModel,
    canonical_digest,
    number_text,
)

if TYPE_CHECKING:
    from cadence_mcp_bridge.research_bench import BenchNetlistConditions, ResearchBenchPlan


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


_SPECTRE_DECIMAL = r"[0-9]{1,20}(?:\.[0-9]{1,20})?(?:[eE][+-]?[0-9]{1,2})?[afpnum]?"
JunctionLiteral = Annotated[str, Field(pattern=rf"^{_SPECTRE_DECIMAL}$", max_length=32)]


class MosJunctions(VariableModel):
    model_config = ConfigDict(serialize_by_alias=True)

    source_area: JunctionLiteral = Field(alias="as")
    drain_area: JunctionLiteral = Field(alias="ad")
    source_perimeter: JunctionLiteral = Field(alias="ps")
    drain_perimeter: JunctionLiteral = Field(alias="pd")


class MosGenerationObservation(VariableModel):
    """Raw CDF and matching independently reopened OA junction literals."""

    cdf_sha256: Digest
    junctions: MosJunctions


class MosGeometry(VariableModel):
    w: Length
    fw: Length
    length: Length
    multiplier: PositiveInt
    fingers: PositiveInt
    width_meaning: Literal["total_width", "finger_width", "cdf_defined"]
    source: Evidence
    generation_observation: MosGenerationObservation | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

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
        _validate_research_graph(self)
        return self

    def validate_measurements(self, cells: dict[str, Circuit]) -> None:
        _validate_research_measurements(self, cells)


class ResearchCircuitStaticPreview(VariableModel):
    """A validated circuit graph with no execution or physical revision binding."""

    schema_version: Literal[1] = 1
    document_kind: Literal["research-circuit-static-preview-v1"] = (
        "research-circuit-static-preview-v1"
    )
    execution_authorized: Literal[False] = False
    source_draft_sha256: Digest
    source: Evidence
    unresolved: Annotated[tuple[Name, ...], Field(min_length=1, max_length=128)]
    dut: Name
    bench: Name
    circuits: Annotated[tuple[Circuit, ...], Field(min_length=2, max_length=32)]
    analyses: Annotated[tuple[Analysis, ...], Field(max_length=3)] = ()
    observations: Annotated[tuple[Observation, ...], Field(max_length=256)] = ()
    measurements: Annotated[tuple[Measurement, ...], Field(max_length=128)] = ()

    @model_validator(mode="after")
    def hierarchy(self) -> Self:
        _validate_research_graph(self)
        return self


def _validate_research_graph(definition: ResearchCircuit | ResearchCircuitStaticPreview) -> None:
    cells = {cell.name: cell for cell in definition.circuits}
    if (
        len(cells) != len(definition.circuits)
        or definition.dut not in cells
        or definition.bench not in cells
    ):
        raise ValueError("duplicate circuit or missing DUT/testbench")
    if (
        definition.dut == definition.bench
        or cells[definition.bench].ports
        or cells[definition.dut].symbol is None
    ):
        raise ValueError("testbench must be a distinct root and DUT must define a symbol")
    parents: set[str] = set()
    for cell in definition.circuits:
        for inst in cell.instances:
            if not isinstance(inst, Child):
                continue
            child = cells.get(inst.circuit)
            if (
                child is None
                or child.symbol is None
                or child.name == definition.bench
                or set(inst.connections) != {port.name for port in child.ports}
            ):
                raise ValueError("invalid child circuit or incomplete port mapping")
            if cell.name == definition.bench:
                parents.add(child.name)
    if definition.dut not in parents:
        raise ValueError("testbench must instantiate the DUT")

    depths: dict[str, int] = {}
    active: set[str] = set()

    def depth(name: str) -> int:
        if name in active:
            raise ValueError("recursive circuit hierarchy")
        if name not in depths:
            active.add(name)
            depths[name] = 1 + max(
                (depth(inst.circuit) for inst in cells[name].instances if isinstance(inst, Child)),
                default=0,
            )
            active.remove(name)
        return depths[name]

    if depth(definition.bench) > 16 or depths.keys() != cells.keys():
        raise ValueError("unreachable circuit or hierarchy exceeds depth")
    _validate_research_measurements(definition, cells)


def _validate_research_measurements(
    definition: ResearchCircuit | ResearchCircuitStaticPreview, cells: dict[str, Circuit]
) -> None:
    bench = cells[definition.bench]
    analysis_kinds = {analysis.kind for analysis in definition.analyses}
    if len(analysis_kinds) != len(definition.analyses) or len(
        {measurement.name for measurement in definition.measurements}
    ) != len(definition.measurements):
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

    for observation in definition.observations:
        if isinstance(observation, DeviceObservation):
            if not isinstance(resolve(observation.path), Mos):
                raise ValueError("device observation requires a MOS")
        elif observation.net not in bench.nets:
            raise ValueError("unknown testbench observation net")
    for measurement in definition.measurements:
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


class MosBlockScripts(VariableModel):
    """Two local script texts for separate operator-controlled invocations."""

    plan_sha256: Digest
    generate: str
    reopen: str


_BLOCK_PRELUDE = r"""
procedure(m2BlockPoint(point x y)
 m2Require(and(xCoord(point)==x yCoord(point)==y)))
procedure(m2BlockPlacement(inst x y orientation)
 m2Require(and(inst inst~>orient==orientation))
 m2BlockPoint(inst~>xy x y))
procedure(m2BlockCheckPlacement(cv name x y orientation)
 let((inst)
  inst=m2Require(car(setof(entry cv~>instances entry~>name==name)))
  m2BlockPlacement(inst x y orientation)))
procedure(m2BlockTerminal(cv name direction net)
 let((term)
  term=car(setof(entry cv~>terminals entry~>name==name))
  m2Require(and(term term~>direction==direction term~>net~>name==net))
  term))
procedure(m2BlockSymbolPin(cv name direction x y)
 let((term fig box)
  term=m2BlockTerminal(cv name direction name)
  m2Require(length(term~>pins)==1)
  m2Require(length(car(term~>pins)~>figs)==1)
  fig=car(car(term~>pins)~>figs)
  box=fig~>bBox
  m2BlockPoint(lowerLeft(box) x y)
  m2BlockPoint(upperRight(box) x+0.125 y+0.125)))
procedure(m2BlockInstance(cv name library cell x y terms)
 let((inst)
  inst=car(setof(entry cv~>instances entry~>name==name))
  m2Require(and(inst inst~>libName==library inst~>cellName==cell
                inst~>viewName=="symbol" inst~>orient=="R0"
                length(inst~>instTerms)==terms))
  m2BlockPoint(inst~>xy x y)
  inst))
procedure(m2BlockBody(cv x0 y0 x1 y1)
 let((body box)
  body=setof(entry cv~>shapes entry~>layerName=="device" && entry~>purpose=="drawing")
  m2Require(length(body)==1)
  m2Require(car(body)~>objType=="rect")
  box=car(body)~>bBox
  m2BlockPoint(lowerLeft(box) x0 y0)
  m2BlockPoint(upperRight(box) x1 y1)))
procedure(m2BlockEffective(inst name expected)
 let((cdf param)
  cdf=m2Require(cdfGetInstCDF(inst))
  param=car(setof(entry cdf~>parameters entry~>name==name))
  m2Require(and(param param~>value==expected))))
"""


def _pinned_block(plan: OwnedMosBlockPlan, expected_plan_sha256: Digest) -> OwnedMosBlockPlan:
    plan = OwnedMosBlockPlan.model_validate_json(plan.model_dump_json())
    if canonical_digest(plan) != expected_plan_sha256:
        raise ValueError("MOS block plan digest mismatch")
    return plan


def _child_first(plan: OwnedMosBlockPlan) -> list[Circuit]:
    cells = {cell.name: cell for cell in plan.circuits}
    if len(cells) != len(plan.circuits):
        raise ValueError("duplicate MOS block cell")
    ordered: dict[str, Circuit] = {}
    active: set[str] = set()

    def visit(name: str) -> None:
        if name in ordered:
            return
        if name in active or name not in cells:
            raise ValueError("cyclic or missing MOS block cell")
        active.add(name)
        cell = cells[name]
        for inst in cell.instances:
            if isinstance(inst, Child):
                visit(inst.circuit)
        ordered[name] = cell
        active.remove(name)

    visit(plan.root)
    if ordered.keys() != cells.keys():
        raise ValueError("unreachable MOS block cell")
    return list(ordered.values())


def _block_cdf_values(inst: Mos, devices: tuple[dict[str, object], ...]) -> dict[str, str]:
    matches = [
        device
        for device in devices
        if device["library"] == inst.master.library and device["cell"] == inst.master.cell
    ]
    if len(matches) != 1:
        raise ValueError("MOS CDF master observation is missing or ambiguous")
    device = matches[0]
    terminals = ("D", "G", "S", "B")
    observed = device["terminals"]
    if (
        not isinstance(observed, tuple)
        or len(observed) != 4
        or set(observed) != set(terminals)
        or device["spectre"] != (("base", None, terminals), ("effective", None, terminals))
    ):
        raise ValueError("MOS Spectre D/G/S/B order is unsupported")
    geometry = inst.geometry
    observation = geometry.generation_observation
    if observation is None:
        values = _mos_parameters(device)
    else:
        values = _mos_parameters(
            device, compare_widths=lambda total, finger: _cdf_length(total) == _cdf_length(finger)
        )
        junctions = observation.junctions.model_dump(by_alias=True)
        rows = device["parameters"]
        if (
            not isinstance(rows, tuple)
            or {name: values[name] for name in junctions} != junctions
            or not values.keys()
            <= {row[1] for row in rows if row[0] == "effective" and row[2] == "instData"}
            or any(row[:2] == ("effective", "nf") for row in rows)
        ):
            raise ValueError("MOS target CDF differs from the retained OA values")
    spectre = inst.spectre
    if (
        spectre is None
        or (_cdf_length(values["w"]), _cdf_length(values["fw"]), _cdf_length(values["l"]))
        != (geometry.w.metres(), geometry.fw.metres(), geometry.length.metres())
        or geometry.multiplier != int(values["m"])
        or geometry.fingers != int(values["fingers"])
        or (spectre.model, spectre.width.metres(), spectre.length.metres(), spectre.multiplier)
        != (values["model"], _cdf_length(values["fw"]), _cdf_length(values["l"]), int(values["m"]))
    ):
        raise ValueError("MOS CDF values disagree with declared geometry or Spectre mapping")
    return values


def render_research_positioned_instance(
    master: Master,
    instance: Component,
) -> tuple[tuple[str, ...], str]:
    """Open the symbol first, then create and verify the instance at literal XY."""
    master = Master.model_validate_json(master.model_dump_json())
    placement = Placement.model_validate_json(instance.placement.model_dump_json())
    if master.view != "symbol" or placement.orientation != "R0":
        raise ValueError("research instance requires a symbol master and R0 placement")
    x, y = placement.origin.x, placement.origin.y
    name = _quote(instance.name)
    library, cell = _quote(master.library), _quote(master.cell)
    return (
        (
            f'master=m2Require(dbOpenCellViewByType({library} {cell} "symbol" "" "r"))',
            f'inst=m2Require(dbCreateInst(cv master {name} list({x} {y}) "R0"))',
            f'm2BlockPlacement(inst {x} {y} "R0")',
        ),
        f'm2BlockCheckPlacement(cv {name} {x} {y} "R0")',
    )


_SCHEMATIC_PORT_CHECK = r"""
procedure(m2BlockSchematicPort(cv name direction net x y)
 let((term pin fig)
  term=m2BlockTerminal(cv name direction net)
  m2Require(length(term~>pins)==1)
  pin=car(term~>pins)
  m2Require(and(pin~>term==term length(pin~>figs)==1))
  fig=car(pin~>figs)
  m2Require(and(fig~>cellView==cv fig~>objType=="inst"
                fig~>libName=="basic" fig~>cellName=="iopin" fig~>viewName=="symbol"
                fig~>pin==pin))
  m2BlockPoint(fig~>xy x y)))
"""


_TARGET_PROPERTY_CHECK = r"""
procedure(m2BlockTargetProperties(inst cell name values emit)
 let((cdf key expected prop param raw value oaType cdfType units)
  cdf=m2Require(cdfGetInstCDF(inst))
  foreach(entry values
   key=car(entry) expected=cadr(entry)
   prop=dbFindProp(inst key) param=cdfFindParamByName(cdf key)
   raw=if(prop then prop~>value else nil)
   value=if(param then param~>value else nil)
   oaType=if(prop then prop~>valueType else nil)
   cdfType=if(param then param~>type else nil)
   units=if(param then param~>units else nil)
   cond(
    (key=="nf" m2Require(and(!prop !param)))
    (key=="dfm" m2Require(and(!prop cdfType=="instData" !units value=="Minimum")))
    (t m2Require(and(oaType=="string" cdfType=="instData" raw==expected value==expected
      units==caddr(entry)))))
   when(emit
    printf("OTA17_TARGET_PROP|%s|%s|%s|%L|%L|%L|%L|%L\n"
      cell name key oaType raw cdfType units value)))
  t))
"""


def _block_generation_parts(
    plan: OwnedMosBlockPlan,
    ordered: list[Circuit],
    cdf_frames: Mapping[str, bytes],
    *,
    verify_schematic_port_positions: bool,
) -> tuple[list[str], list[str]]:
    devices: dict[str, tuple[dict[str, object], ...]] = {}
    create: list[str] = []
    reopen: list[str] = []
    q = _quote
    lib = q(plan.output_library)
    for cell in ordered:
        symbol = cell.symbol
        if (
            symbol is None
            or not cell.ports
            or cell.wires
            or any(port.name != port.net for port in cell.ports)
            or any(inst.placement.orientation != "R0" for inst in cell.instances)
        ):
            raise ValueError("renderer supports R0, named ports and terminal label stubs only")
        symbol_pins = {pin.port: pin.origin for pin in symbol.pins}
        name = q(cell.name)
        create.append(
            f'cv=m2Require(dbOpenCellViewByType({lib} {name} "schematic" "schematic" "w"))'
        )
        reopen.append(f'cv=m2Require(dbOpenCellViewByType({lib} {name} "schematic" "" "r"))')
        reopen.extend(
            (
                f"m2Require(length(cv~>terminals)=={len(cell.ports)})",
                f"m2Require(length(cv~>nets)=={len(cell.nets)})",
                f"m2Require(length(setof(entry cv~>instances "
                f'!(entry~>libName=="basic" && entry~>cellName=="iopin")))=={len(cell.instances)})',
            )
        )
        initial_checks: list[str] = []
        placement_checks: list[str] = []
        for port in cell.ports:
            args = f"{q(port.name)} {q(port.direction)}"
            create.append(f"m2Port(cv {args} {port.origin.x} {port.origin.y})")
            if verify_schematic_port_positions:
                check = (
                    f"m2BlockSchematicPort(cv {args} {q(port.net)} {port.origin.x} {port.origin.y})"
                )
                initial_checks.append(check)
                reopen.append(check)
            else:
                reopen.append(f"m2BlockTerminal(cv {args} {q(port.net)})")
        for inst in cell.instances:
            props: dict[str, str] = {}
            observation = None
            if isinstance(inst, Child):
                master_lib, master_cell = plan.output_library, inst.circuit
            elif isinstance(inst, Mos):
                master_lib, master_cell = inst.master.library, inst.master.cell
                observation = inst.geometry.generation_observation
                pin = observation.cdf_sha256 if observation else inst.master_source.sha256
                if (
                    inst.master.view != "symbol"
                    or master_lib == plan.output_library
                    or inst.master_source.status != "confirmed"
                    or inst.geometry.source.status != "confirmed"
                    or inst.spectre is None
                    or inst.spectre.source.status != "confirmed"
                    or pin is None
                    or inst.master_source.sha256 is None
                    or inst.geometry.source.sha256 is None
                    or inst.spectre.source.sha256 is None
                    or (
                        observation is None
                        and (
                            pin != inst.geometry.source.sha256 or pin != inst.spectre.source.sha256
                        )
                    )
                ):
                    raise ValueError("renderer requires confirmed MOS evidence and target CDF")
                if pin not in devices:
                    raw = cdf_frames.get(pin)
                    if (
                        raw is None
                        or sha256(raw).hexdigest() != pin
                        or not raw.startswith(b"M2_CDF_V2\n")
                    ):
                        raise ValueError("missing or stale MOS CDF frame")
                    devices[pin] = parse_frame(raw)
                props = _block_cdf_values(inst, devices[pin])
                if observation and (
                    len(devices[pin]) != 1 or not isinstance(devices[pin][0]["instance"], str)
                ):
                    raise ValueError("MOS target CDF must contain exactly one observed instance")
            else:
                raise ValueError("renderer accepts only MOS and child cells")
            x, y = inst.placement.origin.x, inst.placement.origin.y
            target = f"{q(master_lib)} {q(master_cell)}"
            inst_name = q(inst.name)
            creation, placement_check = render_research_positioned_instance(
                Master(library=master_lib, cell=master_cell, view="symbol"), inst
            )
            create.extend(creation)
            placement_checks.append(placement_check)
            find_instance = (
                f"inst=m2BlockInstance(cv {inst_name} {target} {x} {y} {len(inst.links)})"
            )
            reopen.append(find_instance)
            if observation is not None:
                initial_checks.append(find_instance)
            for key, value in props.items():
                create.append(f"m2Param(inst {q(key)} {q(value)})")
                if observation is None:
                    reopen.append(f"m2Property(cv {inst_name} {q(key)} {q(value)})")
                    reopen.append(f"m2BlockEffective(inst {q(key)} {q(value)})")
            if observation is not None:
                entries = []
                for key, value in props.items():
                    units = q("lengthMetric") if key in ("w", "fw", "l", "ps", "pd") else "nil"
                    entries.append(f"list({q(key)} {q(value)} {units})")
                entries.extend(('list("nf" nil nil)', 'list("dfm" nil nil)'))
                args = f"inst {name} {inst_name} list({' '.join(entries)})"
                initial_checks.append(f"m2BlockTargetProperties({args} nil)")
                reopen.append(f"m2BlockTargetProperties({args} t)")
            for link in inst.links:
                args = f"{q(link.terminal)} {q(link.net)}"
                create.append(f"m2Wire(cv inst {args})")
                reopen.append(f"m2Net(cv {inst_name} {args})")
                initial_checks.append(f"m2Net(cv {inst_name} {args})")
        lo, hi = symbol.lower_left, symbol.upper_right
        create.extend(
            (
                "m2Require(schCheck(cv))",
                *initial_checks,
                *placement_checks,
                "m2Require(dbSave(cv)) dbClose(cv)",
                f'cv=m2Require(dbOpenCellViewByType({lib} {name} "symbol" "schematicSymbol" "w"))',
                f'm2Require(dbCreateRect(cv list("device" "drawing") '
                f"list(list({lo.x} {lo.y}) list({hi.x} {hi.y}))))",
            )
        )
        reopen.extend(
            (
                "dbClose(cv)",
                f'cv=m2Require(dbOpenCellViewByType({lib} {name} "symbol" "" "r"))',
                f"m2Require(length(cv~>terminals)=={len(cell.ports)})",
            )
        )
        reopen.append(f"m2BlockBody(cv {lo.x} {lo.y} {hi.x} {hi.y})")
        for port in cell.ports:
            origin = symbol_pins[port.name]
            net = q(port.name)
            create.extend(
                (
                    f"net=m2Require(dbCreateNet(cv {net}))",
                    f"m2Require(dbCreateTerm(net {net} {q(port.direction)}))",
                    f'fig=m2Require(dbCreateRect(cv list("pin" "drawing") '
                    f"list(list({origin.x} {origin.y}) list({origin.x}+0.125 {origin.y}+0.125))))",
                    "m2Require(dbCreatePin(net fig))",
                )
            )
            reopen.append(f"m2BlockSymbolPin(cv {net} {q(port.direction)} {origin.x} {origin.y})")
        create.append("m2Require(dbSave(cv)) dbClose(cv)")
        reopen.append("dbClose(cv)")
    return create, reopen


def render_owned_mos_block(
    plan: OwnedMosBlockPlan,
    cdf_frames: Mapping[str, bytes],
    *,
    expected_plan_sha256: Digest,
    owned_library_path: str,
    verify_schematic_port_positions: bool = False,
) -> MosBlockScripts:
    """Render a fresh-library writer and separate read-only saved-view checker."""
    plan = _pinned_block(plan, expected_plan_sha256)
    if (
        re.fullmatch(r"/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+", owned_library_path) is None
        or any(part in (".", "..") for part in owned_library_path.split("/"))
        or plan.output_library in {"basic", "analogLib"}
    ):
        raise ValueError("invalid operator-bound owned block destination")
    create, reopen = _block_generation_parts(
        plan,
        _child_first(plan),
        cdf_frames,
        verify_schematic_port_positions=verify_schematic_port_positions,
    )

    has_target_properties = any(
        isinstance(instance, Mos) and instance.geometry.generation_observation is not None
        for circuit in plan.circuits
        for instance in circuit.instances
    )

    def script(body: list[str]) -> str:
        text = "\n".join(
            (
                _PRELUDE,
                _BLOCK_PRELUDE,
                *([_SCHEMATIC_PORT_CHECK] if verify_schematic_port_positions else []),
                *([_TARGET_PROPERTY_CHECK] if has_target_properties else []),
                "procedure(m2BlockRun() let((cv inst net fig master)",
                *body,
                "t))",
                "let((result) result=errset(m2BlockRun() t) if(result then exit(0) else exit(1)))",
                "",
            )
        )

        if len(text) > 1_048_576:
            raise ValueError("rendered MOS block script exceeds size bound")
        return text

    lib = _quote(plan.output_library)
    if has_target_properties:
        reopen.extend(
            (
                f'printf("OTA17_TARGET_PROPERTIES_END|{expected_plan_sha256}\\n")',
                "drain(poport)",
            )
        )
    return MosBlockScripts(
        plan_sha256=expected_plan_sha256,
        generate=script(
            [
                f'when(ddGetObj({lib}) error("M2_OWNED_LIBRARY_COLLISION"))',
                f"m2Require(ddCreateLib({lib} {_quote(owned_library_path)}))",
                *create,
                f'printf("MOS_BLOCK_SAVED|{expected_plan_sha256}\\n")',
            ]
        ),
        reopen=script(
            [
                *reopen,
                f'printf("MOS_BLOCK_REOPENED_CHECKED|{expected_plan_sha256}\\n")',
            ]
        ),
    )


_SPECTRE_ID = r"[A-Za-z_][A-Za-z0-9_#-]{0,63}"
_BLOCK_DEVICE = re.compile(rf"({_SPECTRE_ID}) \(([^()]{{1,8192}})\) ({_SPECTRE_ID})(?: (.+))?")
_BLOCK_PRODUCT = re.compile(r"(?:([1-9][0-9]{0,5})|\(([1-9][0-9]{0,5})\)\*\(1\))")


def _netlist_dimension(text: str) -> Length:
    if re.fullmatch(rf"(?:{_SPECTRE_DECIMAL}|\({_SPECTRE_DECIMAL}\))", text) is None:
        raise ValueError("unsupported MOS Spectre dimension")
    return Length(value=str(_cdf_length(text.strip("()"))), unit="m")


def _netlist_multiplier(text: str) -> int:
    found = _BLOCK_PRODUCT.fullmatch(text)
    if found is None:
        raise ValueError("unsupported MOS Spectre multiplier")
    return int(found.group(1) or found.group(2))


def _netlist_mos(
    name: str,
    model: str,
    nodes: list[str],
    options: str | None,
    observation: MosGenerationObservation | None = None,
) -> NetlistedMos:
    pairs = [] if options is None else [token.split("=", 1) for token in options.split()]
    if any(len(pair) != 2 for pair in pairs) or len(nodes) != 4:
        raise ValueError("invalid MOS Spectre terminal or option list")
    values = dict(pairs)
    junctions = {"as", "ad", "ps", "pd"}
    expected = {"w", "l", "m", *junctions}
    if len(values) != len(pairs) or set(values) not in (expected, expected | {"simM"}):
        raise ValueError("missing, duplicate or unsupported MOS Spectre option")
    if any(re.fullmatch(_SPECTRE_DECIMAL, values[key]) is None for key in junctions):
        raise ValueError("unsupported MOS Spectre junction geometry")
    multiplicity = _netlist_multiplier(values["m"])
    if "simM" in values and _netlist_multiplier(values["simM"]) != multiplicity:
        raise ValueError("inconsistent MOS Spectre multiplicity")
    if observation is not None:
        expected_factor = f"({multiplicity})*(1)"
        if (
            any(
                _cdf_length(values[key]) != _cdf_length(value)
                for key, value in observation.junctions.model_dump(by_alias=True).items()
            )
            or values["m"] != expected_factor
            or values.get("simM") != expected_factor
        ):
            raise ValueError("netlisted MOS junctions or multiplicity factors differ from target")
    d, g, s, b = nodes
    return NetlistedMos(
        name=name,
        model=model,
        terminals=(d, g, s, b),
        width=_netlist_dimension(values["w"]),
        length=_netlist_dimension(values["l"]),
        multiplier=multiplicity,
    )


def project_mos_block_netlist(
    plan: OwnedMosBlockPlan,
    raw: bytes,
    *,
    expected_plan_sha256: Digest,
    expected_netlist_artifact_sha256: Digest,
) -> tuple[NetlistedCircuit, ...]:
    """Read and compare a bounded DUT-only hierarchical Spectre artifact.

    Compare declared topology and W/L/m, plus junctions and both multiplicity
    factors when the plan carries a per-target generation observation.
    """
    plan = _pinned_block(plan, expected_plan_sha256)
    if len(raw) > 1_048_576 or sha256(raw).hexdigest() != expected_netlist_artifact_sha256:
        raise ValueError("MOS block raw netlist digest or size mismatch")
    cells = {cell.name: cell for cell in _child_first(plan)}
    expected = {name: _netlisted_circuit(cell, cells) for name, cell in cells.items()}
    observations = {
        (cell.name, inst.name): inst.geometry.generation_observation
        for cell in cells.values()
        for inst in cell.instances
        if isinstance(inst, Mos) and inst.geometry.generation_observation is not None
    }
    _, _, analyses, static = partition_input(raw)  # type: ignore[no-untyped-call]
    if analyses:
        raise ValueError("MOS block projection requires a DUT-only Spectre artifact")
    projected: dict[str, NetlistedCircuit] = {}
    current: str | None = None
    ports: tuple[str, ...] = ()
    mos: list[NetlistedMos] = []
    children: list[NetlistedChild] = []
    seen_global = False
    for line in static:
        if current is None:
            if line == "global 0" and not seen_global and not projected:
                seen_global = True
                continue
            head = re.fullmatch(rf"subckt ({_SPECTRE_ID}) (.+)", line)
            if head is None or head.group(1) not in expected or head.group(1) in projected:
                raise ValueError("unexpected or duplicate Spectre subcircuit")
            current = head.group(1)
            formals = head.group(2)
            if formals.startswith("(") and formals.endswith(")"):
                formals = formals[1:-1]
            ports = tuple(formals.split())
            mos, children = [], []
            continue
        if line in ("ends", f"ends {current}"):
            projected[current] = NetlistedCircuit(
                name=current, ports=ports, mos=tuple(mos), children=tuple(children)
            )
            current = None
            continue
        device = _BLOCK_DEVICE.fullmatch(line)
        if device is None:
            raise ValueError("unsupported MOS block Spectre statement")
        name, nodes, model, options = device.groups()
        terminals = nodes.split()
        if any(inst.name == name for inst in expected[current].children):
            if options is not None:
                raise ValueError("parameterized child subcircuit is unsupported")
            children.append(NetlistedChild(name=name, circuit=model, terminals=tuple(terminals)))
        else:
            observation = observations.get((current, name))
            mos.append(_netlist_mos(name, model, terminals, options, observation))
        if len(children) + len(mos) > 128:
            raise ValueError("MOS block Spectre instance bound exceeded")
    if (
        current is not None
        or projected.keys() != expected.keys()
        or any(
            _netlisted_identity(projected[name]) != _netlisted_identity(cell)
            for name, cell in expected.items()
        )
    ):
        raise ValueError("netlisted MOS block topology or effective values mismatch")
    return tuple(projected[name] for name in sorted(projected))


class MosBlockStageReceipt(VariableModel):
    """Operator-normalized receipt from one successful native phase.

    The operator authenticates the original executor record and tree observation.
    The handoff compares the fields against independent pins and actual bytes.
    """

    phase: Literal["save", "reopen", "netlist"]
    operation_id: OperationId
    plan_sha256: Digest
    library: NativeLibrary
    source_cell: RemotePath
    source_tree_sha256: Digest
    bench_cell: RemotePath
    bench_tree_sha256: Digest
    artifact_sha256: Digest
    script_sha256: Digest | None = None

    @model_validator(mode="after")
    def script_scope(self) -> Self:
        if (self.script_sha256 is None) != (self.phase == "netlist"):
            raise ValueError("save and reopen receipts require their exact script digests")
        return self


class MosBlockHandoffPins(VariableModel):
    """Pins independently obtained from the operator's reviewed operation records."""

    plan_sha256: Digest
    save_receipt_sha256: Digest
    reopen_receipt_sha256: Digest
    netlist_receipt_sha256: Digest
    raw_netlist_sha256: Digest
    full_netlist_sha256: Digest
    bench_plan_sha256: Digest
    bench_conditions_sha256: Digest


class MosBlockRegistrationHandoff(VariableModel):
    """Local source candidate for native registration, with no admission authority."""

    schema_version: Literal[1] = 1
    status: Literal["LOCAL_SOURCE_EVIDENCE_MATCHED"] = "LOCAL_SOURCE_EVIDENCE_MATCHED"
    provenance: Literal["OPERATOR_AUTHENTICATION_REQUIRED"] = "OPERATOR_AUTHENTICATION_REQUIRED"
    execution_authorized: Literal[False] = False
    operation_id: OperationId
    binding: RevisionBinding
    library: NativeLibrary
    source_cell: RemotePath
    source_tree_sha256: Digest
    bench_cell: RemotePath
    bench_tree_sha256: Digest
    pins: MosBlockHandoffPins
    static_statements_sha256: Digest

    @property
    def handoff_sha256(self) -> Digest:
        return canonical_digest(self)


class ObservedSchematicPort(Port):
    cell: Name


class SchematicPortReadback(VariableModel):
    """Coordinates captured from saved schematic pin instances by the operator."""

    operation_id: OperationId
    plan_sha256: Digest
    output_library: BindingName
    reopened_tree_sha256: Digest
    library_tree_sha256: Digest
    origin_basis: Literal["schematic_pin_instance_xy"]
    ports: Annotated[tuple[ObservedSchematicPort, ...], Field(min_length=1, max_length=31 * 64)]


def project_schematic_port_readback(
    plan: OwnedMosBlockPlan,
    handoff: MosBlockRegistrationHandoff,
    raw: bytes,
    *,
    expected_handoff_sha256: Digest,
    expected_observation_sha256: Digest,
) -> dict[str, tuple[Port, ...]]:
    """Check only the schematic ports of a pinned readback, without supplying missing geometry.

    The caller authenticates the capture and confirms the unique native pin-to-terminal
    association. This projection does not supply the other reopened evidence rows.
    """
    handoff = MosBlockRegistrationHandoff.model_validate_json(handoff.model_dump_json())
    if handoff.handoff_sha256 != expected_handoff_sha256:
        raise ValueError("schematic port handoff digest mismatch")
    plan = _pinned_block(plan, handoff.pins.plan_sha256)
    _closed_document(raw)
    if sha256(raw).hexdigest() != expected_observation_sha256:
        raise ValueError("schematic port observation digest mismatch")
    captured = SchematicPortReadback.model_validate_json(raw)
    if (
        plan.binding != handoff.binding
        or handoff.library.name != plan.output_library
        or handoff.source_cell != f"{handoff.library.path}/{plan.root}"
        or captured.operation_id != handoff.operation_id
        or captured.plan_sha256 != handoff.pins.plan_sha256
        or captured.output_library != plan.output_library
        or captured.reopened_tree_sha256 != handoff.source_tree_sha256
        or captured.library_tree_sha256 != handoff.library.tree_sha256
    ):
        raise ValueError("schematic port observation source binding mismatch")

    observed: dict[str, list[Port]] = {}
    for row in captured.ports:
        observed.setdefault(row.cell, []).append(
            Port.model_validate(row.model_dump(exclude={"cell"}))
        )
    projection = {
        name: tuple(sorted(ports, key=lambda port: port.name)) for name, ports in observed.items()
    }
    expected = {
        cell.name: tuple(sorted(cell.ports, key=lambda port: port.name))
        for cell in _child_first(plan)
    }
    if projection != expected:
        raise ValueError("schematic port inventory, association or origin mismatch")
    return projection


def _check_mos_phase_stdout(
    raw: bytes,
    markers: tuple[str, ...],
    script: str,
    receipt: MosBlockStageReceipt,
) -> None:
    if len(raw) > 65_536 or sha256(raw).hexdigest() != receipt.artifact_sha256:
        raise ValueError("MOS phase stdout digest or size mismatch")
    observed_markers = [
        line
        for line in raw.splitlines()
        if line.startswith(
            (b"MOS_BLOCK_SAVED|", b"MOS_BLOCK_REOPENED_CHECKED|", b"RESEARCH_BENCH_")
        )
    ]
    expected = [marker.encode("ascii") for marker in markers]
    if (
        observed_markers != expected
        or sha256(script.encode("ascii")).hexdigest() != receipt.script_sha256
    ):
        raise ValueError("MOS phase completion marker or executed script mismatch")


def _check_mos_target_stdout(
    plan: OwnedMosBlockPlan,
    raw: bytes,
    artifact_sha256: Digest,
    cdf_frames: Mapping[str, bytes],
) -> None:
    targets = [
        (cell.name, instance, target)
        for cell in plan.circuits
        for instance in cell.instances
        if isinstance(instance, Mos)
        if (target := instance.geometry.generation_observation) is not None
    ]
    if not targets:
        return
    from cadence_mcp_bridge.ota_reopen_evidence import parse_ota_reopen_properties

    if any(cell != plan.root for cell, _, _ in targets):
        raise ValueError("OTA target readback requires a flat root")
    reopened = parse_ota_reopen_properties(
        raw,
        stdout_sha256=artifact_sha256,
        plan_sha256=canonical_digest(plan),
        cell=plan.root,
        instance_names=[instance.name for _, instance, _ in targets],
    )
    for _, instance, target in targets:
        frame = cdf_frames.get(target.cdf_sha256)
        if frame is None or sha256(frame).hexdigest() != target.cdf_sha256:
            raise ValueError("missing or stale OTA target CDF")
        values = _block_cdf_values(instance, parse_frame(frame))
        actual = {
            name: (entry.oa_value, entry.cdf_units)
            for name, entry in reopened[instance.name].items()
            if name not in ("dfm", "nf")
        }
        expected = {
            name: (value, "lengthMetric" if name in ("w", "fw", "l", "ps", "pd") else None)
            for name, value in values.items()
        }
        if actual != expected:
            raise ValueError("independent OTA reopen properties differ from planned instance")


def _dut_subcircuits(static: list[str], expected: set[str]) -> dict[str, tuple[str, ...]]:
    """Retain exact normalized DUT definitions, including subcircuit port order."""
    scopes: list[str] = []
    block: list[str] = []
    found: dict[str, tuple[str, ...]] = {}
    for line in static:
        words = line.split()
        if words[0] == "subckt" or words[:2] == ["inline", "subckt"]:
            name = words[1] if words[0] == "subckt" else words[2]
            if name in expected and (scopes or name in found):
                raise ValueError("duplicate or nested DUT definition in Spectre input")
            scopes.append(name)
            if len(scopes) == 1 and name in expected:
                block = []
        if scopes and scopes[0] in expected:
            block.append(line)
        if words[0] == "ends":
            name = scopes.pop()
            if not scopes and name in expected:
                found[name] = tuple(block)
    if found.keys() != expected:
        raise ValueError("Spectre input does not contain the complete DUT closure")
    return found


def _check_full_bench_dut_identity(
    plan: OwnedMosBlockPlan,
    full_netlist: bytes,
    raw_dut_netlist: bytes,
    expected_full_netlist_sha256: Digest,
) -> Digest:
    if (
        len(full_netlist) > ADE_INPUT_LIMIT
        or sha256(full_netlist).hexdigest() != expected_full_netlist_sha256
    ):
        raise ValueError("full bench netlist digest or size mismatch")
    expected = {cell.name for cell in plan.circuits}
    _, _, analyses, full_static = partition_input(full_netlist)  # type: ignore[no-untyped-call]
    _, _, _, dut_static = partition_input(raw_dut_netlist)  # type: ignore[no-untyped-call]
    if not analyses or _dut_subcircuits(full_static, expected) != _dut_subcircuits(
        dut_static, expected
    ):
        raise ValueError("DUT projection differs from the full bench netlist")
    static_digest: Digest = static_fingerprint(full_static)  # type: ignore[no-untyped-call]
    return static_digest


def _verify_mos_block_handoff(
    plan: OwnedMosBlockPlan,
    scripts: MosBlockScripts,
    *,
    pins: MosBlockHandoffPins,
    bench_name: str,
    save_markers: tuple[str, ...],
    reopen_markers: tuple[str, ...],
    saved: MosBlockStageReceipt,
    reopened: MosBlockStageReceipt,
    netlisted: MosBlockStageReceipt,
    save_stdout: bytes,
    reopen_stdout: bytes,
    raw_netlist: bytes,
    full_netlist: bytes,
) -> MosBlockRegistrationHandoff:
    """Compare the exact generation, read-only reopen and DUT capture as one operation."""
    pins = MosBlockHandoffPins.model_validate_json(pins.model_dump_json())
    plan = _pinned_block(plan, pins.plan_sha256)
    saved, reopened, netlisted = (
        MosBlockStageReceipt.model_validate_json(receipt.model_dump_json())
        for receipt in (saved, reopened, netlisted)
    )
    library = saved.library
    source_cell = f"{library.path}/{plan.root}"
    if (
        library.name != plan.output_library
        or scripts.plan_sha256 != pins.plan_sha256
        or bench_name == plan.root
        or saved.bench_cell != f"{library.path}/{bench_name}"
    ):
        raise ValueError("MOS handoff output library mismatch")
    for phase, receipt, digest in (
        ("save", saved, pins.save_receipt_sha256),
        ("reopen", reopened, pins.reopen_receipt_sha256),
        ("netlist", netlisted, pins.netlist_receipt_sha256),
    ):
        if (
            receipt.phase != phase
            or canonical_digest(receipt) != digest
            or receipt.operation_id != saved.operation_id
            or receipt.plan_sha256 != pins.plan_sha256
            or receipt.library != library
            or receipt.source_cell != source_cell
            or receipt.source_tree_sha256 != saved.source_tree_sha256
            or receipt.bench_cell != saved.bench_cell
            or receipt.bench_tree_sha256 != saved.bench_tree_sha256
        ):
            raise ValueError("MOS handoff phase, operation, plan or source binding mismatch")
    _check_mos_phase_stdout(save_stdout, save_markers, scripts.generate, saved)
    _check_mos_phase_stdout(reopen_stdout, reopen_markers, scripts.reopen, reopened)
    if netlisted.artifact_sha256 != pins.full_netlist_sha256:
        raise ValueError("MOS handoff netlist receipt digest mismatch")
    project_mos_block_netlist(
        plan,
        raw_netlist,
        expected_plan_sha256=pins.plan_sha256,
        expected_netlist_artifact_sha256=pins.raw_netlist_sha256,
    )
    static_digest = _check_full_bench_dut_identity(
        plan, full_netlist, raw_netlist, pins.full_netlist_sha256
    )
    return MosBlockRegistrationHandoff(
        operation_id=saved.operation_id,
        binding=plan.binding,
        library=library,
        source_cell=source_cell,
        source_tree_sha256=saved.source_tree_sha256,
        bench_cell=saved.bench_cell,
        bench_tree_sha256=saved.bench_tree_sha256,
        pins=pins,
        static_statements_sha256=static_digest,
    )


def verify_mos_block_handoff(
    plan: OwnedMosBlockPlan,
    bench_plan: ResearchBenchPlan,
    cdf_frames: Mapping[str, bytes],
    *,
    pins: MosBlockHandoffPins,
    conditions: BenchNetlistConditions,
    saved: MosBlockStageReceipt,
    reopened: MosBlockStageReceipt,
    netlisted: MosBlockStageReceipt,
    save_stdout: bytes,
    reopen_stdout: bytes,
    raw_netlist: bytes,
    full_netlist: bytes,
) -> MosBlockRegistrationHandoff:
    """Check the package's exact composite build and its complete bench baseline."""
    from cadence_mcp_bridge.research_bench import (
        render_research_bench,
        verify_research_bench_netlist,
    )

    pins = MosBlockHandoffPins.model_validate_json(pins.model_dump_json())
    plan = _pinned_block(plan, pins.plan_sha256)
    saved = MosBlockStageReceipt.model_validate_json(saved.model_dump_json())
    scripts = render_research_bench(
        bench_plan,
        plan,
        cdf_frames,
        expected_plan_sha256=pins.bench_plan_sha256,
        owned_library_path=saved.library.path,
    )
    handoff = _verify_mos_block_handoff(
        plan,
        scripts,
        pins=pins,
        bench_name=scripts.bench_cell,
        save_markers=scripts.save_markers,
        reopen_markers=scripts.reopen_markers,
        saved=saved,
        reopened=reopened,
        netlisted=netlisted,
        save_stdout=save_stdout,
        reopen_stdout=reopen_stdout,
        raw_netlist=raw_netlist,
        full_netlist=full_netlist,
    )
    _check_mos_target_stdout(plan, reopen_stdout, reopened.artifact_sha256, cdf_frames)
    verify_research_bench_netlist(
        bench_plan,
        plan,
        full_netlist,
        raw_netlist,
        expected_plan_sha256=pins.bench_plan_sha256,
        expected_netlist_sha256=pins.full_netlist_sha256,
        expected_dut_netlist_sha256=pins.raw_netlist_sha256,
        conditions=conditions,
        expected_conditions_sha256=pins.bench_conditions_sha256,
    )
    return handoff


def verify_mos_block_registration_source(
    handoff: MosBlockRegistrationHandoff,
    observation: RegistrationObservation,
    *,
    expected_handoff_sha256: Digest,
    expected_observation_sha256: Digest,
) -> None:
    """Check the bench registration source and the authenticated DUT library dependency.

    The full baseline simulation netlist and ADE/model bindings have their own
    existing registration checks. No comparison assumes a bench tree is the DUT.
    """
    handoff = MosBlockRegistrationHandoff.model_validate_json(handoff.model_dump_json())
    observation = RegistrationObservation.model_validate_json(observation.model_dump_json())
    libraries = [
        library for library in observation.libraries if library.name == handoff.library.name
    ]
    if (
        handoff.handoff_sha256 != expected_handoff_sha256
        or canonical_digest(observation) != expected_observation_sha256
        or observation.source_cell != handoff.bench_cell
        or observation.ade.design_id != handoff.binding.design_id
        or observation.ade.source_tree_sha256 != handoff.bench_tree_sha256
        or observation.baseline_input_sha256 != handoff.pins.full_netlist_sha256
        or observation.ade.static_statements_sha256 != handoff.static_statements_sha256
        or libraries != [handoff.library]
    ):
        raise ValueError("MOS block registration source or library fingerprint mismatch")
