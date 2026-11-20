"""Bounded Source9 testbench generation and Spectre input comparison."""

from __future__ import annotations

import re
from collections.abc import Mapping
from hashlib import sha256

from cadence_mcp_bridge._native_rendering import partition_input
from cadence_mcp_bridge.m2_inverter import _quote
from cadence_mcp_bridge.research_circuit import (
    Child,
    Circuit,
    MosBlockScripts,
    OwnedMosBlockPlan,
    Pulse,
    ResearchCircuit,
    VoltageSource,
    _inverter_bench,
    plan_owned_mos_block,
    project_mos_block_netlist,
    render_owned_mos_block,
)
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest

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


def plan_research_bench(
    definition: ResearchCircuit,
    dut_plan: OwnedMosBlockPlan,
    *,
    expected_definition_sha256: Digest,
    expected_dut_plan_sha256: Digest,
) -> ResearchBenchPlan:
    """Bind the declared Source9 bench to the DUT closure of the exact definition."""
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
    _check_bench(bench, rebuilt.root)
    return ResearchBenchPlan(
        definition_sha256=expected_definition_sha256,
        dut_plan_sha256=expected_dut_plan_sha256,
        bench=bench,
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
    _check_bench(plan.bench, dut_plan.root)
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
    """Render one fresh-library writer and an independent read-only checker."""
    plan = _pinned_bench(plan, dut_plan, expected_plan_sha256)
    dut = render_owned_mos_block(
        dut_plan,
        cdf_frames,
        expected_plan_sha256=plan.dut_plan_sha256,
        owned_library_path=owned_library_path,
    )
    q = _quote
    library, bench = q(dut_plan.output_library), q(plan.bench.name)
    create = [
        f'when(ddGetObj({library} {bench}) error("M2_OWNED_BENCH_COLLISION"))',
        f'cv=dbOpenCellViewByType({library} {bench} "schematic" "schematic" "w") m2Require(cv)',
    ]
    reopen = [
        f'cv=dbOpenCellViewByType({library} {bench} "schematic" "" "r") m2Require(cv)',
        "m2Require(length(cv~>instances)==4 && length(cv~>terminals)==0)",
    ]
    devices = {device.name: device for device in plan.bench.instances}
    for x, name in zip((0, 4, 8, 12), ("DUT", "VDD", "VIN", "CL"), strict=True):
        device = devices[name]
        props: dict[str, str]
        if isinstance(device, Child):
            master_lib, master, props = library, q(dut_plan.root), {}
        else:
            primitive, props = _PRIMITIVES[name]
            master_lib, master = q("analogLib"), q(primitive)
        create.append(f"inst=m2Instance(cv {master_lib} {master} {q(name)} {x} 0)")
        create.extend(f"m2Param(inst {q(key)} {q(value)})" for key, value in props.items())
        links = device.connections
        create.extend(f"m2Wire(cv inst {q(key)} {q(net)})" for key, net in links.items())
        reopen.append(
            f"inst=m2BlockInstance(cv {q(name)} {master_lib} {master} {x} 0 {len(links)})"
        )
        reopen.extend(f"m2Net(cv {q(name)} {q(key)} {q(net)})" for key, net in links.items())
        reopen.extend(f"m2Property(cv {q(name)} {q(key)} {q(v)})" for key, v in props.items())
    saved = f"RESEARCH_BENCH_SAVED|{expected_plan_sha256}|{plan.bench.name}"
    reopened = f"RESEARCH_BENCH_REOPENED_CHECKED|{expected_plan_sha256}|{plan.bench.name}"
    block_saved = f"MOS_BLOCK_SAVED|{plan.dut_plan_sha256}"
    block_reopened = f"MOS_BLOCK_REOPENED_CHECKED|{plan.dut_plan_sha256}"
    create.extend(
        ("m2Require(schCheck(cv))", "m2Require(dbSave(cv)) dbClose(cv)", f'printf("{saved}\\n")')
    )
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
    if (
        params != conditions.parameters
        or "m2_vin" not in params
        or tuple(includes) != conditions.includes
        or not analyses
        or tuple(analyses) != conditions.analyses
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
    expected: dict[str, tuple[str, set[str]]] = {
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
    remaining = []
    seen_devices: set[str] = set()
    seen_controls: set[str] = set()
    for line in top:
        name, kind, *_ = line.split()
        if name not in expected:
            if (
                name in seen_controls
                or _SOURCE9_TOP_LEVEL_CONTROLS.get(name) != kind
                or (name == "global" and line != "global 0")
            ):
                raise ValueError("unsupported extra bench device or top-level control")
            seen_controls.add(name)
            remaining.append(line)
            continue
        head, options = expected[name]
        match = re.fullmatch(re.escape(head) + r"(?: (.+))?", line)
        words = (match.group(1) or "").split() if match else []
        if (
            name in seen_devices
            or match is None
            or set(words) != options
            or len(words) != len(options)
        ):
            raise ValueError("bench device, model, terminals or effective values mismatch")
        seen_devices.add(name)
    if (
        seen_devices != expected.keys()
        or "global" not in seen_controls
        or tuple(remaining) != conditions.fixed_top_level
    ):
        raise ValueError("bench instance inventory or fixed top-level statements mismatch")
