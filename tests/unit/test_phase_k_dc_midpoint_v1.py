"""The third DC point is a single bounded job on the copied circuit."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
midpoint = importlib.import_module("phase_k_dc_midpoint_v1")


def test_policy_pins_three_points_and_prior_evidence() -> None:
    policy = json.loads(midpoint.POLICY.read_text(encoding="utf-8"))
    prior_policy = json.loads(midpoint.prior.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == midpoint._sha(midpoint.v1._canonical(prior_policy))
    assert policy["dc_result_sha256"] == midpoint.scalars.RESULT_HASHES
    assert policy["prior_ac_recovery_sha256"] == midpoint.PRIOR_AC_RECOVERY_SHA256
    assert policy["ac_result_sha256"] == midpoint.AC_RESULT_SHA256
    assert policy["sweep_points_mv"] == [[300, 650], [310, 676], [320, 702]]
    assert policy["midpoint_bias_mv"] == [310, 676]
    assert policy["vdd_mv"] == 1000
    assert policy["input_vcm_mv"] == 500
    assert policy["spectre_attempt_count_before"] == 3
    for name, path in midpoint.LOCAL_FILES.items():
        assert midpoint._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_authority_rejects_counter_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = json.loads(midpoint.prior.POLICY.read_text(encoding="utf-8"))
    base = json.loads(midpoint.v1.POLICY.read_text(encoding="utf-8"))
    digest = midpoint._sha(midpoint.v1._canonical(old))
    monkeypatch.setattr(midpoint.prior, "_authority", lambda: (old, digest, tmp_path, base))
    monkeypatch.setattr(midpoint.dc_v2, "_counter", lambda _root: 4)
    with pytest.raises(midpoint.DcMidpointV1Error, match="Spectre count changed"):
        midpoint._authority()


def test_remote_job_has_one_fixed_spectre_attempt() -> None:
    helper = midpoint.LOCAL_FILES["dc_helper.py"].read_text(encoding="ascii")
    runner = midpoint.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert '"parameters VBIASN=310m VBIASP=676m' in helper
    assert '"dc1 dc\\n"' in helper
    assert '"save Vop Vom VDD Vp Vm\\n"' in helper
    assert "circuit.count(line) != 1" in helper
    assert 'write_file(JOB + "/design-netlist.scs", circuit)' in helper
    assert "flock -n 9" in runner
    assert runner.count('timeout 120 "$SPECTRE"') == 1
    assert '"status": status' in helper
