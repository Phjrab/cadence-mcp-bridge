"""Synthetic 500-attempt boundaries and crash/replay accounting; no remote runs."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from test_native_diagnostics import remote_module

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
operator = importlib.import_module("spectre_limit")


def helper() -> Any:
    return remote_module("native-mcp-v2")


def counter(count: int = 32, reserved: int = 3088056320) -> dict[str, Any]:
    return {"campaign_id": "AUTO-PHASE-01", "count": count, "result_reserved_bytes": reserved}


@pytest.mark.parametrize("count", [32, 99, 100, 101, 499])
def test_only_requested_ceiling_is_increased(count: int) -> None:
    helper().validate_counter(
        counter(count), {"max_spectre_attempts": 500, "max_new_results_bytes": 5 * 1024**3}
    )


@pytest.mark.parametrize("count", [31, 500, 501, True, -1])
def test_counter_floor_exhaustion_and_boolean_rejected(count: int) -> None:
    with pytest.raises(ValueError, match="Spectre budget"):
        helper().validate_counter(
            counter(count), {"max_spectre_attempts": 500, "max_new_results_bytes": 5 * 1024**3}
        )


@pytest.mark.parametrize("reserved", [3088056319, 5 * 1024**3, True, -1])
def test_result_budget_is_unchanged(reserved: int) -> None:
    with pytest.raises(ValueError, match="result budget"):
        helper().validate_counter(
            counter(100, reserved),
            {"max_spectre_attempts": 500, "max_new_results_bytes": 5 * 1024**3},
        )


@pytest.mark.parametrize("fault", ["campaign", "extra", "missing"])
def test_closed_ledger_schema(fault: str) -> None:
    value = counter()
    if fault == "campaign":
        value["campaign_id"] = "reset"
    elif fault == "extra":
        value["untracked_attempts"] = 1
    else:
        del value["count"]
    with pytest.raises(ValueError):
        helper().validate_counter(
            value, {"max_spectre_attempts": 500, "max_new_results_bytes": 5 * 1024**3}
        )


def configured(module: ModuleType, tmp_path: Path) -> Any:
    value: Any = module
    # POSIX rename replaces atomically; emulate that guest behavior on Windows.
    value.os = SimpleNamespace(**(vars(os) | {"rename": os.replace}))
    value.N.JOBS = str(tmp_path / "jobs")
    Path(value.N.JOBS).mkdir()
    value.N.contained = lambda _: None
    value.BASE.JOB = str(tmp_path / "job")
    Path(value.BASE.JOB).mkdir()
    value.BASE.COUNTER = str(tmp_path / "counter.json")
    Path(value.BASE.COUNTER).write_text(json.dumps(counter(499)))
    value.BASE.environment_preflight = lambda: None
    value.BASE.verify_netlist = lambda: None
    value.authorization = lambda: {
        "max_spectre_attempts": 500,
        "max_new_results_bytes": 5 * 1024**3,
    }
    return value


def test_last_reservation_preserves_existing_counts_and_replay(tmp_path: Path) -> None:
    value = configured(helper(), tmp_path)
    value.reserve()
    actual = json.loads(Path(value.BASE.COUNTER).read_text())
    assert actual == counter(500, 3088056320 + 128 * 1024**2)
    assert json.loads((Path(value.BASE.JOB) / "attempt-reserved").read_text()) == actual
    with pytest.raises(ValueError, match="replay"):
        value.reserve()
    assert json.loads(Path(value.BASE.COUNTER).read_text()) == actual


@pytest.mark.parametrize("fault", ["temp", "future_marker"])
def test_uncertain_transaction_blocks_new_id(fault: str, tmp_path: Path) -> None:
    value = configured(helper(), tmp_path)
    if fault == "temp":
        Path(value.BASE.COUNTER + ".ade-tmp").write_text("preserved partial update")
    else:
        record = Path(value.N.JOBS) / "00000000-0000-4000-8000-000000000001" / "work"
        record.mkdir(parents=True)
        (record / "attempt-reserved").write_text(json.dumps(counter(500)))
    with pytest.raises(ValueError, match="uncertain|unreconciled"):
        value.reserve()
    assert not (Path(value.BASE.JOB) / "attempt-reserved").exists()
    assert json.loads(Path(value.BASE.COUNTER).read_text()) == counter(499)


def test_crash_intent_is_preserved_before_counter_update(tmp_path: Path) -> None:
    value = configured(helper(), tmp_path)
    real_save = value.BASE.save

    def save(path: str, data: Any) -> None:
        if path.endswith(".ade-tmp"):
            raise OSError("synthetic interruption")
        real_save(path, data)

    value.BASE.save = save
    with pytest.raises(OSError):
        value.reserve()
    assert (Path(value.BASE.JOB) / "attempt-reserved").exists()
    assert json.loads(Path(value.BASE.COUNTER).read_text()) == counter(499)
    with pytest.raises(ValueError, match="replay"):
        value.reserve()


@pytest.mark.parametrize("fault", ["none", "policy", "activation", "missing"])
def test_runtime_requires_exact_policy_and_private_activation(fault: str) -> None:
    value = helper()
    policy = json.loads(operator.LIMIT.read_text())
    active = operator.activation()
    if fault == "policy":
        policy["max_spectre_attempts"] = 501
    elif fault == "activation":
        active["policy_sha256"] = "drift"
    elif fault == "missing":
        active = {}
    value.BASE.read = lambda path, *_: json.dumps(
        policy if path.endswith("budget-policy.json") else active
    ).encode()
    if fault == "none":
        assert value.authorization()["max_spectre_attempts"] == 500
    else:
        with pytest.raises(ValueError):
            value.authorization()


def test_local_deployment_denies_missing_user_ceiling_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operator.campaign, "_load_authority", lambda: "parent")
    monkeypatch.setattr(operator.diag, "authority", lambda: None)
    monkeypatch.setattr(operator.previous, "authority", lambda: None)
    read = operator.campaign._read_json
    monkeypatch.setattr(
        operator.campaign, "_read_json", lambda path: read(path) if path == operator.LIMIT else {}
    )
    with pytest.raises(ValueError, match="ceiling delegation missing"):
        operator.authority()
