"""Native ADE qualification: provenance, partial failure, budgets and replay."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
operator = importlib.import_module("ade_qual")


@pytest.fixture
def helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    source = (operator.LOCAL / "helper.py").read_text(encoding="ascii")
    module: Any = ModuleType("ade_test")
    exec(compile(source.replace("import imp\n", ""), "helper.py", "exec"), module.__dict__)
    module.JOB = str(tmp_path / "job")
    Path(module.JOB).mkdir()
    module.COUNTER = str(tmp_path / "counter.json")
    module.MODEL = module.os.path.realpath(module.MODEL)
    module.verify_netlist = lambda: {"result_name": "dcOp"}
    # CentOS rename replaces atomically; Windows rename refuses existing targets.
    monkeypatch.setattr(module.os, "rename", module.os.replace)
    return module


@pytest.mark.parametrize("text", ["nan", "inf", "1e999", "1;run()", "1 2", "1e13"])
def test_invalid_numbers(helper: Any, text: str) -> None:
    with pytest.raises(ValueError):
        helper.number(text)


def test_owned_state_remap_only_routing(helper: Any) -> None:
    original = (
        'designInfo = \'("MyDesignLib" "Differential_Amplifier_TB2" "schematic" "spectre")\n'
        'projectDir = \'"~/simulation"\nother = \'"preserved"\n'
    )
    remapped = helper.remap_info(original)
    assert 'other = \'"preserved"' in remapped
    assert helper.JOB + "/project" in remapped
    with pytest.raises(ValueError):
        helper.remap_info(original + original)


def test_state_comparison_covers_empty_directories_and_extra_files(
    helper: Any, tmp_path: Path
) -> None:
    import shutil

    original = tmp_path / "original"
    original.mkdir()
    (original / "waveformSetup_ws").mkdir()
    (original / "variables").write_text("synthetic variable")
    (original / "ADE_state.info").write_text("original routing")
    copy = tmp_path / "copy"
    shutil.copytree(original, copy)
    (copy / "ADE_state.info").write_text("owned routing")
    assert helper.state_records(str(original)) == helper.state_records(str(copy))
    (copy / "waveformSetup_ws" / "extra").write_text("unexpected")
    assert helper.state_records(str(original)) != helper.state_records(str(copy))


def test_protected_drift_blocks_before_execution(helper: Any, tmp_path: Path) -> None:
    helper.STATE = str(tmp_path / "source-state")
    helper.COPIED_STATE = str(tmp_path / "owned-state")
    for path in (helper.STATE, helper.COPIED_STATE):
        Path(path).mkdir()
        Path(path, "ADE_state.info").write_bytes(b"synthetic")
    baseline = {"source_sha256": "synthetic-baseline"}
    helper.snapshot = lambda: baseline.copy()
    helper.state_facts = lambda: {"enabled_analyses": ["dc"]}
    before = {
        **baseline,
        "state_facts": helper.state_facts(),
        "state_copy_info_sha256": helper.sha(b"synthetic"),
    }
    helper.verify_protected(before)
    baseline["source_sha256"] = "unexpected-drift"
    with pytest.raises(ValueError, match="protected drift"):
        helper.verify_protected(before)


def _input(helper: Any) -> tuple[str, str, dict[str, Any]]:
    facts = {"variables_v": {"VBIASN": 0.32, "VBIASP": 0.702}, "temperature_c": 27}
    text = (
        f'include "{helper.MODEL}" section=NN\ninclude "netlist"\n'
        "parameters VBIASN=320m VBIASP=702m\noptions options temp=27\ndcOp dc\n"
    )
    circuit = "// synthetic fixture\nV0 (VDD 0) vsource dc=1 type=dc\n"
    return text, circuit, facts


@pytest.mark.parametrize(
    "change", ["variable", "model", "analysis", "temperature", "circuit", "vdd"]
)
def test_netlist_gates(helper: Any, change: str) -> None:
    text, circuit, facts = _input(helper)
    previous = circuit
    assert helper.validate_netlist(text, circuit, previous, facts) == "dcOp"
    if change == "variable":
        text = text.replace("320m", "300m")
    elif change == "model":
        text = text.replace("section=NN", "section=FF")
    elif change == "analysis":
        text += "ac1 ac\n"
    elif change == "temperature":
        text = text.replace("temp=27", "temp=28")
    elif change == "circuit":
        circuit += "Rfake (VDD 0) resistor r=1k\n"
    else:
        previous = circuit = circuit.replace("dc=1", "dc=2")
    with pytest.raises(ValueError):
        helper.validate_netlist(text, circuit, previous, facts)


@pytest.mark.parametrize(
    "field,value",
    [
        ("count", True),
        ("count", 100),
        ("count", 13),
        ("result_reserved_bytes", True),
        ("result_reserved_bytes", 5 * 1024**3),
    ],
)
def test_budget_negative(helper: Any, field: str, value: Any) -> None:
    counter = {"campaign_id": "AUTO-PHASE-01", "count": 14, "result_reserved_bytes": 672137216}
    counter[field] = value
    Path(helper.COUNTER).write_text(json.dumps(counter))
    with pytest.raises(ValueError):
        helper.reserve()
    assert not Path(helper.JOB, "attempt-reserved").exists()


def test_counter_accumulates_and_replay_blocks(helper: Any) -> None:
    Path(helper.COUNTER).write_text(
        json.dumps(
            {"campaign_id": "AUTO-PHASE-01", "count": 14, "result_reserved_bytes": 672137216}
        )
    )
    helper.reserve()
    counter = json.loads(Path(helper.COUNTER).read_text())
    assert counter["count"] == 15
    assert counter["result_reserved_bytes"] == 672137216 + helper.RESERVATION
    with pytest.raises(ValueError, match="replay"):
        helper.reserve()
    assert json.loads(Path(helper.COUNTER).read_text()) == counter


def test_crash_during_counter_update_blocks_retry(
    helper: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    Path(helper.COUNTER).write_text(
        json.dumps(
            {"campaign_id": "AUTO-PHASE-01", "count": 14, "result_reserved_bytes": 672137216}
        )
    )

    def crash(*args: Any) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(helper.os, "rename", crash)
    with pytest.raises(OSError):
        helper.reserve()
    with pytest.raises(ValueError, match="replay"):
        helper.reserve()


@pytest.mark.parametrize(
    "stage,state,simulation",
    [
        ("simulator_failed", "failed", "failed"),
        ("extraction_failed", "failed", "succeeded"),
        ("simulating", "unknown", "not_confirmed"),
        ("netlisted", "netlisted", "not_confirmed"),
    ],
)
def test_status_does_not_reuse_netlist_success(
    helper: Any, stage: str, state: str, simulation: str
) -> None:
    Path(helper.JOB, "netlist-result.json").write_text('{"netlist_valid":true}')
    helper.set_stage(stage)
    captured: list[dict[str, Any]] = []
    helper.emit = captured.append
    helper.status()
    assert captured[0]["state"] == state
    assert captured[0]["simulation"] == simulation
    assert "result" not in captured[0]


def test_policy_bytes_and_readonly_native_contract() -> None:
    policy = json.loads(operator.POLICY.read_text())
    parent = json.loads(operator.campaign.POLICY.read_text())
    assert policy == operator.expected_policy(operator.digest(operator.campaign._canonical(parent)))
    for name in operator.FILES:
        assert b"\r" not in (operator.LOCAL / name).read_bytes()
    ocean = (operator.LOCAL / "netlist.ocn").read_text()
    assert "asiLoadState(" in ocean and "sevNetlistFile(" in ocean
    assert "sevStartSession(?design copy)" in ocean
    assert '"schematic" "" "r")' in ocean
    assert "dbSave" not in ocean and "asiSaveState" not in ocean


def test_operator_dependency_denied_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "authority", lambda: ({}, "test"))
    monkeypatch.setattr(operator, "command", lambda *args: pytest.fail("transport invoked"))
    with pytest.raises(operator.campaign.CampaignError):
        operator.run("dc")


def test_operator_reservation_survives_transport_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".codex").mkdir()
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "authority", lambda: ({}, "test"))
    monkeypatch.setattr(
        operator, "deploy", lambda *args: (_ for _ in ()).throw(ValueError("uncertain"))
    )
    with pytest.raises(ValueError):
        operator.run("deploy")
    with pytest.raises(FileExistsError):
        operator.run("deploy")
    assert (
        json.loads((tmp_path / ".codex/ade-qual-v4-deploy.json").read_text())["state"] == "reserved"
    )
