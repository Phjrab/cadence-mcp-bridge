"""Local program fixtures. These tuple renders confer no installed PDK qualification."""

import re
from hashlib import sha256
from typing import Any, Literal

import pytest

from cadence_mcp_bridge.mos_wl_skill import render_mos_wl_skill
from cadence_mcp_bridge.mos_wlm_skill import render_mos_wlm_skill


@pytest.mark.parametrize(
    ("master", "width_nm", "length_nm", "candidate_m"),
    [
        ("nmos1v", "1000", "250", 1),
        ("nmos1v", "1500", "250", 1),
        ("nmos1v", "10000", "250", 1),
        ("nmos1v", "15000", "250", 1),
        ("pmos1v", "3000", "250", 1),
        ("pmos1v", "30000", "250", 1),
        ("pmos1v", "10000", "1000", 1),
        ("pmos1v", "16000", "1000", 6),
    ],
)
def test_research_tuple_recipe_order(
    master: Literal["nmos1v", "pmos1v"], width_nm: str, length_nm: str, candidate_m: int
) -> None:
    # The registered source starts with m=1. Retain it without invoking m.
    multiplier = None if candidate_m == 1 else candidate_m
    program = render_mos_wlm_skill(
        master, length_nm=length_nm, width_nm=width_nm, multiplier=multiplier
    )
    recipe = f'list("l" "{length_nm}n") list("w" "{width_nm}n")'
    if multiplier is not None:
        recipe += ' list("m" "6")'
    assert program.isascii()
    assert program.decode("ascii").endswith(f'mcpMosWlmApply(inst "{master}" list({recipe})))\n')
    assert program == render_mos_wlm_skill(
        master, width_nm=width_nm, length_nm=length_nm, multiplier=multiplier
    )


@pytest.mark.parametrize(
    "candidate_arguments",
    [
        {},
        {"length_nm": "0.0"},
        {"length_nm": "1e3"},
        {"width_nm": "3u"},
        {"width_nm": "nan"},
        {"length_nm": '250")\nexit(0)'},
        {"width_nm": "+25"},
        {"width_nm": "9" * 25},
        {"multiplier": True},
        {"multiplier": "6"},
        {"multiplier": 6.0},
        {"multiplier": 0},
        {"multiplier": 7},
    ],
)
def test_invalid_values_cannot_enter_script(candidate_arguments: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        render_mos_wlm_skill("pmos1v", **candidate_arguments)


def test_m_only_keeps_geometry_and_fingers_withdrawn_from_writes() -> None:
    program = render_mos_wlm_skill("pmos1v", multiplier=6)
    assert program.endswith(b'mcpMosWlmApply(inst "pmos1v" list(list("m" "6"))))\n')
    assert b'if(assoc("l" mcpSteps) || assoc("w" mcpSteps) then mcpJunctions else nil)' in program
    assert b"MCP_MOS_WLM_HELD_JUNCTION" in program
    assert b'if(field=="m" || field=="fingers" then observed==expected else' in program
    assert b'mcpMosWlmValue(cdfgData "fingers")=="1"' in program
    assert b"dbSave(" not in program
    assert render_mos_wlm_skill("pmos1v", multiplier=1).endswith(
        b'mcpMosWlmApply(inst "pmos1v" list(list("m" "1"))))\n'
    )


def test_wlm_lifecycle_keeps_live_instance_context_and_rereads_oa() -> None:
    program = render_mos_wlm_skill("nmos1v", width_nm="1500", length_nm="250").decode("ascii")
    calls = (
        "mcpMosVerifyCallbacks(mcpInst mcpCallbacks)==t",
        "PasCdfFormInit(cdfgData)",
        "cdfgData==mcpCdf",
        "mcpParam~>value=cadr(mcpStep)",
        "mcpParam~>callback==cadr(mcpPair)",
        "errset(evalstring(cadr(mcpPair)) t)",
        "cdfgData==mcpCdf",
        'dbReplaceProp(mcpInst mcpField "string" mcpValue)',
        "PasCdfDone(mcpInst)",
        "mcpEffective=cdfGetInstCDF(mcpInst)",
        "mcpProp=dbFindProp(mcpInst mcpField)",
        "MCP_MOS_WLM_DONE_OA_READBACK",
        "MCP_MOS_WL_READY_FOR_SAVE_CHECK",
    )
    offset = -1
    for call in calls:
        offset = program.index(call, offset + 1)
    assert program.count("evalstring(") == 1
    assert program.count("PasCdfDone(mcpInst)") == 1

    # Lexical guard for static fixtures. The native SKILL parser still belongs to C1.
    without_strings_or_comments = re.sub(r'"(?:[^"\\]|\\.)*"|;[^\n]*', "", program)
    depth = 0
    for token in without_strings_or_comments:
        depth += (token == "(") - (token == ")")
        assert depth >= 0
    assert depth == 0


def test_legacy_qualification_program_digests_are_unchanged() -> None:
    assert sha256(render_mos_wl_skill("nmos1v", length_nm="200")).hexdigest() == (
        "85a1651a171999d194453b7a3367943f1c54d406503dc180147ea73e8696661a"
    )
    assert (
        sha256(render_mos_wl_skill("pmos1v", width_nm="3000", width_field="w")).hexdigest()
        == "832b0128002048d2b6754116a20cbe7dfeb503df3a30bb21c0fba937326dfb23"
    )
