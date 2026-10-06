"""Fixed grid parser, policy activation, disk/protection gates and durable budget admission."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from test_native_diagnostics import remote_module

ROOT = Path(__file__).resolve().parents[2]


def frame(m: Any) -> bytes:
    lines = ["BEGIN"]
    for signal in ("Vop", "Vom", "Vp", "Vm"):
        lines.append("VECTOR|" + signal + "|251")
        for index in range(251):
            f = 10 ** (1 + index / 50)
            v = {"Vop": 2, "Vom": -2, "Vp": 0.5, "Vm": -0.5}[signal]
            lines.append("POINT|" + str(index) + "|" + repr(f) + "|" + str(v) + "|0")
    return ("\n".join([*lines, "END"]) + "\n").encode("ascii")


@pytest.mark.parametrize(
    "case",
    ["valid", "missing", "trailing", "unordered", "identity", "axis", "nan", "stimulus", "length"],
)
def test_closed_frame_and_effective_input(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    m = remote_module("bandwidth-qual-v1")
    monkeypatch.setattr(m.os.path, "realpath", lambda p: p)
    m.configure("50")
    text = frame(m).decode()
    if case == "missing":
        text = text.replace("VECTOR|Vm|251", "VECTOR|Other|251")
    if case == "trailing":
        text = text.replace("END", "extra\nEND")
    if case == "unordered":
        text = text.replace("POINT|1|", "POINT|0|", 1)
    if case == "identity":
        text = text.replace("BEGIN", "bad")
    if case == "axis":
        text = text.replace("POINT|0|10.0|", "POINT|0|20.0|", 1)
    if case == "nan":
        text = text.replace("|2|0", "|nan|0", 1)
    if case == "stimulus":
        text = text.replace("|0.5|0", "|0.4|0", 1)
    if case == "length":
        text = text.replace("VECTOR|Vop|251", "VECTOR|Vop|99999")
    if case == "valid":
        p = m.parse_frame(text.encode())
        assert len(p) == 251 and p[0]["gain_db"] > 0
    else:
        with pytest.raises((ValueError, IndexError)):
            m.parse_frame(text.encode())


@pytest.mark.parametrize(
    "count, reserved, read_only, valid",
    [
        (62, 7114588160, False, True),
        (499, 10 * 1024**3 - 128 * 1024**2, False, True),
        (500, 10 * 1024**3, False, False),
        (500, 10 * 1024**3, True, True),
        (501, 7114588160, True, False),
        (62, 10 * 1024**3 + 1, True, False),
        (True, 7114588160, True, False),
        (62, True, True, False),
    ],
)
def test_cumulative_limits_and_exhausted_reads(
    monkeypatch: pytest.MonkeyPatch, count: int, reserved: int, read_only: bool, valid: bool
) -> None:
    m = remote_module("bandwidth-qual-v1")
    monkeypatch.setattr(m.os.path, "realpath", lambda p: p)
    data = {"campaign_id": "AUTO-PHASE-01", "count": count, "result_reserved_bytes": reserved}
    monkeypatch.setattr(m.B, "read", lambda *args: json.dumps(data).encode())
    monkeypatch.setattr(
        m.N,
        "authorization",
        lambda: {"max_spectre_attempts": 500, "max_new_results_bytes": 10 * 1024**3},
    )
    monkeypatch.setattr(m.N, "audit_reservations", lambda *args: None)
    monkeypatch.setattr(m.os.path, "lexists", lambda *args: False)
    if valid:
        assert m.counter(read_only) == data
    else:
        with pytest.raises(ValueError):
            m.counter(read_only)


@pytest.mark.parametrize(
    "case", ["valid", "replay", "disk", "protected", "uncertain", "ledger-write"]
)
def test_reservation_fails_before_simulation_and_keeps_uncertain_intent(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    m = remote_module("bandwidth-qual-v1")
    monkeypatch.setattr(m.os.path, "realpath", lambda p: p)
    m.configure("50")
    original = {"campaign_id": "AUTO-PHASE-01", "count": 62, "result_reserved_bytes": 7114588160}
    writes: dict[str, Any] = {}
    moves = []

    def fail() -> None:
        raise ValueError("blocked")

    monkeypatch.setattr(m, "authorization", lambda: "a" * 64)
    monkeypatch.setattr(m.B, "environment_preflight", fail if case == "disk" else lambda: None)
    monkeypatch.setattr(m, "verify", fail if case == "protected" else lambda: {})
    monkeypatch.setattr(m, "counter", fail if case == "uncertain" else lambda: dict(original))
    monkeypatch.setattr(m.os.path, "lexists", lambda p: case == "replay")

    def save(p: str, data: Any) -> None:
        if case == "ledger-write" and p.endswith(".ade-tmp"):
            raise OSError("write interrupted")
        writes[p] = dict(data)

    monkeypatch.setattr(m.B, "save", save)
    monkeypatch.setattr(m.os, "rename", lambda a, b: moves.append((a, b)))
    if case == "valid":
        m.reserve()
        assert writes[m.B.COUNTER + ".ade-tmp"]["count"] == 63
        assert (
            writes[m.B.COUNTER + ".ade-tmp"]["result_reserved_bytes"]
            == original["result_reserved_bytes"] + 128 * 1024**2
        )
        assert moves == [(m.B.COUNTER + ".ade-tmp", m.B.COUNTER)]
    else:
        with pytest.raises((ValueError, OSError)):
            m.reserve()
        assert not moves
        assert bool(writes) == (case == "ledger-write")
        if writes:
            assert m.JOB + "/attempt-reserved" in writes


@pytest.mark.parametrize("grid", ["10", "51", "../50", "/private", "50;echo", "050"])
def test_grid_and_path_rejection(grid: str) -> None:
    with pytest.raises(ValueError):
        remote_module("bandwidth-qual-v1").configure(grid)


def test_symlink_or_parent_escape_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    m = remote_module("bandwidth-qual-v1")
    monkeypatch.setattr(m.os.path, "realpath", lambda p: "/outside")
    with pytest.raises(ValueError):
        m.configure("50")


def test_runtime_is_fixed_and_shared_guarded() -> None:
    script = (ROOT / "remote/phase-campaign/bandwidth-qual-v1/run.sh").read_text()
    assert "flock -n 9" in script and '[[ "$2" = 50 || "$2" = 100 ]]' in script
    assert "timeout 120" in script and "timeout 90" in script and "ulimit -f" in script
    assert 'helper.py" reserve' in script and script.index('helper.py" reserve') < script.index(
        "tools/bin/spectre"
    )
    assert "sha256sum -c manifest.sha256" in script and "rm " not in script


@pytest.mark.parametrize(
    "case", ["valid", "missing", "changed-policy", "changed-delegation", "changed-file"]
)
def test_operator_authority_is_bound_to_current_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "bw_operator_test", ROOT / "scripts/bandwidth_qualification.py"
    )
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    parent = "a" * 64
    monkeypatch.setattr(m.campaign, "_load_authority", lambda: parent)
    monkeypatch.setattr(m, "POLICY", tmp_path / "policy.json")
    monkeypatch.setattr(m, "DELEGATION", tmp_path / "delegation.json")
    policy = m.expected_policy(parent)
    digest = m.hashlib.sha256(m.campaign._canonical(policy)).hexdigest()
    delegate = m.activation(digest)
    if case == "changed-policy":
        policy["new_attempt_ceiling"] = 999
    if case == "changed-delegation":
        delegate["policy_sha256"] = "0" * 64
    if case == "changed-file":
        policy["files"]["helper.py"] = "0" * 64
        delegate = m.activation(m.hashlib.sha256(m.campaign._canonical(policy)).hexdigest())
    m.POLICY.write_text(json.dumps(policy))
    if case != "missing":
        m.DELEGATION.write_text(json.dumps(delegate))
    if case == "valid":
        assert m.authority() == digest
    else:
        with pytest.raises((ValueError, m.campaign.CampaignError)):
            m.authority()
