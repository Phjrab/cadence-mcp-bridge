"""Two fixed AC PSFs can be measured without another simulation."""

from __future__ import annotations

import ast
import importlib
import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
scalar = importlib.import_module("phase_n_ac_two_point_scalars_v1")


def test_policy_pins_completed_ac_and_files() -> None:
    policy = json.loads(scalar.POLICY.read_text(encoding="utf-8"))
    parent = json.loads(scalar.ac.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == scalar._sha(scalar.v1._canonical(parent))
    assert policy["ac_result_sha256"] == scalar.AC_RESULTS
    assert policy["psf_tree_sha256"] == scalar.PSF_HASHES
    assert policy["spectre_attempt_count"] == 6
    assert policy["new_simulation"] is False
    for name, path in scalar.LOCAL_FILES.items():
        assert scalar._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_counter_drift_blocks_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = json.loads(scalar.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(scalar.v1, "_authority", lambda: (base, "base", tmp_path))
    monkeypatch.setattr(scalar.dc_v2, "_counter", lambda _root: 7)
    with pytest.raises(scalar.AcTwoPointScalarsError, match="Spectre count changed"):
        scalar._authority()


def test_parser_accepts_high_small_signal_gain_and_rejects_drift() -> None:
    helper = scalar.LOCAL_FILES["scalar_helper.py"].read_text(encoding="ascii")
    tree = ast.parse(helper)
    func = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "parse_scalars"
    )
    namespace = {
        "LINE": re.compile(
            r"^MCP_AC_POINT[|](Vop|Vom|Vp|Vm)[|]([01])[|]([-+0-9.eE]+)[|]([-+0-9.eE]+)[|]([-+0-9.eE]+)$"
        ),
        "VECTOR_LINE": re.compile(r"^MCP_AC_VECTOR[|](Vop|Vom|Vp|Vm)[|]([0-9]+)[|]([0-9]+)$"),
        "STAGES": (
            "MCP_AC_STAGE|file_open",
            "MCP_AC_STAGE|results_open",
            "MCP_AC_STAGE|ac_selected",
        ),
        "SIGNALS": ("Vop", "Vom", "Vp", "Vm"),
        "FREQUENCIES": (1000.0, 10000.0),
        "math": math,
    }
    exec(compile(ast.Module(body=[func], type_ignores=[]), "parser", "exec"), namespace)
    lines = list(namespace["STAGES"])
    for signal, real_part in (("Vop", 4431.5), ("Vom", -4431.5), ("Vp", 0.5), ("Vm", -0.5)):
        lines.append(f"MCP_AC_VECTOR|{signal}|3|3")
        for index, frequency in enumerate((1000, 10000)):
            lines.append(f"MCP_AC_POINT|{signal}|{index}|{frequency}|{real_part}|0")
    lines.append("MCP_AC_POINT_COMPLETE|true")
    points = namespace["parse_scalars"]("\n".join(lines))
    assert [point["gain_v_per_v"] for point in points] == [8863.0, 8863.0]
    lines[4] = "MCP_AC_POINT|Vop|0|999|4431.5|0"
    with pytest.raises(ValueError, match="invalid AC scalar"):
        namespace["parse_scalars"]("\n".join(lines))


def test_remote_reader_is_fixed_to_existing_psfs() -> None:
    runner = scalar.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert 'case "$1" in baseline|midpoint)' in runner
    assert "flock -n 9" in runner
    assert 'timeout 90 "$OCEAN"' in runner
    for mode in scalar.AC_RESULTS:
        ocean = scalar.LOCAL_FILES[f"extract-{mode}.ocn"].read_text(encoding="ascii")
        assert f"wp14-ac-sweep-two-point-v1/{mode}/psf" in ocean
        assert "openResults(resultPath)" in ocean
        assert "createNetlist" not in ocean
        assert "run()" not in ocean
