"""Recovery validates one consumed OCEAN attempt without invoking EDA again."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
recovery = importlib.import_module("phase_d_netlist_recover_v1")


def test_recovery_policy_pins_observed_artifacts() -> None:
    policy = json.loads(recovery.POLICY.read_text(encoding="utf-8"))
    prior = json.loads(recovery.phase.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == recovery._sha(recovery.v1._canonical(prior))
    assert policy["operation"] == recovery.phase.OPERATIONS["netlist"]
    assert len(policy["ocean_log_sha256"]) == 64
    assert len(policy["circuit_netlist_sha256"]) == 64


def test_recovery_requires_reserved_original_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = json.loads(recovery.phase.POLICY.read_text(encoding="utf-8"))
    base = json.loads(recovery.v1.POLICY.read_text(encoding="utf-8"))
    digest = recovery._sha(recovery.v1._canonical(old))
    monkeypatch.setattr(recovery.phase, "_authority", lambda: (old, digest, tmp_path, base))

    def fake_read(path: Path) -> dict[str, str]:
        if path.name == "phased-netlist-v1-deploy.json":
            return {"state": "succeeded", "policy_sha256": digest}
        return {"state": "succeeded", "policy_sha256": digest}

    monkeypatch.setattr(recovery.parent, "_read_json", fake_read)
    with pytest.raises(recovery.NetlistRecoveryError, match="consumed netlist record changed"):
        recovery._authority()


def test_recovery_only_reads_fixed_evidence_and_preserves_no_simulation() -> None:
    operator = (ROOT / "scripts/phase_d_netlist_recover_v1.py").read_text(encoding="utf-8")
    assert "ocean_exit=0\\nparser_exit=69\\n" in operator
    assert 'log.count(b"MCP_WP14_COPIED_NETLIST|true") != 1' in operator
    assert '"simulation_run": False' in operator
    assert 'v1._ssh("cat " + NETLIST)' in operator
    assert 'phase.REMOTE_VERSION + "/run.sh"' not in operator
