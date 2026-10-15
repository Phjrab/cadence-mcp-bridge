"""Synthetic observations test closed generation, never qualify a real PDK."""

import hashlib
import json
import re

import pytest

from cadence_mcp_bridge.m2_inverter import (
    OwnedInverterPlan,
    observed_devices,
    render_generator,
    verify_generated_netlist,
)
from cadence_mcp_bridge.schematic_plan import RevisionBinding


def fixture() -> tuple[OwnedInverterPlan, bytes]:
    lines = ["M2_CDF_V2"]
    for library, cell, component, terms, parameters in (
        (
            "TestPdk",
            "N",
            "nil",
            ("D", "G", "S", "B"),
            {
                "w": ("lengthMetric", "120n"),
                "l": ("lengthMetric", "100n"),
                "m": (None, "1"),
                "model": (None, "test_n"),
            },
        ),
        (
            "TestPdk",
            "P",
            "nil",
            ("D", "G", "S", "B"),
            {
                "w": ("lengthMetric", "350n"),
                "l": ("lengthMetric", "100n"),
                "m": (None, "1"),
                "model": (None, "test_p"),
            },
        ),
        ("analogLib", "vdc", "vsource", ("PLUS", "MINUS"), {"vdc": ("voltage", "")}),
        (
            "analogLib",
            "vpulse",
            "vsource",
            ("PLUS", "MINUS"),
            {
                k: ("voltage" if k in ("v1", "v2", "dc", "vdc") else "time", "")
                for k in ("v1", "v2", "dc", "vdc", "td", "tr", "tf", "pw", "per")
            },
        ),
        ("analogLib", "cap", "capacitor", ("PLUS", "MINUS"), {"c": ("capacitance", "1p")}),
    ):
        if library == "TestPdk":
            parameters.update(
                fw=parameters["w"],
                fingers=(None, "1"),
                simW=("lengthMetric", 'iPar("fw")'),
                simM=(None, 'iPar("m")*iPar("fingers")'),
                **{
                    "as": (None, "1f"),
                    "ad": (None, "1f"),
                    "ps": ("lengthMetric", "1u"),
                    "pd": ("lengthMetric", "1u"),
                },
            )
        lines += [f'DEVICE|"{library}"|"{cell}"|nil']
        lines += [f'TERM|"{t}"' for t in terms]
        order = "(" + " ".join(terms) + ")"
        for scope in ("base", "effective"):
            for key, (unit, value) in parameters.items():
                unit_data = f'"{unit}"' if unit else "nil"
                lines.append(
                    f'PARAM|"{scope}"|"{key}"|"instData"|{unit_data}|{json.dumps(value)}|{json.dumps(value)}'
                )
            for key in (
                "simInfo",
                "spectre",
                "componentName",
                "termOrder",
                "namePrefix",
                "modelName",
                "instParameters",
                "netlistProcedure",
            ):
                value = (
                    component if key == "componentName" else order if key == "termOrder" else "nil"
                )
                status = "missing" if value == "nil" and key == "componentName" else "observed"
                kind = (
                    "list"
                    if key in ("simInfo", "spectre", "termOrder", "instParameters")
                    else "symbol"
                )
                lines.append(f'META|"{scope}"|"{key}"|"{status}"|{kind}|{value}')
            lines.append(f'SIM|"{scope}"|{component}|{order}')
        lines.append("END")
    lines.append("COMPLETE")
    frame = ("\n".join(lines) + "\n").encode()
    plan = OwnedInverterPlan(
        binding=RevisionBinding(
            workspace_id="work",
            design_id="owned-inverter",
            revision_id="r1",
            source_baseline_sha256="a" * 64,
        ),
        cdf_frame_sha256=hashlib.sha256(frame).hexdigest(),
        output_library="Owned",
        dut_cell="Dut",
        testbench_cell="Bench",
        nmos_library="TestPdk",
        nmos_cell="N",
        pmos_library="TestPdk",
        pmos_cell="P",
    )
    return plan, frame


def test_generator_binds_observed_values_and_checks_before_and_after_save() -> None:
    plan, frame = fixture()
    assert len(observed_devices(plan, frame)) == 5
    program = render_generator(plan, frame, owned_library_path="/owned/work/new-library").decode()
    assert 'm2Param(inst "w" "350n")' in program
    assert 'm2Param(inst "w" "120n")' in program
    assert program.count('m2Property(cv "MP" "w" "350n")') == 2
    assert program.index("M2_OWNED_LIBRARY_COLLISION") < program.index("ddCreateLib(")
    assert program.index('m2Net(cv "MN" "B" "vss")') < program.index("dbSave(cv)")
    assert "span=min(span separation/8.0)" in program
    assert 'm2Port(cv "vin" "input" 100 100)' in program
    assert plan.semantic_sha256 in program
    for forbidden in ("dbCopyCellView", "dbDelete", "cdfSet", "eval(", "load("):
        assert forbidden not in program
    depth = 0
    for char in re.sub(r'"(?:[^"\\]|\\.)*"', "", program):
        depth += int(char == "(") - int(char == ")")
        assert depth >= 0
    assert depth == 0


