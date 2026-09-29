"""The remaining two AC sweep points are fixed and sequential."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
ac = importlib.import_module("phase_m_ac_two_point_v1")


def test_policy_pins_existing_results_and_two_ac_points() -> None:
    policy = json.loads(ac.POLICY.read_text(encoding="utf-8"))
    parent = json.loads(ac.scalar.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == ac._sha(ac.v1._canonical(parent))
    assert policy["prior_scalar_result_sha256"] == ac.PRIOR_SCALAR_SHA256
    assert policy["candidate_ac_result_sha256"] == ac.PRIOR_AC_SHA256
    assert policy["bias_points_mv"] == [[300, 650], [310, 676]]
    assert policy["vdd_mv"] == 1000
    assert policy["input_vcm_mv"] == 500
    assert policy["frequencies_hz"] == [1000, 10000]
    assert policy["spectre_attempt_count_before"] == 4
    for name, path in ac.LOCAL_FILES.items():
        assert ac._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_authority_rejects_attempt_counter_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = json.loads(ac.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(ac.v1, "_authority", lambda: (base, "base", tmp_path))
    monkeypatch.setattr(ac.dc_v2, "_counter", lambda _root: 6)
    with pytest.raises(ac.AcTwoPointV1Error, match="Spectre count changed"):
        ac._authority("baseline")


def test_unknown_mode_is_rejected_before_transport() -> None:
    with pytest.raises(ac.AcTwoPointV1Error, match="not allowlisted"):
        ac.run("baseline; false")


def test_remote_runner_is_fixed_to_sequential_work_copy_jobs() -> None:
    helper = ac.LOCAL_FILES["ac_helper.py"].read_text(encoding="ascii")
    runner = ac.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert '"baseline": ("300m", "650m", 0.300, 0.650)' in helper
    assert '"midpoint": ("310m", "676m", 0.310, 0.676)' in helper
    assert '"ac1 ac start=1k stop=10k lin=2' in helper
    assert 'os.listdir(JOB_ROOT) != ["baseline"]' in helper
    assert 'baseline_psf["sha256"] != baseline_result.get("psf_tree_sha256")' in helper
    assert 'case "$1" in baseline|midpoint)' in runner
    assert "flock -n 9" in runner
    assert runner.count('timeout 120 "$SPECTRE"') == 1
