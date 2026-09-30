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
    source = source.replace("import imp\n", "").replace("import pwd\n", "")
    exec(compile(source, "helper.py", "exec"), module.__dict__)
    module.JOB = str(tmp_path / "job")
    Path(module.JOB).mkdir()
    module.COUNTER = str(tmp_path / "counter.json")
    module.MODEL = module.os.path.realpath(module.MODEL)
    module.verify_netlist = lambda: {"result_name": "dcOp"}
    module.actual_environment_preflight = module.environment_preflight
    module.environment_preflight = lambda: None
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
    circuit = "// synthetic fixture\nV0 (VDD 0) vsource dc=1 type=dc\n"
    text = (
        "simulator lang=spectre\nglobal 0\nparameters VBIASN=320m VBIASP=702m\n"
        f'include "{helper.MODEL}" section=NN\n' + circuit + helper.NATIVE_CONTROL + "\n"
    )
    return text, circuit, facts


@pytest.mark.parametrize(
    "change",
    [
        "variable",
        "model",
        "analysis",
        "temperature",
        "circuit",
        "vdd",
        "inline",
        "unexpected_write",
        "extra_include",
        "extra_parameter",
    ],
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
    elif change == "vdd":
        previous = circuit = circuit.replace("dc=1", "dc=2")
    elif change == "inline":
        text = text.replace(circuit, 'include "netlist"\n')
    elif change == "unexpected_write":
        text = text.replace('sensfile="../psf/sens.output"', 'sensfile="/tmp/unowned"')
    elif change == "extra_include":
        text += 'include "/tmp/unowned"\n'
    else:
        text = text.replace("parameters VBIASN", "parameters extra=1 VBIASN")
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
    assert 'sevStartSession(?lib "MCP_WorkLib" ?cell "WP14_AUTO_PHASE_01_TB2"' in ocean
    assert "copy=asiGetTopCellView(asiSession)" in ocean
    assert 'copy~>libName=="MCP_WorkLib"' in ocean
    assert '"schematic" "" "r")' in ocean
    assert "dbSave" not in ocean and "asiSaveState" not in ocean


def test_operator_dependency_denied_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "authority", lambda: ({}, "test"))
    monkeypatch.setattr(operator, "reserve_correction", lambda *args: None)
    monkeypatch.setattr(operator, "command", lambda *args: pytest.fail("transport invoked"))
    with pytest.raises(operator.campaign.CampaignError):
        operator.run("dc")


def test_operator_reservation_survives_transport_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".codex").mkdir()
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "authority", lambda: ({}, "test"))
    monkeypatch.setattr(operator, "reserve_correction", lambda *args: None)
    monkeypatch.setattr(
        operator, "deploy", lambda *args: (_ for _ in ()).throw(ValueError("uncertain"))
    )
    with pytest.raises(ValueError):
        operator.run("deploy")
    with pytest.raises(FileExistsError):
        operator.run("deploy")
    assert (
        json.loads((tmp_path / ".codex/ade-qual-v6-deploy.json").read_text())["state"] == "reserved"
    )


@pytest.mark.parametrize("fault", ["echo_only", "error", "duplicate", "missing_session"])
def test_graphical_markers_require_actual_unique_error_free_output(helper: Any, fault: str) -> None:
    markers = [
        "MCP_ADE_SOURCE_COPY|true",
        "MCP_ADE_SESSION|true",
        "MCP_ADE_STATE_LOAD|true",
        "MCP_ADE_NETLIST|true",
    ]
    actual = "\n".join("\\o " + value for value in markers)
    helper.validate_native_log(actual)
    if fault == "echo_only":
        actual = "\n".join('\\i printf("' + value + '\\n")' for value in markers)
    elif fault == "error":
        actual += "\n\\e *Error* native session failed"
    elif fault == "duplicate":
        actual += "\n\\o " + markers[0]
    else:
        actual = actual.replace("\\o " + markers[1], "\\i " + markers[1])
    with pytest.raises(ValueError):
        helper.validate_native_log(actual)


def test_added_corrections_are_consumed_once_and_never_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".codex").mkdir()
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "renewal_authority", lambda: "renewal")
    monkeypatch.setattr(operator, "CORRECTION_ORDINAL", 4)
    operator.reserve_correction("v5")
    with pytest.raises(FileExistsError):
        operator.reserve_correction("v5")
    monkeypatch.setattr(operator, "CORRECTION_ORDINAL", 6)
    with pytest.raises(operator.campaign.CampaignError):
        operator.reserve_correction("v7")


def test_missing_renewal_denies_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(operator, "RENEWAL_DELEGATION", tmp_path / "absent.json")
    with pytest.raises(operator.campaign.CampaignError):
        operator.renewal_authority()


@pytest.mark.parametrize("ordinal", [True, 3, 7])
def test_correction_limit_cannot_be_extended_by_another_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ordinal: Any
) -> None:
    monkeypatch.setattr(operator, "ROOT", tmp_path)
    monkeypatch.setattr(operator, "CORRECTION_ORDINAL", ordinal)
    with pytest.raises(ValueError, match="budget"):
        operator.reserve_correction("unapproved")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("fault", ["host", "user", "disk"])
def test_remote_preflight_rejects_identity_and_disk_floor(
    helper: Any, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        helper.socket, "gethostname", lambda: "other" if fault == "host" else "cadence"
    )
    monkeypatch.setattr(helper.os, "getuid", lambda: 1, raising=False)
    helper.pwd = SimpleNamespace(
        getpwuid=lambda uid: SimpleNamespace(pw_name="other" if fault == "user" else "buet")
    )
    monkeypatch.setattr(
        helper.os,
        "statvfs",
        lambda path: SimpleNamespace(
            f_bavail=100 if fault == "disk" else 50 * 1024**3,
            f_frsize=1,
            f_blocks=60 * 1024**3,
        ),
        raising=False,
    )
    with pytest.raises(ValueError):
        helper.actual_environment_preflight()


def test_native_extraction_requires_advertised_exact_result(
    helper: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper.read = lambda path: b"  unless(selectResult('dc) close(port) exit(1))\n"
    captured: list[str] = []
    helper.write_new = lambda path, content: captured.append(content)
    helper.extraction()
    assert "member('dcOp results())" in captured[0]
    assert "selectResult('dcOp)" in captured[0]
    assert helper.JOB + "/selector.txt" in captured[0]
    helper.verify_netlist = lambda: {"result_name": "unqualified"}
    with pytest.raises(ValueError, match="unqualified"):
        helper.extraction()
    assert len(captured) == 1
