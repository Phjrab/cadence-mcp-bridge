"""Native AC/TRAN boundary and independent waveform arithmetic tests."""

from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
operator = importlib.import_module("native_ac_tran")


@pytest.fixture
def helper() -> Any:
    base: Any = ModuleType("dc_test")
    source = (operator.dc.LOCAL / "helper.py").read_text()
    exec(
        compile(source.replace("import imp\n", "").replace("import pwd\n", ""), "dc.py", "exec"),
        base.__dict__,
    )
    base.MODEL = base.os.path.realpath(base.MODEL)
    base.guard = lambda: SimpleNamespace(finite=lambda text: _finite(text))
    module: Any = ModuleType("native_test")
    module.BASE = base
    source = (operator.LOCAL / "helper.py").read_text()
    source = source.replace("import imp\n", "")
    source = source.replace(
        'BASE = imp.load_source("native_dc_guard", ROOT + "/phase-campaign/ade-qual-v6/helper.py")',
        "",
    )
    exec(compile(source, "native.py", "exec"), module.__dict__)
    return module


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("nonfinite")
    return value


def native_input(helper: Any, analysis: str) -> tuple[str, str, dict[str, Any]]:
    helper.configure(analysis)
    facts = {"variables_v": {"VBIASN": 0.3, "VBIASP": 0.65}, "temperature_c": 27}
    # Synthetic source fixture; contains no device or PDK content.
    circuit = (
        "V0 (VDD 0) vsource dc=1 type=dc\n"
        "V1 (Vp 0) vsource dc=500m mag=500m type=sine ampl=50m freq=1K\n"
        "V2 (Vm 0) vsource dc=500m mag=-500m type=sine ampl=50m sinephase=180 freq=1K\n"
    )
    control = helper.BASE.NATIVE_CONTROL.replace("dcOpInfo info what=oppoint where=rawfile\n", "")
    dc_line = 'dcOp dc write="spectre.dc" maxiters=150 maxsteps=10000 annotate=status'
    replacement = (
        "ac ac start=10 stop=100M dec=10 annotate=status"
        if analysis == "ac"
        else 'tran tran stop=4m maxstep=10u write="spectre.ic" writefinal="spectre.fc" '
        "annotate=status maxiters=5 method=trap\n"
        "finalTimeOP info what=oppoint where=rawfile"
    )
    control = control.replace(dc_line, replacement)
    text = (
        "simulator lang=spectre\nglobal 0\nparameters VBIASN=300m VBIASP=650m\n"
        f'include "{helper.BASE.MODEL}" section=NN\n'
    )
    return text + circuit + control + "\n", circuit, facts


@pytest.mark.parametrize("analysis", ["ac", "tran"])
@pytest.mark.parametrize(
    "fault",
    ["none", "analysis", "range", "write", "stimulus", "extra", "bias", "include", "final_op"],
)
def test_native_controls_and_stimulus(helper: Any, analysis: str, fault: str) -> None:
    text, circuit, facts = native_input(helper, analysis)
    previous = circuit
    if fault == "none":
        assert helper.validate_netlist(text, circuit, previous, facts) == analysis
        return
    if fault == "analysis":
        text = text.replace(analysis + " " + analysis, "wrong " + analysis)
    elif fault == "range":
        text = (
            text.replace("stop=100M", "stop=200M")
            if analysis == "ac"
            else text.replace("stop=4m", "stop=5m")
        )
    elif fault == "write":
        text = text.replace('sensfile="../psf/sens.output"', 'sensfile="/tmp/unsafe"')
    elif fault == "stimulus":
        previous = circuit = circuit.replace("mag=-500m", "mag=0")
        text = text.replace("mag=-500m", "mag=0")
    elif fault == "extra":
        text += "extra tran stop=4m\n"
    elif fault == "bias":
        text = text.replace("VBIASN=300m", "VBIASN=320m")
    elif fault == "include":
        text += 'include "/tmp/unsafe"\n'
    else:
        text += "finalTimeOP info what=oppoint where=rawfile\n"
    with pytest.raises(ValueError):
        helper.validate_netlist(text, circuit, previous, facts)


