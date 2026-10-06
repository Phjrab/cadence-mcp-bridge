"""Synthetic checks of fixed DC input, reservation identity and rejection guards."""

import json
import os
from typing import Any

import pytest
from test_native_diagnostics import remote_module


@pytest.fixture(autouse=True)
def posix_paths(monkeypatch: Any) -> None:
    # The guest is POSIX. Windows host path resolution is not its filesystem.
    monkeypatch.setattr(os.path, "realpath", lambda p: p)


@pytest.mark.parametrize("case", ["zero", "minus1", "plus1", "minus05", "plus05"])
def test_fixed_effective_dc_points(case: str) -> None:
    m = remote_module("offset-qual-v1")
    m.configure(case)
    vp, vm, _ = m.VALUES[case]
    lines = ["BEGIN", "Vop|0.227", "Vom|0.227"]
    lines += [f"Vp|{float(vp[:-1]) * 0.001:.16g}", f"Vm|{float(vm[:-1]) * 0.001:.16g}"]
    lines += ["VDD|1", "END"]
    assert m.parse("\n".join(lines).encode())["VDD"] == 1
    for invalid in ("VDD|0.9", "VDD|nan", "VDD|inf", "Vm|0.51"):
        altered = list(lines)
        altered[-2 if invalid.startswith("VDD") else -3] = invalid
        with pytest.raises(ValueError):
            m.parse("\n".join(altered).encode())
    with pytest.raises(ValueError):
        m.parse("\n".join([*lines, "Vop|0.1"]).encode())


def test_unknown_case_and_zero_reservation_denied() -> None:
    m = remote_module("offset-qual-v1")
    with pytest.raises(ValueError):
        m.configure("../other")
    m.configure("zero")
    with pytest.raises(ValueError, match="existing"):
        m.reserve()


def test_symlink_escape_still_denied(monkeypatch: Any) -> None:
    m = remote_module("offset-qual-v1")
    monkeypatch.setattr(m.os.path, "realpath", lambda p: "/outside")
    with pytest.raises(ValueError, match="containment"):
        m.configure("minus1")


@pytest.mark.parametrize("change", ["valid", "gap", "marker", "unaccounted", "reset"])
def test_durable_sequence_and_ledger_conservation(monkeypatch: Any, change: str) -> None:
    m = remote_module("offset-qual-v1")
    reservation = 128 * 1024**2
    current = {"campaign_id": "AUTO-PHASE-01", "count": 70, "result_reserved_bytes": 8188329984}
    markers = {
        m.RUNTIME + "/minus1/attempt-reserved": {
            "campaign_id": "AUTO-PHASE-01", "count": 69,
            "result_reserved_bytes": 7919894528 + reservation,
        },
        m.RUNTIME + "/plus1/attempt-reserved": dict(current),
    }
    if change == "gap":
        del markers[m.RUNTIME + "/minus1/attempt-reserved"]
    elif change == "marker":
        markers[m.RUNTIME + "/minus1/attempt-reserved"]["count"] = 70
    elif change == "unaccounted":
        current["count"] = 71
    elif change == "reset":
        current["result_reserved_bytes"] = 0
    monkeypatch.setattr(m.W, "counter", lambda readonly: current)
    monkeypatch.setattr(m.os.path, "lexists", lambda p: p in markers)
    monkeypatch.setattr(m.B, "read", lambda p, limit: json.dumps(markers[p]).encode())
    if change == "valid":
        assert m.counter() == current
    else:
        with pytest.raises(ValueError):
            m.counter()


def test_effective_input_and_protected_source_cannot_be_substituted(monkeypatch: Any) -> None:
    m = remote_module("offset-qual-v1")
    m.configure("minus1")
    monkeypatch.setattr(m, "authorization", lambda: "opaque")
    before = {"protected": {"source": "old"}, "counter": {
        "campaign_id": "AUTO-PHASE-01", "count": 68, "result_reserved_bytes": 7919894528,
    }}
    monkeypatch.setattr(m.B, "read", lambda p, *args: json.dumps(before).encode())
    monkeypatch.setattr(m, "protected", lambda: {"source": "changed"})
    with pytest.raises(ValueError, match="drift"):
        m.verify()
