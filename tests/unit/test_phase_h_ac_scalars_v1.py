"""The AC scalar reader is bound to one completed candidate PSF."""

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
reader = importlib.import_module("phase_h_ac_scalars_v1")


def test_policy_pins_completed_ac_and_exact_extractor_files() -> None:
    policy = json.loads(reader.POLICY.read_text(encoding="utf-8"))
    ac_policy = json.loads(reader.ac.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == reader._sha(reader.v1._canonical(ac_policy))
    assert policy["ac_files"] == ac_policy["files"]
    assert policy["ac_result_sha256"] == reader.AC_RESULT_SHA256
    assert policy["psf_tree_sha256"] == reader.PSF_SHA256
    assert policy["spectre_attempt_count"] == 3
    for name, path in reader.LOCAL_FILES.items():
        assert reader._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_authority_rejects_counter_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dc_policy = json.loads(reader.dc_v1.POLICY.read_text(encoding="utf-8"))
    base = json.loads(reader.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        reader.dc_v1,
        "_authority",
        lambda: (dc_policy, reader.DC_POLICY_SHA256, tmp_path, base),
    )
    monkeypatch.setattr(reader.dc_v2, "_counter", lambda _root: 4)
    with pytest.raises(reader.AcScalarsV1Error, match="predecessor changed"):
        reader._authority()


def test_response_requires_two_finite_points_and_verified_input() -> None:
    policy = json.loads(reader.POLICY.read_text(encoding="utf-8"))
    points = [
        {
            "frequency_hz": frequency,
            "input_diff_mag_v": 1.0,
            "output_diff_mag_v": 2.0,
            "gain_v_per_v": 2.0,
            "gain_db": 6.020599913,
            "gain_phase_deg": 0.0,
        }
        for frequency in (1000, 10000)
    ]
    result = {
        "schema_version": 1,
        "plan_id": "WP14_FIXED_CANDIDATE_AC_SCALARS_V1",
        "status": "observed",
        "source_sha256": policy["source_fingerprint_sha256"],
        "target_sha256": policy["copy_target_sha256"],
        "psf_sha256": reader.PSF_SHA256,
        "protected_and_result_unchanged": True,
        "simulation_run": False,
        "points": points,
    }
    assert reader._check_response(json.dumps(result).encode(), policy)["points"] == points
    points[1]["input_diff_mag_v"] = 0.0
    with pytest.raises(reader.AcScalarsV1Error, match="input differs"):
        reader._check_response(json.dumps(result).encode(), policy)


def test_ocean_script_is_read_only_and_fixed_to_existing_ac_psf() -> None:
    script = reader.LOCAL_FILES["extract.ocn"].read_text(encoding="ascii")
    runner = reader.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert "openResults(resultPath)" in script
    assert "selectResult('ac)" in script
    assert 'list("Vop" "Vom" "Vp" "Vm")' in script
    assert "real(sample) imag(sample)" in script
    assert "createNetlist" not in script
    assert "run()" not in script
    assert "flock -n 9" in runner
    assert 'timeout 90 "$OCEAN"' in runner


def test_remote_parser_computes_complex_differential_gain() -> None:
    helper = reader.LOCAL_FILES["scalar_helper.py"].read_text(encoding="ascii")
    tree = ast.parse(helper)
    func = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "parse_scalars"
    )
    namespace = {
        "LINE": re.compile(
            r"^MCP_AC_POINT[|](Vop|Vom|Vp|Vm)[|]([01])[|]"
            r"([-+0-9.eE]+)[|]([-+0-9.eE]+)[|]([-+0-9.eE]+)$"
        ),
        "SIGNALS": ("Vop", "Vom", "Vp", "Vm"),
        "FREQUENCIES": (1000.0, 10000.0),
        "math": math,
    }
    exec(compile(ast.Module(body=[func], type_ignores=[]), "parser", "exec"), namespace)
    lines = []
    for signal, real_part in (("Vop", 1.0), ("Vom", -1.0), ("Vp", 0.5), ("Vm", -0.5)):
        for index, frequency in enumerate((1000, 10000)):
            lines.append(f"MCP_AC_POINT|{signal}|{index}|{frequency}|{real_part}|0")
    lines.append("MCP_AC_POINT_COMPLETE|true")
    points = namespace["parse_scalars"]("\n".join(lines))
    assert [point["gain_v_per_v"] for point in points] == [2.0, 2.0]
    assert all(abs(point["gain_db"] - 6.020599913) < 1e-6 for point in points)
    with pytest.raises(ValueError, match="AC scalar line count"):
        namespace["parse_scalars"]("\n".join(lines[:-2]))
