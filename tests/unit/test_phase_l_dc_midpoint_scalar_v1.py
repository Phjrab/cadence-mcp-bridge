"""The midpoint scalar reader is pinned to the completed fourth Spectre result."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
scalar = importlib.import_module("phase_l_dc_midpoint_scalar_v1")


def test_policy_pins_completed_midpoint_and_no_simulation() -> None:
    policy = json.loads(scalar.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == scalar.MIDPOINT_POLICY_SHA256
    assert policy["midpoint_result_sha256"] == scalar.MIDPOINT_RESULT_SHA256
    assert policy["prior_scalar_result_sha256"] == scalar.PRIOR_SCALARS_SHA256
    assert policy["psf_tree_sha256"] == scalar.PSF_SHA256
    assert policy["psf_bytes"] == 3971
    assert policy["spectre_attempt_count"] == 4
    assert policy["new_simulation"] is False
    for name, path in scalar.LOCAL_FILES.items():
        assert scalar._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_authority_rejects_counter_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = json.loads(scalar.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(scalar.v1, "_authority", lambda: (base, "base", tmp_path))
    monkeypatch.setattr(scalar.dc_v2, "_counter", lambda _root: 5)
    with pytest.raises(scalar.DcMidpointScalarV1Error, match="Spectre count changed"):
        scalar._authority()


def test_remote_script_reads_one_existing_psf() -> None:
    helper = scalar.LOCAL_FILES["scalar_helper.py"].read_text(encoding="ascii")
    runner = scalar.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    ocean = scalar.LOCAL_FILES["extract.ocn"].read_text(encoding="ascii")
    assert 'ROOT + "/wp14-dc-midpoint-v1/psf"' in helper
    assert helper.count("PSF_SHA256") >= 2
    assert "len(lines) != 6" in helper
    assert 'abs(values["VDD"] - 1.0)' in helper
    assert 'abs(values["Vp"] - 0.5)' in helper
    assert "MCP_DC_MIDPOINT_SCALAR_COMPLETE|true" in ocean
    assert ocean.count("openResults(resultPath)") == 1
    assert "flock -n 9" in runner
    assert runner.count('timeout 90 "$OCEAN"') == 1
    assert "spectre" not in runner.lower()
