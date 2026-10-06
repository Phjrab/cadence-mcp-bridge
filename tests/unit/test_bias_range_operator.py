"""Synthetic grid extraction/admission rejection; no physical qualification."""

import json
import os
from typing import Any

import pytest
from test_native_diagnostics import remote_module


@pytest.fixture(autouse=True)
def posix_paths(monkeypatch: Any) -> None:
    monkeypatch.setattr(os.path, "realpath", lambda p: p)


def dc_frame(value: float) -> bytes:
    rows = ["BEGIN"]
    rows += [f"NODE|{n}|{v}" for n, v in (
        ("Vop", 0.227), ("Vom", 0.227), ("Vp", 0.5), ("Vm", 0.5),
        ("VDD", 1), ("Vbiasn", value), ("Vbiasp", 0.702),
    )]
    rows += [f"SOURCE|{n}|{v}|{i}" for n, v, i in (
        ("vdd", 1, -0.002), ("vss", 0, 0.002), ("bias-n", value, 0),
        ("bias-p", 0.702, 0), ("input-p", 0.5, 0), ("input-m", 0.5, 0),
    )]
    return "\n".join([*rows, "END"]).encode()


@pytest.mark.parametrize("case", ["lowerdc", "lowerac", "upperdc", "upperac"])
def test_fixed_case_binding(case: str) -> None:
    m = remote_module("bias-range-qual-v1")
    m.configure(case)
    assert case[-2:] == m.MODE
    assert ("319m" if case.startswith("lower") else "321m") == m.VALUE
    if m.MODE == "dc":
        r = m.parse(dc_frame(float(m.VALUE[:-1]) * 0.001))
        assert len(r["sources"]) == 6 and r["scalars"]["VDD"] == 1


@pytest.mark.parametrize("bad", ["../other", "lowertran", "center", "", "/tmp/x"])
def test_unknown_case_denied(bad: str) -> None:
    with pytest.raises(ValueError):
        remote_module("bias-range-qual-v1").configure(bad)


@pytest.mark.parametrize("old,new", [
    ("NODE|VDD|1", "NODE|VDD|0.9"),
    ("NODE|Vm|0.5", "NODE|Vm|0.51"),
    ("NODE|Vbiasn|0.319", "NODE|Vbiasn|0.321"),
    ("NODE|Vbiasp|0.702", "NODE|Vbiasp|0.65"),
    ("NODE|Vop|0.227", "NODE|Vop|nan"),
    ("NODE|Vop|0.227", "NODE|Vop|inf"),
    ("SOURCE|vdd|1|-0.002", "SOURCE|vdd|1|nil"),
    ("SOURCE|vdd|1|-0.002", "SOURCE|vdd|1|nan"),
    ("SOURCE|vdd|1|-0.002", "SOURCE|vdd|1.1|-0.002"),
    ("SOURCE|vss", "SOURCE|vdd"),
    ("END", "END\nEXTRA"),
])
def test_nonfinite_effective_and_incomplete_inventory_denied(old: str, new: str) -> None:
    m = remote_module("bias-range-qual-v1")
    m.configure("lowerdc")
    with pytest.raises(ValueError):
        m.parse(dc_frame(0.319).replace(old.encode(), new.encode()))


@pytest.mark.parametrize("change", ["valid", "gap", "marker", "unaccounted", "reset"])
def test_exact_ordered_ledger(monkeypatch: Any, change: str) -> None:
    m = remote_module("bias-range-qual-v1")
    markers = {m.RUNTIME + "/" + case + "/attempt-reserved": {
        "campaign_id": "AUTO-PHASE-01", "count": 73 + i,
        "result_reserved_bytes": 8456765440 + (i + 1) * 128 * 1024**2,
    } for i, case in enumerate(m.CASES[:2])}
    current = dict(markers[m.RUNTIME + "/lowerac/attempt-reserved"])
    if change == "gap":
        del markers[m.RUNTIME + "/lowerdc/attempt-reserved"]
    elif change == "marker":
        markers[m.RUNTIME + "/lowerdc/attempt-reserved"]["count"] = 72
    elif change == "unaccounted":
        current["count"] += 1
    elif change == "reset":
        current["result_reserved_bytes"] = 0
    monkeypatch.setattr(m.W, "counter", lambda readonly: current)
    monkeypatch.setattr(m.os.path, "lexists", lambda p: p in markers)
    monkeypatch.setattr(m.B, "read", lambda p, *args: json.dumps(markers[p]).encode())
    if change == "valid":
        assert m.counter() == current
    else:
        with pytest.raises(ValueError):
            m.counter()


def test_no_follow_containment(monkeypatch: Any) -> None:
    m = remote_module("bias-range-qual-v1")
    monkeypatch.setattr(m.os.path, "realpath", lambda p: "/outside")
    with pytest.raises(ValueError, match="containment"):
        m.configure("upperdc")


@pytest.mark.parametrize("change", ["admission", "protected", "input", "valid"])
def test_receipt_source_binding(monkeypatch: Any, change: str) -> None:
    m = remote_module("bias-range-qual-v1")
    m.configure("lowerdc")
    digest = "a" * 64
    original = b"synthetic VBIASN=320m rest"
    m.SOURCES["dc"] = ("opaque", m.B.sha(original), "b" * 64)
    admission = {"case": "lowerdc", "source_job_id": "opaque", "policy_sha256": digest}
    before = {"protected": {"offset": "old"}, "counter": {
        "campaign_id": "AUTO-PHASE-01", "count": 72, "result_reserved_bytes": 8456765440,
    }}
    effective = original.replace(b"320m", b"319m")
    if change == "admission":
        admission["case"] = "upperdc"
    if change == "input":
        effective += b" extra"
    def read(path: str, *args: Any) -> bytes:
        if path.endswith("admission.json"):
            return json.dumps(admission).encode()
        if path.endswith("before.json"):
            return json.dumps(before).encode()
        return effective
    monkeypatch.setattr(m, "authorization", lambda: digest)
    monkeypatch.setattr(m, "protected", lambda: {"offset": "changed" if
                                               change == "protected" else "old"})
    monkeypatch.setattr(m.B, "read", read)
    monkeypatch.setattr(m, "source", lambda: {})
    if change == "valid":
        m.verify()
    else:
        with pytest.raises(ValueError):
            m.verify()


def test_existing_ac_scientific_parser_reused(monkeypatch: Any) -> None:
    m = remote_module("bias-range-qual-v1")
    m.configure("lowerac")
    with pytest.raises(ValueError):
        m.parse(b"BEGIN\nAC|fake|60\nEND")


def test_replay_or_environment_failure_precedes_copy(monkeypatch: Any) -> None:
    m = remote_module("bias-range-qual-v1")
    m.configure("lowerdc")
    monkeypatch.setattr(m, "authorization", lambda: "a" * 64)
    def fail() -> None:
        raise ValueError("disk/active preflight")
    monkeypatch.setattr(m.B, "environment_preflight", fail)
    with pytest.raises(ValueError, match="preflight"):
        m.begin()
    monkeypatch.setattr(m.B, "environment_preflight", lambda: None)
    monkeypatch.setattr(m, "counter", lambda submit: {"count": 73})
    with pytest.raises(ValueError, match="replay/order"):
        m.begin()
