"""Local checks for the v2-only retarget and extraction metadata contract."""

import re

import pytest
from test_ota_mos_candidate_skill import _EDIT_PINS, _FIXED_PINS

from cadence_mcp_bridge import _ota_mos_candidate_skill as v1
from cadence_mcp_bridge import _ota_mos_candidate_v2_skill as v2
from cadence_mcp_bridge._ota_mos_candidate_runtime import render_ota_skill
from cadence_mcp_bridge._registered_mos_edit_phase import COMMON, SIZING_TRACE_SKILL


def _render(template, **extra):
    values = _FIXED_PINS | {"OWNED": v2.V2_PATH} | extra
    source = render_ota_skill(
        v2.common_v2(v1.compose_common(COMMON)) + template,
        {f"@{key}@": value for key, value in values.items()},
    )
    _balanced(source.decode("ascii"))
    return source


def _balanced(text):
    parts = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    depth = 0
    for char in parts:
        depth += (char == "(") - (char == ")")
        assert depth >= 0
    assert depth == 0


def test_v2_retarget_keeps_destination_master_open_through_save_and_reopen():
    program = _render(v2.RETARGET_BODY)
    body = program.split(b"procedure(otaRetarget(runStarted)", 1)[1]
    guards = [
        b"dut~>master=dstSymbol",
        b"schCheck(copy)",
        b"otaExtraction(",
        b"dbSave(copy)",
        b"otaSaved(",
        b'"REOPEN_FOOTPRINT"',
        b"dbClose(dstSymbol)",
        b"OTA17_CANDIDATE_BENCH_RETARGETED|",
    ]
    positions = [body.index(guard) for guard in guards]
    assert positions == sorted(set(positions))
    assert b"Ota17CandidateOutputs20261126_v1" not in program
    assert b"dbPurge(" not in program
    _balanced(v2.RETARGET_DRIVER)
    assert 'errset(load("work/retarget-body.il") t)' in v2.RETARGET_DRIVER
    assert "errset(otaRetarget(runStarted) t)" in v2.RETARGET_DRIVER
    assert v2.V2_PATH in v2.RETARGET_DRIVER
    assert v2.RETARGET_DRIVER.count("dbPurge(") == 1 and "dbSave(" not in v2.RETARGET_DRIVER


def test_v2_writer_checks_same_metadata_without_changing_readonly_footprint():
    options = _EDIT_PINS | {"OVERRIDES": '\'("w" "fw" "as" "ad" "ps" "pd")'}
    edit = _render(
        SIZING_TRACE_SKILL
        + v2.edit_begin(v1.EDIT_BEGIN)
        + v2.edit_checks(v1.EDIT_CHECKS)
        + v2.edit_end(v1.EDIT_END),
        **options,
    )
    markers = [
        b"counterBefore=dbGetCellViewCounter(child)",
        b"mcpMosApplyWL(inst)",
        b"schCheck(child)",
        b"otaExtraction(stable checked",
        b"dbSave(child)",
        b"otaSaved(checked saved",
        b'"EDIT_SAVED_META"',
        b'/saved.properties"',
        b"C6_MOS_EDIT_SAVED|",
    ]
    positions = [edit.index(marker) for marker in markers]
    assert positions == sorted(set(positions))
    assert b"otaStableWriterFoot(saved)" in edit
    assert b"checked=otaFootFields(child nil nil nil)" in edit
    assert b"saved=otaFootFields(child nil nil nil)" in edit
    assert b"dbPurge(" in edit
    reopened = _render(v2.reopen(v1.REOPEN), **options)
    assert b"otaStableWriterFoot(observed)" in reopened
    assert reopened.index(b'"EDIT_REOPEN_META"') < reopened.index(b"C6_MOS_READ_ONLY_CLOSED|")
    dc = reopened.index(b'mosOpen("MCP_GREL_WorkDc"')
    assert reopened.index(b'mosOpen("MCP_GREL_Work"') < dc
    assert dc < reopened.index(b'"DC_COPY_CLOSE"') < reopened.index(b"C6_MOS_READ_ONLY_CLOSED|")
    assert reopened.count(b"otaTbMaster(copied ") == 2
    assert b"dbSave(" not in reopened and b"dbPurge(" not in reopened


def test_projected_actual_amp_counter_and_time_values_parse_for_both_stages():
    # Former AUTO120 native save/readback reported these values. Only the new
    # OTA wire prefix is synthetic; no candidate v2 CAPTURE has happened.
    old = b"109570|109570|Nov 22 10:14:43 2026"
    edit = b"Cadence \xa9\nOTA17_RT_META|EDIT_SAVED_META|" + old
    reopened = b"OTA17_RT_META|EDIT_REOPEN_META|" + old
    assert v2.parse_writer_metadata(edit, "EDIT_SAVED_META") == v2.parse_writer_metadata(
        reopened, "EDIT_REOPEN_META"
    )
    for changed in (
        edit + b"\n" + edit,
        edit.replace(b"109570|109570", b"109570|109571"),
        edit.replace(b"Nov 22 10:14:43 2026", b"Nov 22 25:14:43 2026"),
        edit.replace(b"Nov 22", b"Nov 32"),
    ):
        with pytest.raises(ValueError, match="ota_v2_writer_metadata"):
            v2.parse_writer_metadata(changed, "EDIT_SAVED_META")
