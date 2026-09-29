"""The copied-cell netlist probe is fixed, private, and once only."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
netlist_v1 = importlib.import_module("phase_d_netlist_v1")


def test_policy_pins_copy_evidence_and_exact_files() -> None:
    policy = json.loads(netlist_v1.POLICY.read_text(encoding="utf-8"))
    prior = json.loads(netlist_v1.prior.POLICY.read_text(encoding="utf-8"))
    assert policy["parent_policy_sha256"] == netlist_v1._sha(netlist_v1.v1._canonical(prior))
    assert policy["copy_files"] == prior["files"]
    assert policy["copy_result_sha256"] == netlist_v1.COPY_RESULT_SHA256
    assert policy["copy_target_sha256"] == netlist_v1.TARGET_SHA256
    assert policy["operation_ids"] == list(netlist_v1.OPERATIONS.values())
    for name, path in netlist_v1.LOCAL_FILES.items():
        assert not path.is_symlink()
        assert netlist_v1._sha(path.read_bytes()) == policy["files"][name]
        assert b"\r" not in path.read_bytes()


def test_netlist_reservation_is_once_only(tmp_path: Path) -> None:
    record = netlist_v1._reserve(tmp_path, "netlist", "digest")
    assert record.name == "phased-netlist-v1-run.json"
    with pytest.raises(netlist_v1.NetlistV1Error, match="already reserved"):
        netlist_v1._reserve(tmp_path, "netlist", "digest")


def test_netlist_requires_successful_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = json.loads(netlist_v1.prior.POLICY.read_text(encoding="utf-8"))
    base = json.loads(netlist_v1.v1.POLICY.read_text(encoding="utf-8"))
    digest = netlist_v1._sha(netlist_v1.v1._canonical(old))
    monkeypatch.setattr(netlist_v1.prior, "_authority", lambda: (old, digest, tmp_path, base))

    def fake_read(path: Path) -> dict[str, str]:
        if path.name == "phasec-copy-v1-deploy.json":
            return {"state": "succeeded", "policy_sha256": digest}
        return {"state": "reserved", "policy_sha256": digest}

    monkeypatch.setattr(netlist_v1.parent, "_read_json", fake_read)
    with pytest.raises(netlist_v1.NetlistV1Error, match="one-shot copy evidence absent"):
        netlist_v1._authority()


def test_ocean_is_read_only_copy_with_managed_project() -> None:
    script = netlist_v1.LOCAL_FILES["copied-netlist.ocn"].read_text(encoding="ascii")
    helper = netlist_v1.LOCAL_FILES["netlist_helper.py"].read_text(encoding="ascii")
    runner = netlist_v1.LOCAL_FILES["run.sh"].read_text(encoding="ascii")
    assert script.index('envSetVal("asimenv.startup" "projectDir"') < script.index(
        "simulator('spectre)"
    )
    assert 'design("MCP_WorkLib" "WP14_AUTO_PHASE_01_TB2" "schematic" "r")' in script
    assert "createNetlist(?recreateAll t ?display nil)" in script
    assert "run()" not in script
    assert "TARGET_SHA256" in helper
    assert "os.path.lexists(DEFAULT_OUTPUT)" in helper
    assert '"simulation_run": False' in helper
    assert '"${component_status[0]}" -eq 0' in runner
    assert "timeout 180" in runner
