from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "remote" / "py26" / "ade_profile_introspection.py"
WORKER = ROOT / "remote" / "lib" / "run-ade-profile-introspection.sh"
SKILL = ROOT / "remote" / "discovery" / "ade-profile-introspection.il"
RUNNER = ROOT / "remote" / "bin" / "cadence-runner"
DEPLOY = ROOT / "scripts" / "deploy-remote.ps1"
LINEAGE = ROOT / "remote" / "config" / "runner-lineage.json"


def load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ade_profile_introspection", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_fixed_fixture(module: ModuleType, root: Path) -> None:
    source = root / "source"
    state = root / "state"
    runtime = root / "runtime"
    profile = root / "profile.json"
    netlist = root / "netlist"
    model = root / "model.scs"
    source.mkdir()
    state.mkdir()
    runtime.mkdir()
    (source / "sch.oa").write_bytes(b"oa")
    netlist.write_text("simulator lang=spectre\n", encoding="utf-8")
    model.write_text("simulator lang=spectre\n", encoding="utf-8")

    module.SOURCE_DIRECTORY = str(source)
    module.STATE_DIRECTORY = str(state)
    module.RUNTIME = str(runtime)
    module.BEFORE_PATH = str(runtime / "before.json")
    module.SKILL_STDOUT = str(runtime / "skill.stdout")
    module.PROFILE_PATH = str(profile)
    module.SOURCE_NETLIST = str(netlist)
    module.MODEL_FILE = str(model)

    profile.write_text(
        json.dumps(
            {
                "profile_id": module.PROFILE_ID,
                "classification": "actual",
                "library": "MyDesignLib",
                "cell": "Differential_Amplifier_TB2",
                "view": "schematic",
                "ade_product": "ADE L",
                "state": "state1",
                "pdk": "gpdk090",
                "pdk_version": "4.6",
                "model_section": "NN",
                "temperature_c": 27.0,
                "source_netlist": str(netlist),
                "state_path": str(state),
                "model_file": str(model),
                "analyses": ["dc"],
                "fixed_parameters": {"VBIASN": "300m", "VBIASP": "650m"},
                "outputs": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (state / "ADE_state.info").write_text(
        'designInfo = \'("MyDesignLib" "Differential_Amplifier_TB2" "schematic" "spectre")\n',
        encoding="utf-8",
    )
    (state / "analyses").write_text(
        "analysis(dc fields enable) (t)\nanalysis(tran fields enable) (nil)\n"
        'analysis(tran fields stop) "4m"\n',
        encoding="utf-8",
    )
    (state / "variables").write_text(
        'tmp1->name = "VBIASN"\ntmp1->expression = "300m"\n'
        'tmp2->name = "VBIASP"\ntmp2->expression = "650m"\n',
        encoding="utf-8",
    )
    (state / "outputs").write_text("tmp1->name = nil\n", encoding="utf-8")
    (state / "modelSetup").write_text(f'(("{model}" "NN"))\n', encoding="utf-8")
    (state / "simulatorOptions").write_text('(opts temp) "27"\n', encoding="utf-8")
    (runtime / "skill.stdout").write_text(
        "MCP_ADE_OA|true|35|14|8\n", encoding="utf-8"
    )
    os.utime(netlist, (1, 1))


def test_runner_preserves_both_capabilities_without_mcp_exposure() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    server = (ROOT / "src" / "cadence_mcp_bridge" / "server.py").read_text(encoding="utf-8")
    service = (ROOT / "src" / "cadence_mcp_bridge" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "RUNNER_VERSION=0.19.0" in runner
    assert "inspect-ade-profile) runner_inspect_ade_profile" in runner
    assert "wp14-role-discovery) runner_wp14_role_discovery" in runner
    assert '"actual-differential-amplifier-tb2-transient"' in runner
    assert "flock -n 9" in runner
    assert "inspect-ade-profile" not in server
    assert "inspect-ade-profile" not in service
    for forbidden in ("eval ", "bash -c", "sh -c", "run-shell", "run-skill"):
        assert forbidden not in runner


def test_lineage_is_reconciled_but_deployment_remains_blocked() -> None:
    lineage = json.loads(LINEAGE.read_text(encoding="utf-8"))
    deploy = DEPLOY.read_text(encoding="utf-8")
    assert lineage["repository_runner_version"] == "0.19.0"
    assert lineage["observed_remote_runner_version"] == "0.18.0"
    assert lineage["observed_remote_reference_head"] == (
        "15d85bf440b86d191a8f9d07e7b9e687ccf003c0"
    )
    assert lineage["deployment_enabled"] is False
    assert "repository_capability_reconciled" in lineage["lineage_status"]
    assert "$lineagePolicy.lineage_status" in deploy
    for path in (
        "run-ade-profile-introspection.sh",
        "ade_profile_introspection.py",
        "ade-profile-introspection.il",
    ):
        assert path in deploy


def test_skill_and_worker_are_fixed_read_only_and_bounded() -> None:
    skill = SKILL.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")
    assert "dbOpenCellViewByType(" in skill and '"r"' in skill
    assert '"MyDesignLib"' in skill
    assert '"Differential_Amplifier_TB2"' in skill
    assert "dbClose(cv)" in skill
    for forbidden in (
        "dbSave",
        "dbCopyCellView",
        "dbReplaceProp",
        "dbCreateInst",
        "dbDeleteObject",
        "evalstring",
        "load(",
        "system(",
    ):
        assert forbidden not in skill
    assert '[ "$#" -eq 0 ]' in worker
    assert "timeout 90" in worker
    assert "ulimit -f 2048" in worker
    assert '"$(wc -c < "$RESULT.tmp")" -le 65536' in worker
    assert "ssh" not in worker and "scp" not in worker


def test_helper_reconstructs_profile_drift_and_preserves_fingerprints(tmp_path: Path) -> None:
    helper = load_helper()
    prepare_fixed_fixture(helper, tmp_path)
    before = helper.build_snapshot()
    result = helper.build_result(before, helper.build_snapshot())
    assert result["status"] == "profile_drift"
    assert result["drift_codes"] == ["snapshot_freshness_unconfirmed"]
    assert result["design_variables"] == [
        {"name": "VBIASN", "value": "300m"},
        {"name": "VBIASP", "value": "650m"},
    ]
    topology = result["source_structural_fingerprint"]
    assert topology["instances"] == 35
    assert topology["nets"] == 14
    assert topology["terminals"] == 8
    assert result["fingerprints"]["all_unchanged"] is True
    assert result["read_only"] is True
    assert result["paths_included"] is False
    assert result["raw_content_included"] is False


@pytest.mark.parametrize(
    "mutation",
    ["topology", "lock", "fingerprint", "unsafe_variable", "oversize_output"],
)
def test_helper_fails_closed_on_invariant_or_bound_violation(
    tmp_path: Path, mutation: str
) -> None:
    helper = load_helper()
    prepare_fixed_fixture(helper, tmp_path)
    before = helper.build_snapshot()
    if mutation == "topology":
        Path(helper.SKILL_STDOUT).write_text("MCP_ADE_OA|true|34|14|8\n", encoding="utf-8")
    elif mutation == "lock":
        (Path(helper.SOURCE_DIRECTORY) / "sch.oa.cdslck").write_text("lock", encoding="utf-8")
    elif mutation == "fingerprint":
        (Path(helper.SOURCE_DIRECTORY) / "sch.oa").write_bytes(b"changed")
    elif mutation == "unsafe_variable":
        (Path(helper.STATE_DIRECTORY) / "variables").write_text(
            'tmp1->name = "VBIASN"\ntmp1->expression = "$(unsafe)"\n', encoding="utf-8"
        )
    else:
        helper.MAX_PUBLIC_BYTES = 10
    after = helper.build_snapshot()
    with pytest.raises(ValueError):
        helper.build_result(before, after)
