"""Fixed copied-netlist DC jobs preserve the source and cumulative limits."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
dc_v1 = importlib.import_module("phase_e_copied_dc_v1")


def test_dc_policy_pins_netlist_and_fixed_modes() -> None:
    policy = json.loads(dc_v1.POLICY.read_text(encoding="utf-8"))
    old = json.loads(dc_v1.netlist.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == dc_v1._sha(dc_v1.v1._canonical(old))
    assert policy["netlist_files"] == old["files"]
    assert policy["netlist_result_sha256"] == dc_v1.NETLIST_RESULT_SHA256
    assert policy["baseline_bias_mv"] == [300, 650]
    assert policy["candidate_bias_mv"] == [320, 702]
    assert policy["vdd_mv"] == 1000
    assert policy["operation_ids"] == list(dc_v1.OPERATIONS.values())
    for name, path in dc_v1.LOCAL_FILES.items():
        assert dc_v1._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_attempt_budget_counts_before_execution(tmp_path: Path) -> None:
    dc_v1._increment_attempts(tmp_path)
    dc_v1._increment_attempts(tmp_path)
    path = tmp_path / "phasee-copied-dc-v1-spectre-attempts.json"
    assert json.loads(path.read_text(encoding="utf-8"))["count"] == 2
    path.write_text(json.dumps({"campaign_id": "AUTO-PHASE-01", "count": 100}), encoding="utf-8")
    with pytest.raises(dc_v1.CopiedDcV1Error, match="100 Spectre attempts"):
        dc_v1._increment_attempts(tmp_path)


def test_candidate_requires_completed_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = json.loads(dc_v1.POLICY.read_text(encoding="utf-8"))
    base = json.loads(dc_v1.v1.POLICY.read_text(encoding="utf-8"))
    monkeypatch.setattr(dc_v1, "_authority", lambda: (policy, "digest", tmp_path, base))

    def fake_read(path: Path) -> dict[str, str]:
        if path.name == "phasee-copied-dc-v1-deploy.json":
            return {"state": "succeeded", "policy_sha256": "digest"}
        return {"state": "reserved", "policy_sha256": "digest"}

    monkeypatch.setattr(dc_v1.parent, "_read_json", fake_read)
    with pytest.raises(dc_v1.CopiedDcV1Error, match="baseline DC not completed"):
        dc_v1.run("candidate")


def test_remote_job_is_fixed_and_job_local() -> None:
    helper = dc_v1.LOCAL_FILES["dc_helper.py"].read_text(encoding="ascii")
    runner = dc_v1.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert 'MODES = {"baseline": ("300m", "650m"), "candidate": ("320m", "702m")}' in helper
    assert '"V0 (VDD 0) vsource dc=1 type=dc"' in helper
    assert '"V1 (Vp 0) vsource dc=500m"' in helper
    assert '"V2 (Vm 0) vsource dc=500m"' in helper
    assert '"dc1 dc\\n"' in helper
    assert '"save Vop Vom VDD Vp Vm\\n"' in helper
    assert 'write_file(job + "/design-netlist.scs"' in helper
    assert "flock -n 9" in runner
    assert "timeout 120" in runner
    assert "-format psfbin -raw psf" in runner
