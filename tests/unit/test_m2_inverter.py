"""Synthetic observations test closed generation, never qualify a real PDK."""

import hashlib
import json
import re
from typing import Any, cast

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.m2_inverter import (
    OwnedInverterGenerationIntent,
    OwnedInverterPlan,
    generation_intent,
    observed_devices,
    render_generator,
    verify_generated_netlist,
)
from cadence_mcp_bridge.schematic_plan import RevisionBinding


def fixture() -> tuple[OwnedInverterPlan, bytes]:
    lines = ["M2_CDF_V2"]
    definitions: tuple[
        tuple[str, str, str, tuple[str, ...], dict[str, tuple[str | None, str]]], ...
    ] = (
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
    )
    for library, cell, component, terms, parameters in definitions:
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
        native + b"EXTRA-1 (vin 0) resistor r=1\n",
        native + b"EXTRA#1 (vin 0) resistor r=1\n",
        native + b"E" + b"x" * 63 + b" (vin 0) resistor r=1\n",
        native + b"DUT (vdd vin vout 0) Dut\n",
        native + b"global vss\n",
        native + b"global 0\n",
        native.replace(b"global 0\n", b"global 0 vss\n"),
        native.replace(b"global 0\n", b"").replace(b"ends Dut\n", b"global 0\nends Dut\n"),
        native.replace(b"subckt Dut vdd vin vout vss\n", b"").replace(
            b"ends Dut\n", b"subckt Dut vdd vin vout vss\nends Dut\n"
        ),
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


def test_legacy_default_and_explicit_none_preserve_prechange_artifact_hashes() -> None:
    # Captured at parent0c08c83 BEFORE the optional preset implementation.
    plan, frame = fixture()
    original = render_generator(plan, frame, owned_library_path="/owned/work/new-library")
    explicit = render_generator(
        plan, frame, owned_library_path="/owned/work/new-library", experiment_profile=None,
    )
    assert original == explicit
    assert hashlib.sha256(original).hexdigest() == (
        "20b3573b65ee37d67d5c6f87fc8fc6a436f83ae95b01698352245dc1cb490ec7"
    )
    assert plan.semantic_sha256 == (
        "e7016caccbf3d420c3582807b21d49d99f44f13907790a98cf6245e36d496ac3"
    )
    assert hashlib.sha256(plan.model_dump_json().encode()).hexdigest() == (
        "ddb01aac2c82c4479a4ebfe01f8264987137f3d8819e3b6d39ff6ad87b9f8601"
    )
    schema = json.dumps(
        OwnedInverterPlan.model_json_schema(), sort_keys=True, separators=(",", ":"),
    )
    assert hashlib.sha256(schema.encode()).hexdigest() == (
        "b192d0f32add13577a6f4c85c36e57c3cd6d829c712873c8b2244a43586e50e6"
    )
    assert f"M2_OWNED_READBACK_V1|{plan.semantic_sha256}".encode() in original
    assert b"M2_OWNED_READBACK_V2" not in original


def test_long_preset_properties_reopen_checks_and_compound_v2_identity() -> None:
    plan, frame = fixture()
    intent = generation_intent(plan, "long-plateau-150ns-v1")
    program = render_generator(
        plan, frame, owned_library_path="/owned/work/new-library",
        experiment_profile="long-plateau-150ns-v1",
    ).decode()
    for name, value in (("td", "10n"), ("tr", "100p"), ("tf", "100p"),
                        ("pw", "65n"), ("per", "150n")):
        assert f'm2Param(inst "{name}" "{value}")' in program
        assert program.count(f'm2Property(cv "VIN" "{name}" "{value}")') == 2
    for value in ('m2Param(inst "w" "350n")', 'm2Param(inst "w" "120n")',
                  'm2Param(inst "vdc" "1")', 'm2Param(inst "c" "1p")'):
        assert value in program
    assert f"M2_OWNED_READBACK_V2|{intent.intent_sha256}" in program
    assert "M2_OWNED_READBACK_V1" not in program
    assert intent.plan == plan and intent.intent_sha256 != plan.semantic_sha256
    body = {"plan": plan.model_dump(mode="json"), "experiment_profile": "long-plateau-150ns-v1"}
    assert intent.intent_sha256 == hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()
    changed = plan.model_copy(update={"testbench_cell": "Bench2"})
    assert generation_intent(changed, "long-plateau-150ns-v1").intent_sha256 != intent.intent_sha256


