"""Synthetic standard-VM HNL syntax, without proprietary model or OA data."""

import hashlib

import pytest

from cadence_mcp_bridge import _native_rendering as rendering


def candidate(analysis="dc", extra=""):
    static = [
        "global 0",
        "R0 (in out) resistor r=1000",
        "C0 (out 0) capacitor c=0.000001",
        'simulatorOptions options temp=27 sensfile="../psf/sens.output"',
    ]
    options = {
        "dc": 'write="spectre.dc" maxiters=150 maxsteps=10000 annotate=status',
        "ac": "start=10 stop=1000 dec=3 annotate=status",
        "tran": "stop=0.00000002 maxstep=0.000000001 method=gear2only "
        'write="spectre.ic" writefinal="spectre.fc" maxiters=5 annotate=status',
    }[analysis] + extra
    inputs = (
        {
            "analysis": "dc",
            "mode": "saved_operating_point",
            "statement_sha256": hashlib.sha256(("dc " + options).encode()).hexdigest(),
        }
        if analysis == "dc"
        else {"analysis": "ac", "start_hz": "10", "stop_hz": "1000", "points_per_decade": 3}
        if analysis == "ac"
        else {
            "analysis": "tran",
            "stop_s": "0.00000002",
            "maxstep_s": "0.000000001",
            "method": "gear2only",
        }
    )
    raw = (
        "simulator lang=spectre\nparameters Bias=0.6\n"
        + "\n".join(static)
        + "\nanalysis0 "
        + analysis
        + " "
        + options
        + "\n"
    ).encode()
    return raw, inputs, rendering.static_fingerprint(static)


@pytest.mark.parametrize("analysis", ["dc", "ac", "tran"])
def test_native_defaults_and_folded_static_statements_match_same_binding(analysis):
    raw, inputs, static = candidate(analysis)
    folded = raw.replace(b"resistor r=1000", b"resistor " + bytes([92]) + b"\n    r=1000")
    first = rendering.effective_input(raw, {"Bias": "0.6"}, [], inputs, static)
    second = rendering.effective_input(folded, {"Bias": "0.6"}, [], inputs, static)
    assert first["parameter_count"] == second["parameter_count"] == 1
    assert first["input_sha256"] != second["input_sha256"]


@pytest.mark.parametrize(
    "extra",
    [
        " param=Bias start=0 stop=1",
        " dev=V0",
        " readns=/protected",
        " maxiters=0",
        " maxsteps=100001",
        " write=spectre.dc",
    ],
)
def test_even_exact_dc_hash_cannot_promote_sweep_or_external_io_to_op(extra):
    raw, inputs, static = candidate(extra=extra)
    with pytest.raises(ValueError, match="analysis_binding_mismatch"):
        rendering.effective_input(raw, {"Bias": "0.6"}, [], inputs, static)


@pytest.mark.parametrize(
    "before,after",
    [
        (b'write="spectre.dc"', b'write="/protected/source"'),
        (b'sensfile="../psf/sens.output"', b'sensfile="../../psf/sens.output"'),
        (b'sensfile="../psf/sens.output"', b'x="../psf/sens.output"'),
        (b'write="spectre.dc"', b'write="spectre.dc"junk'),
    ],
)
def test_quoted_output_paths_have_no_arbitrary_path_escape(before, after):
    raw, inputs, static = candidate()
    with pytest.raises(ValueError, match="dialect_unsupported"):
        rendering.effective_input(raw.replace(before, after), {"Bias": "0.6"}, [], inputs, static)


@pytest.mark.parametrize(
    "analysis,extra",
    [
        ("ac", " readns=/protected"),
        ("ac", " annotate=all"),
        ("tran", " maxiters=6"),
        ("tran", ' write="spectre.ic"'),
    ],
)
def test_extra_analysis_options_and_duplicates_are_not_inherited(analysis, extra):
    raw, inputs, static = candidate(analysis, extra)
    with pytest.raises(ValueError, match="analysis_binding_mismatch"):
        rendering.effective_input(raw, {"Bias": "0.6"}, [], inputs, static)


@pytest.mark.parametrize(
    "suffix",
    [
        b"\n" + bytes([92]),
        b"\nR0 " + bytes([92]) + b"\n// comment",
        b"\nR0 " + bytes([92]) + b"\n",
        b"\nR0 " + bytes([92]) + b"x",
        b"\n" + b"x" * 16385,
    ],
)
def test_incomplete_or_ambiguous_continuations_fail_closed(suffix):
    raw, inputs, static = candidate()
    with pytest.raises(ValueError, match="dialect_unsupported"):
        rendering.effective_input(raw + suffix, {"Bias": "0.6"}, [], inputs, static)


@pytest.mark.parametrize("analysis", ["dc", "ac", "tran"])
@pytest.mark.parametrize(
    "extra",
    [
        "extra psp fund=1G",
        "extra qpsp fund=1G",
        "extra hbsp fund=1G",
        "extra qpstb fund=1G",
        "extra futureAnalysis stop=1",
        "extra PSP fund=1G",
        "extra (in out) psp fund=1G",
        "extra (in out) QPSTB fund=1G",
        "extra (in out) psp fund=1G trailing",
        "extra options temp=27 extra psp fund=1G",
        "unrecognized command=1",
    ],
)
def test_unknown_controls_fail_even_with_registered_static_hash(analysis, extra):
    raw, inputs, _ = candidate(analysis)
    raw += (extra + "\n").encode()
    static = rendering.static_fingerprint(rendering.statements(raw)[1:-2] + [extra])
    with pytest.raises(ValueError, match="spectre_control_unsupported"):
        rendering.effective_input(raw, {"Bias": "0.6"}, [], inputs, static)


@pytest.mark.parametrize(
    "pragma", ["//pragma protect begin", "// pragma protect end", "//PRAGMA PROTECT begin"]
)
def test_protection_pragmas_are_not_ordinary_comments(pragma):
    raw, inputs, static = candidate()
    with pytest.raises(ValueError, match="spectre_scope_unsupported"):
        rendering.effective_input(
            pragma.encode() + b"\n" + raw, {"Bias": "0.6"}, [], inputs, static
        )
