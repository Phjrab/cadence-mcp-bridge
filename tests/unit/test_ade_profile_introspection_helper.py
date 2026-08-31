from __future__ import annotations

import json
import os
from importlib import util
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = PROJECT_ROOT / "remote" / "py26" / "ade_profile_introspection.py"


def load_helper() -> ModuleType:
    spec = util.spec_from_file_location("ade_profile_introspection", HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_fixture(helper: ModuleType, tmp_path: Path) -> tuple[dict[str, object], Path]:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source_directory = tmp_path / "source"
    source_directory.mkdir()
    (source_directory / "master.tag").write_text("master.tag", encoding="utf-8")
    (source_directory / "sch.oa").write_bytes(b"oa-fixture")
    source_netlist = tmp_path / "netlist"
    source_netlist.write_text("fixture netlist", encoding="utf-8")
    model_file = tmp_path / "gpdk090.scs"
    model_file.write_text("fixture model", encoding="utf-8")
    state = tmp_path / "state1"
    state.mkdir()
    (state / "ADE_state.info").write_text(
        "projectDir = '\"fixture\"\n"
        "designInfo = '(\"MyDesignLib\" \"Differential_Amplifier_TB2\" "
        "\"schematic\" \"spectre\")\n",
        encoding="utf-8",
    )
    (state / "analyses").write_text(
        'analysis(dc fields enable) (t)\n'
        'analysis(dc fields stop) ""\n'
        'analysis(tran fields enable) (nil)\n'
        'analysis(tran fields stop) "4m"\n',
        encoding="utf-8",
    )
    (state / "variables").write_text(
        'tmp1->name = "VBIASN"\n'
        'tmp1->expression = "300m"\n'
        'tmp2->name = "VBIASP"\n'
        'tmp2->expression = "650m"\n',
        encoding="utf-8",
    )
    (state / "outputs").write_text("tmp1->name = nil\n", encoding="utf-8")
    (state / "modelSetup").write_text(
        f'(("{model_file.as_posix()}" "NN"))\n', encoding="utf-8"
    )
    (state / "simulatorOptions").write_text('(opts temp) "27"\n', encoding="utf-8")
    os.utime(source_netlist, (1000, 1000))
    for path in state.iterdir():
        os.utime(path, (2000, 2000))
    os.utime(state, (2000, 2000))
    profile = {
        "profile_id": helper.PROFILE_ID,
        "classification": "actual",
        "library": "MyDesignLib",
        "cell": "Differential_Amplifier_TB2",
        "view": "schematic",
        "ade_product": "ADE L",
        "state": "state1",
        "pdk": "gpdk090",
        "pdk_version": "4.6",
        "model_file": str(model_file),
        "model_section": "NN",
        "temperature_c": 27.0,
        "analyses": ["tran"],
        "fixed_parameters": {"VBIASN": "300m", "VBIASP": "650m"},
        "outputs": [],
        "source_netlist": str(source_netlist),
        "state_path": str(state),
    }
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    skill_stdout = runtime / "skill.stdout"
    skill_stdout.write_text("MCP_ADE_OA|true|35|14|8\n", encoding="utf-8")

    helper.RUNTIME = str(runtime)
    helper.BEFORE_PATH = str(runtime / "before.json")
    helper.SKILL_STDOUT = str(skill_stdout)
    helper.PROFILE_PATH = str(profile_path)
    helper.SOURCE_DIRECTORY = str(source_directory)
    helper.SOURCE_NETLIST = str(source_netlist)
    helper.STATE_PATH = str(state)
    helper.MODEL_FILE = str(model_file)
    return profile, state


def test_fixed_introspection_reports_bounded_profile_drift(tmp_path: Path) -> None:
    helper = load_helper()
    unused_profile, unused_state = prepare_fixture(helper, tmp_path)
    before = helper.build_snapshot()

    result = helper.build_result(before, helper.build_snapshot())

    assert result["status"] == "profile_drift"
    assert result["drift_codes"] == [
        "analysis_mismatch",
        "snapshot_freshness_unconfirmed",
    ]
    assert result["design_variables"] == [
        {"name": "VBIASN", "value": "300m"},
        {"name": "VBIASP", "value": "650m"},
    ]
    assert result["outputs"] == []
    assert result["source_structural_fingerprint"]["instances"] == 35
    assert result["fingerprints"]["all_unchanged"] is True
    assert result["paths_included"] is False
    assert result["raw_content_included"] is False
    serialized = json.dumps(result)
    assert str(tmp_path) not in serialized
    assert "fixture netlist" not in serialized
    assert "fixture model" not in serialized


def test_fixed_introspection_rejects_protected_state_change(tmp_path: Path) -> None:
    helper = load_helper()
    unused_profile, state = prepare_fixture(helper, tmp_path)
    before = helper.build_snapshot()
    (state / "variables").write_text(
        'tmp1->name = "VBIASN"\n'
        'tmp1->expression = "370m"\n'
        'tmp2->name = "VBIASP"\n'
        'tmp2->expression = "650m"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="fingerprint changed"):
        helper.build_result(before, helper.build_snapshot())
