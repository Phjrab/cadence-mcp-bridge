"""Real disposable account files and processes; no actual account/VM mutations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from test_environments import profile_data
from test_physical_metadata import current_account_owner

from cadence_mcp_bridge import binding_observation_claim as claims
from cadence_mcp_bridge import physical_metadata as retained
from cadence_mcp_bridge.environments import EnvironmentProfile


@pytest.fixture
def campaign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    with current_account_owner():
        home = tmp_path / "h"
        home.mkdir(mode=0o700)
        monkeypatch.setattr(retained, "_operator_home", lambda: home)
        environment = EnvironmentProfile.model_validate_json(json.dumps(profile_data()))
        predecessor = {
            "predecessor_collector_sha256": retained.INITIAL_COLLECTOR_SHA256,
            "predecessor_plan_sha256": "a" * 64,
            "predecessor_host_request_sha256": "b" * 64,
            "predecessor_remote_request_sha256": "c" * 64,
        }
        evidence = {name: "d" * 64 for name in claims._EVIDENCE}
        retained._claim_intent(environment, predecessor["predecessor_collector_sha256"],
                               predecessor["predecessor_plan_sha256"],
                               predecessor["predecessor_host_request_sha256"])
        yield environment, predecessor, evidence, home


def slots(environment: EnvironmentProfile) -> tuple[Path, dict[str, bytes]]:
    pool = retained._followup_pool(environment, True)
    for number in range(1, 11):
        retained._exclusive_intent(pool / f"slot-{number:02d}.private.json", {
            "status": "ATTEMPT_SPENT_NO_RETRY", "slot": number,
            "invocation_id": f"{number:032x}", "plan_sha256": "a" * 64,
            "request_sha256": "b" * 64, "authorization_sha256": "c" * 64,
            "collector_sha256": "d" * 64,
        })
    return pool, {p.name: p.read_bytes() for p in pool.glob("slot-*.private.json")}


def test_claim_keeps_original_and_ten_spent_slots(campaign: Any) -> None:
    environment, predecessor, evidence, home = campaign
    original = {p.name: p.read_bytes() for p in home.joinpath(
        ".cadence-mcp-physical-intents-v1").glob("*.private.json")}
    pool, before = slots(environment)
    claims.claim(environment, predecessor, evidence)
    value = json.loads((pool / claims.LEAF).read_bytes())
    assert value["retained_physical_slot_sha256"] == {
        name: retained._sha(raw) for name, raw in before.items()
    }
    assert value["approval_is_external"] is True
    assert {p.name: p.read_bytes() for p in pool.glob("slot-*.private.json")} == before
    assert {p.name: p.read_bytes() for p in home.joinpath(
        ".cadence-mcp-physical-intents-v1").glob("*.private.json")} == original


def test_alias_helper_plan_and_receipt_changes_cannot_reopen(campaign: Any) -> None:
    environment, predecessor, evidence, _ = campaign
    claims.claim(environment, predecessor, evidence)
    pool = retained._followup_pool(environment, False)
    before = (pool / claims.LEAF).read_bytes()
    changed = environment.model_copy(update={"ssh_alias": "other", "environment_id": "other"})
    with pytest.raises(FileExistsError, match="spent_no_retry"):
        claims.claim(changed, predecessor, {key: "e" * 64 for key in evidence})
    assert (pool / claims.LEAF).read_bytes() == before


@pytest.mark.parametrize("partial", [b"", b"{", b"{}"])
def test_partial_marker_stays_spent(campaign: Any, partial: bytes) -> None:
    environment, predecessor, evidence, _ = campaign
    pool = retained._followup_pool(environment, True)
    (pool / claims.LEAF).write_bytes(partial)
    with pytest.raises(FileExistsError, match="spent_no_retry"):
        claims.claim(environment, predecessor, evidence)
    assert (pool / claims.LEAF).read_bytes() == partial


@pytest.mark.parametrize("which", ["predecessor", "evidence"])
@pytest.mark.parametrize("bad", ["extra", "missing", "uppercase", "newline", "number"])
def test_refs_are_closed_and_strict(campaign: Any, which: str, bad: str) -> None:
    environment, predecessor, evidence, _ = campaign
    target = dict(predecessor if which == "predecessor" else evidence)
    first = next(iter(target))
    if bad == "extra":
        target["extra"] = "a" * 64
    elif bad == "missing":
        del target[first]
    else:
        target[first] = {"uppercase": "A" * 64, "newline": "a" * 64 + "\n",
                         "number": 1}[bad]  # type: ignore[assignment]
    with pytest.raises(ValueError, match="closed_digest"):
        claims.claim(environment, target if which == "predecessor" else predecessor,
                     target if which == "evidence" else evidence)
    assert not retained._followup_pool(environment, False).exists()


def test_wrong_predecessor_rejects_before_new_pool(campaign: Any) -> None:
    environment, predecessor, evidence, _ = campaign
    predecessor["predecessor_plan_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="predecessor_binding"):
        claims.claim(environment, predecessor, evidence)
    assert not retained._followup_pool(environment, False).exists()


@pytest.mark.parametrize("bad", [b"{", b"{}", b'{"slot":1,"slot":1}'])
def test_invalid_physical_history_cannot_be_skipped(campaign: Any, bad: bytes) -> None:
    environment, predecessor, evidence, _ = campaign
    pool, _ = slots(environment)
    path = pool / "slot-10.private.json"
    path.write_bytes(bad)
    with pytest.raises(ValueError):
        claims.claim(environment, predecessor, evidence)
    assert path.read_bytes() == bad and not (pool / claims.LEAF).exists()


def test_concurrent_claims_have_one_winner(campaign: Any) -> None:
    environment, predecessor, evidence, _ = campaign
    retained._followup_pool(environment, True)

    def attempt(_: int) -> bool:
        try:
            claims.claim(environment, predecessor, evidence)
            return True
        except FileExistsError:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(attempt, range(32))) == 1


def test_partial_publication_failure_stays_spent(campaign: Any, monkeypatch: Any) -> None:
    environment, predecessor, evidence, _ = campaign

    def fail(path: Path, value: Any) -> None:
        with path.open("xb") as stream:
            stream.write(b"{")
        raise OSError("synthetic publication failure")

    monkeypatch.setattr(retained, "_exclusive_intent", fail)
    with pytest.raises(OSError):
        claims.claim(environment, predecessor, evidence)
    with pytest.raises(FileExistsError, match="spent_no_retry"):
        claims.claim(environment, predecessor, evidence)


def test_process_restart_uses_same_account_claim(campaign: Any) -> None:
    environment, predecessor, evidence, home = campaign
    claims.claim(environment, predecessor, evidence)
    code = (
        "import json,sys; from pathlib import Path; "
        "from cadence_mcp_bridge import physical_metadata as p; "
        "from cadence_mcp_bridge.binding_observation_claim import claim; "
        "from cadence_mcp_bridge.environments import EnvironmentProfile; "
        "p._operator_home=lambda:Path(sys.argv[1]); "
        "claim(EnvironmentProfile.model_validate_json(sys.argv[2]),"
        "json.loads(sys.argv[3]),json.loads(sys.argv[4]))"
    )
    process = subprocess.run([sys.executable, "-B", "-c", code, str(home),
                              environment.model_dump_json(), json.dumps(predecessor),
                              json.dumps(evidence)], capture_output=True, timeout=30)
    assert process.returncode != 0
    assert b"binding_observation_spent_no_retry" in process.stderr


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode guard; Windows reuses DACL guard")
def test_untrusted_pool_is_not_repaired(campaign: Any) -> None:
    environment, predecessor, evidence, _ = campaign
    pool = retained._followup_pool(environment, True)
    pool.chmod(0o777)
    with pytest.raises(ValueError, match="intent_permissions"):
        claims.claim(environment, predecessor, evidence)
    assert pool.stat().st_mode & 0o777 == 0o777
