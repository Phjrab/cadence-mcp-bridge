"""Both active guards must preserve counters while enforcing the explicit 10 GiB cap."""

import json
from pathlib import Path
from typing import Any

import pytest
from test_native_diagnostics import remote_module

ROOT = Path(__file__).resolve().parents[2]
LIMIT = 10 * 1024**3
RESERVATION = 128 * 1024**2


def module(kind: str) -> Any:
    return (
        remote_module("native-mcp-v3")
        if kind == "native"
        else remote_module(
            "sweep-mcp-v2",
            "budget.py",
        )
    )


@pytest.mark.parametrize("kind", ["native", "sweep"])
@pytest.mark.parametrize(
    "count,reserved,allowed",
    [
        (62, 7114588160, True),
        (499, LIMIT - RESERVATION, True),
        (500, 7114588160, False),
        (62, LIMIT - RESERVATION + 1, False),
        (62, LIMIT, False),
        (True, 7114588160, False),
        (62, True, False),
    ],
)
def test_exact_reservation_boundaries(kind: str, count: int, reserved: int, allowed: bool) -> None:
    value = {"campaign_id": "AUTO-PHASE-01", "count": count, "result_reserved_bytes": reserved}
    policy = {"max_spectre_attempts": 500, "max_new_results_bytes": LIMIT}
    if allowed:
        module(kind).validate_counter(value, policy)
    else:
        with pytest.raises(ValueError):
            module(kind).validate_counter(value, policy)
    assert value == {
        "campaign_id": "AUTO-PHASE-01",
        "count": count,
        "result_reserved_bytes": reserved,
    }


@pytest.mark.parametrize("kind", ["native", "sweep"])
@pytest.mark.parametrize("changed", [False, True])
def test_exact_activation_and_policy(kind: str, changed: bool) -> None:
    value = module(kind)
    policy = json.loads((ROOT / "docs/policy/PHASE_RESULT_LIMIT_V4.json").read_bytes())
    activation = {
        "schema_version": 1,
        "campaign_id": "AUTO-PHASE-01",
        "change_id": "RESULT-LIMIT-10GIB-01",
        "policy_sha256": value.POLICY_SHA,
        "user_delegation": "explicit-in-current-task",
    }
    if changed:
        activation["policy_sha256"] = "0" * 64
    def read(path: str, *_: object) -> bytes:
        return json.dumps(policy if path.endswith("budget-policy.json") else activation).encode()
    if kind == "native":
        value.BASE.read = read
    else:
        value.read = read
    if changed:
        with pytest.raises(ValueError):
            value.authorization()
    else:
        assert value.authorization()["max_new_results_bytes"] == LIMIT


def test_disk_floor_before_ledger_mutation(tmp_path: Path) -> None:
    from types import SimpleNamespace

    value = module("sweep")
    counter = {"campaign_id": "AUTO-PHASE-01", "count": 62, "result_reserved_bytes": 7114588160}
    value.authorization = lambda: {"max_spectre_attempts": 500, "max_new_results_bytes": LIMIT}
    value.COUNTER = str(tmp_path / "counter.json")
    Path(value.COUNTER).write_text(json.dumps(counter))
    value.MARKERS = str(tmp_path / "markers")
    Path(value.MARKERS).mkdir()
    value.read = lambda path, _: Path(path).read_bytes()
    value.sys = SimpleNamespace(
        argv=["guard", "reserve", "00000000-0000-5000-8000-000000000001"],
        stdout=SimpleNamespace(write=lambda _: None),
    )
    value.subprocess = SimpleNamespace(
        PIPE=-1,
        Popen=lambda *a, **k: SimpleNamespace(
            communicate=lambda: (b"bash\n", b""),
            returncode=0,
        )
    )
    import os

    value.os = SimpleNamespace(
        **(
            vars(os)
            | {
                "statvfs": lambda _: SimpleNamespace(f_blocks=100000, f_bavail=1, f_frsize=4096),
            }
        )
    )
    with pytest.raises(ValueError, match="free-space floor"):
        value.main()
    assert json.loads(Path(value.COUNTER).read_bytes()) == counter
    assert not list(Path(value.MARKERS).iterdir())


def test_native_reserve_replay_with_preserved_ledger(tmp_path: Path) -> None:
    from test_spectre_limit import configured, counter

    value = configured(module("native"), tmp_path)
    Path(value.BASE.COUNTER).write_text(json.dumps(counter(62, 7114588160)))
    value.authorization = lambda: {"max_spectre_attempts": 500, "max_new_results_bytes": LIMIT}
    value.reserve()
    assert json.loads(Path(value.BASE.COUNTER).read_bytes()) == counter(
        63, 7114588160 + RESERVATION
    )
    with pytest.raises(ValueError, match="replay"):
        value.reserve()
