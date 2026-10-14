"""Independent known-loop calibration and rejection; no native origin claim."""

import cmath
import hashlib
import json
import math

import pytest
from pydantic import ValidationError
from test_generic_measurements import frame_for, reader_for
from test_generic_measurements import operator as operator
from test_generic_measurements import operator_base as operator_base

from cadence_mcp_bridge.generic_loop import IdealVoltageLoopDefinition, sampled_loop_margin
from cadence_mcp_bridge.generic_measurements import project_frame
from cadence_mcp_bridge.operator_operations import OperationRejected


def definition(statements=None, **changes):
    statements = statements or [
        "feedback (Ret Cm Op Om) vcvs gain=1",
        "probe (In Ret) vsource dc=0 mag=1 phase=0 type=dc",
        "positive (Fixed 0) vsource dc=0.5 mag=0 phase=0 type=dc",
        "common (Cm 0) vsource dc=0.5 mag=0 phase=0 type=dc",
    ]
    values = dict(
        static_statements=statements,
        static_statements_sha256=hashlib.sha256(
            ("\n".join(statements) + "\n").encode(),
        ).hexdigest(),
        return_node="Ret", driven_input_node="In", fixed_input_node="Fixed", common_node="Cm",
        output_plus_node="Op", output_minus_node="Om", feedback_instance="feedback",
        probe_instance="probe", return_signal="ret", driven_input_signal="inn",
        fixed_input_signal="inp", common_signal="cm",
        nodes=[{"logical_id": n, "selector": s} for n, s in
               (("ret", "/Ret"), ("inn", "/In"), ("inp", "/Fixed"), ("cm", "/Cm"))],
    )
    return IdealVoltageLoopDefinition.model_validate_json(json.dumps(values | changes))


def waves(ratio=None, ppd=16):
    # Solve the independently known feedback equations Vm-Vr=1 and Vr=-L*Vm.
    # This forward simulation construction does not use the margin implementation.
    ratio = ratio or (lambda f: 100 / (1 + 1j * f / 100) ** 2)
    result = {n: [] for n in ("ret", "inn", "inp", "cm")}
    for i in range(6 * ppd + 1):
        f = 10 ** (i / ppd)
        loop = ratio(f)
        vm = 1 / (1 + loop)
        vr = vm - 1
        for name, value in (("ret", vr), ("inn", vm), ("inp", 0j), ("cm", 0j)):
            result[name].append({"frequency_hz": f, "real_v": value.real, "imag_v": value.imag})
    return result


def test_independent_two_pole_known_loop_sign_and_grid():
    # |100/(1+j*f/100)^2|=1 => f=100*sqrt(99), PM=180-2*atan(sqrt(99)).
    expected_f = 100 * math.sqrt(99)
    expected_pm = 180 - 2 * math.degrees(math.atan(math.sqrt(99)))
    coarse = sampled_loop_margin(waves(ppd=8), definition())
    fine = sampled_loop_margin(waves(), definition())
    assert fine["status"] == coarse["status"] == "OBSERVED_SINGLE_SAMPLED_MARGIN"
    assert fine["value"] == pytest.approx(expected_pm, abs=.1)
    assert fine["crossings"][0]["frequency_hz"] == pytest.approx(expected_f, rel=.001)
    assert abs(fine["value"] - coarse["value"]) < .1
    assert fine["loop_ratio"][0]["real_v_per_v"] > 0
    assert fine["native_provenance"] == "NOT_ATTESTED"


