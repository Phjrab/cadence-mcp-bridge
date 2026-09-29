"""Candidate wideband AC is a single fixed, bounded work-copy run."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
wide = importlib.import_module("phase_o_candidate_wideband_ac_v1")


def test_policy_pins_completed_scalars_and_frequency_range() -> None:
    policy = json.loads(wide.POLICY.read_text(encoding="utf-8"))
    parent = json.loads(wide.scalars.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == wide._sha(wide.v1._canonical(parent))
    assert policy["prior_scalar_result_sha256"] == wide.SCALAR_RESULTS
    assert policy["candidate_bias_mv"] == [320, 702]
    assert policy["vdd_mv"] == 1000
    assert policy["input_vcm_mv"] == 500
    assert policy["frequency_start_hz"] == 10
    assert policy["frequency_stop_hz"] == 100000000
    assert policy["points_per_decade"] == 10
    assert policy["spectre_attempt_count_before"] == 6
    for name, path in wide.LOCAL_FILES.items():
        assert wide._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_counter_drift_blocks_before_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = json.loads(wide.scalars.POLICY.read_text(encoding="utf-8"))
    base = json.loads(wide.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        wide.scalars,
        "_authority",
        lambda: (parent, wide.PARENT_POLICY_SHA256, tmp_path, base),
    )
    monkeypatch.setattr(wide.dc_v2, "_counter", lambda _root: 7)
    with pytest.raises(wide.CandidateWidebandAcError, match="Spectre count changed"):
        wide._authority()


def test_runner_uses_one_fixed_copy_only_spectre_job() -> None:
    helper = wide.LOCAL_FILES["ac_helper.py"].read_text(encoding="ascii")
    runner = wide.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert '"parameters VBIASN=320m VBIASP=702m' in helper
    assert '"ac1 ac start=10 stop=100Meg dec=10' in helper
    assert '"V0 (VDD 0) vsource dc=1 type=dc"' in helper
    assert '"V1 (Vp 0) vsource dc=500m mag=500m"' in helper
    assert '"V2 (Vm 0) vsource dc=500m mag=-500m"' in helper
    assert 'write_file(JOB + "/design-netlist.scs", circuit)' in helper
    assert "flock -n 9" in runner
    assert runner.count('timeout 120 "$SPECTRE"') == 1
    assert '"status": status' in helper
