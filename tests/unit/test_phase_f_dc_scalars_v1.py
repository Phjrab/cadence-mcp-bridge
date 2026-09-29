"""Read-only scalar extraction is bound to both completed copied-cell DC jobs."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
scalars_v1 = importlib.import_module("phase_f_dc_scalars_v1")


def test_scalar_policy_pins_both_results_and_exact_files() -> None:
    policy = json.loads(scalars_v1.POLICY.read_text(encoding="utf-8"))
    old = json.loads(scalars_v1.dc_v2.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == scalars_v1._sha(scalars_v1.v1._canonical(old))
    assert policy["dc_v2_files"] == old["files"]
    assert policy["baseline_result_sha256"] == scalars_v1.RESULT_HASHES["baseline"]
    assert policy["candidate_result_sha256"] == scalars_v1.RESULT_HASHES["candidate"]
    assert policy["psf_tree_sha256"] == scalars_v1.PSF_HASHES
    for name, path in scalars_v1.LOCAL_FILES.items():
        assert scalars_v1._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_scalar_authority_requires_two_completed_dc_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = json.loads(scalars_v1.dc_v2.POLICY.read_text(encoding="utf-8"))
    base = json.loads(scalars_v1.v1.POLICY.read_text(encoding="utf-8"))
    digest = scalars_v1._sha(scalars_v1.v1._canonical(old))
    monkeypatch.setattr(scalars_v1.dc_v2, "_authority", lambda: (old, digest, tmp_path, base, "v1"))
    monkeypatch.setattr(scalars_v1.dc_v2, "_counter", lambda _root: 2)
    monkeypatch.setattr(scalars_v1.parent, "_read_json", lambda _path: {"state": "reserved"})
    with pytest.raises(scalars_v1.DcScalarsV1Error, match="result not verified"):
        scalars_v1._authority()


def test_ocean_reads_only_existing_psf_and_parser_checks_constraints() -> None:
    script = scalars_v1.LOCAL_FILES["extract.ocn"].read_text(encoding="ascii")
    helper = scalars_v1.LOCAL_FILES["scalar_helper.py"].read_text(encoding="ascii")
    runner = scalars_v1.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert 'foreach(mode list("baseline" "candidate")' in script
    assert "openResults(path)" in script
    assert "selectResult('dc)" in script
    assert "createNetlist" not in script
    assert "run()" not in script
    assert "drGetWaveformYVec(data)" in script
    assert 'abs(values[mode]["VDD"] - 1.0) > 1e-6' in helper
    assert 'abs(values[mode]["Vp"] - 0.5) > 1e-6' in helper
    assert '"simulation_run": False' in helper
    assert "flock -n 9" in runner
