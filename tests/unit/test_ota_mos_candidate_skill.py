"""Check closed native stages without opening Cadence or applying an edit."""

import json
import re

import pytest

from cadence_mcp_bridge import _ota_mos_candidate_skill as ota
from cadence_mcp_bridge._registered_mos_edit_phase import COMMON, SIZING_TRACE_SKILL

_FIXED_PINS = {
    "OP": "730a1469-9c78-4521-8f83-287f39f57613",
    "LIB": "Ota17Candidate20261126",
    "SOURCEALIAS": "Ota17Base20261126",
    "SOURCE": "/home/buet/cds_work/Ota17BaseOutputs20261126_v1/Ota17Base20261126",
    "OWNED": "/home/buet/cds_work/Ota17CandidateOutputs20261126_v1/Ota17Candidate20261126",
    "OTA_INVENTORY": "list("
    + " ".join(
        f'list("M{index}" "nmos1v" list(list("D" "out") list("G" "inp") '
        'list("S" "VSS") list("B" "VSS")))'
        for index in range(17)
    )
    + ")",
}
_EDIT_PINS = {
    "TARGET": "M0",
    "MASTER": "nmos1v",
    "TARGET_LINKS": 'list(list("D" "out") list("G" "inp") list("S" "VSS") list("B" "VSS"))',
    "WORK": "/private/job/work",
    "NETLISTCELL": "Grel_730a1469_9c78_4521_8f83_287f39f57613",
    "BEFORE": "mcpCheckOriginal(inst)",
    "MUTATION": "mosRequire(mcpMosApplyWL(inst)==t)",
    "AFTER": "mcpCheckRequestedAndHeld(inst)",
}


def _render(stage: str, **extra: str) -> str:
    values = _FIXED_PINS | extra
    program = re.sub(
        r"@([A-Z_]+)@", lambda match: values[match[1]], ota.compose_common(COMMON) + stage
    )
    # SKILL strings can contain parentheses. Check the remaining balanced source.
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', program)
    depth = 0
    for char in text:
        depth += (char == "(") - (char == ")")
        assert depth >= 0
    assert depth == 0
    return program


def test_retarget_writes_only_the_owned_bench_and_checks_reopened_copy() -> None:
    source = _render(ota.RETARGET)
    body = source.split("procedure(otaRetarget()", 1)[1]
    writes = re.findall(r'mosOpen\("([^"]+)" "([^"]+)" "a"\)', body)
    assert writes == [(_FIXED_PINS["LIB"], "self_cascode_ota_tb")]
    assert body.count("dut~>master=symbol") == body.count("dbSave(") == 1
    assert body.index("equal(otaFoot(source nil nil nil) otaFoot(child nil nil nil))") < body.index(
        "dut~>master=symbol"
    )
    assert body.index('otaTbMaster(child "Ota17Candidate20261126")') < body.index("dbSave(")
    assert body.index("dbSave(") < body.index('equal(original otaBench("Ota17Candidate20261126"))')
    assert body.index('equal(original otaBench("Ota17Candidate20261126"))') < body.index(
        "OTA17_CANDIDATE_BENCH_RETARGETED|"
    )


@pytest.mark.parametrize("overrides", ["l as ad ps pd", "w fw as ad ps pd"])
def test_one_axis_edit_preserves_copy_and_detached_view_contract(overrides: str) -> None:
    values = _EDIT_PINS | {"OVERRIDES": "'(" + " ".join(map(json.dumps, overrides.split())) + ")"}
    edit = _render(SIZING_TRACE_SKILL + ota.EDIT_BEGIN + ota.EDIT_CHECKS + ota.EDIT_END, **values)
    body = edit.split("procedure(mosEdit()", 1)[1]
    assert re.findall(r'mosOpen\("([^"]+)" "([^"]+)" "a"\)', body) == [
        (_FIXED_PINS["LIB"], "self_cascode_ota_17mos")
    ]
    assert "equal(original otaFoot(child nil nil nil))" in body
    assert body.index("otaMask(omit)") < body.index("mcpMosApplyWL(inst)")
    assert body.index("mcpCheckOriginal(inst)") < body.index("mcpMosApplyWL(inst)")
    assert body.index("mcpMosApplyWL(inst)") < body.index('stable otaFoot(child "M0" omit nil)')
    assert body.index("mcpCheckRequestedAndHeld(inst)") < body.index("dbSave(child)")
    assert body.index("dbClose(child))\n  printf(") < body.index("C6_MOS_EDIT_SAVED|")

    reopened = _render(ota.REOPEN, **values)
    body = reopened.split("procedure(mosReopen()", 1)[1]
    assert "dbSave(" not in reopened and '"a")' not in body
    assert "mcpMosApplyWL" not in reopened
    assert 'otaFoot(child "M0" omit nil)' in body
    for token in ("reopened.properties", "m2ReopenedMosFrame(inst)", "mosRequire(dbClose(copied))"):
        assert body.index(token) < body.index("C6_MOS_READ_ONLY_CLOSED|")