@pytest.mark.parametrize(
    "change", ["frame", "unit", "terminal", "expression", "multiplicity", "metadata"]
)
def test_observation_drift_or_unknown_semantics_blocks_generation(change: str) -> None:
    plan, frame = fixture()
    if change == "frame":
        frame += b"x"
    else:
        frame = frame.replace(
            {
                "unit": b'"lengthMetric"',
                "terminal": b"(D G S B)",
                "expression": b'"350n"',
                "multiplicity": b'"m"|"instData"|nil|"1"|"1"',
                "metadata": b'"simInfo"|"observed"|list',
            }[change],
            {
                "unit": b'"unknown"',
                "terminal": b"(G D S B)",
                "expression": b'"pPar(width)"',
                "multiplicity": b'"m"|"instData"|nil|"1"|"1.5"',
                "metadata": b'"simInfo"|"missing"|list',
            }[change],
        )
        plan = plan.model_copy(update={"cdf_frame_sha256": hashlib.sha256(frame).hexdigest()})
    with pytest.raises(ValueError):
        render_generator(plan, frame, owned_library_path="/owned/work/new-library")


@pytest.mark.parametrize(
    "path", ["relative", "/owned/../vendor", "/owned/./x", '/owned/"x', "/owned/x\n", "/"]
)
def test_destination_syntax_rejects(path: str) -> None:
    plan, frame = fixture()
    with pytest.raises(ValueError):
        render_generator(plan, frame, owned_library_path=path)


def test_target_or_master_role_collision_rejects() -> None:
    plan, _ = fixture()
    with pytest.raises(ValueError):
        OwnedInverterPlan.model_validate(plan.model_dump() | {"output_library": "TestPdk"})
    with pytest.raises(ValueError):
        OwnedInverterPlan.model_validate(plan.model_dump() | {"dut_cell": "Bench"})


def test_effective_netlist_must_match_observed_derived_values_and_topology() -> None:
    plan, frame = fixture()
    native = b"""simulator lang=spectre
global 0
parameters m2_vin=0.5
subckt Dut vdd vin vout vss
MN (vout vin vss vss) test_n w=(120n) l=100n as=1f ad=1f ps=1u pd=1u m=(1)*(1) simM=(1)*(1)
MP (vout vin vdd vdd) test_p w=(350n) l=100n as=1f ad=1f ps=1u pd=1u m=(1)*(1) simM=(1)*(1)
ends Dut
DUT (vdd vin vout 0) Dut
VDD (vdd 0) vsource dc=1 type=dc
VIN (vin 0) vsource dc=m2_vin type=pulse val0=0 val1=1 period=4n \
delay=1n rise=100p fall=100p width=2n
CL (vout 0) capacitor c=1p
dc dc write="spectre.dc" annotate=status
"""
    verify_generated_netlist(plan, frame, native)
    for bad in (
        native.replace(b"w=(350n)", b"w=(120n)"),
        native.replace(b"(vout vin vdd vdd)", b"(vout vin 0 0)"),
        native.replace(b"c=1p", b"c=2p"),
        native + b"EXTRA (vin 0) resistor r=1\n",
        native + b"DUT (vdd vin vout 0) Dut\n",
    ):
        with pytest.raises(ValueError):
            verify_generated_netlist(plan, frame, bad)


@pytest.mark.parametrize("replacement", [b"", b'PARAM|"base"|"vdc"|"instData"|"time"|""|""\n'])
def test_unobserved_or_wrong_unit_pulse_vdc_rejects(replacement: bytes) -> None:
    plan, frame = fixture()
    # Keep vdc's own observation, alter only the pulse record.
    prefix, pulse = frame.split(b'DEVICE|"analogLib"|"vpulse"', 1)
    pulse = pulse.replace(b'PARAM|"base"|"vdc"|"instData"|"voltage"|""|""\n', replacement)
    frame = prefix + b'DEVICE|"analogLib"|"vpulse"' + pulse
    plan = plan.model_copy(update={"cdf_frame_sha256": hashlib.sha256(frame).hexdigest()})
    with pytest.raises(ValueError, match="parameter/unit"):
        render_generator(plan, frame, owned_library_path="/owned/work/new-library")
