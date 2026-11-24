"""Focused local checks for the composite Source9 writer and input guard."""

import json
from copy import deepcopy
from hashlib import sha256
from typing import Literal

import pytest
from test_m2_inverter import fixture as inverter_fixture
from test_research_circuit import mos_block_fixture, payload, raw_block_netlist

from cadence_mcp_bridge.research_bench import (
    BenchNetlistConditions,
    ResearchBenchPlan,
    SignedAcSourceEvidence,
    SignedAcSourceObservation,
    plan_research_bench,
    render_research_bench,
    verify_research_bench_netlist,
)
from cadence_mcp_bridge.research_circuit import (
    Circuit,
    OwnedMosBlockPlan,
    ResearchCircuit,
    plan_owned_mos_block,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


def _definition(*, long_pulse: bool = True) -> ResearchCircuit:
    inverter, _ = inverter_fixture()
    previous, _ = mos_block_fixture()
    data = payload(inverter)
    bench = data["circuits"][1]
    if long_pulse:
        bench["instances"][2]["pulse"].update(delay_s="10e-9", width_s="65e-9", period_s="150e-9")
    data["circuits"] = [*(cell.model_dump(mode="json") for cell in previous.circuits), bench]
    return ResearchCircuit.model_validate_json(json.dumps(data))


def _plans(definition: ResearchCircuit) -> tuple[ResearchBenchPlan, OwnedMosBlockPlan]:
    definition_pin = canonical_digest(definition)
    dut = plan_owned_mos_block(
        definition,
        expected_binding=definition.binding,
        expected_definition_sha256=definition_pin,
        output_library="OwnedBlock",
    )
    return plan_research_bench(
        definition,
        dut,
        expected_definition_sha256=definition_pin,
        expected_dut_plan_sha256=canonical_digest(dut),
    ), dut


def test_composite_write_and_independent_read_only_reopen() -> None:
    plan, dut = _plans(_definition())
    inverter, frame = inverter_fixture()
    args = {"expected_plan_sha256": canonical_digest(plan), "owned_library_path": "/owned/block"}
    cdf_frames = {inverter.cdf_frame_sha256: frame}
    result = render_research_bench(plan, dut, cdf_frames, **args)
    assert result == render_research_bench(plan, dut, cdf_frames, **args)
    assert result.plan_sha256 == canonical_digest(dut)
    assert result.bench_plan_sha256 == canonical_digest(plan)
    assert result.bench_cell == plan.bench.name
    assert result.generate.count("m2Require(ddCreateLib(") == 1
    assert result.generate.index("M2_OWNED_LIBRARY_COLLISION") < result.generate.index(
        "ddCreateLib("
    )
    assert result.generate.index("M2_OWNED_BENCH_COLLISION") < result.generate.index(
        f'"{plan.bench.name}" "schematic" "schematic" "w"'
    )
    assert 'm2Param(inst "per" "150n")' in result.generate
    assert 'm2BlockInstance(cv "DUT" "OwnedBlock" "Dut" 0 0 4)' in result.reopen
    assert 'm2Property(cv "VIN" "dc" "m2_vin")' in result.reopen
    assert 'm2Net(cv "CL" "PLUS" "vout")' in result.reopen
    assert f'"{plan.bench.name}" "schematic" "" "r"' in result.reopen
    assert all(term not in result.reopen for term in ("dbSave(", "ddCreateLib(", ' "w")'))
    for script, markers in (
        (result.generate, result.save_markers),
        (result.reopen, result.reopen_markers),
    ):
        first, second = (f'printf("{marker}\\n")' for marker in markers)
        assert script.count(first) == script.count(second) == 1
        assert script.index(first) < script.index(second)
    with pytest.raises(ValueError, match="identity mismatch"):
        render_research_bench(
            plan, dut, cdf_frames, expected_plan_sha256="0" * 64, owned_library_path="/owned/block"
        )


def test_bench_checks_position_before_wiring_and_before_save() -> None:
    plan, dut = _plans(_definition())
    inverter, frame = inverter_fixture()
    scripts = render_research_bench(
        plan,
        dut,
        {inverter.cdf_frame_sha256: frame},
        expected_plan_sha256=canonical_digest(plan),
        owned_library_path="/owned/block",
    )
    bench_open = f'"{plan.bench.name}" "schematic" "schematic" "w"'
    bench_write = scripts.generate.split(bench_open, 1)[1].splitlines()
    check = bench_write.index("m2Require(schCheck(cv))")
    save = bench_write.index("m2Require(dbSave(cv)) dbClose(cv)")
    assert check < save
    assert not any(line.startswith("inst=m2Instance(") for line in bench_write)
    devices = {device.name: device for device in plan.bench.instances}
    for name, lib, cell, x in (
        ("DUT", "OwnedBlock", "Dut", 0),
        ("VDD", "analogLib", "vdc", 4),
        ("VIN", "analogLib", "vpulse", 8),
        ("CL", "analogLib", "cap", 12),
    ):
        open_master = f'master=m2Require(dbOpenCellViewByType("{lib}" "{cell}" "symbol" "" "r"))'
        create = f'inst=m2Require(dbCreateInst(cv master "{name}" list({x} 0) "R0"))'
        check_immediate = f'm2BlockPlacement(inst {x} 0 "R0")'
        check_saved = f'm2BlockCheckPlacement(cv "{name}" {x} 0 "R0")'
        start = bench_write.index(open_master)
        assert bench_write[start : start + 3] == [open_master, create, check_immediate]
        terminal, net = next(iter(devices[name].connections.items()))
        first_wire = bench_write.index(f'm2Wire(cv inst "{terminal}" "{net}")', start)
        assert start + 2 < first_wire < check
        assert bench_write.count(check_saved) == 1
        assert check < bench_write.index(check_saved) < save


def test_reject_unobserved_bench_timing() -> None:
    with pytest.raises(ValueError, match="unsupported Source9 stimulus"):
        _plans(_definition(long_pulse=False))


_CONTROLS = b'parameters m2_vin=0\ninclude "/models/source9.scs" section=NN\n'
_DEVICES = (
    b"DUT (vin vout vdd 0) Dut\n"
    b"VDD (vdd 0) vsource dc=1 type=dc\n"
    b"VIN (vin 0) vsource dc=m2_vin type=pulse val0=0 val1=1 period=150n \\\n"
    b"    delay=10n rise=100p fall=100p width=65n\n"
    b"CL (vout 0) capacitor c=1p\n"
)
_ANALYSIS = b"dcOp dc maxiters=150\nsaveOptions options save=allpub\n"


def _verify(
    raw: bytes, *, netlist_pin: str | None = None, additional_fixed: tuple[str, ...] = ()
) -> None:
    plan, dut = _plans(_definition())
    conditions = BenchNetlistConditions(
        parameters={"m2_vin": "0"},
        includes=(("/models/source9.scs", "NN"),),
        analyses=(("dc", "maxiters=150"),),
        fixed_top_level=("global 0", "saveOptions options save=allpub", *additional_fixed),
    )
    dut_raw = raw_block_netlist()
    verify_research_bench_netlist(
        plan,
        dut,
        raw,
        dut_raw,
        expected_plan_sha256=canonical_digest(plan),
        expected_netlist_sha256=netlist_pin or sha256(raw).hexdigest(),
        expected_dut_netlist_sha256=sha256(dut_raw).hexdigest(),
        conditions=conditions,
        expected_conditions_sha256=canonical_digest(conditions),
    )


def test_full_netlist_checks_real_source9_dialect_and_top_level_device_permutation() -> None:
    invocation, primitives = _DEVICES.split(b"\n", 1)
    _verify(raw_block_netlist() + _CONTROLS + _DEVICES + _ANALYSIS)
    _verify(raw_block_netlist() + _CONTROLS + primitives + invocation + b"\n" + _ANALYSIS)


@pytest.mark.parametrize(
    "old,new",
    [
        (b"as=1f", b"as=2f"),
        (b"DUT (vin vout vdd 0)", b"DUT (vout vin vdd 0)"),
        (b"DUT (vin vout vdd 0) Dut", b"DUT (vin vout vdd 0) Helper"),
        (b"c=1p", b"c=2p"),
        (b"period=150n", b"period=150n period=150n"),
        (b"m2_vin=0", b"m2_vin=1"),
        (b"section=NN", b"section=FF"),
        (b"maxiters=150", b"maxiters=100"),
        (b"save=allpub", b"save=all"),
        (
            b"CL (vout 0) capacitor c=1p\n",
            b"CL (vout 0) capacitor c=1p\nCL2 (vout 0) capacitor c=1p\n",
        ),
        (
            b"CL (vout 0) capacitor c=1p\n",
            b"CL (vout 0) capacitor c=1p\nCL (vout 0) capacitor c=1p\n",
        ),
        (b"CL (vout 0) capacitor c=1p\n", b""),
    ],
)
def test_full_netlist_rejects_unauthorized_input_changes(old: bytes, new: bytes) -> None:
    raw = raw_block_netlist() + _CONTROLS + _DEVICES + _ANALYSIS
    assert old in raw
    with pytest.raises(ValueError):
        _verify(raw.replace(old, new, 1))


def test_full_netlist_checks_raw_hash() -> None:
    with pytest.raises(ValueError, match="netlist digest"):
        _verify(raw_block_netlist() + _CONTROLS + _DEVICES + _ANALYSIS, netlist_pin="0" * 64)


@pytest.mark.parametrize(
    ("additional", "reason"),
    [
        ("extra (vout 0) capacitor c=1p", "unsupported extra bench device"),
        ("extra options temp=27", "unsupported extra bench device"),
        ("global 0 hidden", "unsupported extra bench device"),
        ("subckt Other vin vout\nends Other", "subcircuit body differs"),
    ],
)
def test_pinned_controls_cannot_admit_extra_topology(additional: str, reason: str) -> None:
    raw = raw_block_netlist() + _CONTROLS + _DEVICES + _ANALYSIS
    with pytest.raises(ValueError, match=reason):
        _verify(
            raw + (additional + "\n").encode("ascii"),
            additional_fixed=tuple(additional.splitlines()),
        )


def _declarative_fixture() -> tuple[
    ResearchBenchPlan, OwnedMosBlockPlan, dict[str, bytes], BenchNetlistConditions, bytes, bytes
]:
    definition = _definition().model_dump(mode="json")
    root = next(cell for cell in definition["circuits"] if cell["name"] == definition["dut"])
    template = root["instances"][:2]
    root["nets"].append("inn")
    root["ports"].append(
        {
            "name": "inn",
            "net": "inn",
            "direction": "input",
            "origin": {"x": "108", "y": "100"},
        }
    )
    root["symbol"]["pins"].append({"port": "inn", "origin": {"x": "-1", "y": "-0.5"}})
    instances = []
    statements = []
    for index in range(17):
        device = deepcopy(template[index % 2])
        name = f"M{index}"
        gate = "vin" if index % 2 == 0 else "inn"
        rail = "vss" if index % 2 == 0 else "vdd"
        device["name"] = name
        device["placement"]["origin"] = {"x": str(index * 4), "y": "0"}
        next(link for link in device["links"] if link["terminal"] == "G")["net"] = gate
        instances.append(device)
        statements.append(
            f"{name} (vout {gate} {rail} {rail}) {device['spectre']['model']}"
            f" w=({device['geometry']['w']['value']}n) l=100n m=1 as=1f ad=1f ps=1u pd=1u"
        )
    root["instances"] = instances
    bench = next(cell for cell in definition["circuits"] if cell["name"] == definition["bench"])
    bench["nets"].append("inn")
    ref, _, vin, _ = bench["instances"]
    ref["links"].append({"terminal": "inn", "net": "inn"})
    vin.update(pulse=None, dc_variable=None, dc_v="0.5", ac_magnitude_v="0.5", ac_phase_deg="0")
    inn = deepcopy(vin)
    inn.update(name="VNEG", ac_phase_deg="180")
    inn["placement"]["origin"]["x"] = "16"
    next(link for link in inn["links"] if link["terminal"] == "PLUS")["net"] = "inn"
    bench["instances"].append(inn)
    definition["circuits"] = [root, bench]
    definition["observations"] = [
        {"kind": "device", "path": ["DUT", device["name"]], "quantity": "gm"}
        for device in instances
    ]
    model = ResearchCircuit.model_validate_json(json.dumps(definition))
    dut = plan_owned_mos_block(
        model,
        expected_binding=model.binding,
        expected_definition_sha256=canonical_digest(model),
        output_library="OwnedBlock",
    )
    inverter, frame = inverter_fixture()
    # These added AC CDF property rows are synthetic and qualify only the Python path.
    primitive = frame.replace(b'|"vdc"|"instData"|', b'|"vdc"|"baseCellData"|')
    primitive = primitive.replace(b'|"c"|"instData"|', b'|"c"|"baseCellData"|')
    for scope in ("base", "effective"):
        old = f'PARAM|"{scope}"|"vdc"|"baseCellData"|"voltage"|""|""\n'.encode()
        new = (
            f'PARAM|"{scope}"|"acm"|"baseCellData"|"voltage"|"0"|"0"\n'
            f'PARAM|"{scope}"|"acp"|"baseCellData"|"angle"|"0"|"0"\n'
        ).encode()
        primitive = primitive.replace(old, old + new)
    assert primitive != frame
    primitive_pin = sha256(primitive).hexdigest()
    plan = plan_research_bench(
        model,
        dut,
        expected_definition_sha256=canonical_digest(model),
        expected_dut_plan_sha256=canonical_digest(dut),
        primitive_cdf_sha256=primitive_pin,
    )
    raw = (
        "simulator lang=spectre\nglobal 0\nsubckt Dut vin vout vdd vss inn\n"
        + "\n".join(statements)
        + "\nends Dut\n"
    ).encode()
    full = raw + (
        b"DUT (vin vout vdd 0 inn) Dut\nVDD (vdd 0) vsource dc=1 type=dc\n"
        b"VIN (vin 0) vsource dc=500m mag=500m phase=0 type=dc\n"
        b"VNEG (inn 0) vsource dc=500m mag=500m phase=180 type=dc\n"
        b"CL (vout 0) capacitor c=1p\nac ac start=1 stop=1e9 dec=16\n"
    )
    conditions = BenchNetlistConditions(
        parameters={},
        includes=(),
        analyses=(("ac", "start=1 stop=1e9 dec=16"),),
        fixed_top_level=("global 0",),
    )
    return (
        plan,
        dut,
        {inverter.cdf_frame_sha256: frame, primitive_pin: primitive},
        conditions,
        raw,
        full,
    )


def test_declarative_bench_renders_17_mos_and_compares_differential_input() -> None:
    plan, dut, frames, conditions, raw, full = _declarative_fixture()
    plan_pin = canonical_digest(plan)
    scripts = render_research_bench(
        plan,
        dut,
        frames,
        expected_plan_sha256=plan_pin,
        owned_library_path="/owned/block",
    )
    assert scripts.generate.count('dbCreateInst(cv master "M') == 17
    assert 'm2Net(cv "DUT" "inn" "inn")' in scripts.reopen
    assert 'm2BlockSchematicPort(cv "inn" "input" "inn" 108 100)' in scripts.reopen
    assert 'm2Param(inst "acp" "180")' in scripts.generate
    assert 'm2Property(cv "VNEG" "acp" "180")' in scripts.reopen
    assert "dbSave(" not in scripts.reopen
    assert "primitive_cdf_sha256" not in _plans(_definition())[0].model_dump()

    def check(candidate: bytes) -> None:
        verify_research_bench_netlist(
            plan,
            dut,
            candidate,
            raw,
            expected_plan_sha256=plan_pin,
            expected_netlist_sha256=sha256(candidate).hexdigest(),
            expected_dut_netlist_sha256=sha256(raw).hexdigest(),
            conditions=conditions,
            expected_conditions_sha256=canonical_digest(conditions),
        )

    check(full)
    for bad in (
        full.replace(b"vdd 0 inn", b"vdd inn 0"),
        full.replace(b"phase=180", b"phase=0"),
        full.replace(b"capacitor c=1p", b"capacitor c=2p"),
    ):
        with pytest.raises(ValueError, match="bench device"):
            check(bad)
    assert plan.primitive_cdf_sha256 is not None
    untrusted = {key: frame for key, frame in frames.items() if key != plan.primitive_cdf_sha256}
    with pytest.raises(ValueError, match="bench primitive CDF"):
        render_research_bench(
            plan,
            dut,
            untrusted,
            expected_plan_sha256=plan_pin,
            owned_library_path="/owned/block",
        )

    primitive = frames[plan.primitive_cdf_sha256]
    for changed in (
        primitive.replace(b'"acp"|"baseCellData"|"angle"', b'"acp"|"baseCellData"|nil'),
        primitive.replace(b'"acp"|"baseCellData"|"angle"', b'"acp"|"instData"|"angle"'),
    ):
        changed_pin = sha256(changed).hexdigest()
        changed_plan = plan.model_copy(update={"primitive_cdf_sha256": changed_pin})
        with pytest.raises(ValueError, match="bench primitive CDF parameter, type or unit"):
            render_research_bench(
                changed_plan,
                dut,
                {**frames, changed_pin: changed},
                expected_plan_sha256=canonical_digest(changed_plan),
                owned_library_path="/owned/block",
            )


def test_signed_ac_uses_same_master_evidence_and_checks_emitted_sign() -> None:
    plan, dut, frames, conditions, raw, full = _declarative_fixture()
    assert plan.primitive_cdf_sha256 is not None
    primitive = frames[plan.primitive_cdf_sha256].replace(
        b'"acp"|"baseCellData"|"angle"', b'"acp"|"baseCellData"|nil'
    )
    primitive_pin = sha256(primitive).hexdigest()
    plan = plan.model_copy(update={"primitive_cdf_sha256": primitive_pin})
    frames[primitive_pin] = primitive
    sources = (
        SignedAcSourceObservation(
            instance="V1",
            master="analogLib/vdc/symbol",
            plus="vp",
            minus="0",
            dc_string="500m",
            acm_string="500m",
            acp_absent=True,
            statement="V1 (vp 0) vsource dc=500m mag=500m type=dc",
        ),
        SignedAcSourceObservation(
            instance="V2",
            master="analogLib/vdc/symbol",
            plus="vm",
            minus="0",
            dc_string="500m",
            acm_string="-500m",
            acp_absent=True,
            statement="V2 (vm 0) vsource dc=500m mag=-500m type=dc",
        ),
    )
    effective = ("simulator lang=spectre\n" + "\n".join(row.statement for row in sources)).encode()
    effective_pin = sha256(effective).hexdigest()
    frames[effective_pin] = effective
    evidence = SignedAcSourceEvidence(
        primitive_cdf_sha256=primitive_pin,
        native_manifest_sha256="1" * 64,
        saved_tree_sha256="2" * 64,
        reopen_artifact_sha256="3" * 64,
        effective_netlist_sha256=effective_pin,
        sources=sources,
    )

    def render(witness: bytes, *, retained: bool = True) -> ResearchBenchPlan:
        pin = sha256(witness).hexdigest()
        signed = plan.model_copy(update={"signed_ac_evidence_sha256": pin})
        scripts = render_research_bench(
            signed,
            dut,
            {**frames, pin: witness} if retained else frames,
            expected_plan_sha256=canonical_digest(signed),
            owned_library_path="/owned/block",
        )
        assert 'm2Param(inst "acm" "-0.5")' in scripts.generate
        assert 'm2Property(cv "VNEG" "acm" "-0.5")' in scripts.reopen
        assert 'm2Param(inst "acp"' not in scripts.generate
        assert 'm2Require(dbFindProp(inst "acp")==nil)' in scripts.reopen
        return signed

    witness = evidence.model_dump_json().encode()
    signed = render(witness)
    with pytest.raises(ValueError, match="signed AC evidence"):
        render(witness, retained=False)
    with pytest.raises(ValueError, match="signed AC evidence"):
        render(witness.replace(b"mag=-500m", b"mag=500m"))
    with pytest.raises(ValueError, match="requires analogLib/vdc/symbol"):
        render(witness.replace(b"analogLib/vdc/symbol", b"analogLib/vsin/symbol"))

    def compare(candidate: bytes) -> None:
        verify_research_bench_netlist(
            signed,
            dut,
            candidate,
            raw,
            expected_plan_sha256=canonical_digest(signed),
            expected_netlist_sha256=sha256(candidate).hexdigest(),
            expected_dut_netlist_sha256=sha256(raw).hexdigest(),
            conditions=conditions,
            expected_conditions_sha256=canonical_digest(conditions),
        )

    opposite = full.replace(b"mag=500m phase=180", b"mag=-500m")
    compare(opposite)
    for wrong in (b"mag=500m", b"mag=-500m phase=180"):
        with pytest.raises(ValueError, match="bench device"):
            compare(opposite.replace(b"mag=-500m", wrong))


def test_fixed_vsin_pair_checks_native_shape_and_emitted_controls() -> None:
    plan, dut, frames, conditions, raw, full = _declarative_fixture()
    assert plan.primitive_cdf_sha256 is not None
    primitive = frames[plan.primitive_cdf_sha256]
    start = primitive.index(b'DEVICE|"analogLib"|"vdc"|nil\n')
    end = primitive.index(b"END\n", start)
    master = primitive[start:end]
    effective_rows = {
        "vdc": ("voltage", "500m"),
        "acm": ("voltage", "500m"),
        "va": ("voltage", "50m"),
        "freq": ("frequency", "1K"),
        "acp": (None, ""),
        "sinephase": (None, ""),
    }
    sources = []
    for index, node in enumerate(("pos", "neg")):
        name = f"V{index + 1}"
        fields: dict[Literal["va", "freq", "filenums", "sinephase"], str] = {
            "va": "50m",
            "freq": "1K",
            "filenums": "none",
        }
        magnitude = "-500m" if index else "500m"
        options = f"dc=500m mag={magnitude} type=sine ampl=50m freq=1K"
        if index:
            fields["sinephase"] = "180"
            options += " sinephase=180"
        sources.append(
            SignedAcSourceObservation(
                instance=name,
                master="analogLib/vsin/symbol",
                plus=node,
                minus="0",
                dc_string="500m",
                acm_string=magnitude,
                acp_absent=True,
                statement=f"{name} ({node} 0) vsource {options}",
                sine_string_properties=fields,
            )
        )
        rows = [f'DEVICE|"analogLib"|"vsin"|"{name}"']
        rows.extend(
            line.decode()
            for line in master.splitlines()
            if line.startswith((b"SIM|", b"META|", b"TERM|"))
        )
        for scope in ("base", "effective"):
            for field, (unit, value) in effective_rows.items():
                unit_token = f'"{unit}"' if unit else "nil"
                default = ""
                if scope == "base":
                    value = default
                elif field == "acm":
                    value = magnitude
                elif field == "sinephase" and index:
                    value = "180"
                rows.append(
                    f'PARAM|"{scope}"|"{field}"|"baseCellData"|{unit_token}|"{default}"|"{value}"'
                )
        primitive = primitive.removesuffix(b"COMPLETE\n")
        primitive += ("\n".join([*rows, "END", "COMPLETE", ""])).encode()
    native = ("simulator lang=spectre\n" + "\n".join(row.statement for row in sources)).encode()
    native_pin = sha256(native).hexdigest()
    frames[native_pin] = native

    def prepare(cdf: bytes) -> tuple[ResearchBenchPlan, dict[str, bytes]]:
        pin = sha256(cdf).hexdigest()
        witness = (
            SignedAcSourceEvidence(
                primitive_cdf_sha256=pin,
                native_manifest_sha256="1" * 64,
                saved_tree_sha256="2" * 64,
                reopen_artifact_sha256="3" * 64,
                effective_netlist_sha256=native_pin,
                sources=(sources[0], sources[1]),
            )
            .model_dump_json()
            .encode()
        )
        witness_pin = sha256(witness).hexdigest()
        return (
            plan.model_copy(
                update={
                    "primitive_cdf_sha256": pin,
                    "signed_ac_evidence_sha256": witness_pin,
                    "signed_ac_vsin_pair": True,
                }
            ),
            {**frames, pin: cdf, witness_pin: witness},
        )

    def render(cdf: bytes, bench: Circuit | None = None) -> ResearchBenchPlan:
        signed, captures = prepare(cdf)
        if bench is not None:
            signed = signed.model_copy(update={"bench": bench})
        scripts = render_research_bench(
            signed,
            dut,
            captures,
            expected_plan_sha256=canonical_digest(signed),
            owned_library_path="/owned/block",
        )
        assert scripts.generate.count('"analogLib" "vsin"') == 2
        assert 'm2Param(inst "va" "50m")' in scripts.generate
        assert 'm2Param(inst "acm" "-500m")' in scripts.generate
        assert 'm2Property(cv "VNEG" "sinephase" "180")' in scripts.reopen
        assert 'm2Require(dbFindProp(inst "acp")==nil)' in scripts.reopen
        assert 'm2Require(dbFindProp(inst "sinephase")==nil)' in scripts.reopen
        return signed

    signed = render(primitive)

    def remap_negative(source_net: str, dut_net: str = "inn") -> Circuit:
        bench = signed.bench.model_dump(mode="json")
        targets = {"DUT": ("inn", dut_net), "VNEG": ("PLUS", source_net)}
        for inst in bench["instances"]:
            if inst["name"] in targets:
                terminal, net = targets[inst["name"]]
                next(link for link in inst["links"] if link["terminal"] == terminal)["net"] = net
        bench["nets"] = list(
            dict.fromkeys(link["net"] for inst in bench["instances"] for link in inst["links"])
        )
        return Circuit.model_validate_json(json.dumps(bench))

    alias = render(primitive, remap_negative("negative_drive", "negative_drive"))
    assert alias.bench != signed.bench
    for source_net, dut_net in (
        ("vout", "inn"),  # output
        ("vdd", "inn"),  # supply
        ("vdd", "vdd"),  # input tied to a supply port
        ("vin", "vin"),  # shorted differential inputs
        ("inn", "negative_drive"),  # port label differs from its mapped net
    ):
        with pytest.raises(ValueError, match="distinct, unshared DUT inputs"):
            render(primitive, remap_negative(source_net, dut_net))

    changed = primitive.replace(b'|"va"|"baseCellData"|', b'|"vo"|"baseCellData"|')
    with pytest.raises(ValueError, match="vsin CDF parameter metadata"):
        render(changed)
    changed = primitive.replace(b'|"voltage"|""|"50m"', b'|"voltage"|""|"60m"')
    with pytest.raises(ValueError, match="effective CDF value disagrees"):
        render(changed)
    candidate = full.replace(
        b"mag=500m phase=0 type=dc", b"mag=500m type=sine ampl=50m freq=1K"
    ).replace(
        b"mag=500m phase=180 type=dc",
        b"mag=-500m type=sine ampl=50m freq=1K sinephase=180",
    )

    def verify(netlist: bytes, case: BenchNetlistConditions = conditions) -> None:
        verify_research_bench_netlist(
            signed,
            dut,
            netlist,
            raw,
            expected_plan_sha256=canonical_digest(signed),
            expected_netlist_sha256=sha256(netlist).hexdigest(),
            expected_dut_netlist_sha256=sha256(raw).hexdigest(),
            conditions=case,
            expected_conditions_sha256=canonical_digest(case),
        )

    verify(candidate)
    with pytest.raises(ValueError, match="bench device"):
        verify(candidate.replace(b"sinephase=180", b"phase=180"))
    with pytest.raises(ValueError, match="registered for AC only"):
        verify(candidate, conditions.model_copy(update={"analyses": (("tran", "stop=1n"),)}))
