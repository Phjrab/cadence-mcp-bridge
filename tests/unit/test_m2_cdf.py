import pytest

from cadence_mcp_bridge.m2_cdf import (
    CdfSource,
    parse_frame,
    render_collector,
    render_reopened_mos_cdf,
    render_research_cdf_facts,
)


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
    assert "~>simInfo~>spectre" not in program
    assert '"wrong_type"' in program
    assert "errset(m2Collect() t)" in program
    assert "else exit(1)" in program
    assert "symbolToString(field)" in program
    assert "symbolName(" not in program
    assert 'inst~>libName=="basic"' in program
    assert 'member(inst~>cellName list("ipin" "opin" "iopin"))' in program
    # Only known port markers are omitted; every other instance still needs CDF.
    assert 'unless(base error("M2_CDF_MISSING"))' in program


def test_research_probe_limits_reads_and_omits_callback_bodies() -> None:
    source = render_research_cdf_facts()
    for library, device in (
        (b"gpdk090", b"nmos1v"), (b"gpdk090", b"pmos1v"),
        (b"analogLib", b"vdc"), (b"analogLib", b"vsource"), (b"analogLib", b"cap"),
    ):
        assert source.count(b'm2CdfDump(port "%s" "%s" nil list(' % (library, device)) == 1
    assert b'member(candidate~>name names)' in source
    assert b'm2CdfDump(port "analogLib" "vdc" nil list("vdc" ' in source
    assert b'"acm" "acp"' in source
    assert b"field!='callback" in source
    assert b'outfile("cdf-constraints.txt")' in source
    assert b"dbSave" not in source and b"eval(" not in source


def test_reopen_cdf_dumps_only_the_checked_instance_in_the_existing_process() -> None:
    source = render_reopened_mos_cdf()
    assert b'inst~>libName=="gpdk090" inst~>viewName=="symbol"' in source
    assert source.count(b"m2CdfDump(port inst~>libName inst~>cellName inst list(") == 1
    assert b'"simW" "simM"' in source
    assert b"cdfGetInstCDF(inst)" in source
    assert b"exit(" not in source and b"dbSave" not in source


def test_research_probe_adds_only_explicit_registered_view_reads():
    source = render_research_cdf_facts(
        amp_source=CdfSource("AmpCopy", "AmpTB"),
        mos_source=CdfSource("InverterCopy", "DUT"),
    )
    assert b'm2ResearchInstances(port bindings "AmpCopy" "AmpTB" "amp")' in source
    assert b'm2ResearchInstances(port bindings "InverterCopy" "DUT" "mos")' in source
    assert b'list("V1" "V2")' in source and b'list("MN" "MP")' in source
    assert b'cv~>mode=="r"' in source
    assert b"dbFindProp(inst field)" in source and b"term~>net~>name" in source
    assert b"dbSave" not in source and b"dbReplaceProp" not in source


def v2_frame(*, unknown: bool = False) -> bytes:
    raw = frame().replace(b"M2_CDF_V1", b"M2_CDF_V2")
    rows = []
    for scope in ("base", "effective"):
        for name in (
            "simInfo",
            "spectre",
            "componentName",
            "termOrder",
            "namePrefix",
            "modelName",
            "instParameters",
            "netlistProcedure",
        ):
            value = (
                '"nmos"'
                if name == "componentName"
                else ('("D" "G" "S" "B")' if name == "termOrder" else "nil")
            )
            status = "wrong_type" if unknown else "observed"
            rows.append(
                f'META|"{scope}"|"{name}"|"{status}"|string|{value if not unknown else "nil"}'
            )
    if unknown:
        raw = raw.replace(b'"nmos"|("D" "G" "S" "B")', b"nil|nil")
    return raw.replace(b"END\n", ("\n".join(rows) + "\nEND\n").encode())


def test_missing_or_wrong_type_is_complete_but_unqualified_data() -> None:
    result = parse_frame(v2_frame(unknown=True))[0]
    assert result["spectre"] == (("base", None, None), ("effective", None, None))
    assert len(result["metadata_fields"]) == 16  # type: ignore[arg-type]
    assert "qualified" not in result


def test_typed_metadata_conflict_rejects() -> None:
    assert len(parse_frame(v2_frame())) == 1
    with pytest.raises(ValueError, match="conflicting"):
        parse_frame(
            v2_frame().replace(
                b'"componentName"|"observed"|string|"nmos"',
                b'"componentName"|"observed"|string|"pmos"',
            )
        )


def test_observed_symbol_headed_list_printer_is_data_only() -> None:
    raw = v2_frame().replace(
        b'"instParameters"|"observed"|string|nil',
        b'"instParameters"|"observed"|list|dc(mag phase type)',
    )
    result = parse_frame(raw)[0]
    rows = result["metadata_fields"]
    assert any(row[-1] == ("dc", "mag", "phase", "type") for row in rows)  # type: ignore[union-attr]
    with pytest.raises(ValueError):
        parse_frame(raw.replace(b"dc(mag phase type)", b'load("evil")'))
    with pytest.raises(ValueError):
        parse_frame(raw.replace(b"dc(mag phase type)", b"dc(mag) other"))
    with pytest.raises(ValueError):
        parse_frame(raw.replace(b"dc(mag phase type)", b"dc(mag(nested))"))


def test_typed_metadata_truncation_rejects() -> None:
    with pytest.raises(ValueError, match="incomplete typed"):
        parse_frame(v2_frame().replace(b'META|"base"|"simInfo"|"observed"|string|nil\n', b""))


def test_emitted_program_has_balanced_forms() -> None:
    import re

    text = render_collector(CdfSource("RegisteredLib", "RegisteredCell")).decode()
    without_strings = re.sub(r'"(?:[^"\\]|\\.)*"', "", text)
    depth = 0
    for char in without_strings:
        depth += int(char == "(") - int(char == ")")
        assert depth >= 0
    assert depth == 0


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
