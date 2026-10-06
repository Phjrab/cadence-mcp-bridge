"""Independent synthetic step science and fail-closed shared execution guards."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from test_native_diagnostics import remote_module

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("case", ["current", "future", "ceiling", "reset", "over-limit", "marker"])
def test_timeless_reader_keeps_historical_accounting(case: str) -> None:
    m = remote_module("slew-read-v2")
    markers = [
        {
            "campaign_id": "AUTO-PHASE-01",
            "count": 65 + i,
            "result_reserved_bytes": 7383023616 + (i + 1) * 128 * 1024**2,
        }
        for i in range(4)
    ]
    current = dict(markers[-1])
    if case == "future":
        current.update(count=69, result_reserved_bytes=8054112256)
    elif case == "ceiling":
        current.update(count=500, result_reserved_bytes=10 * 1024**3)
    elif case == "reset":
        current["count"] = 67
    elif case == "over-limit":
        current["result_reserved_bytes"] = 10 * 1024**3 + 1
    elif case == "marker":
        markers[0]["count"] = 66
    if case in ("current", "future", "ceiling"):
        m.accounting(current, markers)
    else:
        with pytest.raises(ValueError):
            m.accounting(current, markers)


@pytest.mark.parametrize("case", ["same", "future-job", "removed", "changed", "source", "active"])
def test_reader_preserves_every_old_job_and_protected_fact(case: str) -> None:
    m = remote_module("slew-read-v2")
    before = {
        "native": {"jobs": {"opaque-old": {"hash": "a" * 64}}, "active_eda": False},
        "protected": {"source_hash": "b" * 64},
    }
    now = json.loads(json.dumps(before))
    if case == "future-job":
        now["native"]["jobs"]["opaque-new"] = {"hash": "c" * 64}
    elif case == "removed":
        now["native"]["jobs"] = {}
    elif case == "changed":
        now["native"]["jobs"]["opaque-old"]["hash"] = "d" * 64
    elif case == "source":
        now["protected"]["source_hash"] = "e" * 64
    elif case == "active":
        now["native"]["active_eda"] = True
    if case in ("same", "future-job"):
        m.preserved(before, now)
    else:
        with pytest.raises(ValueError):
            m.preserved(before, now)


def frame() -> bytes:
    lines = ["BEGIN"]
    for signal in ("Vop", "Vom", "Vp", "Vm", "VDD"):
        lines.append(f"VECTOR|{signal}|1001")
        for i in range(1001):
            t = i * 1e-8
            pulse = (
                0
                if t <= 2e-6
                else min(1, (t - 2e-6) / 1e-9)
                if t < 6e-6
                else max(0, 1 - (t - 6e-6) / 1e-9)
            )
            out = (
                -0.5 + min(1, max(0, (t - 2.1e-6) / 5e-7))
                if t < 6e-6
                else (0.5 - min(1, max(0, (t - 6.1e-6) / 5e-7)))
            )
            v = {
                "Vop": 0.5 + out / 2,
                "Vom": 0.5 - out / 2,
                "Vp": 0.45 + 0.1 * pulse,
                "Vm": 0.55 - 0.1 * pulse,
                "VDD": 1,
            }[signal]
            lines.append(f"POINT|{i}|{t:.16g}|{v:.16g}")
    return ("\n".join([*lines, "END"]) + "\n").encode()


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "signal",
        "length",
        "index",
        "nan",
        "supply",
        "stimulus",
        "axis",
        "trailing",
        "framing",
    ],
)
def test_bounded_effective_step_parser(case: str) -> None:
    m = remote_module("slew-qual-v4", "analysis.py")
    text = frame().decode()
    if case == "signal":
        text = text.replace("VECTOR|Vm|1001", "VECTOR|other|1001")
    elif case == "length":
        text = text.replace("VECTOR|Vop|1001", "VECTOR|Vop|16001")
    elif case == "index":
        text = text.replace("POINT|1|", "POINT|0|", 1)
    elif case == "nan":
        text = text.replace("|0.25\n", "|nan\n", 1)
    elif case == "supply":
        text = text.replace("VECTOR|VDD|1001\nPOINT|0|0|1", "VECTOR|VDD|1001\nPOINT|0|0|0.9")
    elif case == "stimulus":
        text = text.replace("POINT|0|0|0.45", "POINT|0|0|0.44")
    elif case == "axis":
        text = text.replace("POINT|0|0|0.25", "POINT|0|1e-9|0.25", 1)
    elif case == "trailing":
        text = text.replace("END", "extra\nEND")
    elif case == "framing":
        text = text.replace("BEGIN", "OTHER")
    if case == "valid":
        r = m.parse(text.encode(), "coarse")
        assert r["transitions"][0]["status"] == "DEFINED_TRANSITION"
        assert r["transitions"][1]["status"] == "DEFINED_TRANSITION"
        assert r["transitions"][0]["rate_v_per_s"] == pytest.approx(2e6)
        assert r["transitions"][1]["rate_v_per_s"] == pytest.approx(-2e6)
        assert r["transitions"][0]["subwindow_rate_ratio"] == pytest.approx(1)
        assert not r["transitions"][0]["input_edge_overlap"]
    else:
        with pytest.raises((ValueError, IndexError)):
            m.parse(text.encode(), "coarse")


@pytest.mark.parametrize("case", ["missing", "small", "unsettled", "ringing", "coarse"])
def test_invalid_science_never_produces_a_rate(case: str) -> None:
    m = remote_module("slew-qual-v4", "analysis.py")
    dt = 1e-8 if case != "coarse" else 5e-7
    ts = [i * dt for i in range(int(6e-6 / dt) + 1)]
    vs = [min(1, max(0, (t - 2.1e-6) / 5e-7)) for t in ts]
    if case == "missing":
        ts, vs = ts[:100], vs[:100]
    elif case == "small":
        vs = [v * 0.01 for v in vs]
    elif case == "unsettled":
        vs = [
            v + (0.01 * (i % 2) if t > 4e-6 else 0)
            for i, (t, v) in enumerate(zip(ts, vs, strict=True))
        ]
    elif case == "ringing":
        vs = [1.1 if 3e-6 < t < 3.2e-6 else v for t, v in zip(ts, vs, strict=True)]
    r = m.transition(ts, vs, 2e-6, 6e-6)
    assert r["rate_v_per_s"] is None and r["status"] != "DEFINED_TRANSITION"


@pytest.mark.parametrize(
    "case", ["valid", "replay", "disk", "protected", "uncertain", "ledger-write", "order"]
)
def test_reserve_retains_uncertain_admission_and_prevents_execution(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    m = remote_module("slew-qual-v4")
    monkeypatch.setattr(m.os.path, "realpath", lambda p: p)
    m.configure("coarse")
    writes: dict[str, Any] = {}
    moves = []

    def fail() -> None:
        raise ValueError("blocked")

    monkeypatch.setattr(m, "authorization", lambda: "a" * 64)
    monkeypatch.setattr(m.B, "environment_preflight", fail if case == "disk" else lambda: None)
    monkeypatch.setattr(m, "verify", fail if case == "protected" else lambda: None)
    monkeypatch.setattr(
        m,
        "counter",
        fail
        if case == "uncertain"
        else lambda: {
            "campaign_id": "AUTO-PHASE-01",
            "count": 65 if case == "order" else 64,
            "result_reserved_bytes": 7383023616,
        },
    )
    monkeypatch.setattr(m.os.path, "lexists", lambda p: case == "replay")

    def save(p: str, data: Any) -> None:
        if case == "ledger-write" and p.endswith(".ade-tmp"):
            raise OSError("interrupted")
        writes[p] = dict(data)

    monkeypatch.setattr(m.B, "save", save)
    monkeypatch.setattr(m.os, "rename", lambda a, b: moves.append((a, b)))
    if case == "valid":
        m.reserve()
        assert writes[m.JOB + "/attempt-reserved"]["count"] == 65
        assert writes[m.JOB + "/attempt-reserved"]["result_reserved_bytes"] == 7517241344
        assert len(moves) == 1
    else:
        with pytest.raises((ValueError, OSError)):
            m.reserve()
        assert not moves
        assert bool(writes) == (case == "ledger-write")


@pytest.mark.parametrize("case", ["../fine", "/private", "fine;echo", "5", "FINE"])
def test_opaque_case_rejection(case: str) -> None:
    with pytest.raises(ValueError):
        remote_module("slew-qual-v4").configure(case)


def test_symlink_and_effective_input_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    m = remote_module("slew-qual-v4")
    monkeypatch.setattr(m.os.path, "realpath", lambda p: "/outside")
    with pytest.raises(ValueError):
        m.configure("fine")


@pytest.mark.parametrize("case", ["valid", "missing", "policy", "delegate", "file"])
def test_operator_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "slew_operator_test", ROOT / "scripts/slew_qualification.py"
    )
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m.campaign, "_load_authority", lambda: "a" * 64)
    monkeypatch.setattr(m, "POLICY", tmp_path / "p.json")
    monkeypatch.setattr(m, "DELEGATION", tmp_path / "d.json")
    p = m.expected_policy("a" * 64)
    digest = m.hashlib.sha256(m.campaign._canonical(p)).hexdigest()
    d = m.activation(digest)
    if case == "policy":
        p["new_attempt_ceiling"] = 100
    elif case == "delegate":
        d["policy_sha256"] = "0" * 64
    elif case == "file":
        p["files"]["analysis.py"] = "0" * 64
        d = m.activation(m.hashlib.sha256(m.campaign._canonical(p)).hexdigest())
    m.POLICY.write_text(json.dumps(p))
    if case != "missing":
        m.DELEGATION.write_text(json.dumps(d))
    if case == "valid":
        assert m.authority() == digest
    else:
        with pytest.raises((ValueError, m.campaign.CampaignError)):
            m.authority()
