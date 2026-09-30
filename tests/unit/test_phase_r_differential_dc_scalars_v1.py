"""The fixed DC scalar reader pins both results and validates actual inputs."""

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
reader = importlib.import_module("phase_r_differential_dc_scalars_v1")


def test_policy_pins_both_completed_runs_and_remote_bytes() -> None:
    policy = json.loads(reader.POLICY.read_text(encoding="utf-8"))
    parent = json.loads(reader.dc.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == reader._sha(reader.v1._canonical(parent))
    assert policy["dc_result_sha256"] == reader.DC_RESULTS
    assert policy["psf_tree_sha256"] == reader.PSF_HASHES
    assert policy["spectre_attempt_count"] == 9
    assert policy["new_simulation"] is False
    for name, path in reader.LOCAL_FILES.items():
        assert reader._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_counter_drift_blocks_before_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = json.loads(reader.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(reader.v1, "_authority", lambda: (base, "", tmp_path))
    monkeypatch.setattr(reader.dc_v2, "_counter", lambda _root: 10)
    with pytest.raises(reader.DifferentialDcScalarsError, match="Spectre count changed"):
        reader._authority()


def _parser(mode: str):
    source = reader.LOCAL_FILES["scalar_helper.py"].read_text(encoding="ascii")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "parse_scalars"
    )
    namespace = {
        "math": math,
        "LINE": re.compile(r"^MCP_DIFFERENTIAL_DC_SCALAR[|](Vop|Vom|VDD|Vp|Vm)[|]([-+0-9.eE]+)$"),
        "SIGNALS": ("Vop", "Vom", "VDD", "Vp", "Vm"),
        "INPUTS": {"positive": (0.5000005, 0.4999995), "negative": (0.4999995, 0.5000005)},
        "mode": mode,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "helper", "exec"), namespace)
    return namespace["parse_scalars"]


@pytest.mark.parametrize("mode,vp,vm", [
    ("positive", 0.5000005, 0.4999995),
    ("negative", 0.4999995, 0.5000005),
])
def test_parser_checks_differential_dc_input(mode: str, vp: float, vm: float) -> None:
    parse = _parser(mode)
    lines = [
        "MCP_DIFFERENTIAL_DC_SCALAR|Vop|0.23",
        "MCP_DIFFERENTIAL_DC_SCALAR|Vom|0.22",
        "MCP_DIFFERENTIAL_DC_SCALAR|VDD|1",
        f"MCP_DIFFERENTIAL_DC_SCALAR|Vp|{vp}",
        f"MCP_DIFFERENTIAL_DC_SCALAR|Vm|{vm}",
        "MCP_DIFFERENTIAL_DC_SCALAR_COMPLETE|true",
    ]
    result = parse("\n".join(lines))
    assert result["output_diff_v"] == pytest.approx(0.01)
    lines[3] = "MCP_DIFFERENTIAL_DC_SCALAR|Vp|0.5"
    with pytest.raises(ValueError, match="supply or common-mode mismatch"):
        parse("\n".join(lines))
