"""The AC scalar recovery preserves the failed one-shot v1 attempt."""

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
recovery = importlib.import_module("phase_i_ac_scalars_v2")


def test_policy_pins_failed_v1_and_new_exact_files() -> None:
    policy = json.loads(recovery.POLICY.read_text(encoding="utf-8"))
    old = json.loads(recovery.old.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == recovery._sha(recovery.v1._canonical(old))
    assert policy["v1_scalar_files"] == old["files"]
    assert policy["v1_before_sha256"] == recovery.OLD_BEFORE_SHA256
    assert policy["v1_ocean_log_sha256"] == recovery.OLD_OCEAN_LOG_SHA256
    assert policy["v1_attempt_status_sha256"] == recovery.OLD_ATTEMPT_SHA256
    assert policy["v1_scalar_bytes"] == 0
    assert policy["spectre_attempt_count"] == 3
    for name, path in recovery.LOCAL_FILES.items():
        assert recovery._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_authority_refuses_reused_v1_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old_policy = json.loads(recovery.old.POLICY.read_text(encoding="utf-8"))
    base = json.loads(recovery.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        recovery.old,
        "_authority",
        lambda: (old_policy, recovery.OLD_POLICY_SHA256, tmp_path, base),
    )
    monkeypatch.setattr(
        recovery.parent,
        "_read_json",
        lambda _path: {"state": "succeeded", "policy_sha256": recovery.OLD_POLICY_SHA256},
    )
    with pytest.raises(recovery.AcScalarsV2Error, match="v1 read state changed"):
        recovery._authority()


def test_v2_parser_accepts_bounded_multisample_waveform_endpoints() -> None:
    helper = recovery.LOCAL_FILES["scalar_helper.py"].read_text(encoding="ascii")
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
    for signal, real_part in (("Vop", 1.0), ("Vom", -1.0), ("Vp", 0.5), ("Vm", -0.5)):
        lines.append(f"MCP_AC_VECTOR|{signal}|3|3")
        for index, frequency in enumerate((1000, 10000)):
            lines.append(f"MCP_AC_POINT|{signal}|{index}|{frequency}|{real_part}|0")
    lines.append("MCP_AC_POINT_COMPLETE|true")
    points = namespace["parse_scalars"]("\n".join(lines))
    assert [point["gain_v_per_v"] for point in points] == [2.0, 2.0]
    lines[3] = "MCP_AC_VECTOR|Vop|1|1"
    with pytest.raises(ValueError, match="AC vector length"):
        namespace["parse_scalars"]("\n".join(lines))


def test_v2_ocean_logs_bounded_stages_and_reads_only_existing_psf() -> None:
    script = recovery.LOCAL_FILES["extract.ocn"].read_text(encoding="ascii")
    runner = recovery.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert "MCP_AC_STAGE|results_open" in script
    assert "MCP_AC_BLOCK|wave|%s" in script
    assert "lastIndex = sub1(length)" in script
    assert "openResults(resultPath)" in script
    assert "createNetlist" not in script
    assert "run()" not in script
    assert "flock -n 9" in runner