@pytest.mark.parametrize("bad", ["digest", "plan", "profile", "extra"])
def test_custom_intent_cannot_validate_a_mutated_plan_or_preset(bad: str) -> None:
    plan, _ = fixture()
    data = generation_intent(plan, "long-plateau-150ns-v1").model_dump(mode="json")
    if bad == "digest":
        data["intent_sha256"] = plan.semantic_sha256
    elif bad == "plan":
        data["plan"]["testbench_cell"] = "Bench2"
    elif bad == "profile":
        data["experiment_profile"] = "arbitrary-pulse"
    else:
        data["pulse"] = "eval(x)"
    with pytest.raises(ValidationError):
        OwnedInverterGenerationIntent.model_validate_json(json.dumps(data))


def long_netlist() -> bytes:
    # Independent effective netlist fixture, not derived from renderer properties.
    return b"""simulator lang=spectre
global 0
parameters m2_vin=0
subckt Dut vdd vin vout vss
MN (vout vin vss vss) test_n w=(120n) l=100n as=1f ad=1f ps=1u pd=1u m=(1)*(1) simM=(1)*(1)
MP (vout vin vdd vdd) test_p w=(350n) l=100n as=1f ad=1f ps=1u pd=1u m=(1)*(1) simM=(1)*(1)
ends Dut
DUT (vdd vin vout 0) Dut
VDD (vdd 0) vsource dc=1 type=dc
VIN (vin 0) vsource dc=m2_vin type=pulse val0=0 val1=1 period=150n \\
delay=10n rise=100p fall=100p width=65n
CL (vout 0) capacitor c=1p
tran tran stop=150n maxstep=1n method=trap
"""


def test_independent_long_verifier_accepts_only_explicit_matching_profile() -> None:
    plan, frame = fixture()
    verify_generated_netlist(plan, frame, long_netlist(),
                             experiment_profile="long-plateau-150ns-v1")
    with pytest.raises(ValueError, match="hierarchy/stimulus/load"):
        verify_generated_netlist(plan, frame, long_netlist())
    old = long_netlist().replace(b"period=150n", b"period=4n").replace(
        b"delay=10n", b"delay=1n",
    ).replace(b"width=65n", b"width=2n")
    verify_generated_netlist(plan, frame, old, experiment_profile=None)
    with pytest.raises(ValueError, match="hierarchy/stimulus/load"):
        verify_generated_netlist(plan, frame, old, experiment_profile="long-plateau-150ns-v1")


@pytest.mark.parametrize("before,after", [
    (b"period=150n", b"period=149n"), (b"delay=10n", b"delay=11n"),
    (b"rise=100p", b"rise=90p"), (b"fall=100p", b"fall=90p"),
    (b"width=65n", b"width=64n"), (b"c=1p", b"c=2p"),
    (b"w=(350n)", b"w=(120n)"), (b"VDD (vdd 0)", b"VDD (vin 0)"),
])
def test_long_verifier_rejects_single_timing_load_device_or_supply_drift(
    before: bytes, after: bytes,
) -> None:
    plan, frame = fixture()
    with pytest.raises(ValueError):
        verify_generated_netlist(plan, frame, long_netlist().replace(before, after),
                                 experiment_profile="long-plateau-150ns-v1")


def test_long_verifier_rejects_extra_device_and_generator_rejects_cdf_drift() -> None:
    plan, frame = fixture()
    with pytest.raises(ValueError):
        verify_generated_netlist(plan, frame, long_netlist() + b"EXTRA (vin 0) resistor r=1\n",
                                 experiment_profile="long-plateau-150ns-v1")
    with pytest.raises(ValueError, match="CDF frame digest"):
        render_generator(plan, frame + b"x", owned_library_path="/owned/work/new-library",
                         experiment_profile="long-plateau-150ns-v1")


@pytest.mark.parametrize("bad", ["unknown", "", True, {"td": "10n"}])
def test_unknown_profiles_never_become_arbitrary_stimulus(bad: object) -> None:
    plan, frame = fixture()
    with pytest.raises(ValueError, match="unsupported inverter experiment profile"):
        render_generator(plan, frame, owned_library_path="/owned/work/new-library",
                         experiment_profile=cast(Any, bad))
    with pytest.raises(ValueError, match="unsupported inverter experiment profile"):
        verify_generated_netlist(plan, frame, long_netlist(), experiment_profile=cast(Any, bad))
    with pytest.raises(ValidationError):
        generation_intent(plan, cast(Any, bad))
