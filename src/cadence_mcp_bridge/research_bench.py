"""Bounded research testbench generation and Spectre input comparison."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from decimal import Decimal, localcontext
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from cadence_mcp_bridge._native_rendering import partition_input, statements
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.m2_cdf import parse_frame
from cadence_mcp_bridge.m2_inverter import _quote
from cadence_mcp_bridge.research_circuit import (
    Capacitor,
    Child,
    Circuit,
    Master,
    MosBlockScripts,
    OwnedMosBlockPlan,
    Pulse,
    ResearchCircuit,
    VoltageSource,
    _inverter_bench,
    plan_owned_mos_block,
    project_mos_block_netlist,
    render_owned_mos_block,
    render_research_positioned_instance,
)
from cadence_mcp_bridge.variable_contracts import (
    BindingName,
    Digest,
    VariableModel,
    canonical_digest,
    number_text,
)

_REFERENCE_INVERTER_PULSE = Pulse(
    low_v="0",
    high_v="1",
    delay_s="1e-9",
    rise_s="100e-12",
    fall_s="100e-12",
    width_s="2e-9",
    period_s="4e-9",
)
_SOURCE9_PULSE = Pulse(
    low_v="0",
    high_v="1",
    delay_s="10e-9",
    rise_s="100e-12",
    fall_s="100e-12",
    width_s="65e-9",
    period_s="150e-9",
)
_PRIMITIVES = {
    "VDD": ("vdc", {"vdc": "1"}),
    "VIN": (
        "vpulse",
        {
            "v1": "0",
            "v2": "1",
            "dc": "m2_vin",
            "vdc": "m2_vin",
            "td": "10n",
            "tr": "100p",
            "tf": "100p",
            "pw": "65n",
            "per": "150n",
        },
    ),
    "CL": ("cap", {"c": "1p"}),
}
_BENCH_SIZE_LIMIT = 1_048_576
_SOURCE9_TOP_LEVEL_CONTROLS = {
    "dcOpInfo": "info",
    "designParamVals": "info",
    "element": "info",
    "finalTimeOP": "info",
    "global": "0",
    "modelParameter": "info",
    "outputParameter": "info",
    "primitives": "info",
    "saveOptions": "options",
    "simulatorOptions": "options",
    "subckts": "info",
}


class ResearchBenchPlan(VariableModel):
    definition_sha256: Digest
    dut_plan_sha256: Digest
    bench: Circuit
    primitive_cdf_sha256: Digest | None = None
    signed_ac_evidence_sha256: Digest | None = None
    signed_ac_vsin_pair: bool = False
    signed_ac_vsin_dc: bool = Field(default=False, exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def signed_ac_requires_primitive_cdf(self) -> ResearchBenchPlan:
        if self.signed_ac_evidence_sha256 is not None and self.primitive_cdf_sha256 is None:
            raise ValueError("signed AC requires a verified primitive CDF")
        if self.signed_ac_vsin_pair and self.signed_ac_evidence_sha256 is None:
            raise ValueError("vsin pair requires signed AC evidence")
        if self.signed_ac_vsin_dc and not self.signed_ac_vsin_pair:
            raise ValueError("vsin DC verification requires the reviewed differential pair")
        return self

    @model_serializer(mode="wrap")
    def preserve_legacy_identity(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data: dict[str, object] = handler(self)
        if self.primitive_cdf_sha256 is None:
            data.pop("primitive_cdf_sha256", None)
        if self.signed_ac_evidence_sha256 is None:
            data.pop("signed_ac_evidence_sha256", None)
        if not self.signed_ac_vsin_pair:
            data.pop("signed_ac_vsin_pair", None)
        return data


_ObservedScalar = Annotated[str, Field(min_length=1, max_length=64)]
_ObservedNode = Annotated[str, Field(pattern=r"^(?:0|[A-Za-z][A-Za-z0-9_#-]{0,63})$")]


class SignedAcSourceObservation(VariableModel):
    """Normalized saved voltage source properties and their Spectre statement."""

    instance: BindingName
    master: Literal["analogLib/vdc/symbol", "analogLib/vsin/symbol"]
    plus: _ObservedNode
    minus: _ObservedNode
    dc_string: _ObservedScalar
    acm_string: _ObservedScalar
    acp_absent: Literal[True]
    statement: Annotated[str, Field(min_length=1, max_length=512)]
    sine_string_properties: (
        dict[Literal["va", "freq", "filenums", "sinephase"], _ObservedScalar] | None
    ) = None


class SignedAcSourceEvidence(VariableModel):
    """Operator-reviewed and pinned normalization of same-master native evidence."""

    primitive_cdf_sha256: Digest
    native_manifest_sha256: Digest
    saved_tree_sha256: Digest
    reopen_artifact_sha256: Digest
    effective_netlist_sha256: Digest
    sources: tuple[SignedAcSourceObservation, SignedAcSourceObservation]


class ResearchBenchScripts(MosBlockScripts):
    bench_plan_sha256: Digest
    bench_cell: str
    save_markers: tuple[str, ...]
    reopen_markers: tuple[str, ...]


class BenchNetlistConditions(VariableModel):
    """Fixed inputs from the bench registration for one analysis."""

    parameters: dict[str, str]
    includes: tuple[tuple[str, str], ...]
    analyses: tuple[tuple[str, str], ...]
    fixed_top_level: tuple[str, ...]


def _check_bench(bench: Circuit, dut: str) -> None:
    if bench.ports or bench.symbol is not None or bench.wires:
        raise ValueError("Source9 bench requires label stubs and no external ports or symbol")
    devices = []
    for device in bench.instances:
        if device.name == "VIN" and isinstance(device, VoltageSource):
            if device.pulse != _SOURCE9_PULSE:
                raise ValueError("unsupported Source9 stimulus pulse")
            # Check the shared inverter contract with its original timing profile.
            device = device.model_copy(update={"pulse": _REFERENCE_INVERTER_PULSE})
        devices.append(device)
    if not _inverter_bench(bench.model_copy(update={"instances": tuple(devices)}), dut):
        raise ValueError("unsupported Source9 testbench components or connectivity")


def _check_profile(
    bench: Circuit,
    dut_plan: OwnedMosBlockPlan,
    primitive_cdf_sha256: Digest | None,
    *,
    signed_ac_vsin_pair: bool,
) -> None:
    if primitive_cdf_sha256 is None:
        _check_bench(bench, dut_plan.root)
        return
    if (
        bench.ports
        or bench.symbol is not None
        or bench.wires
        or not 2 <= len(bench.instances) <= 32
        or "gnd!" not in bench.nets
        or "0" in bench.nets
        or len({(inst.placement.origin.x, inst.placement.origin.y) for inst in bench.instances})
        != len(bench.instances)
        or any(inst.placement.orientation != "R0" for inst in bench.instances)
    ):
        raise ValueError("unsupported declarative bench placement, ground or topology")
    root = next((cell for cell in dut_plan.circuits if cell.name == dut_plan.root), None)
    refs = [inst for inst in bench.instances if isinstance(inst, Child)]
    if (
        root is None
        or len(refs) != 1
        or refs[0].circuit != root.name
        or set(refs[0].connections) != {port.name for port in root.ports}
    ):
        raise ValueError("declarative bench requires exactly one fully connected DUT")
    if signed_ac_vsin_pair:
        _check_vsin_pair(bench, root, refs[0])
    if not any(isinstance(inst, VoltageSource) for inst in bench.instances):
        raise ValueError("declarative bench requires an explicit voltage source")
    for inst in bench.instances:
        if isinstance(inst, VoltageSource):
            if inst.pulse is not None or inst.dc_v is None:
                raise ValueError("declarative bench supports fixed DC and AC source values only")
        elif not isinstance(inst, (Child, Capacitor)):
            raise ValueError("unsupported declarative bench primitive")


def _primitive_setup(
    inst: VoltageSource | Capacitor,
    *,
    signed_ac: bool,
    vsin_pair: bool = False,
) -> tuple[str, str, dict[str, str], dict[str, str | None]]:
    if isinstance(inst, Capacitor):
        return "cap", "capacitor", {"c": inst.capacitance_f}, {"c": "capacitance"}
    if inst.dc_v is None:
        raise ValueError("fixed DC value is required")
    props = {"vdc": inst.dc_v}
    units: dict[str, str | None] = {"vdc": "voltage"}
    if inst.ac_magnitude_v != "0" or inst.ac_phase_deg != "0":
        if vsin_pair:
            return "vsin", "vsource", _vsin_oa_properties(Decimal(inst.ac_phase_deg) == 180), {}
        if signed_ac:
            props["acm"] = _signed_ac_magnitude(inst)
            units.update(acm="voltage", acp=None)
        else:
            props.update(acm=inst.ac_magnitude_v, acp=inst.ac_phase_deg)
            units.update(acm="voltage", acp="angle")
    return "vdc", "vsource", props, units


def _signed_ac_magnitude(inst: VoltageSource) -> str:
    phase = Decimal(inst.ac_phase_deg)
    magnitude = Decimal(inst.ac_magnitude_v)
    if magnitude <= 0 or phase not in (0, 180):
        raise ValueError("signed AC requires positive amplitude and phase of 0 or 180 degrees")
    return number_text(str(magnitude if phase == 0 else magnitude.copy_negate()))


def _vsin_oa_properties(negative: bool) -> dict[str, str]:
    props = {
        "vdc": "500m",
        "acm": "-500m" if negative else "500m",
        "va": "50m",
        "freq": "1K",
        "filenums": "none",
    }
    if negative:
        props["sinephase"] = "180"
    return props


def _check_vsin_pair(bench: Circuit, root: Circuit, dut: Child) -> None:
    sources = [
        inst
        for inst in bench.instances
        if isinstance(inst, VoltageSource)
        and (inst.ac_magnitude_v != "0" or inst.ac_phase_deg != "0")
    ]
    connections = dut.connections
    port_counts = Counter(connections.values())
    input_nets = {
        connections[port.name]
        for port in root.ports
        if port.direction == "input" and port_counts[connections[port.name]] == 1
    }
    if (
        len(sources) != 2
        or {inst.ac_phase_deg for inst in sources} != {"0", "180"}
        or len({inst.connections["PLUS"] for inst in sources}) != 2
        or any(
            inst.dc_v != "0.5"
            or inst.ac_magnitude_v != "0.5"
            or inst.connections["PLUS"] == "gnd!"
            or inst.connections["PLUS"] not in input_nets
            or inst.connections["MINUS"] != "gnd!"
            for inst in sources
        )
    ):
        raise ValueError(
            "vsin pair must drive distinct, unshared DUT inputs at the reviewed stimulus"
        )


def _check_bench_conditions(plan: ResearchBenchPlan, conditions: BenchNetlistConditions) -> None:
    analyses = tuple(kind for kind, _ in conditions.analyses)
    if plan.signed_ac_vsin_pair and analyses != ("ac",):
        if not plan.signed_ac_vsin_dc:
            raise ValueError("vsin differential stimulus is registered for AC only")
        if analyses != ("dc",):
            raise ValueError("vsin bench verification requires one registered DC or AC analysis")


def _bench_analyses_match(
    plan: ResearchBenchPlan,
    observed: tuple[tuple[str, str], ...],
    expected: tuple[tuple[str, str], ...],
) -> bool:
    if observed == expected:
        return True
    # The OTA seed can print a frequency using scientific notation. Keep all
    # other tokens, their order, and the number of analyses exact.
    ota_sweep = (("ac", "start=1 stop=1000000000 dec=16 annotate=status"),)
    if not plan.signed_ac_vsin_dc or expected != ota_sweep or len(observed) != 1:
        return False
    analysis, options = observed[0]
    frequencies = re.fullmatch(r"start=(\S+) stop=(\S+) dec=16 annotate=status", options)
    return bool(
        analysis == "ac"
        and frequencies
        and number_text(frequencies[1]) == "1"
        and number_text(frequencies[2]) == "1000000000"
    )


def _check_primitive_cdf(
    cdf_frames: Mapping[str, bytes],
    pin: Digest,
    bench: Circuit,
    *,
    signed_ac: bool,
    vsin_pair: bool,
) -> tuple[dict[str, object], ...]:
    frame = cdf_frames.get(pin)
    if frame is None or not frame.startswith(b"M2_CDF_V2\n") or sha256(frame).hexdigest() != pin:
        raise ValueError("missing or stale bench primitive CDF frame")
    requirements: dict[tuple[str, str], dict[str, str | None]] = {}
    for inst in bench.instances:
        if isinstance(inst, (VoltageSource, Capacitor)):
            cell, component, _, units = _primitive_setup(
                inst, signed_ac=signed_ac, vsin_pair=vsin_pair
            )
            if units:
                requirements.setdefault((cell, component), {}).update(units)
    observed = parse_frame(frame)
    terms = ("PLUS", "MINUS")
    for (cell, component), units in requirements.items():
        matches = [row for row in observed if (row["library"], row["cell"]) == ("analogLib", cell)]
        if len(matches) != 1:
            raise ValueError("missing or ambiguous bench primitive CDF master")
        device = matches[0]
        terminals = device["terminals"]
        if (
            not isinstance(terminals, tuple)
            or len(terminals) != len(terms)
            or set(terminals) != set(terms)
            or device["spectre"] != (("base", component, terms), ("effective", component, terms))
        ):
            raise ValueError("bench primitive terminal order or Spectre model mismatch")
        rows = device["parameters"]
        if not isinstance(rows, tuple):
            raise ValueError("bench primitive CDF parameters missing")
        parameter_types = {row[:4] for row in rows}
        if any(
            (scope, key, "baseCellData", unit) not in parameter_types
            for scope in ("base", "effective")
            for key, unit in units.items()
        ):
            raise ValueError("bench primitive CDF parameter, type or unit mismatch")
        if (
            signed_ac
            and "acp" in units
            and any(
                row[4:] not in (("", ""), ("0", "0"), (None, None))
                for row in rows
                if row[1] == "acp"
            )
        ):
            raise ValueError("bench primitive AC phase default is not zero or absent")
    return observed


def plan_research_bench(
    definition: ResearchCircuit,
    dut_plan: OwnedMosBlockPlan,
    *,
    expected_definition_sha256: Digest,
    expected_dut_plan_sha256: Digest,
    primitive_cdf_sha256: Digest | None = None,
    signed_ac_evidence_sha256: Digest | None = None,
    signed_ac_vsin_pair: bool = False,
) -> ResearchBenchPlan:
    """Bind a supported bench to the DUT closure of the exact definition."""
    definition = ResearchCircuit.model_validate_json(definition.model_dump_json())
    rebuilt = plan_owned_mos_block(
        definition,
        expected_binding=dut_plan.binding,
        expected_definition_sha256=expected_definition_sha256,
        output_library=dut_plan.output_library,
    )
    if rebuilt != dut_plan or canonical_digest(rebuilt) != expected_dut_plan_sha256:
        raise ValueError("bench DUT plan does not match the research definition")
    bench = next(cell for cell in definition.circuits if cell.name == definition.bench)
    if {cell.name for cell in rebuilt.circuits} | {bench.name} != {
        cell.name for cell in definition.circuits
    }:
        raise ValueError("research definition contains cells outside the DUT and bench")
    _check_profile(bench, rebuilt, primitive_cdf_sha256, signed_ac_vsin_pair=signed_ac_vsin_pair)
    return ResearchBenchPlan(
        definition_sha256=expected_definition_sha256,
        dut_plan_sha256=expected_dut_plan_sha256,
        bench=bench,
        primitive_cdf_sha256=primitive_cdf_sha256,
        signed_ac_evidence_sha256=signed_ac_evidence_sha256,
        signed_ac_vsin_pair=signed_ac_vsin_pair,
        signed_ac_vsin_dc=signed_ac_vsin_pair
        and tuple(analysis.kind for analysis in definition.analyses) == ("dc", "ac"),
    )


def _pinned_bench(
    plan: ResearchBenchPlan, dut_plan: OwnedMosBlockPlan, expected_plan_sha256: Digest
) -> ResearchBenchPlan:
    plan = ResearchBenchPlan.model_validate_json(plan.model_dump_json())
    if (
        canonical_digest(plan) != expected_plan_sha256
        or canonical_digest(dut_plan) != plan.dut_plan_sha256
        or dut_plan.definition_sha256 != plan.definition_sha256
        or plan.bench.name in {cell.name for cell in dut_plan.circuits}
    ):
        raise ValueError("bench plan or DUT plan identity mismatch")
    _check_profile(
        plan.bench,
        dut_plan,
        plan.primitive_cdf_sha256,
        signed_ac_vsin_pair=plan.signed_ac_vsin_pair,
    )
    return plan


def _insert_before_marker(script: str, lines: list[str], marker: str) -> str:
    statement = f'printf("{marker}\\n")'
    existing = script.splitlines(keepends=True)
    if existing.count(statement + "\n") != 1:
        raise ValueError("MOS block script completion marker mismatch")
    offset = existing.index(statement + "\n")
    existing[offset:offset] = [line + "\n" for line in lines]
    result = "".join(existing)
    if len(result.encode("ascii")) > _BENCH_SIZE_LIMIT:
        raise ValueError("rendered bench script exceeds size bound")
    return result


def render_research_bench(
    plan: ResearchBenchPlan,
    dut_plan: OwnedMosBlockPlan,
    cdf_frames: Mapping[str, bytes],
    *,
    expected_plan_sha256: Digest,
    owned_library_path: str,
) -> ResearchBenchScripts:
    """Render separate writer and reader from pinned CDF and optional AC evidence bytes."""
    plan = _pinned_bench(plan, dut_plan, expected_plan_sha256)
    dut = render_owned_mos_block(
        dut_plan,
        cdf_frames,
        expected_plan_sha256=plan.dut_plan_sha256,
        owned_library_path=owned_library_path,
        verify_schematic_port_positions=plan.primitive_cdf_sha256 is not None,
    )
    declarative = plan.primitive_cdf_sha256 is not None
    signed_ac = plan.signed_ac_evidence_sha256 is not None
    if plan.primitive_cdf_sha256 is not None:
        cdf = _check_primitive_cdf(
            cdf_frames,
            plan.primitive_cdf_sha256,
            plan.bench,
            signed_ac=signed_ac,
            vsin_pair=plan.signed_ac_vsin_pair,
        )
        if signed_ac:
            _check_signed_ac_evidence(cdf_frames, plan, cdf)
    q = _quote
    library, bench = q(dut_plan.output_library), q(plan.bench.name)
    create = [
        f'when(ddGetObj({library} {bench}) error("M2_OWNED_BENCH_COLLISION"))',
        f'cv=dbOpenCellViewByType({library} {bench} "schematic" "schematic" "w") m2Require(cv)',
    ]
    reopen = [
        f'cv=dbOpenCellViewByType({library} {bench} "schematic" "" "r") m2Require(cv)',
        f"m2Require(length(cv~>instances)=={len(plan.bench.instances)} "
        "&& length(cv~>terminals)==0)",
    ]
    saved_positions: list[str] = []
    devices = {device.name: device for device in plan.bench.instances}
    connection_checks: list[str] = []
    order = tuple(devices) if declarative else ("DUT", "VDD", "VIN", "CL")
    for name in order:
        device = devices[name]
        props: dict[str, str]
        if isinstance(device, Child):
            master = Master(library=dut_plan.output_library, cell=dut_plan.root, view="symbol")
            props = {}
        else:
            if declarative:
                if not isinstance(device, (VoltageSource, Capacitor)):
                    raise ValueError("unsupported declarative bench primitive")
                primitive, _, props, _ = _primitive_setup(
                    device, signed_ac=signed_ac, vsin_pair=plan.signed_ac_vsin_pair
                )
            else:
                primitive, props = _PRIMITIVES[name]
            master = Master(library="analogLib", cell=primitive, view="symbol")
        positioned, saved_position = render_research_positioned_instance(master, device)
        create.extend(positioned)
        saved_positions.append(saved_position)
        create.extend(f"m2Param(inst {q(key)} {q(value)})" for key, value in props.items())
        links = device.connections
        create.extend(f"m2Wire(cv inst {q(key)} {q(net)})" for key, net in links.items())
        origin = device.placement.origin
        reopen.append(
            f"inst=m2BlockInstance(cv {q(name)} {q(master.library)} {q(master.cell)} "
            f"{origin.x} {origin.y} {len(links)})"
        )
        wire_checks = [f"m2Net(cv {q(name)} {q(key)} {q(net)})" for key, net in links.items()]
        reopen.extend(wire_checks)
        if declarative:
            connection_checks.extend(wire_checks)
        prop_checks = [f"m2Property(cv {q(name)} {q(key)} {q(v)})" for key, v in props.items()]
        reopen.extend(prop_checks)
        if signed_ac and "acm" in props:
            absent = ['m2Require(dbFindProp(inst "acp")==nil)']
            if plan.signed_ac_vsin_pair and "sinephase" not in props:
                absent.append('m2Require(dbFindProp(inst "sinephase")==nil)')
            reopen.extend(absent)
            connection_checks.extend(prop_checks)
            connection_checks.extend(
                (
                    f"inst=m2Require(car(setof(entry cv~>instances entry~>name=={q(name)})))",
                    *absent,
                )
            )
    saved = f"RESEARCH_BENCH_SAVED|{expected_plan_sha256}|{plan.bench.name}"
    reopened = f"RESEARCH_BENCH_REOPENED_CHECKED|{expected_plan_sha256}|{plan.bench.name}"
    block_saved = f"MOS_BLOCK_SAVED|{plan.dut_plan_sha256}"
    block_reopened = f"MOS_BLOCK_REOPENED_CHECKED|{plan.dut_plan_sha256}"
    create.append("m2Require(schCheck(cv))")
    create.extend(saved_positions)
    create.extend(connection_checks)
    create.extend(("m2Require(dbSave(cv)) dbClose(cv)", f'printf("{saved}\\n")'))
    reopen.extend(("dbClose(cv)", f'printf("{reopened}\\n")'))
    return ResearchBenchScripts(
        plan_sha256=dut.plan_sha256,
        bench_plan_sha256=expected_plan_sha256,
        bench_cell=plan.bench.name,
        save_markers=(saved, block_saved),
        reopen_markers=(reopened, block_reopened),
        generate=_insert_before_marker(dut.generate, create, block_saved),
        reopen=_insert_before_marker(dut.reopen, reopen, block_reopened),
    )


def _split_static(lines: list[str]) -> tuple[list[str], list[str]]:
    body: list[str] = []
    top: list[str] = []
    depth = 0
    for line in lines:
        if line.startswith(("subckt ", "inline subckt ")):
            depth += 1
        (body if depth else top).append(line)
        if line == "ends" or line.startswith("ends "):
            depth -= 1
    return body, top


_SPECTRE_SCALES = {"a": -18, "f": -15, "p": -12, "n": -9, "u": -6, "m": -3, "K": 3}


def _spectre_scalar(value: str) -> Decimal:
    scale = _SPECTRE_SCALES.get(value[-1:], 0)
    scalar = Decimal(number_text(value[:-1] if scale else value))
    with localcontext() as context:
        context.prec = 128
        return scalar.scaleb(scale)


def _vsin_netlist_options(negative: bool) -> dict[str, str]:
    options = {
        "type": "sine",
        "dc": "0.5",
        "mag": "-0.5" if negative else "0.5",
        "ampl": "0.05",
        "freq": "1000",
    }
    if negative:
        options["sinephase"] = "180"
    return options


def _check_vsin_source_cdf(
    devices: tuple[dict[str, object], ...],
    source: SignedAcSourceObservation,
    *,
    negative: bool,
) -> None:
    matches = [
        row
        for row in devices
        if (row["library"], row["cell"], row["instance"]) == ("analogLib", "vsin", source.instance)
    ]
    if len(matches) != 1:
        raise ValueError("missing or ambiguous observed vsin instance CDF")
    device = matches[0]
    terminals = device["terminals"]
    order = ("PLUS", "MINUS")
    if (
        not isinstance(terminals, tuple)
        or len(terminals) != 2
        or set(terminals) != set(order)
        or device["spectre"] != (("base", "vsource", order), ("effective", "vsource", order))
    ):
        raise ValueError("observed vsin CDF terminal order or Spectre mapping mismatch")
    rows = device["parameters"]
    if not isinstance(rows, tuple):
        raise ValueError("observed vsin CDF parameters missing")
    parameters = {(row[0], row[1]): row for row in rows}
    props = _vsin_oa_properties(negative)
    phase_default = (None, "", "0")
    for name in ("vdc", "acm", "va", "freq", "sinephase", "acp", "filenums"):
        base = parameters.get(("base", name))
        effective = parameters.get(("effective", name))
        if (
            base is None
            or effective is None
            or base[2] != "baseCellData"
            or effective[2] != "instData"
            or effective[3] != base[3]
        ):
            raise ValueError("observed vsin CDF parameter metadata missing or inconsistent")
        value = effective[5]
        if name in ("acp", "sinephase") and base[4] not in phase_default:
            raise ValueError("observed vsin phase default is not zero or absent")
        if name == "filenums":
            if base[4] != props[name] or value != props[name]:
                raise ValueError("observed vsin CDF file selector disagrees with saved OA")
        elif name in props:
            if not isinstance(value, str) or _spectre_scalar(value) != _spectre_scalar(props[name]):
                raise ValueError("observed vsin effective CDF value disagrees with saved OA")
        elif value not in phase_default:
            raise ValueError("observed vsin phase disagrees with saved OA")


def _check_signed_ac_evidence(
    cdf_frames: Mapping[str, bytes],
    plan: ResearchBenchPlan,
    cdf: tuple[dict[str, object], ...],
) -> None:
    pin = plan.signed_ac_evidence_sha256
    raw = cdf_frames.get(pin) if pin is not None else None
    if raw is None or len(raw) > 4096 or sha256(raw).hexdigest() != pin:
        raise ValueError("missing or stale signed AC evidence")
    evidence = SignedAcSourceEvidence.model_validate_json(raw)
    if evidence.primitive_cdf_sha256 != plan.primitive_cdf_sha256:
        raise ValueError("signed AC evidence CDF digest mismatch")
    effective = cdf_frames.get(evidence.effective_netlist_sha256)
    if (
        effective is None
        or len(effective) > _BENCH_SIZE_LIMIT
        or sha256(effective).hexdigest() != evidence.effective_netlist_sha256
    ):
        raise ValueError("missing or stale signed AC effective netlist")
    _, _, _, static = partition_input(effective)  # type: ignore[no-untyped-call]
    _, top = _split_static(static)
    plus, minus = evidence.sources
    magnitude = _spectre_scalar(plus.acm_string)
    dc = _spectre_scalar(plus.dc_string)
    if (
        magnitude <= 0
        or _spectre_scalar(minus.acm_string) != magnitude.copy_negate()
        or _spectre_scalar(minus.dc_string) != dc
        or plus.instance == minus.instance
        or plus.plus == minus.plus
        or plus.minus != minus.minus
        or plus.minus in (plus.plus, minus.plus)
    ):
        raise ValueError("signed AC evidence requires opposite magnitudes at equal DC bias")
    for source, negative in ((plus, False), (minus, True)):
        if plan.signed_ac_vsin_pair:
            props: dict[str, str] = {
                "vdc": source.dc_string,
                "acm": source.acm_string,
            }
            props.update((source.sine_string_properties or {}).items())
            if (
                source.master != "analogLib/vsin/symbol"
                or source.minus != "0"
                or props != _vsin_oa_properties(negative)
            ):
                raise ValueError("signed AC evidence disagrees with the observed vsin pair")
            _check_vsin_source_cdf(cdf, source, negative=negative)
            options = _vsin_netlist_options(negative)
        else:
            if source.master != "analogLib/vdc/symbol" or source.sine_string_properties is not None:
                raise ValueError("signed AC evidence requires analogLib/vdc/symbol")
            options = {
                "type": "dc",
                "dc": str(dc),
                "mag": str(_spectre_scalar(source.acm_string)),
            }
        words = source.statement.split()
        if (
            " ".join(words[:4]) != f"{source.instance} ({source.plus} {source.minus}) vsource"
            or [row for row in top if row.partition(" ")[0] == source.instance] != [" ".join(words)]
            or not _declarative_options_match(
                words[4:],
                options,
                allow_zero_phase=not plan.signed_ac_vsin_pair,
            )
        ):
            raise ValueError("signed AC evidence disagrees with its observed Spectre statement")
    if not any(
        isinstance(inst, VoltageSource) and Decimal(inst.ac_magnitude_v) != 0
        for inst in plan.bench.instances
    ):
        raise ValueError("signed AC evidence supplied for a bench without AC stimulus")


def _declarative_top_level(
    bench: Circuit,
    root: Circuit,
    *,
    signed_ac: bool,
    vsin_pair: bool,
) -> dict[str, tuple[str, dict[str, str]]]:
    expected = {}
    for inst in bench.instances:
        if isinstance(inst, Child):
            connections = [inst.connections[port.name] for port in root.ports]
            model, options = root.name, {}
        elif isinstance(inst, VoltageSource) and inst.dc_v is not None:
            connections = [inst.connections[key] for key in ("PLUS", "MINUS")]
            model, options = "vsource", {"type": "dc", "dc": inst.dc_v}
            if inst.ac_magnitude_v != "0" or inst.ac_phase_deg != "0":
                if vsin_pair:
                    options = _vsin_netlist_options(Decimal(inst.ac_phase_deg) == 180)
                elif signed_ac:
                    options["mag"] = _signed_ac_magnitude(inst)
                else:
                    options.update(mag=inst.ac_magnitude_v, phase=inst.ac_phase_deg)
        elif isinstance(inst, Capacitor):
            connections = [inst.connections[key] for key in ("PLUS", "MINUS")]
            model, options = "capacitor", {"c": inst.capacitance_f}
        else:
            raise ValueError("unsupported declarative bench primitive")
        terminals = " ".join("0" if net == "gnd!" else net for net in connections)
        expected[inst.name] = (f"{inst.name} ({terminals}) {model}", options)
    return expected


def _declarative_options_match(
    words: list[str], expected: dict[str, str], *, allow_zero_phase: bool = False
) -> bool:
    actual: dict[str, str] = {}
    for token in words:
        key, separator, value = token.partition("=")
        if not separator or key in actual or not value:
            return False
        actual[key] = value
    try:
        if allow_zero_phase and "phase" in actual and _spectre_scalar(actual.pop("phase")) != 0:
            return False
        if actual.keys() != expected.keys():
            return False
        return all(
            actual[key] == value
            if key == "type"
            else _spectre_scalar(actual[key]) == Decimal(value)
            for key, value in expected.items()
        )
    except ValueError:
        return False


def verify_research_bench_netlist(
    plan: ResearchBenchPlan,
    dut_plan: OwnedMosBlockPlan,
    raw: bytes,
    dut_raw: bytes,
    *,
    expected_plan_sha256: Digest,
    expected_netlist_sha256: Digest,
    expected_dut_netlist_sha256: Digest,
    conditions: BenchNetlistConditions,
    expected_conditions_sha256: Digest,
) -> None:
    """Compare the exact bench devices, DUT body and registered fixed inputs."""
    plan = _pinned_bench(plan, dut_plan, expected_plan_sha256)
    conditions = BenchNetlistConditions.model_validate_json(conditions.model_dump_json())
    _check_bench_conditions(plan, conditions)
    if canonical_digest(conditions) != expected_conditions_sha256:
        raise ValueError("bench conditions digest mismatch")
    if len(raw) > _BENCH_SIZE_LIMIT or sha256(raw).hexdigest() != expected_netlist_sha256:
        raise ValueError("bench netlist digest or size mismatch")
    project_mos_block_netlist(
        dut_plan,
        dut_raw,
        expected_plan_sha256=plan.dut_plan_sha256,
        expected_netlist_artifact_sha256=expected_dut_netlist_sha256,
    )
    _, _, _, dut_static = partition_input(dut_raw)  # type: ignore[no-untyped-call]
    params, includes, analyses, static = partition_input(raw)  # type: ignore[no-untyped-call]
    declarative = plan.primitive_cdf_sha256 is not None
    if (
        params != conditions.parameters
        or (not declarative and "m2_vin" not in params)
        or tuple(includes) != conditions.includes
        or not analyses
        or not _bench_analyses_match(plan, tuple(analyses), conditions.analyses)
    ):
        raise ValueError("bench parameters, model includes or analyses mismatch")
    dut_body, _ = _split_static(dut_static)
    body, top = _split_static(static)
    if body != dut_body:
        raise ValueError("bench DUT subcircuit body differs from the pinned DUT netlist")
    root = next(cell for cell in dut_plan.circuits if cell.name == dut_plan.root)
    ref = next(device for device in plan.bench.instances if isinstance(device, Child))
    nodes = tuple(ref.connections[port.name] for port in root.ports)
    dut_terminals = " ".join("0" if net == "gnd!" else net for net in nodes)
    legacy_expected: dict[str, tuple[str, set[str]]] = {
        "DUT": (f"DUT ({dut_terminals}) {root.name}", set()),
        "VDD": ("VDD (vdd 0) vsource", {"dc=1", "type=dc"}),
        "VIN": (
            "VIN (vin 0) vsource",
            {
                "dc=m2_vin",
                "type=pulse",
                "val0=0",
                "val1=1",
                "period=150n",
                "delay=10n",
                "rise=100p",
                "fall=100p",
                "width=65n",
            },
        ),
        "CL": ("CL (vout 0) capacitor", {"c=1p"}),
    }
    signed_ac = plan.signed_ac_evidence_sha256 is not None
    typed_expected = (
        _declarative_top_level(
            plan.bench, root, signed_ac=signed_ac, vsin_pair=plan.signed_ac_vsin_pair
        )
        if declarative
        else {}
    )
    expected_names = typed_expected.keys() if declarative else legacy_expected.keys()
    remaining = []
    seen_devices: set[str] = set()
    seen_controls: set[str] = set()
    for line in top:
        words = line.split()
        name, kind = words[0], words[1] if len(words) > 1 else ""
        if name not in expected_names:
            if (
                name in seen_controls
                or _SOURCE9_TOP_LEVEL_CONTROLS.get(name) != kind
                or (name == "global" and line != "global 0")
            ):
                raise ValueError("unsupported extra bench device or top-level control")
            seen_controls.add(name)
            remaining.append(line)
            continue
        if declarative:
            head, typed_options = typed_expected[name]
        else:
            head, legacy_options = legacy_expected[name]
        match = re.fullmatch(re.escape(head) + r"(?: (.+))?", line)
        words = (match.group(1) or "").split() if match else []
        matches = (
            _declarative_options_match(
                words,
                typed_options,
                allow_zero_phase=signed_ac
                and not plan.signed_ac_vsin_pair
                and "mag" in typed_options,
            )
            if declarative
            else set(words) == legacy_options and len(words) == len(legacy_options)
        )
        if name in seen_devices or match is None or not matches:
            raise ValueError("bench device, model, terminals or effective values mismatch")
        seen_devices.add(name)
    if (
        seen_devices != expected_names
        or "global" not in seen_controls
        or tuple(remaining) != conditions.fixed_top_level
    ):
        raise ValueError("bench instance inventory or fixed top-level statements mismatch")


class FixedDcBenchNetlistEquivalence(VariableModel):
    """Local comparison over two independently pinned full inputs."""

    expected_raw_sha256: Digest
    observed_raw_sha256: Digest
    expected_statements_sha256: Digest
    observed_statements_sha256: Digest
    status: Literal["MATCHED_FIXED_DC_BENCH"] = "MATCHED_FIXED_DC_BENCH"
    execution_authorized: Literal[False] = False


def _fixed_dc_statement_surroundings(
    lines: list[str], primitive_names: set[str]
) -> tuple[list[str], list[str]]:
    depth = 0
    positions = []
    for index, line in enumerate(lines):
        if line.startswith(("subckt ", "inline subckt ")):
            depth += 1
        elif line == "ends" or line.startswith("ends "):
            depth -= 1
        elif line.partition(" ")[0] in primitive_names:
            if depth != 0:
                raise ValueError("fixed DC bench primitive name shadows a DUT statement")
            positions.append(index)
    if not positions or positions != list(range(positions[0], positions[0] + len(primitive_names))):
        raise ValueError("expected one contiguous top-level fixed DC primitive block")
    return lines[: positions[0]], lines[positions[-1] + 1 :]


def verify_fixed_dc_bench_netlist_equivalence(
    plan: ResearchBenchPlan,
    dut_plan: OwnedMosBlockPlan,
    expected_raw: bytes,
    observed_raw: bytes,
    dut_raw: bytes,
    *,
    expected_plan_sha256: Digest,
    expected_statements_sha256: Digest,
    expected_raw_sha256: Digest,
    observed_raw_sha256: Digest,
    expected_dut_netlist_sha256: Digest,
    conditions: BenchNetlistConditions,
    expected_conditions_sha256: Digest,
) -> FixedDcBenchNetlistEquivalence:
    """Permit primitive order and numeric spelling differences in a fixed DC bench.

    The expected statement digest must come from the original reviewed scope.
    Neither input supplies execution or completion evidence.
    """
    plan = _pinned_bench(plan, dut_plan, expected_plan_sha256)
    if (
        plan.primitive_cdf_sha256 is None
        or plan.signed_ac_evidence_sha256 is not None
        or tuple(kind for kind, _ in conditions.analyses) != ("dc",)
        or any(
            inst.ac_magnitude_v != "0" or inst.ac_phase_deg != "0"
            for inst in plan.bench.instances
            if isinstance(inst, VoltageSource)
        )
    ):
        raise ValueError("netlist equivalence requires a declarative fixed DC bench")
    for raw, raw_pin in ((expected_raw, expected_raw_sha256), (observed_raw, observed_raw_sha256)):
        verify_research_bench_netlist(
            plan,
            dut_plan,
            raw,
            dut_raw,
            expected_plan_sha256=expected_plan_sha256,
            expected_netlist_sha256=raw_pin,
            expected_dut_netlist_sha256=expected_dut_netlist_sha256,
            conditions=conditions,
            expected_conditions_sha256=expected_conditions_sha256,
        )
    expected_lines = statements(expected_raw)  # type: ignore[no-untyped-call]
    observed_lines = statements(observed_raw)  # type: ignore[no-untyped-call]
    if sha256(_canonical(expected_lines)).hexdigest() != expected_statements_sha256:
        raise ValueError("expected bench statement digest differs from the reviewed scope")
    primitive_names = {
        inst.name for inst in plan.bench.instances if isinstance(inst, (VoltageSource, Capacitor))
    }
    if _fixed_dc_statement_surroundings(
        expected_lines, primitive_names
    ) != _fixed_dc_statement_surroundings(observed_lines, primitive_names):
        raise ValueError("bench netlist changed outside the fixed DC primitive block")
    return FixedDcBenchNetlistEquivalence(
        expected_raw_sha256=expected_raw_sha256,
        observed_raw_sha256=observed_raw_sha256,
        expected_statements_sha256=expected_statements_sha256,
        observed_statements_sha256=sha256(_canonical(observed_lines)).hexdigest(),
    )
