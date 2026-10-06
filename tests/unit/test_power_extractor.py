"""Closed remote inventory/size/protection and immutable operator admission."""

import json
from pathlib import Path
from typing import Any

import pytest
from test_native_diagnostics import remote_module


def extractor(monkeypatch: pytest.MonkeyPatch) -> Any:
    module = remote_module("analog-power-v1")
    monkeypatch.setattr(module.N.N, "configure", lambda *args: None)
    monkeypatch.setattr(module.B, "environment_preflight", lambda: None)
    monkeypatch.setattr(module.B, "verify_netlist", lambda: {"input_sha256": module.INPUT_SHA})
    monkeypatch.setattr(module.B, "snapshot", lambda: {"protected": "unchanged"})
    module.B.JOB = "/managed/source/work"
    module.B.NETDIR = module.B.JOB + "/net"
    monkeypatch.setattr(
        module.N.N.CAND,
        "tree",
        lambda p: {
            "sha256": module.PSF_SHA if p.endswith("/psf") else "a" * 64,
            "total_bytes": 1234,
        },
    )
    monkeypatch.setattr(module.N, "authorization", lambda: {})
    monkeypatch.setattr(module.N, "validate_counter", lambda *args: None)
    return module


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "extra",
        "duplicate",
        "missing",
        "negative-node",
        "source-too-large",
        "psf-drift",
        "input-drift",
    ],
)
def test_fixed_source_inventory_and_reserved_capacity_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    m = extractor(monkeypatch)
    # Minimal synthetic parser data; no vendor models or private circuit fixture.
    lines = [f"{instance} ({node} 0) vsource dc=1 type=dc" for _, instance, node, _, _ in m.SOURCES]
    if case == "extra":
        lines.append("V9 (other 0) vsource dc=1 type=dc")
    if case == "duplicate":
        lines.append(lines[0])
    if case == "missing":
        lines.pop()
    if case == "negative-node":
        lines[0] = lines[0].replace(" 0)", " other)")
    if case == "source-too-large":
        monkeypatch.setattr(
            m.N.N.CAND, "tree", lambda p: {"sha256": m.PSF_SHA, "total_bytes": 128 * 1024**2}
        )
    if case == "psf-drift":
        monkeypatch.setattr(m.N.N.CAND, "tree", lambda p: {"sha256": "0" * 64, "total_bytes": 0})
    if case == "input-drift":
        monkeypatch.setattr(m.B, "verify_netlist", lambda: {"input_sha256": "0" * 64})
    monkeypatch.setattr(
        m.B,
        "read",
        lambda p, *args: (
            "\n".join(lines).encode("ascii")
            if p.endswith("/netlist")
            else json.dumps({"count": 62}).encode("ascii")
        ),
    )
    if case == "valid":
        assert m.snapshot()["source"]["total_bytes"] == 1234
    else:
        with pytest.raises(ValueError):
            m.snapshot()


def test_remote_script_has_no_simulator_or_caller_parameters() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "remote/phase-campaign/analog-power-v1/run.sh").read_text()
    assert 'case "$1" in read|result)' in script and "flock -n 9" in script
    assert "timeout 90" in script and "ulimit -f 2048" in script
    assert '"$2"' not in script and " -raw " not in script
    assert "rm " not in script and " -restore " in script


@pytest.mark.parametrize(
    "count, reserved, valid",
    [
        (62, 7114588160, True),
        (500, 10 * 1024**3, True),
        (501, 7114588160, False),
        (500, 10 * 1024**3 + 1, False),
        (True, 7114588160, False),
        (62, True, False),
    ],
)
def test_read_counter_allows_valid_exhausted_budget_without_reserving(
    count: int,
    reserved: int,
    valid: bool,
) -> None:
    m = remote_module("analog-power-v2")
    counter = {"campaign_id": "AUTO-PHASE-01", "count": count, "result_reserved_bytes": reserved}
    policy = {"max_spectre_attempts": 500, "max_new_results_bytes": 10 * 1024**3}
    before = json.dumps(counter)
    if valid:
        m.validate_read_counter(counter, policy)
    else:
        with pytest.raises(ValueError):
            m.validate_read_counter(counter, policy)
    assert json.dumps(counter) == before
