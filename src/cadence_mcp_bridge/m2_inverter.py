"""Operator-only, observed-CDF-bound inverter writer for an exclusive owned library.

No transport, public MCP tool, production registry promotion or execution grant.
The caller authenticates the frame/library snapshots and owns the destination.
The original synthetic plan/registry contract remains unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Literal

from pydantic import model_validator

from cadence_mcp_bridge import _native_rendering as native_rendering
from cadence_mcp_bridge.m2_cdf import CdfSource, parse_frame
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest


class OwnedInverterPlan(VariableModel):
    binding: RevisionBinding
    cdf_frame_sha256: Digest
    output_library: str
    dut_cell: str
    testbench_cell: str
    nmos_library: str
    nmos_cell: str
    pmos_library: str
    pmos_cell: str
    supply_v: Literal["1"] = "1"
    load_f: Literal["1e-12"] = "1e-12"
    input_variable: Literal["m2_vin"] = "m2_vin"
    provenance: Literal["operator_bound_actual_cdf_observation"] = (
        "operator_bound_actual_cdf_observation"
    )

    @model_validator(mode="after")
    def closed_names(self) -> OwnedInverterPlan:
        for library, cell in (
            (self.output_library, self.dut_cell),
            (self.output_library, self.testbench_cell),
            (self.nmos_library, self.nmos_cell),
            (self.pmos_library, self.pmos_cell),
        ):
            CdfSource(library, cell)
        if (
            self.dut_cell == self.testbench_cell
            or self.output_library in (self.nmos_library, self.pmos_library, "analogLib", "basic")
            or (self.nmos_library, self.nmos_cell) == (self.pmos_library, self.pmos_cell)
        ):
            raise ValueError("owned target or device-role collision")
        return self

    @property
    def semantic_sha256(self) -> str:
        return canonical_digest(self)


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _mos_parameters(device: dict[str, object]) -> dict[str, str]:
    rows = device["parameters"]
    if not isinstance(rows, tuple):
        raise ValueError("missing observed CDF parameters")
    selected: dict[str, str] = {}
    for name in ("w", "fw", "l", "m", "fingers", "model", "as", "ad", "ps", "pd"):
        entries = [row for row in rows if row[:2] == ("effective", name)]
        if len(entries) != 1 or not isinstance(entries[0][5], str):
            raise ValueError("missing observed MOS value")
        value = entries[0][5]
        if name == "model":
            CdfSource("ObservedModel", value)
        elif name in ("m", "fingers"):
            if re.fullmatch(r"[1-9][0-9]{0,5}", value) is None:
                raise ValueError("observed multiplicity is not a bounded integer")
        else:
            if (name not in ("as", "ad") and entries[0][3] != "lengthMetric") or re.fullmatch(
                r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,2})?[afpnum]?", value
            ) is None:
                raise ValueError("observed length needs explicit numeric units")
            if Decimal(value.rstrip("afpnum")) <= 0 or len(value) > 32:
                raise ValueError("observed length must be positive and bounded")
        selected[name] = value
    # This bounded slice preserves observed single-finger devices. It does not
    # infer total/per-finger semantics or a general nf range from a name.
    if selected["fingers"] != "1" or selected["w"] != selected["fw"]:
        raise ValueError("only observed equal-width single-finger MOS is supported")
    for name, expected in (("simW", 'iPar("fw")'), ("simM", 'iPar("m")*iPar("fingers")')):
        matches = [row for row in rows if row[:2] == ("effective", name)]
        if len(matches) != 1 or matches[0][5] != expected:
            raise ValueError("unknown derived MOS netlist expression")
    return selected


def verify_generated_netlist(plan: OwnedInverterPlan, frame: bytes, native: bytes) -> None:
    """Compare effective generated topology/values against independent CDF plan.

    A fingerprint computed from the candidate alone cannot establish this match.
    This deliberately accepts only the observed standard-VM single-finger form.
    """
    devices = observed_devices(plan, frame)
    _, _, _, static = native_rendering.partition_input(native)  # type: ignore[no-untyped-call]
    expected_tail = [
        f"ends {plan.dut_cell}",
        f"DUT (vdd vin vout 0) {plan.dut_cell}",
        "VDD (vdd 0) vsource dc=1 type=dc",
        "VIN (vin 0) vsource dc=m2_vin type=pulse val0=0 val1=1 period=4n "
        "delay=1n rise=100p fall=100p width=2n",
        "CL (vout 0) capacitor c=1p",
    ]
    expected = ["global 0", f"subckt {plan.dut_cell} vdd vin vout vss"]
    for device, name, rail in zip(devices[:2], ("MN", "MP"), ("vss", "vdd"), strict=True):
        values = _mos_parameters(device)
        candidates = [line for line in static if line.startswith(name + " ")]
        prefix = f"{name} (vout vin {rail} {rail}) {values['model']} "
        if len(candidates) != 1 or not candidates[0].startswith(prefix):
            raise ValueError("generated MOS topology/model mismatch")
        options = candidates[0][len(prefix) :].split()
        if any(token.count("=") != 1 for token in options):
            raise ValueError("generated MOS options invalid")
        pairs = [token.split("=", 1) for token in options]
        actual = dict(pairs)
        expected_options = {key: values[key] for key in ("l", "as", "ad", "ps", "pd")}
        expected_options.update(
            w=f"({values['fw']})", m=f"({values['m']})*(1)", simM=f"({values['m']})*(1)"
        )
        if len(actual) != len(pairs) or actual != expected_options:
            raise ValueError("generated effective MOS values mismatch")
        expected.append(candidates[0])
    expected.extend(expected_tail)
    actual_devices = [
        line
        for line in static
        if re.match(r"(?:[A-Za-z][A-Za-z0-9_#-]{0,63} \(|global |(?:inline )?subckt |ends )", line)
    ]
    if actual_devices != expected:
        raise ValueError("generated hierarchy/stimulus/load mismatch")


def observed_devices(plan: OwnedInverterPlan, frame: bytes) -> tuple[dict[str, object], ...]:
    """Resolve exact observations; no inferred PDK parameter ranges or callbacks."""
    plan = OwnedInverterPlan.model_validate_json(plan.model_dump_json())
    if (
        not frame.startswith(b"M2_CDF_V2\n")
        or hashlib.sha256(frame).hexdigest() != plan.cdf_frame_sha256
    ):
        raise ValueError("CDF frame digest mismatch")
    devices = parse_frame(frame)
    selected = []
    for library, cell, terminals, component in (
        (plan.nmos_library, plan.nmos_cell, ("D", "G", "S", "B"), None),
        (plan.pmos_library, plan.pmos_cell, ("D", "G", "S", "B"), None),
        ("analogLib", "vdc", ("PLUS", "MINUS"), "vsource"),
        ("analogLib", "vpulse", ("PLUS", "MINUS"), "vsource"),
        ("analogLib", "cap", ("PLUS", "MINUS"), "capacitor"),
    ):
        matches = [d for d in devices if (d["library"], d["cell"]) == (library, cell)]
        if len(matches) != 1:
            raise ValueError("CDF device selection is missing or ambiguous")
        device = matches[0]
        observed_terminals = device["terminals"]
        if not isinstance(observed_terminals, tuple) or set(observed_terminals) != set(terminals):
            raise ValueError("observed symbol terminal set mismatch")
        if device["spectre"] != (
            ("base", component, terminals),
            ("effective", component, terminals),
        ):
            raise ValueError("observed Spectre terminal/component contract mismatch")
        metadata = device.get("metadata_fields", ())
        if not isinstance(metadata, tuple):
            raise ValueError("missing typed CDF observations")
        for scope in ("base", "effective"):
            for field in ("simInfo", "spectre", "termOrder", "instParameters"):
                if not any(row[:4] == (scope, field, "observed", "list") for row in metadata):
                    raise ValueError("required typed CDF metadata missing")
        selected.append(device)
    for device in selected[:2]:
        _mos_parameters(device)
    requirements = (
        (selected[2], {"vdc": "voltage"}),
        (
            selected[3],
            {
                "v1": "voltage",
                "v2": "voltage",
                "vdc": "voltage",
                "td": "time",
                "tr": "time",
                "tf": "time",
                "pw": "time",
                "per": "time",
                "dc": "voltage",
            },
        ),
        (selected[4], {"c": "capacitance"}),
    )
    for device, required in requirements:
        rows = device["parameters"]
        if not isinstance(rows, tuple):
            raise ValueError("missing primitive CDF observations")
        for name, unit in required.items():
            if not any(row[:2] == ("base", name) and row[3] == unit for row in rows):
                raise ValueError("primitive CDF parameter/unit mismatch")
    return tuple(selected)


_PRELUDE = r"""
procedure(m2Require(value) unless(value error("M2_OWNED_READBACK_FAILED")) value)
procedure(m2Wire(cv inst termName netName)
 let((term fig start stop wires span otherFig otherPoint separation)
  term=car(setof(termEntry inst~>master~>terminals termEntry~>name==termName))
  m2Require(term) fig=car(car(term~>pins)~>figs) m2Require(fig)
  start=dbTransformPoint(centerBox(fig~>bBox) inst~>transform)
  span=0.0625
  foreach(other inst~>master~>terminals
   unless(other==term
    otherFig=car(car(other~>pins)~>figs) m2Require(otherFig)
    otherPoint=dbTransformPoint(centerBox(otherFig~>bBox) inst~>transform)
    separation=max(abs(xCoord(otherPoint)-xCoord(start))
                   abs(yCoord(otherPoint)-yCoord(start)))
    m2Require(separation>0) span=min(span separation/8.0)))
  stop=list(xCoord(start)+span yCoord(start))
  wires=schCreateWire(cv "draw" "full" list(start stop) span span 0)
  m2Require(wires)
  foreach(wire wires m2Require(schCreateWireLabel(cv wire stop netName
   "lowerLeft" "R0" "stick" 0.0625 nil))) t))
