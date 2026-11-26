"""Local fixtures for explicit circuit definitions and the existing inverter path."""

import json
from copy import deepcopy
from hashlib import sha256
from typing import Any

import pytest
from pydantic import ValidationError
from test_m2_inverter import fixture as inverter_fixture

from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration, DcInputs
from cadence_mcp_bridge.m2_inverter import OwnedInverterPlan, render_generator
from cadence_mcp_bridge.native_registration import RegistrationObservation
from cadence_mcp_bridge.native_runtime import NativeLibrary
from cadence_mcp_bridge.research_circuit import (
    MosBlockEvidence,
    MosBlockHandoffPins,
    MosBlockRegistrationHandoff,
    MosBlockStageReceipt,
    OwnedMosBlockPlan,
    ResearchCircuit,
    _verify_mos_block_handoff,
    adapt_owned_inverter,
    plan_owned_mos_block,
    project_mos_block_netlist,
    project_schematic_port_readback,
    render_owned_mos_block,
    verify_mos_block_handoff,
    verify_mos_block_registration_source,
    verify_owned_mos_block,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


def payload(plan: OwnedInverterPlan) -> dict[str, Any]:
    evidence = {
        "reference": "synthetic CDF fixture",
        "status": "confirmed",
        "sha256": plan.cdf_frame_sha256,
    }

    def point(x: int, y: int = 0) -> dict[str, str]:
        return {"x": str(x), "y": str(y)}

    def component(name: str, kind: str, x: int, **links: str) -> dict[str, Any]:
        return {
            "name": name,
            "kind": kind,
            "placement": {"origin": point(x)},
            "links": [{"terminal": terminal, "net": net} for terminal, net in links.items()],
        }

    devices = []
    for name, kind, x, width, rail, cell in (
        ("MN", "nmos", 0, "120", "vss", plan.nmos_cell),
        ("MP", "pmos", 4, "350", "vdd", plan.pmos_cell),
    ):
        devices.append(
            component(name, kind, x, D="vout", G="vin", S=rail, B=rail)
            | {
                "master": {"library": "TestPdk", "cell": cell, "view": "symbol"},
                "master_source": evidence,
                "geometry": {
                    "w": {"value": width, "unit": "nm"},
                    "fw": {"value": width, "unit": "nm"},
                    "length": {"value": "0.1", "unit": "um"},
                    "multiplier": 1,
                    "fingers": 1,
                    "width_meaning": "total_width",
                    "source": evidence,
                },
            }
        )
    names = ("vin", "vout", "vdd", "vss")
    dut = {
        "name": plan.dut_cell,
        "nets": names,
        "instances": devices,
        "ports": [
            {"name": name, "net": name, "direction": direction, "origin": point(100 + 2 * i, 100)}
            for i, (name, direction) in enumerate(
                zip(names, ("input", "output", "inputOutput", "inputOutput"), strict=True)
            )
        ],
        "symbol": {
            "lower_left": point(-1, -1),
            "upper_right": point(1, 1),
            "pins": [
                {"port": name, "origin": point(*xy)}
                for name, xy in zip(names, ((-1, 0), (1, 0), (0, 1), (0, -1)), strict=True)
            ],
        },
    }
    bench = {
        "name": plan.testbench_cell,
        "nets": ["vin", "vout", "vdd", "gnd!"],
        "instances": [
            component("DUT", "child", 0, vin="vin", vout="vout", vdd="vdd", vss="gnd!")
            | {"circuit": plan.dut_cell},
            component("VDD", "voltage", 4, PLUS="vdd", MINUS="gnd!") | {"dc_v": "1"},
            component("VIN", "voltage", 8, PLUS="vin", MINUS="gnd!")
            | {
                "dc_variable": "m2_vin",
                "pulse": {
                    "low_v": "0",
                    "high_v": "1",
                    "delay_s": "1e-9",
                    "rise_s": "100e-12",
                    "fall_s": "100e-12",
                    "width_s": "2e-9",
                    "period_s": "4e-9",
                },
            },
            component("CL", "capacitor", 12, PLUS="vout", MINUS="gnd!")
            | {"capacitance_f": "1e-12"},
        ],
    }
    return {
        "binding": plan.binding.model_dump(),
        "source": evidence,
        "dut": plan.dut_cell,
        "bench": plan.testbench_cell,
        "circuits": [dut, bench],
        "analyses": [{"kind": "dc", "temperature_c": "27"}],
        "observations": [{"kind": "device", "path": ["DUT", "MN"], "quantity": "gm"}],
        "measurements": [
            {
                "name": "power",
                "analysis": "dc",
                "quantity": "supply_power",
                "nets": ["vdd", "gnd!"],
                "supply_path": ["VDD"],
            }
        ],
    }


def adapt(data: dict[str, Any], plan: OwnedInverterPlan, frame: bytes) -> OwnedInverterPlan:
    definition = ResearchCircuit.model_validate_json(json.dumps(data))
    return adapt_owned_inverter(
        definition,
        frame,
        expected_binding=plan.binding,
        expected_definition_sha256=canonical_digest(definition),
        expected_cdf_frame_sha256=plan.cdf_frame_sha256,
        output_library=plan.output_library,
    )


def test_definition_reuses_owned_plan_and_renderer_exactly() -> None:
    plan, frame = inverter_fixture()
    adapted = adapt(payload(plan), plan, frame)
    assert adapted == plan
    assert render_generator(
        adapted, frame, owned_library_path="/owned/fixture"
    ) == render_generator(plan, frame, owned_library_path="/owned/fixture")


@pytest.mark.parametrize(
    "field", ["terminals", "net", "hierarchy", "symbol", "measurement", "width"]
)
def test_invalid_definition_rejected(field: str) -> None:
    plan, _ = inverter_fixture()
    data = payload(plan)
    dut, bench = data["circuits"]
    if field == "terminals":
        dut["instances"][0]["links"].pop()
    elif field == "net":
        dut["instances"][0]["links"][0]["net"] = "missing"
    elif field == "hierarchy":
        bench["instances"][0]["links"].pop()
    elif field == "symbol":
        dut["symbol"]["pins"].pop()
    elif field == "measurement":
        data["measurements"][0]["supply_path"] = ["CL"]
    else:
        dut["instances"][0]["geometry"]["fingers"] = 2
    with pytest.raises(ValidationError):
        ResearchCircuit.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("field", ["unresolved", "multiplier", "placement", "pulse"])
def test_valid_research_definition_can_be_outside_writer_profile(field: str) -> None:
    plan, frame = inverter_fixture()
    data = payload(plan)
    dut, bench = data["circuits"]
    if field == "unresolved":
        data["unresolved"] = ["paper_bulk"]
    elif field == "multiplier":
        dut["instances"][1]["geometry"]["multiplier"] = 6
    elif field == "placement":
        dut["instances"][1]["placement"]["orientation"] = "MX"
    else:
        bench["instances"][2]["pulse"]["period_s"] = "150e-9"
    with pytest.raises(ValueError, match="unresolved|differs|placement|profile"):
        adapt(data, plan, frame)


def test_rejects_stale_independent_definition_pin() -> None:
    plan, frame = inverter_fixture()
    definition = ResearchCircuit.model_validate_json(json.dumps(payload(plan)))
    with pytest.raises(ValueError, match="binding or digest mismatch"):
        adapt_owned_inverter(
            definition,
            frame,
            expected_binding=plan.binding,
            expected_definition_sha256="f" * 64,
            expected_cdf_frame_sha256=plan.cdf_frame_sha256,
            output_library=plan.output_library,
        )


def mos_block_fixture() -> tuple[OwnedMosBlockPlan, MosBlockEvidence]:
    inverter, _ = inverter_fixture()
    data = payload(inverter)
    dut, _ = data["circuits"]
    mn, mp = dut["instances"]
    for inst, model in ((mn, "test_n"), (mp, "test_p")):
        geo = inst["geometry"]
        inst["spectre"] = {
            "model": model,
            "width": geo["fw"],
            "length": geo["length"],
            "multiplier": geo["multiplier"],
            "source": geo["source"],
        }
    # Two instantiations of a named helper produce a larger hierarchical block.
    helper = deepcopy(dut)
    helper["name"] = "Helper"
    for name, x in (("U1", 8), ("U2", 12)):
        dut["instances"].append(
            {
                "name": name,
                "kind": "child",
                "circuit": "Helper",
                "placement": {"origin": {"x": str(x), "y": "0"}},
                "links": [
                    {"terminal": port, "net": port} for port in ("vin", "vout", "vdd", "vss")
                ],
            }
        )
    data["circuits"].append(helper)
    definition = ResearchCircuit.model_validate_json(json.dumps(data))
    plan = plan_owned_mos_block(
        definition,
        expected_binding=inverter.binding,
        expected_definition_sha256=canonical_digest(definition),
        output_library="OwnedBlock",
    )
    reopened = []
    netlisted = []
    for cell in (dut, helper):
        raw = deepcopy(cell)
        for inst in raw["instances"]:
            if inst["kind"] == "child":
                inst.update(library="OwnedBlock", view="symbol")
                continue
            geo = inst.pop("geometry")
            inst.pop("master_source")
            inst.pop("spectre")
            for key in ("w", "fw", "length", "multiplier", "fingers"):
                inst[key] = geo[key]
        raw["wires"] = []
        reopened.append(raw)
        netlisted.append(
            {
                "name": cell["name"],
                "ports": ["vin", "vout", "vdd", "vss"],
                "mos": [
                    {
                        "name": name,
                        "model": model,
                        "terminals": ["vout", "vin", rail, rail],
                        "width": {"value": width, "unit": "um"},
                        "length": {"value": "100", "unit": "nm"},
                        "multiplier": 1,
                    }
                    for name, model, rail, width in (
                        ("MN", "test_n", "vss", "0.12"),
                        ("MP", "test_p", "vdd", "0.35"),
                    )
                ],
                "children": [
                    {"name": name, "circuit": "Helper", "terminals": ["vin", "vout", "vdd", "vss"]}
                    for name in (("U1", "U2") if cell is dut else ())
                ],
            }
        )
    evidence = MosBlockEvidence.model_validate_json(
        json.dumps(
            {
                "plan_sha256": canonical_digest(plan),
                "output_library": "OwnedBlock",
                "reopened_tree_sha256": "a" * 64,
                "netlist_source_tree_sha256": "a" * 64,
                "reopen_artifact_sha256": "b" * 64,
                "netlist_artifact_sha256": "c" * 64,
                "reopened": reopened,
                "netlisted": netlisted,
            }
        )
    )
    return plan, evidence


def verify_block(plan: OwnedMosBlockPlan, evidence: MosBlockEvidence) -> None:
    verify_owned_mos_block(
        plan,
        evidence,
        expected_plan_sha256=canonical_digest(plan),
        expected_reopened_tree_sha256="a" * 64,
        expected_reopen_artifact_sha256="b" * 64,
        expected_netlist_artifact_sha256="c" * 64,
    )


def test_hierarchical_mos_block_compares_reopen_and_effective_netlist() -> None:
    plan, evidence = mos_block_fixture()
    assert {cell.name for cell in plan.circuits} == {"Dut", "Helper"}
    verify_block(plan, evidence)


@pytest.mark.parametrize(
    "field", ["pin", "bulk", "w", "multiplier", "subckt", "child_library", "old_tree", "artifact"]
)
def test_hierarchical_mos_block_rejects_changed_evidence(field: str) -> None:
    plan, evidence = mos_block_fixture()
    data = evidence.model_dump(mode="json")
    if field == "pin":
        data["reopened"][0]["symbol"]["pins"].pop()
    elif field == "bulk":
        data["netlisted"][0]["mos"][1]["terminals"][3] = "vss"
    elif field == "w":
        data["reopened"][0]["instances"][0]["fw"]["value"] = "350"
    elif field == "multiplier":
        data["netlisted"][0]["mos"][1]["multiplier"] = 6
    elif field == "subckt":
        data["netlisted"][0]["children"][0]["terminals"] = ["vout", "vin", "vdd", "vss"]
    elif field == "child_library":
        data["reopened"][0]["instances"][2]["library"] = "Foreign"
    elif field == "old_tree":
        data["netlist_source_tree_sha256"] = "d" * 64
    else:
        data["netlist_artifact_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="mismatch"):
        verify_block(plan, MosBlockEvidence.model_validate_json(json.dumps(data)))


def test_mos_block_requires_confirmed_simulator_mapping() -> None:
    inverter, _ = inverter_fixture()
    definition = ResearchCircuit.model_validate_json(json.dumps(payload(inverter)))
    with pytest.raises(ValueError, match="confirmed symbol, geometry and Spectre mapping"):
        plan_owned_mos_block(
            definition,
            expected_binding=inverter.binding,
            expected_definition_sha256=canonical_digest(definition),
            output_library="OwnedBlock",
        )


def test_block_renderer_emits_separate_save_and_reopen_checks() -> None:
    plan, _ = mos_block_fixture()
    inverter, frame = inverter_fixture()
    pins = {inverter.cdf_frame_sha256: frame}
    one = render_owned_mos_block(
        plan, pins, expected_plan_sha256=canonical_digest(plan), owned_library_path="/owned/block"
    )
    assert one == render_owned_mos_block(
        plan, pins, expected_plan_sha256=canonical_digest(plan), owned_library_path="/owned/block"
    )
    assert one.generate.index('"Helper" "symbol" "schematicSymbol" "w"') < one.generate.index(
        '"Dut" "schematic" "schematic" "w"'
    )
    assert one.generate.index("M2_OWNED_LIBRARY_COLLISION") < one.generate.index("ddCreateLib(")
    assert one.generate.count("dbSave(cv)") == 4
    assert "ddCreateLib(" not in one.reopen and "dbSave(" not in one.reopen
    assert one.reopen.count('"" "r"') >= 4
    assert 'm2Net(cv "MN" "B" "vss")' in one.reopen
    assert 'm2BlockEffective(inst "w" "120n")' in one.reopen
    assert "MOS_BLOCK_REOPENED_CHECKED|" + canonical_digest(plan) in one.reopen


def test_research_writer_checks_literal_positions_before_wiring_and_save() -> None:
    plan, _ = mos_block_fixture()
    inverter, frame = inverter_fixture()
    scripts = render_owned_mos_block(
        plan,
        {inverter.cdf_frame_sha256: frame},
        expected_plan_sha256=canonical_digest(plan),
        owned_library_path="/owned/block",
    )
    body = scripts.generate.split("procedure(m2BlockRun()", 1)[1]
    assert "m2Instance(" not in body
    assert "m2Require(and(inst inst~>orient==orientation))" in scripts.generate
    assert "m2BlockPoint(inst~>xy x y)" in scripts.generate
    assert "xCoord(point)==x yCoord(point)==y" in scripts.generate
    for cell in plan.circuits:
        view_start = body.index(f'"{cell.name}" "schematic" "schematic" "w"')
        view_end = body.index("m2Require(dbSave(cv))", view_start)
        view = body[view_start:view_end]
        checked = view.index("m2Require(schCheck(cv))")
        for instance in cell.instances:
            x, y = instance.placement.origin.x, instance.placement.origin.y
            name = instance.name
            pos = view.index(f'inst=m2Require(dbCreateInst(cv master "{name}" list({x} {y}) "R0"))')
            assert "master=m2Require(dbOpenCellViewByType(" in view[:pos].splitlines()[-1]
            following = view[pos:].splitlines()
            assert following[1] == f'm2BlockPlacement(inst {x} {y} "R0")'
            assert any(line.startswith("m2Wire(") for line in following[2:])
            gate = view.index(f'm2BlockCheckPlacement(cv "{name}" {x} {y} "R0")')
            assert checked < gate
    reopen_body = scripts.reopen.split("procedure(m2BlockRun()", 1)[1]
    assert "dbCreateInst(" not in reopen_body
    assert 'm2BlockInstance(cv "MN" "TestPdk" "N" 0 0 4)' in reopen_body


@pytest.mark.parametrize("issue", ["missing", "changed", "wrong_plan", "routed"])
def test_block_renderer_fails_closed(issue: str) -> None:
    plan, _ = mos_block_fixture()
    inverter, frame = inverter_fixture()
    pins = {inverter.cdf_frame_sha256: frame}
    digest = canonical_digest(plan)
    if issue == "missing":
        pins.clear()
    elif issue == "changed":
        pins[inverter.cdf_frame_sha256] += b"x"
    elif issue == "wrong_plan":
        digest = "d" * 64
    else:
        raw = plan.model_dump(mode="json")
        raw["circuits"][0]["wires"] = [
            {"net": "vin", "points": [{"x": "0", "y": "0"}, {"x": "1", "y": "0"}]}
        ]
        plan = OwnedMosBlockPlan.model_validate_json(json.dumps(raw))
        digest = canonical_digest(plan)
    with pytest.raises(ValueError, match="frame|digest|label stubs"):
        render_owned_mos_block(
            plan, pins, expected_plan_sha256=digest, owned_library_path="/owned/block"
        )


def test_generation_uses_distinct_target_cdf_and_checks_measured_junctions() -> None:
    plan, _ = mos_block_fixture()
    inverter, frame = inverter_fixture()
    nmos, _ = frame.removeprefix(b"M2_CDF_V2\n").split(b"END\n", 1)
    nmos = nmos.replace(b'DEVICE|"TestPdk"|"N"|nil', b'DEVICE|"TestPdk"|"N"|"MeasuredN"')
    target = b"M2_CDF_V2\n" + nmos + b"END\nCOMPLETE\n"
    target_pin = sha256(target).hexdigest()
    raw = plan.model_dump(mode="json")
    for cell in raw["circuits"]:
        for instance in cell["instances"]:
            if instance["kind"] == "nmos":
                instance["geometry"]["source"]["sha256"] = "a" * 64
                instance["spectre"]["source"]["sha256"] = "b" * 64
                instance["geometry"]["generation_observation"] = {
                    "cdf_sha256": target_pin,
                    "junctions": {"as": "1f", "ad": "1f", "ps": "1u", "pd": "1u"},
                }
    plan = OwnedMosBlockPlan.model_validate_json(json.dumps(raw))
    plan_pin = canonical_digest(plan)
    scripts = render_owned_mos_block(
        plan,
        {inverter.cdf_frame_sha256: frame, target_pin: target},
        expected_plan_sha256=plan_pin,
        owned_library_path="/owned/block",
    )
    assert 'list("as" "1f" nil)' in scripts.generate
    assert 'list("pd" "1u" "lengthMetric")' in scripts.reopen
    assert f"OTA17_TARGET_PROPERTIES_END|{plan_pin}" in scripts.reopen
    for candidate in (
        raw_block_netlist(),
        raw_block_netlist().replace(b"as=1f", b"as=0.001p", 1),
    ):
        project_mos_block_netlist(
            plan,
            candidate,
            expected_plan_sha256=plan_pin,
            expected_netlist_artifact_sha256=sha256(candidate).hexdigest(),
        )
    for candidate in (
        raw_block_netlist().replace(b"as=1f", b"as=2f"),
        raw_block_netlist().replace(b" simM=(1)*(1)", b""),
    ):
        with pytest.raises(ValueError, match="junctions or multiplicity"):
            project_mos_block_netlist(
                plan,
                candidate,
                expected_plan_sha256=plan_pin,
                expected_netlist_artifact_sha256=sha256(candidate).hexdigest(),
            )


def raw_block_netlist() -> bytes:
    transistors = (
        "MN (vout vin vss vss) test_n w=(120n) l=100n as=1f ad=1f ps=1u pd=1u "
        "m=(1)*(1) simM=(1)*(1)\n"
        "MP (vout vin vdd vdd) test_p w=(350n) l=100n as=1f ad=1f ps=1u pd=1u "
        "m=(1)*(1) simM=(1)*(1)\n"
    )
    return (
        "simulator lang=spectre\nglobal 0\nsubckt Helper vin vout vdd vss\n"
        + transistors
        + "ends Helper\nsubckt Dut (vin vout vdd vss)\n"
        + transistors
        + "U1 (vin vout vdd vss) Helper\nU2 (vin vout vdd vss) Helper\nends Dut\n"
    ).encode("ascii")


def test_project_raw_hierarchical_spectre() -> None:
    plan, _ = mos_block_fixture()
    raw = raw_block_netlist()
    projected = project_mos_block_netlist(
        plan,
        raw,
        expected_plan_sha256=canonical_digest(plan),
        expected_netlist_artifact_sha256=sha256(raw).hexdigest(),
    )
    assert [cell.name for cell in projected] == ["Dut", "Helper"]
    assert [inst.name for inst in projected[0].children] == ["U1", "U2"]


@pytest.mark.parametrize(
    "old,new",
    [
        (b"w=(350n)", b"w=(120n)"),
        (b"(vout vin vdd vdd)", b"(vout vin vdd vss)"),
        (b"simM=(1)*(1)", b"simM=(2)*(1)"),
        (b"U1 (vin vout vdd vss) Helper", b"U1 (vout vin vdd vss) Helper"),
        (b"ends Dut", b"ends Dut\nX (vin vout vdd vss) Dut"),
    ],
)
def test_raw_projection_rejects_changed_spectre_body(old: bytes, new: bytes) -> None:
    plan, _ = mos_block_fixture()
    raw = raw_block_netlist().replace(old, new, 1)
    with pytest.raises(ValueError, match="mismatch|multiplicity|unexpected"):
        project_mos_block_netlist(
            plan,
            raw,
            expected_plan_sha256=canonical_digest(plan),
            expected_netlist_artifact_sha256=sha256(raw).hexdigest(),
        )


def handoff_fixture() -> tuple[OwnedMosBlockPlan, dict[str, Any]]:
    plan, _ = mos_block_fixture()
    inverter, frame = inverter_fixture()
    frames = {inverter.cdf_frame_sha256: frame}
    plan_sha = canonical_digest(plan)
    library = NativeLibrary(name="OwnedBlock", path="/owned/block", tree_sha256="a" * 64)
    scripts = render_owned_mos_block(
        plan, frames, expected_plan_sha256=plan_sha, owned_library_path=library.path
    )
    save_stdout = f"Cadence fixture\nMOS_BLOCK_SAVED|{plan_sha}\n".encode("ascii")
    reopen_stdout = f"Cadence fixture\nMOS_BLOCK_REOPENED_CHECKED|{plan_sha}\n".encode("ascii")
    raw = raw_block_netlist()
    full = raw + b'U (vin vout vdd vss) Dut\ndc dc write="spectre.dc" annotate=status\n'
    common: dict[str, Any] = dict(
        operation_id="11111111-2222-4333-8444-555555555555",
        plan_sha256=plan_sha,
        library=library,
        source_cell="/owned/block/Dut",
        source_tree_sha256="b" * 64,
        bench_cell="/owned/block/Bench",
        bench_tree_sha256="c" * 64,
    )
    saved = MosBlockStageReceipt(
        phase="save",
        artifact_sha256=sha256(save_stdout).hexdigest(),
        script_sha256=sha256(scripts.generate.encode("ascii")).hexdigest(),
        **common,
    )
    reopened = MosBlockStageReceipt(
        phase="reopen",
        artifact_sha256=sha256(reopen_stdout).hexdigest(),
        script_sha256=sha256(scripts.reopen.encode("ascii")).hexdigest(),
        **common,
    )
    netlisted = MosBlockStageReceipt(
        phase="netlist",
        artifact_sha256=sha256(full).hexdigest(),
        **common,
    )
    return plan, dict(
        scripts=scripts,
        bench_name="Bench",
        save_markers=(f"MOS_BLOCK_SAVED|{plan_sha}",),
        reopen_markers=(f"MOS_BLOCK_REOPENED_CHECKED|{plan_sha}",),
        saved=saved,
        reopened=reopened,
        netlisted=netlisted,
        save_stdout=save_stdout,
        reopen_stdout=reopen_stdout,
        raw_netlist=raw,
        full_netlist=full,
        pins=MosBlockHandoffPins(
            plan_sha256=plan_sha,
            save_receipt_sha256=canonical_digest(saved),
            reopen_receipt_sha256=canonical_digest(reopened),
            netlist_receipt_sha256=canonical_digest(netlisted),
            raw_netlist_sha256=sha256(raw).hexdigest(),
            full_netlist_sha256=sha256(full).hexdigest(),
            bench_plan_sha256="d" * 64,
            bench_conditions_sha256="e" * 64,
        ),
    )


def test_mos_handoff_matches_existing_registration_source_contract() -> None:
    plan, options = handoff_fixture()
    handoff = _verify_mos_block_handoff(plan, **options)
    assert handoff.binding == plan.binding
    assert handoff.provenance == "OPERATOR_AUTHENTICATION_REQUIRED"
    assert handoff.source_cell == "/owned/block/Dut"
    assert handoff.handoff_sha256 == canonical_digest(_verify_mos_block_handoff(plan, **options))
    observation = RegistrationObservation(
        schema_version=1,
        status="REGISTRATION_FINGERPRINTS_PREPARED_NOT_AUTHORIZED",
        ade=AdeExecutionRegistration(
            schema_version=1,
            design_id=handoff.binding.design_id,
            analysis_id="dc",
            design_profile_sha256="1" * 64,
            variable_set_sha256=None,
            source_tree_sha256=handoff.bench_tree_sha256,
            ade_state_tree_sha256="2" * 64,
            static_statements_sha256=handoff.static_statements_sha256,
            model_includes=(),
            inputs=DcInputs(analysis="dc", mode="saved_operating_point", statement_sha256="4" * 64),
        ),
        libraries=(handoff.library,),
        model_files=(),
        source_cell=handoff.bench_cell,
        source_state="/owned/state",
        baseline_input_sha256=handoff.pins.full_netlist_sha256,
        operator_uid=500,
        helper_sha256="6" * 64,
        execution_authorized=False,
        new_simulations=0,
        new_reservations=0,
    )
    verify_mos_block_registration_source(
        handoff,
        observation,
        expected_handoff_sha256=handoff.handoff_sha256,
        expected_observation_sha256=canonical_digest(observation),
    )
    wrong_tree = observation.ade.model_copy(update={"source_tree_sha256": "9" * 64})
    wrong_static = observation.ade.model_copy(update={"static_statements_sha256": "9" * 64})
    wrong_lib = handoff.library.model_copy(update={"tree_sha256": "9" * 64})
    for change in (
        {"source_cell": "/owned/block/Dut"},
        {"ade": wrong_tree},
        {"ade": wrong_static},
        {"libraries": (wrong_lib,)},
        {"baseline_input_sha256": "9" * 64},
    ):
        foreign = observation.model_copy(update=change)
        with pytest.raises(ValueError, match="registration source or library"):
            verify_mos_block_registration_source(
                handoff,
                foreign,
                expected_handoff_sha256=handoff.handoff_sha256,
                expected_observation_sha256=canonical_digest(foreign),
            )


@pytest.mark.parametrize(
    ("stage", "field", "value"),
    [
        ("reopened", "operation_id", "22222222-2222-4333-8444-555555555555"),
        ("reopened", "source_tree_sha256", "f" * 64),
        ("saved", "script_sha256", "f" * 64),
        ("netlisted", "source_cell", "/owned/block/Other"),
        ("netlisted", "phase", "reopen"),
    ],
)
def test_mos_handoff_rejects_independently_pinned_inconsistent_stages(
    stage: str, field: str, value: str
) -> None:
    plan, options = handoff_fixture()
    fields = {field: value}
    if field == "phase":
        fields["script_sha256"] = "f" * 64
    receipt = options[stage].model_copy(update=fields)
    options[stage] = receipt
    pin = {"saved": "save", "reopened": "reopen", "netlisted": "netlist"}[stage]
    options["pins"] = options["pins"].model_copy(
        update={f"{pin}_receipt_sha256": canonical_digest(receipt)}
    )
    with pytest.raises(ValueError, match="binding|executed script"):
        _verify_mos_block_handoff(plan, **options)


@pytest.mark.parametrize(
    "change", ["receipt", "stdout", "duplicate", "stale_netlist", "bulk", "full_digest", "full_dut"]
)
def test_mos_handoff_checks_exact_artifacts_and_dut_content(change: str) -> None:
    plan, options = handoff_fixture()
    if change == "receipt":
        options["pins"] = options["pins"].model_copy(update={"reopen_receipt_sha256": "f" * 64})
    elif change == "stdout":
        options["save_stdout"] += b"unexpected"
    elif change == "duplicate":
        options["reopen_stdout"] *= 2
        receipt = options["reopened"].model_copy(
            update={"artifact_sha256": sha256(options["reopen_stdout"]).hexdigest()}
        )
        options["reopened"] = receipt
        options["pins"] = options["pins"].model_copy(
            update={"reopen_receipt_sha256": canonical_digest(receipt)}
        )
    elif change in {"full_digest", "full_dut"}:
        raw = options["full_netlist"].replace(b"(vout vin vdd vdd)", b"(vout vin vdd vss)", 1)
        options["full_netlist"] = raw
        if change == "full_dut":
            digest = sha256(raw).hexdigest()
            receipt = options["netlisted"].model_copy(update={"artifact_sha256": digest})
            options["netlisted"] = receipt
            options["pins"] = options["pins"].model_copy(
                update={
                    "netlist_receipt_sha256": canonical_digest(receipt),
                    "full_netlist_sha256": digest,
                },
            )
    else:
        raw = options["raw_netlist"].replace(b"(vout vin vdd vdd)", b"(vout vin vdd vss)", 1)
        options["raw_netlist"] = raw
        if change == "bulk":
            digest = sha256(raw).hexdigest()
            options["pins"] = options["pins"].model_copy(
                update={
                    "raw_netlist_sha256": digest,
                }
            )
    with pytest.raises(
        ValueError, match="binding|stdout|marker|digest|topology|projection differs"
    ):
        _verify_mos_block_handoff(plan, **options)


def test_composite_handoff_requires_the_exact_top_level_bench() -> None:
    from cadence_mcp_bridge import research_bench as bench_api

    fixture_plan, options = handoff_fixture()
    inverter, frame = inverter_fixture()
    data = payload(inverter)
    bench = data["circuits"][1]
    bench["instances"][2]["pulse"].update(delay_s="10e-9", width_s="65e-9", period_s="150e-9")
    data["circuits"] = [cell.model_dump(mode="json") for cell in fixture_plan.circuits] + [bench]
    definition = ResearchCircuit.model_validate_json(json.dumps(data))
    definition_sha = canonical_digest(definition)
    plan = plan_owned_mos_block(
        definition,
        expected_binding=inverter.binding,
        expected_definition_sha256=definition_sha,
        output_library=fixture_plan.output_library,
    )
    plan_sha = canonical_digest(plan)
    bench_plan = bench_api.plan_research_bench(
        definition,
        plan,
        expected_definition_sha256=definition_sha,
        expected_dut_plan_sha256=plan_sha,
    )
    bench_sha = canonical_digest(bench_plan)
    frames = {inverter.cdf_frame_sha256: frame}
    scripts = bench_api.render_research_bench(
        bench_plan,
        plan,
        frames,
        expected_plan_sha256=bench_sha,
        owned_library_path="/owned/block",
    )
    conditions = bench_api.BenchNetlistConditions(
        parameters={"m2_vin": "0.5"},
        includes=(),
        analyses=(("dc", 'write="spectre.dc" annotate=status'),),
        fixed_top_level=("global 0",),
    )
    raw = options["raw_netlist"]
    full = raw.replace(b"global 0\n", b"global 0\nparameters m2_vin=0.5\n", 1) + (
        b"DUT (vin vout vdd 0) Dut\n"
        b"VDD (vdd 0) vsource dc=1 type=dc\n"
        b"VIN (vin 0) vsource dc=m2_vin type=pulse val0=0 val1=1 period=150n "
        b"delay=10n rise=100p fall=100p width=65n\n"
        b"CL (vout 0) capacitor c=1p\n"
        b'dc dc write="spectre.dc" annotate=status\n'
    )
    stdout = []
    receipts = []
    for key, markers, script in (
        ("saved", scripts.save_markers, scripts.generate),
        ("reopened", scripts.reopen_markers, scripts.reopen),
    ):
        output = ("\n".join(markers) + "\n").encode("ascii")
        stdout.append(output)
        receipts.append(
            options[key].model_copy(
                update={
                    "plan_sha256": plan_sha,
                    "artifact_sha256": sha256(output).hexdigest(),
                    "script_sha256": sha256(script.encode("ascii")).hexdigest(),
                }
            )
        )
    saved, reopened = receipts

    def verify(candidate: bytes) -> MosBlockRegistrationHandoff:
        full_sha = sha256(candidate).hexdigest()
        netlisted = options["netlisted"].model_copy(
            update={"plan_sha256": plan_sha, "artifact_sha256": full_sha}
        )
        pins = MosBlockHandoffPins(
            plan_sha256=plan_sha,
            bench_plan_sha256=bench_sha,
            bench_conditions_sha256=canonical_digest(conditions),
            save_receipt_sha256=canonical_digest(saved),
            reopen_receipt_sha256=canonical_digest(reopened),
            netlist_receipt_sha256=canonical_digest(netlisted),
            raw_netlist_sha256=sha256(raw).hexdigest(),
            full_netlist_sha256=full_sha,
        )
        return verify_mos_block_handoff(
            plan,
            bench_plan,
            frames,
            pins=pins,
            conditions=conditions,
            saved=saved,
            reopened=reopened,
            netlisted=netlisted,
            save_stdout=stdout[0],
            reopen_stdout=stdout[1],
            raw_netlist=raw,
            full_netlist=candidate,
        )

    assert verify(full).bench_cell == "/owned/block/Bench"
    with pytest.raises(ValueError, match="bench device, model, terminals or effective values"):
        verify(full.replace(b"capacitor c=1p", b"capacitor c=2p"))


@pytest.mark.parametrize(
    "change",
    ("none", "missing-origin", "wrong-origin", "wrong-net", "duplicate", "old-tree", "symbol"),
)
def test_schematic_port_readback_requires_real_coordinates_on_the_bound_tree(change: str) -> None:
    plan, options = handoff_fixture()
    handoff = _verify_mos_block_handoff(plan, **options)
    rows = [
        port.model_dump(mode="json") | {"cell": cell.name}
        for cell in reversed(plan.circuits)
        for port in reversed(cell.ports)
    ]
    data = dict(
        operation_id=handoff.operation_id,
        plan_sha256=handoff.pins.plan_sha256,
        output_library=handoff.library.name,
        reopened_tree_sha256=handoff.source_tree_sha256,
        library_tree_sha256=handoff.library.tree_sha256,
        origin_basis="schematic_pin_instance_xy",
        ports=rows,
    )
    if change == "missing-origin":
        rows[0].pop("origin")
    elif change == "wrong-origin":
        rows[0]["origin"]["y"] = "359"
    elif change == "wrong-net":
        rows[0]["net"] = "vin"
    elif change == "duplicate":
        rows.append(rows[0])
    elif change == "old-tree":
        data["library_tree_sha256"] = "f" * 64
    elif change == "symbol":
        data["origin_basis"] = "symbol_pin_xy"
    raw = json.dumps(data).encode("ascii")
    kwargs = dict(
        expected_handoff_sha256=handoff.handoff_sha256,
        expected_observation_sha256=sha256(raw).hexdigest(),
    )
    if change == "none":
        assert project_schematic_port_readback(plan, handoff, raw, **kwargs) == {
            cell.name: tuple(sorted(cell.ports, key=lambda port: port.name))
            for cell in plan.circuits
        }
    else:
        with pytest.raises(ValueError):
            project_schematic_port_readback(plan, handoff, raw, **kwargs)
