"""Mocked owned filesystem and resource guards, no simulator execution."""

import json
import os
from typing import Any
from uuid import uuid4, uuid5

import pytest
from test_native_diagnostics import remote_module


@pytest.fixture
def module(monkeypatch: Any) -> Any:
    m = remote_module("amplifier-sweep-v1")
    monkeypatch.setattr(os.path, "realpath", lambda p: p)
    m.configure(str(uuid5(uuid4(), "child")))
    return m


@pytest.mark.parametrize("bad", ["../x", "/tmp/x", "", str(uuid4()), "x\n"])
def test_only_compiled_children(module: Any, bad: str) -> None:
    with pytest.raises(ValueError):
        module.configure(bad)


def test_no_follow_escape(module: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(os.path, "realpath", lambda p: "/outside")
    with pytest.raises(ValueError):
        module.configure(str(uuid5(uuid4(), "child")))


@pytest.mark.parametrize("change", ["valid", "request", "input", "protected", "symlink"])
def test_prepared_input_and_full_protection_separate(
    module: Any, monkeypatch: Any, change: str,
) -> None:
    m = module
    original = b"synthetic VBIASN=320m only"
    m.Q.SOURCES["dc"] = ("opaque", m.B.sha(original), "a" * 64)
    r = {"job_id": m.IDENTITY, "analysis": "dc", "value_v": "0.319",
         "plan_hash": "a" * 64, "policy_sha256": "b" * 64}
    if change == "request":
        r["job_id"] = str(uuid5(uuid4(), "other"))
    data = {
        m.JOB + "/request.json": json.dumps(r).encode(),
        m.JOB + "/before.json": json.dumps({"protected": {"old": True}}).encode(),
        m.JOB + "/netlist/input.scs": original.replace(b"320m", b"319m") + (
            b" unexpected" if change == "input" else b""
        ),
    }
    monkeypatch.setattr(m, "authorization", lambda: ({}, "b" * 64))
    monkeypatch.setattr(m.B, "read", lambda p, *args: data[p])
    if change == "symlink":
        monkeypatch.setattr(os.path, "realpath", lambda p: "/outside")
    monkeypatch.setattr(m, "protected", lambda: {"old": change != "protected"})
    monkeypatch.setattr(m.Q, "source", lambda: None)
    if change == "protected":
        assert m.verify_input() == r  # no unsafe global checkpoint during our active worker
        with pytest.raises(ValueError):
            m.verify()
    elif change == "valid":
        assert m.verify() == r
    else:
        with pytest.raises(ValueError):
            m.verify_input()


@pytest.mark.parametrize("change", ["valid", "gap", "bytes", "unaccounted", "unknown", "overflow"])
def test_shared_ledger_exact_conservation(module: Any, monkeypatch: Any, change: str) -> None:
    m = module
    names = [str(uuid5(uuid4(), str(i))) for i in range(7 if change == "overflow" else 2)]
    markers = {m.JOBS + "/" + n + "/attempt-reserved": {
        "campaign_id": "AUTO-PHASE-01", "count": 77 + i,
        "result_reserved_bytes": 8993636352 + (i + 1) * m.B.RESERVATION,
    } for i, n in enumerate(names)}
    current = dict(list(markers.values())[-1])
    if change == "gap":
        del markers[next(iter(markers))]
    elif change == "bytes":
        list(markers.values())[0]["result_reserved_bytes"] += 1
    elif change == "unaccounted":
        current["count"] += 1
    elif change == "unknown":
        names.append("rogue")
    monkeypatch.setattr(m.os, "listdir", lambda p: names)
    monkeypatch.setattr(m.os.path, "lexists", lambda p: p in markers)
    monkeypatch.setattr(m.B, "read", lambda p, *args: json.dumps(markers[p]).encode())
    monkeypatch.setattr(m.W, "counter", lambda read: current)
    if change == "valid":
        assert m.counter() == current
    else:
        with pytest.raises(ValueError):
            m.counter()


def test_environment_and_disk_refusal_precede_copy(module: Any, monkeypatch: Any) -> None:
    m = module
    monkeypatch.setattr(m, "authorization", lambda: ({}, "b" * 64))
    monkeypatch.setattr(m.os.path, "lexists", lambda p: False)
    def deny() -> None:
        raise ValueError("environment/disk/EDA guard")
    monkeypatch.setattr(m.B, "environment_preflight", deny)
    with pytest.raises(ValueError, match="guard"):
        m.prepare("dc", "0.319", "a" * 64)


def test_effective_requires_exact_owned_launch(module: Any, monkeypatch: Any) -> None:
    m = module
    monkeypatch.setattr(m, "verify_input", lambda: {"value_v": "0.319"})
    monkeypatch.setattr(m.os.path, "lexists", lambda p: True)
    monkeypatch.setattr(m.B, "read", lambda p, *args: b"another\n")
    with pytest.raises(ValueError, match="identity"):
        m.effective()
