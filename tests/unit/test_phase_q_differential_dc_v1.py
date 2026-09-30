"""Bounded symmetric DC jobs retain reviewed evidence and cumulative budgets."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
dc = importlib.import_module("phase_q_differential_dc_v1")


def test_fixed_policy_and_remote_bytes() -> None:
    policy = json.loads(dc.POLICY.read_text(encoding="utf-8"))
    parent = json.loads(dc.scalar.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == dc._sha(dc.v1._canonical(parent))
    assert policy["candidate_bias_mv"] == [320, 702]
    assert policy["vdd_mv"] == 1000
    assert policy["input_vcm_mv"] == 500
    assert policy["input_dc_differential_uv"] == [1, -1]
    assert policy["spectre_attempt_count_before"] == 7
    for name, path in dc.LOCAL_FILES.items():
        assert dc._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_cumulative_counter_drift_blocks_before_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = json.loads(dc.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(dc.v1, "_authority", lambda: (base, "", tmp_path))
    monkeypatch.setattr(dc.dc_v2, "_counter", lambda _root: 9)
    with pytest.raises(dc.DifferentialDcV1Error, match="Spectre count changed"):
        dc._authority("deploy")


def test_job_local_symmetry_and_one_active_simulator() -> None:
    helper = dc.LOCAL_FILES["dc_helper.py"].read_text(encoding="ascii")
    runner = dc.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert '"positive": ("500.0005m", "499.9995m", 0.000001)' in helper
    assert '"negative": ("499.9995m", "500.0005m", -0.000001)' in helper
    assert '"parameters VBIASN=320m VBIASP=702m' in helper
    assert '"dc1 dc' in helper
    assert 'write_file(JOB + "/design-netlist.scs", modified)' in helper
    assert (
        'worker._read_bounded(JOB + "/design-netlist.scs", 10 * 1024 * 1024)'
        ' != expected_netlist'
    ) in helper
    assert "flock -n 9" in runner
    assert runner.count('timeout 120 "$SPECTRE"') == 1
