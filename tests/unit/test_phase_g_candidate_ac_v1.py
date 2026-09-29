"""The candidate AC diagnostic stays bound to observed DC and copied netlist."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
ac_v1 = importlib.import_module("phase_g_candidate_ac_v1")


def test_policy_pins_candidate_dc_and_single_ac_setup() -> None:
    policy = json.loads(ac_v1.POLICY.read_text(encoding="utf-8"))
    parent = json.loads(ac_v1.dc_v2.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == ac_v1._sha(ac_v1.v1._canonical(parent))
    assert policy["candidate_dc_result_sha256"] == ac_v1.scalars.RESULT_HASHES["candidate"]
    assert policy["scalar_result_sha256"] == ac_v1.SCALAR_RESULT_SHA256
    assert policy["candidate_bias_mv"] == [320, 702]
    assert policy["vdd_mv"] == 1000
    assert policy["frequencies_hz"] == [1000, 10000]
    assert policy["spectre_attempt_count_before"] == 2
    for name, path in ac_v1.LOCAL_FILES.items():
        assert ac_v1._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_authority_rejects_missing_scalar_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = json.loads(ac_v1.dc_v2.POLICY.read_text(encoding="utf-8"))
    base = json.loads(ac_v1.v1.POLICY.read_text(encoding="utf-8"))
    digest = ac_v1._sha(ac_v1.v1._canonical(old))
    monkeypatch.setattr(ac_v1.dc_v2, "_authority", lambda: (old, digest, tmp_path, base, "v1"))
    monkeypatch.setattr(ac_v1.dc_v2, "_counter", lambda _root: 2)
    monkeypatch.setattr(ac_v1.parent, "_read_json", lambda _path: {"state": "reserved"})
    with pytest.raises(ac_v1.CandidateAcV1Error, match="scalar result changed"):
        ac_v1._authority()


def test_remote_job_uses_fixed_netlist_and_one_spectre_attempt() -> None:
    helper = ac_v1.LOCAL_FILES["ac_helper.py"].read_text(encoding="ascii")
    runner = ac_v1.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert "circuit.count(line) != 1" in helper
    assert '"parameters VBIASN=320m VBIASP=702m' in helper
    assert '"ac1 ac start=1k stop=10k lin=2' in helper
    assert 'write_file(JOB + "/design-netlist.scs", circuit)' in helper
    assert "flock -n 9" in runner
    assert runner.count('timeout 120 "$SPECTRE"') == 1
    assert '"status": status' in helper