@pytest.mark.parametrize("bad", ["hash", "gain", "extra", "stimulus", "mapping", "unsaved"])
def test_closed_topology_rejects(bad):
    model = definition().model_dump(mode="json")
    statements = list(model["static_statements"])
    if bad == "hash":
        model["static_statements_sha256"] = "a" * 64
    elif bad == "gain":
        statements[0] = statements[0].replace("gain=1", "gain=2")
    elif bad == "extra":
        statements.append("extra (Ret 0) resistor r=1")
    elif bad == "stimulus":
        statements[2] = statements[2].replace("mag=0", "mag=1")
    elif bad == "unsaved":
        statements.append("rail (Unknown 0) vsource dc=1")
    else:
        model["nodes"][0]["selector"] = "/Op"
    if bad not in ("hash", "mapping"):
        model["static_statements"] = statements
        model["static_statements_sha256"] = hashlib.sha256(
            ("\n".join(statements) + "\n").encode(),
        ).hexdigest()
    with pytest.raises(ValidationError):
        IdealVoltageLoopDefinition.model_validate_json(json.dumps(model))


@pytest.mark.parametrize("bad", ["injection", "stimulus", "missing", "axes", "nan", "zero"])
def test_measured_proof_rejects(bad):
    data = waves()
    if bad == "injection":
        data["inn"][3]["real_v"] += .01
    elif bad == "stimulus":
        data["inp"][4]["imag_v"] = 1
    elif bad == "missing":
        del data["cm"]
    elif bad == "axes":
        data["cm"][3]["frequency_hz"] *= 1.01
    elif bad == "nan":
        data["ret"][3]["real_v"] = float("nan")
    else:
        data["inn"][3].update(real_v=0, imag_v=0)
        data["ret"][3].update(real_v=-1, imag_v=0)
    with pytest.raises(OperationRejected):
        sampled_loop_margin(data, definition())


def test_no_crossing_coarse_and_reversed_feedback_remain_unqualified():
    assert sampled_loop_margin(waves(lambda f: 2 + 0j), definition())["value"] is None
    coarse = sampled_loop_margin(waves(ppd=4), definition())
    assert coarse["grid_underresolved"] and coarse["value"] is None
    reversed_sign = sampled_loop_margin(waves(lambda f: -10 / (1 + 1j * f / 100)), definition())
    assert reversed_sign["value"] is None


def test_multiple_crossings_and_unresolved_phase_are_preserved():
    data = waves(lambda f: (2 if f < 10 or 100 < f < 1000 else .5) * cmath.exp(-.1j))
    result = sampled_loop_margin(data, definition())
    assert len(result["crossings"]) == 3 and result["value"] is None
    jump = sampled_loop_margin(waves(lambda f: (10 if f < 100 else .1)
                                    * cmath.exp(-2j if f >= 100 else 0j)), definition())
    assert jump["phase_unwrap_ambiguous"] and jump["value"] is None


def test_ac_full_nodes_opt_in_preserves_public_projection(operator):
    args = reader_for(operator, "ac")
    frame = frame_for(args, "P|input|0|1000|0|2\nP|input|1|2000|0|4\n"
                      "P|output|0|1000|0|4\nP|output|1|2000|0|4")
    normal = project_frame(*args, frame)
    full = project_frame(*args, frame, include_ac_waveforms=True)
    assert "ac_waveforms" not in normal and full["transfer"] == normal["transfer"]
    assert full["reader_script_sha256"] == normal["reader_script_sha256"]
    assert full["ac_waveforms"]["input"][0] == {
        "frequency_hz": 1000, "real_v": 0, "imag_v": 2,
    }


@pytest.mark.asyncio
async def test_wrong_retained_plan_rejects_before_remote_contact():
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from cadence_mcp_bridge.generic_analog import capture_phase_margin

    record = SimpleNamespace(operation_id="00000000-0000-4000-8000-000000000001",
                             plan=SimpleNamespace(plan_sha256="a" * 64))
    store = SimpleNamespace(connection=lambda **kwargs: nullcontext(None),
                            _read_operation=lambda *args: record)
    provider = SimpleNamespace(analog_result=AsyncMock())
    native = SimpleNamespace(current=lambda: None, lifecycle=SimpleNamespace(store=store),
                             provider=provider)
    with pytest.raises(OperationRejected):
        await capture_phase_margin(native, record.operation_id, "b" * 64, definition())
    provider.analog_result.assert_not_called()
