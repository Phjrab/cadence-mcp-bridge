"""Finite explicit follow-up allowances on disposable claims and runtimes."""

from __future__ import annotations

import copy
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from test_physical_metadata import (
    confirmed_domain,
    current_account_owner,
    operator,
    operator_base,
    physical_runtime,
    prepared,
    registered,
    root,
)

from cadence_mcp_bridge import _native_setup as setup
from cadence_mcp_bridge import _physical_metadata as native
from cadence_mcp_bridge import _shared_reservations as accounting
from cadence_mcp_bridge import physical_metadata as host
from cadence_mcp_bridge.native_runtime import bundle

__all__ = [
    "confirmed_domain",
    "current_account_owner",
    "isolated_intents",
    "operator",
    "operator_base",
    "physical_runtime",
    "prepared",
    "registered",
    "root",
]


def grant(profile_sha: str = "a" * 64, manifest_sha: str = "b" * 64) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "OPERATOR_APPROVED_PHYSICAL_METADATA_FOLLOWUP_V1",
        "max_additional_attempts": 10,
        "profile_sha256": profile_sha,
        "manifest_sha256": manifest_sha,
        "predecessor_collector_sha256": host.INITIAL_COLLECTOR_SHA256,
        "predecessor_plan_sha256": "c" * 64,
        "predecessor_host_request_sha256": "d" * 64,
        "predecessor_remote_request_sha256": "e" * 64,
    }


@pytest.fixture(autouse=True)
def isolated_intents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    # Short distinct disposable home: preserve actual DACL checks without hitting
    # Windows legacy path limits in nested per-test follow-up domain fixtures.
    with current_account_owner():
        home = tmp_path.parent / ("h" + uuid.uuid4().hex[:8])
        home.mkdir(mode=0o700)
        monkeypatch.setattr(host, "_operator_home", lambda: home)
        yield home


@pytest.fixture
def followup(registered: Any, tmp_path: Path) -> Any:
    context, _, registration = registered
    exported = tmp_path / "b"
    result = bundle(context, registration, exported)
    assets, known = host._load_bundle(exported, result["manifest_sha256"])
    value = grant(host._sha(assets["profile.json"]), result["manifest_sha256"])
    environment = context.contracts.environment
    assert environment is not None
    host._claim_intent(
        environment,
        value["predecessor_collector_sha256"],
        value["predecessor_plan_sha256"],
        value["predecessor_host_request_sha256"],
    )
    authorization = tmp_path / "grant.json"
    authorization.write_bytes(host._canonical(value))
    return environment, exported, value, authorization, assets, known


def test_ten_followups_are_spent_on_transport_failure_and_not_reopened(
    followup: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, exported, value, authorization, _, _ = followup
    calls: list[int] = []

    def failed(*_args: Any, **_kwargs: Any) -> Any:
        calls.append(1)
        raise ValueError("synthetic transport failure")

    monkeypatch.setattr(host, "_ssh", lambda _: ["never-executed"])
    monkeypatch.setattr(host, "run_fixed", failed)
    for number in range(1, 11):
        directory = tmp_path / str(number)
        result = host.prepare_followup(exported, value["manifest_sha256"], authorization, directory)
        assert result["slot"] == number and not result["remote_contact"]
        with pytest.raises(ValueError, match="failed_no_retry"):
            host.collect(directory, result["plan_sha256"])
        assert (directory / "failed.private.json").exists()
        with pytest.raises(FileExistsError):
            host.collect(directory, result["plan_sha256"])
    with pytest.raises(ValueError, match="exhausted"):
        host.prepare_followup(exported, value["manifest_sha256"], authorization, tmp_path / "11")
    assert calls == [1] * 10
    assert len(list(host._followup_pool(environment, False).glob("slot-*"))) == 10


def test_alias_source_grant_changes_and_same_invocation_cannot_reopen(followup: Any) -> None:
    environment, _, value, _, assets, known = followup
    nonce = uuid.uuid4().hex
    allowance = {"authorization": value, "slot": 1, "invocation_id": nonce}
    _, plan = host._plan(assets, value["manifest_sha256"], known, allowance)
    host._claim_followup(environment, plan)
    other = environment.model_copy(update={"environment_id": "other", "ssh_alias": "other"})
    changed = copy.deepcopy(plan)
    changed["collector_sha256"] = "f" * 64
    changed["followup"]["invocation_id"] = uuid.uuid4().hex
    with pytest.raises(FileExistsError):
        host._claim_followup(other, changed)
    changed["followup"]["slot"] = 2
    changed["followup"]["invocation_id"] = nonce
    with pytest.raises(FileExistsError):
        host._claim_followup(other, changed)


def test_concurrent_same_slot_has_one_winner(followup: Any) -> None:
    environment, _, value, _, assets, known = followup

    def claim(_: int) -> bool:
        allowance = {"authorization": value, "slot": 1, "invocation_id": uuid.uuid4().hex}
        _, plan = host._plan(assets, value["manifest_sha256"], known, allowance)
        try:
            host._claim_followup(environment, plan)
            return True
        except FileExistsError:
            return False

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(claim, range(4))) == 1


