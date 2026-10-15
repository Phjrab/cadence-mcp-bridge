import pytest

from cadence_mcp_bridge.m2_cdf import CdfSource, parse_frame, render_collector


def frame() -> bytes:
    return b"""M2_CDF_V1
DEVICE|"pdk"|"mos"|"M0"
TERM|"D"
TERM|"G"
TERM|"S"
TERM|"B"
PARAM|"base"|"w"|"string"|"lengthMetric"|"1u"|"1u"
PARAM|"effective"|"w"|"string"|"lengthMetric"|"1u"|"2u"
SIM|"base"|"nmos"|("D" "G" "S" "B")
SIM|"effective"|"nmos"|("D" "G" "S" "B")
END
COMPLETE
"""


def test_data_is_observation_not_executable_or_numeric_bounds() -> None:
    value = parse_frame(frame())[0]
    assert value["terminals"] == ("D", "G", "S", "B")
    assert value["parameters"] == (
        ("base", "w", "string", "lengthMetric", "1u", "1u"),
        ("effective", "w", "string", "lengthMetric", "1u", "2u"),
    )
    assert "qualified" not in value
    assert "minimum" not in value


@pytest.mark.parametrize("name", ['a") exit(0)', "../x", "a b", "x\n", "a|b", "a" * 65])
def test_source_injection_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        CdfSource(name, "source")


def test_fixed_readonly_script() -> None:
    program = render_collector(CdfSource("RegisteredLib", "RegisteredCell")).decode()
    assert '"RegisteredLib" "RegisteredCell" "schematic" "" "r"' in program
    assert 'outfile("cdf-frame.txt")' in program
    for forbidden in ("dbSave", "dbReplaceProp", "cdfSet", "eval", "load("):
        assert forbidden not in program
    assert 'list("vdc" "vpulse" "cap")' in program


@pytest.mark.parametrize(
    "raw",
    [
        frame().replace(b"COMPLETE", b""),
        frame().replace(b"END\n", b""),
        frame().replace(b'TERM|"D"', b'TERM|"D"\nTERM|"D"'),
        frame().replace(b'"1u"|"2u"', b'"1u"|load("evil")'),
        frame().replace(b'"1u"|"2u"', b'"1u"|"a|b"'),
        frame().replace(b'"1u"|"2u"', b'"1u"|((((((nil))))))'),
        frame().replace(b'SIM|"effective"', b'SIM|"base"'),
        frame() + b"extra\n",
        b"x" * 262145,
        b"\x00" + frame(),
    ],
    ids=[
        "truncated",
        "missing-end",
        "duplicate-terminal",
        "expression",
        "delimiter",
        "depth",
        "duplicate-sim",
        "trailing",
        "size",
        "nul",
    ],
)
def test_malformed_or_truncated_frames_reject(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_frame(raw)


def test_unknown_expression_retained_as_data() -> None:
    value = parse_frame(frame().replace(b'"2u"', b'"pPar(\\"width\\")"'))[0]
    assert value["parameters"][-1][-1] == 'pPar("width")'  # type: ignore[index]