def tran_frame(fault: str = "none") -> str:
    times = [index * 1e-5 for index in range(401)]
    if fault == "nonmonotonic":
        times[2] = times[1]
    elif fault == "endpoint":
        times[-1] = 0.0041
    lines = ["MCP_TRAN_BEGIN"]
    for signal in ("Vop", "Vom", "Vp", "Vm", "VDD"):
        lines.append(f"MCP_TRAN_VECTOR|{signal}|401|401")
        for index, time in enumerate(times):
            excitation = 0.05 * math.sin(2 * math.pi * 1000 * time)
            value = {
                "Vp": 0.5 + excitation,
                "Vm": 0.5 - excitation,
                "VDD": 1,
                "Vop": 0.2 + excitation * 2,
                "Vom": 0.2 - excitation * 2,
            }[signal]
            if fault == "supply" and signal == "VDD":
                value = 0.9
            elif fault == "stimulus" and signal == "Vm":
                value = 0.5 + excitation
            output = (
                "nan"
                if fault == "nonfinite" and signal == "Vop" and index == 5
                else format(value, ".16g")
            )
            axis = time + 1e-12 if fault == "axis" and signal == "Vm" else time
            lines.append(f"MCP_TRAN_POINT|{signal}|{index}|{axis:.16g}|{output}")
    lines.append("MCP_TRAN_COMPLETE")
    if fault == "partial":
        lines.pop()
    elif fault == "trailing":
        lines.insert(-1, "unexpected")
    return "\n".join(lines)


def test_tran_differential_arithmetic(helper: Any) -> None:
    result = helper.tran_result(tran_frame())
    assert result["point_count"] == 401
    assert result["output_differential_max_v"] == pytest.approx(0.2)
    assert result["output_differential_min_v"] == pytest.approx(-0.2)
    assert result["output_common_mode_min_v"] == pytest.approx(0.2)
    assert result["sampling"] == "adaptive_native_no_fft"


@pytest.mark.parametrize(
    "fault",
    ["nonmonotonic", "endpoint", "supply", "stimulus", "nonfinite", "axis", "partial", "trailing"],
)
def test_tran_rejects_invalid_waveforms(helper: Any, fault: str) -> None:
    with pytest.raises((ValueError, IndexError)):
        helper.tran_result(tran_frame(fault))


def test_policy_and_native_readonly_boundary() -> None:
    policy = json.loads(operator.POLICY.read_text())
    parent = json.loads(operator.campaign.POLICY.read_text())
    assert policy == operator.expected_policy(
        operator.dc.digest(operator.campaign._canonical(parent))
    )
    for name in operator.FILES:
        assert b"\r" not in (operator.LOCAL / name).read_bytes()
    for analysis in ("ac", "tran"):
        text = (
            (
                operator.LOCAL
                if analysis == "tran"
                else operator.LOCAL.with_name("native-ac-tran-v3")
            )
            / f"netlist-{analysis}.ocn"
        ).read_text()
        assert "asiLoadState(" in text and "sevNetlistFile(" in text
        assert "asiDisableAnalysis(" in text and "asiEnableAnalysis(" in text
        assert "dbSave" not in text and "asiSaveState" not in text
        extraction = (
            (
                operator.LOCAL
                if analysis == "tran"
                else operator.LOCAL.with_name("native-ac-tran-v3")
            )
            / f"extract-{analysis}.ocn"
        ).read_text()
        assert f"member('{analysis} results())" in extraction
        assert f"MCP_NATIVE_SELECTOR|{analysis}" in extraction


def test_operator_missing_predecessor_denies_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "authority", lambda: ({"previous_policy_sha256": "old"}, "hash"))
    monkeypatch.setattr(operator.dc, "command", lambda *args: pytest.fail("transport invoked"))
    with pytest.raises(operator.campaign.CampaignError):
        operator.run("tran")


def test_uncertain_deploy_claim_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/native-ac-tran-correction-2.json").write_text(
        json.dumps({"change_id": operator.CHANGE, "ordinal": 2, "state": "consumed"})
    )
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "authority", lambda: ({"previous_policy_sha256": "old"}, "hash"))
    monkeypatch.setattr(
        operator, "deploy", lambda *args: (_ for _ in ()).throw(ValueError("uncertain"))
    )
    with pytest.raises(ValueError):
        operator.run("deploy")
    with pytest.raises(FileExistsError):
        operator.run("deploy")
    assert (
        json.loads((tmp_path / f".codex/{operator.VERSION}-deploy.json").read_text())["state"]
        == "reserved"
    )


@pytest.mark.parametrize("analysis", ["ac", "tran"])
def test_native_source_continuations(helper: Any, analysis: str) -> None:
    text, circuit, facts = native_input(helper, analysis)
    continued = circuit.replace("type=sine ampl=50m", "type=sine \\\n    ampl=50m")
    text = text.replace(circuit, continued)
    assert helper.validate_netlist(text, continued, continued, facts) == analysis