def test_partial_local_claim_prevents_transport_retry(
    followup: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment, exported, value, authorization, _, _ = followup
    directory = tmp_path / "p"
    result = host.prepare_followup(exported, value["manifest_sha256"], authorization, directory)
    pool = host._followup_pool(environment, True)
    (pool / "slot-01.private.json").write_bytes(b"{")
    monkeypatch.setattr(host, "run_fixed", lambda *_a, **_k: pytest.fail("SSH attempted"))
    with pytest.raises(FileExistsError):
        host.collect(directory, result["plan_sha256"])


def test_predecessor_drift_fails_before_transport(
    followup: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, exported, value, authorization, _, _ = followup
    value["predecessor_plan_sha256"] = "f" * 64
    authorization.write_bytes(host._canonical(value))
    monkeypatch.setattr(host, "run_fixed", lambda *_a, **_k: pytest.fail("SSH attempted"))
    with pytest.raises(ValueError, match="predecessor_binding"):
        host.prepare_followup(exported, value["manifest_sha256"], authorization, tmp_path / "p")


@pytest.mark.parametrize(
    "key,value", [("slot", True), ("slot", 11), ("slot", 0), ("invocation_id", "a" * 32 + "\n")]
)
def test_strict_allowance(key: str, value: object) -> None:
    allowance = {"authorization": grant(), "slot": 1, "invocation_id": uuid.uuid4().hex}
    allowance[key] = value
    with pytest.raises(ValueError, match="followup"):
        native.validate_followup(allowance, "a" * 64, "b" * 64)


@pytest.mark.parametrize("value", [True, 0, 11, -1])
def test_grant_cannot_expand_ten(value: object) -> None:
    authorization = grant()
    authorization["max_additional_attempts"] = value
    with pytest.raises(ValueError, match="followup_binding"):
        native.validate_followup(
            {"authorization": authorization, "slot": 1, "invocation_id": uuid.uuid4().hex},
            "a" * 64,
            "b" * 64,
        )


def test_production_source_cannot_reopen_initial_query(
    registered: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _, registration = registered
    exported = tmp_path / "b"
    result = bundle(context, registration, exported)
    prepared = host.prepare(exported, result["manifest_sha256"], tmp_path / "p")
    monkeypatch.setattr(host, "run_fixed", lambda *_a, **_k: pytest.fail("SSH attempted"))
    with pytest.raises(ValueError, match="initial_collection_retired"):
        host.collect(tmp_path / "p", prepared["plan_sha256"])


def test_process_restart_keeps_followup_spent(
    followup: Any,
    tmp_path: Path,
    isolated_intents: Path,
) -> None:
    environment, _, value, _, assets, known = followup
    _, plan = host._plan(
        assets,
        value["manifest_sha256"],
        known,
        {"authorization": value, "slot": 1, "invocation_id": uuid.uuid4().hex},
    )
    host._claim_followup(environment, plan)
    raw = tmp_path / "p.json"
    raw.write_bytes(host._canonical(plan))
    script = (
        "import sys,json; from pathlib import Path; "
        "from cadence_mcp_bridge import physical_metadata as h; "
        "from cadence_mcp_bridge.environments import EnvironmentProfile; "
        "h._operator_home=lambda:Path(sys.argv[1]); "
        "sys.path.insert(0,sys.argv[4]); "
        "from test_physical_metadata import current_account_owner\n"
        "with current_account_owner():\n"
        " h._claim_followup(EnvironmentProfile.model_validate_json(sys.argv[2]),"
        "json.loads(Path(sys.argv[3]).read_bytes()))"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(isolated_intents),
            environment.model_dump_json(),
            str(raw),
            str(Path(__file__).parent),
        ],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert completed.returncode != 0 and b"FileExistsError" in completed.stderr


def remote_predecessor(runtime: Any) -> tuple[dict[str, Any], Path]:
    root, query, assets, _, _ = runtime
    authorization = grant(native.digest(assets["profile.json"]), query["manifest_sha256"])
    source = b"# original failed synthetic collector\n"
    authorization["predecessor_collector_sha256"] = native.digest(source)
    directory = root / "physical-metadata-v1" / native.digest(source)
    directory.mkdir(mode=0o700, parents=True)
    directory.parent.chmod(0o700)
    (directory / "collector.py").write_bytes(source)
    (directory / "request.json").write_bytes(
        native.canonical(
            {
                "operation": "physical-metadata-once-v1",
                "manifest_sha256": query["manifest_sha256"],
                "collector_sha256": native.digest(source),
                "request_sha256": authorization["predecessor_remote_request_sha256"],
            }
        )
    )
    for path in directory.iterdir():
        path.chmod(0o600)
    return authorization, directory


@pytest.mark.skipif(os.name != "posix", reason="owned POSIX runtime/flock and metadata")
def test_remote_slots_preserve_original_failure_runtime_and_ledger(physical_runtime: Any) -> None:
    root, query, assets, known, _ = physical_runtime
    authorization, directory = remote_predecessor(physical_runtime)
    predecessor_bytes = {p.name: p.read_bytes() for p in directory.iterdir()}
    before = (root / accounting.LEDGER).read_bytes()
    query.update(operation="physical-metadata-followup-v1")
    for number in range(1, 11):
        query["followup"] = {
            "authorization": authorization,
            "slot": number,
            "invocation_id": uuid.uuid4().hex,
        }
        result = native.run(query, setup, assets, known, b"# new fixed source\n")
        assert result["followup_slot"] == number
        assert result["counter_before"] == result["counter_after"]
        with pytest.raises(FileExistsError):
            native.run(query, setup, assets, known, b"# another synthetic source\n")
    assert (root / accounting.LEDGER).read_bytes() == before
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == predecessor_bytes
    assert not (directory / "receipt.json").exists()
    assert len(list((root / "physical-metadata-followup-v1").iterdir())) == 10


@pytest.mark.skipif(os.name != "posix", reason="owned POSIX predecessor stage")
@pytest.mark.parametrize("drift", ["receipt", "source", "request", "namespace"])
def test_remote_rejects_predecessor_drift_before_new_stage(
    physical_runtime: Any, drift: str
) -> None:
    root, query, assets, known, _ = physical_runtime
    authorization, directory = remote_predecessor(physical_runtime)
    if drift == "receipt":
        (directory / "receipt.json").write_bytes(b"{}")
    elif drift == "namespace":
        (directory / "extra").write_bytes(b"x")
    else:
        target = directory / ("collector.py" if drift == "source" else "request.json")
        target.write_bytes(b"changed")
    query.update(
        operation="physical-metadata-followup-v1",
        followup={"authorization": authorization, "slot": 1, "invocation_id": uuid.uuid4().hex},
    )
    with pytest.raises(ValueError):
        native.run(query, setup, assets, known, b"# source\n")
    assert not (root / "physical-metadata-followup-v1").exists()
