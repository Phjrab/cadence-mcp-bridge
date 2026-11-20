"""Local fixtures for explicit circuit definitions and the existing inverter path."""

import json
from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError
from test_m2_inverter import fixture as inverter_fixture

from cadence_mcp_bridge.m2_inverter import OwnedInverterPlan, render_generator
from cadence_mcp_bridge.research_circuit import (
    MosBlockEvidence,
    OwnedMosBlockPlan,
    ResearchCircuit,
    adapt_owned_inverter,
    plan_owned_mos_block,
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