procedure(m2Instance(cv lib cell name x y)
 let((master inst)
  master=dbOpenCellViewByType(lib cell "symbol" "" "r") m2Require(master)
  inst=dbCreateInst(cv master name list(x y) "R0") m2Require(inst) inst))
procedure(m2Param(inst name value)
 m2Require(dbReplaceProp(inst name "string" value)))
procedure(m2Net(cv instance terminal expected)
 let((inst link)
  inst=car(setof(entry cv~>instances entry~>name==instance)) m2Require(inst)
  link=car(setof(entry inst~>instTerms entry~>name==terminal)) m2Require(link)
  m2Require(link~>net~>name==expected)))
procedure(m2Property(cv instance name expected)
 let((inst prop)
  inst=car(setof(entry cv~>instances entry~>name==instance)) m2Require(inst)
  prop=dbFindProp(inst name) m2Require(prop) m2Require(prop~>value==expected)))
procedure(m2Port(cv name direction x y)
 let((master)
  master=dbOpenCellViewByType("basic" "iopin" "symbol" "" "r") m2Require(master)
  m2Require(schCreatePin(cv master name direction nil list(x y) "R0"))))
"""


def render_generator(plan: OwnedInverterPlan, frame: bytes, *, owned_library_path: str) -> bytes:
    """Render only new cells; runner must bind a fresh path below its workspace.

    Collision checks precede writes; failures retain partial cells. Every named
    terminal/property is checked before save and after reopen. No delete/rollback
    overwrite, original DUT clone, CDF callback or arbitrary expression input.
    """
    devices = observed_devices(plan, frame)
    if re.fullmatch(r"/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+", owned_library_path) is None or any(
        part in (".", "..") for part in owned_library_path.split("/")
    ):
        raise ValueError("invalid operator-bound owned library path")
    q = _quote
    lib, dut, bench = map(q, (plan.output_library, plan.dut_cell, plan.testbench_cell))
    lines = [_PRELUDE, "procedure(m2Create() let((cv sym inst net fig port)"]
    lines.append(
        "foreach(api '(schCreatePin dbCreatePin dbCreateTerm dbCreateNet dbCreateRect) "
        "m2Require(isCallable(api)))"
    )
    lines += [
        f'when(ddGetObj({lib}) error("M2_OWNED_LIBRARY_COLLISION"))',
        f"m2Require(ddCreateLib({lib} {q(owned_library_path)}))",
        f'cv=dbOpenCellViewByType({lib} {dut} "schematic" "schematic" "w") m2Require(cv)',
    ]
    maps: list[tuple[str, dict[str, str], dict[str, str]]] = []
    for index, (device, name, rail) in enumerate(
        zip(devices[:2], ("MN", "MP"), ("vss", "vdd"), strict=True)
    ):
        props = _mos_parameters(device)
        links = {"D": "vout", "G": "vin", "S": rail, "B": rail}
        lines.append(
            f"inst=m2Instance(cv {q(str(device['library']))} {q(str(device['cell']))} "
            f"{q(name)} {index * 4} 0)"
        )
        lines += [f"m2Param(inst {q(key)} {q(value)})" for key, value in props.items()]
        lines += [f"m2Wire(cv inst {q(key)} {q(value)})" for key, value in links.items()]
        maps.append((name, links, props))
    for index, name in enumerate(("vin", "vout", "vdd", "vss")):
        direction = "input" if name == "vin" else "output" if name == "vout" else "inputOutput"
        lines += [f"m2Port(cv {q(name)} {q(direction)} {100 + index * 2} 100)"]

    def checks(items: list[tuple[str, dict[str, str], dict[str, str]]]) -> list[str]:
        result = []
        for name, links, props in items:
            result += [f"m2Net(cv {q(name)} {q(key)} {q(value)})" for key, value in links.items()]
            result += [
                f"m2Property(cv {q(name)} {q(key)} {q(value)})" for key, value in props.items()
            ]
        return result

    lines += [
        "m2Require(schCheck(cv))",
        *checks(maps),
        "m2Require(dbSave(cv)) dbClose(cv)",
        f'cv=dbOpenCellViewByType({lib} {dut} "schematic" "" "r") m2Require(cv)',
        *checks(maps),
        "m2Require(length(cv~>terminals)==4) dbClose(cv)",
        f'sym=dbOpenCellViewByType({lib} {dut} "symbol" "schematicSymbol" "w") m2Require(sym)',
        'm2Require(dbCreateRect(sym list("device" "drawing") list(list(-1 -1) list(1 1))))',
    ]
    for index, name in enumerate(("vin", "vout", "vdd", "vss")):
        x, y = ((-1, 0), (1, 0), (0, 1), (0, -1))[index]
        direction = "input" if name == "vin" else "output" if name == "vout" else "inputOutput"
        lines += [
            f"net=dbCreateNet(sym {q(name)}) m2Require(net)",
            f"m2Require(dbCreateTerm(net {q(name)} {q(direction)}))",
            f'fig=dbCreateRect(sym list("pin" "drawing") list(list({x} {y}) '
            f"list({x + 0.125} {y + 0.125}))) m2Require(fig)",
            "m2Require(dbCreatePin(net fig))",
        ]
    lines += [
        "m2Require(length(sym~>terminals)==4) m2Require(dbSave(sym)) dbClose(sym)",
        f'cv=dbOpenCellViewByType({lib} {bench} "schematic" "schematic" "w") m2Require(cv)',
        f'inst=m2Instance(cv {lib} {dut} "DUT" 0 0)',
    ]
    dut_links = {"vin": "vin", "vout": "vout", "vdd": "vdd", "vss": "gnd!"}
    lines += [f"m2Wire(cv inst {q(key)} {q(value)})" for key, value in dut_links.items()]
    bench_maps: list[tuple[str, dict[str, str], dict[str, str]]] = [("DUT", dut_links, {})]
    for cell, name, x, props, links in (
        ("vdc", "VDD", 4, {"vdc": "1"}, {"PLUS": "vdd", "MINUS": "gnd!"}),
        (
            "vpulse",
            "VIN",
            8,
            {
                "v1": "0",
                "v2": "1",
                "dc": "m2_vin",
                "vdc": "m2_vin",
                "td": "1n",
                "tr": "100p",
                "tf": "100p",
                "pw": "2n",
                "per": "4n",
            },
            {"PLUS": "vin", "MINUS": "gnd!"},
        ),
        ("cap", "CL", 12, {"c": "1p"}, {"PLUS": "vout", "MINUS": "gnd!"}),
    ):
        lines += [f'inst=m2Instance(cv "analogLib" {q(cell)} {q(name)} {x} 0)']
        lines += [f"m2Param(inst {q(key)} {q(value)})" for key, value in props.items()]
        lines += [f"m2Wire(cv inst {q(key)} {q(value)})" for key, value in links.items()]
        bench_maps.append((name, links, props))
    lines += [
        "m2Require(schCheck(cv))",
        *checks(bench_maps),
        "m2Require(dbSave(cv)) dbClose(cv)",
        f'cv=dbOpenCellViewByType({lib} {bench} "schematic" "" "r") m2Require(cv)',
        *checks(bench_maps),
        "m2Require(length(cv~>instances)==4) dbClose(cv)",
        'port=outfile("owned-readback.txt") m2Require(port)',
        f'fprintf(port "M2_OWNED_READBACK_V1|{plan.semantic_sha256}\\nCOMPLETE\\n") '
        "close(port) t))",
        "let((result) result=errset(m2Create() t) if(result then exit(0) else exit(1)))",
    ]
    return ("\n".join(lines) + "\n").encode("ascii")
