"""Fixed CDF inventory accepts only the observed MOS topology and bounded fields."""

from __future__ import annotations

import ast
import importlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
cdf = importlib.import_module("phase_s_mos_cdf_v1")


def test_policy_and_remote_bytes_are_bound() -> None:
    policy = json.loads(cdf.POLICY.read_text(encoding="utf-8"))
    parent = json.loads(cdf.scalars.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == cdf._sha(cdf.v1._canonical(parent))
    assert policy["oa_facts_result_sha256"] == cdf.OA_FACTS_SHA256
    assert policy["prior_scalar_result_sha256"] == cdf.SCALAR_SHA256
    assert policy["mos_master_counts"] == {"nmos1v": 8, "pmos1v": 6}
    assert policy["new_simulation"] is False
    for name, path in cdf.LOCAL_FILES.items():
        assert cdf._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_counter_drift_blocks_before_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = json.loads(cdf.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(cdf.v1, "_authority", lambda: (base, "", tmp_path))
    monkeypatch.setattr(cdf.dc_v2, "_counter", lambda _root: 10)
    with pytest.raises(cdf.MosCdfV1Error, match="Spectre count changed"):
        cdf._authority()


def _parse_private():
    source = cdf.LOCAL_FILES["cdf_helper.py"].read_text(encoding="ascii")
    node = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "parse_private"
    )
    namespace = {
        "TOKEN": re.compile(r"^[A-Za-z0-9_.$+-]{1,128}$"),
        "VALUE": re.compile(r"^[\x21-\x7e]{1,96}$"),
        "NAMES": ("w", "l", "m", "nf", "fw", "width", "length", "fingers", "totalWidth"),
        "PREFIXES": ("MCP_MOS_CDF_BEGIN|", "MCP_MOS_CDF_INST|", "MCP_MOS_CDF_PARAM|",
                     "MCP_MOS_CDF_COUNTS|", "MCP_MOS_CDF_COMPLETE|"),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "helper", "exec"), namespace)
    return namespace["parse_private"]


def test_parser_requires_exact_mos_counts_and_rejects_duplicate_parameter() -> None:
    lines = ["MCP_MOS_CDF_BEGIN|true"]
    for index in range(14):
        master = "nmos1v" if index < 8 else "pmos1v"
        lines.append(f"MCP_MOS_CDF_INST|M{index}|{master}|true")
        lines.append(f'MCP_MOS_CDF_PARAM|M{index}|w|"1u"|"1u"')
    lines.extend(["MCP_MOS_CDF_COUNTS|35|14|14|14", "MCP_MOS_CDF_COMPLETE|true|true"])
    parse = _parse_private()
    value = parse("\n".join(lines))
    assert value["parameter_count"] == 14
    with pytest.raises(ValueError, match="parameter marker"):
        parse("\n".join(lines[:3] + [lines[2]] + lines[3:]))
    lines[-2] = "MCP_MOS_CDF_COUNTS|35|14|13|14"
    with pytest.raises(ValueError, match="topology"):
        parse("\n".join(lines))


def test_skill_source_opens_read_only_without_saving() -> None:
    skill = cdf.LOCAL_FILES["mos-cdf-v1.il"].read_text(encoding="ascii")
    assert 'dbOpenCellViewByType(sourceLib sourceCell sourceView "" "r")' in skill
    assert "cdfGetInstCDF(inst)" in skill
    assert "dbClose(cv)" in skill
    assert "dbSave" not in skill
