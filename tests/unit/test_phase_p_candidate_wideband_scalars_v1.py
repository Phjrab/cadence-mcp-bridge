"""Wideband scalar extraction validates the fixed AC result and complete spectrum."""

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
scalar = importlib.import_module("phase_p_candidate_wideband_scalars_v1")


def test_policy_pins_completed_wideband_psf_and_files() -> None:
    policy = json.loads(scalar.POLICY.read_text(encoding="utf-8"))
    parent = json.loads(scalar.wide.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == scalar._sha(scalar.v1._canonical(parent))
    assert policy["wideband_result_sha256"] == scalar.WIDEBAND_RESULT_SHA256
    assert policy["psf_tree_sha256"] == scalar.PSF_SHA256
    assert policy["psf_bytes"] == 13805
    assert policy["spectre_attempt_count"] == 7
    assert policy["new_simulation"] is False
    for name, path in scalar.LOCAL_FILES.items():
        assert scalar._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_counter_drift_blocks_before_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = json.loads(scalar.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(scalar.v1, "_authority", lambda: (base, "base", tmp_path))
    monkeypatch.setattr(scalar.dc_v2, "_counter", lambda _root: 8)
    with pytest.raises(scalar.CandidateWidebandScalarsError, match="Spectre count changed"):
        scalar._authority()


def test_parser_accepts_bounded_full_spectrum_and_rejects_frequency_drift() -> None:
    helper = scalar.LOCAL_FILES["scalar_helper.py"].read_text(encoding="ascii")
    tree = ast.parse(helper)
    func = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "parse_scalars"
    )
    namespace = {
        "LINE": re.compile(
            r"^MCP_AC_POINT[|](Vop|Vom|Vp|Vm)[|]([0-9]{1,3})[|]"
            r"([-+0-9.eE]+)[|]([-+0-9.eE]+)[|]([-+0-9.eE]+)$"
        ),
        "VECTOR_LINE": re.compile(r"^MCP_AC_VECTOR[|](Vop|Vom|Vp|Vm)[|]([0-9]+)[|]([0-9]+)$"),
        "STAGES": (
            "MCP_AC_STAGE|file_open",
            "MCP_AC_STAGE|results_open",
            "MCP_AC_STAGE|ac_selected",
        ),
        "SIGNALS": ("Vop", "Vom", "Vp", "Vm"),
        "math": math,
    }
    exec(compile(ast.Module(body=[func], type_ignores=[]), "parser", "exec"), namespace)
    lines = list(namespace["STAGES"])
    for signal, value in (("Vop", 4431.5), ("Vom", -4431.5), ("Vp", 0.5), ("Vm", -0.5)):
        lines.append(f"MCP_AC_VECTOR|{signal}|71|71")
        for index in range(71):
            frequency = 10 ** (1 + index / 10)
            lines.append(f"MCP_AC_POINT|{signal}|{index}|{frequency}|{value}|0")
    lines.append("MCP_AC_POINT_COMPLETE|true")
    points = namespace["parse_scalars"]("\n".join(lines))
    assert len(points) == 71
    assert points[0]["gain_v_per_v"] == 8863.0
    scalar._validate_points(points)
    for offset in (5, 77, 149, 221):
        parts = lines[offset].split("|")
        parts[3] = "10"
        lines[offset] = "|".join(parts)
    with pytest.raises(ValueError, match="frequency progression"):
        namespace["parse_scalars"]("\n".join(lines))


def test_reader_only_opens_existing_psf() -> None:
    ocean = scalar.LOCAL_FILES["extract.ocn"].read_text(encoding="ascii")
    runner = scalar.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert "wp14-candidate-wideband-ac-v1/psf" in ocean
    assert "openResults(resultPath)" in ocean
    assert "for(index 0 lastIndex" in ocean
    assert "createNetlist" not in ocean
    assert "run()" not in ocean
    assert "flock -n 9" in runner
    assert 'timeout 90 "$OCEAN"' in runner
