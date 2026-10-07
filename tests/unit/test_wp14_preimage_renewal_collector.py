from __future__ import annotations

import hashlib
import importlib.util
import json
import msvcrt
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = ROOT / "scripts/collect-wp14-renewed-remote-preimages.py"
FAKE_SSH = ROOT / "tests/fixtures/wp14_renewal_fake_ssh.py"
SYNTHETIC_BINDING = "a" * 64
SYNTHETIC_COMMIT = "b" * 40


@dataclass
class Runtime:
    module: ModuleType
    repository: Path
    collection_root: Path
    deployment_root: Path
    collection_lock: Path
    deployment_lock: Path
    collection_claim: Path
    deployment_claim: Path
    renewal_claim: Path
    recovery_claim: Path
    activation: Path
    v1_evidence: Path
    v2_evidence: Path
    deployment_activation: Path
    preserved: dict[Path, bytes]


def _load_collector() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"wp14_renewal_collector_{time.time_ns()}", COLLECTOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalized_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode()).hexdigest()


def _write_json(path: Path, value: object) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode()
    path.write_bytes(raw)
    return raw


def _asset_allowlist(module: ModuleType) -> list[dict[str, str]]:
    return [
        {"path": path, "remote_relative_path": remote, "required_presence": required}
        for path, remote, required in module.ASSETS
    ]


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Runtime:
    module = _load_collector()
    repository = tmp_path / "repository"
    repository.mkdir()

    contract = repository / "contract.md"
    plan = repository / "plan.md"
    package = repository / "package.json"
    single_use = repository / "single-use.json"
    deployment_package = repository / "deployment-package.json"
    old_collector = repository / "old-collector.py"
    deployer = repository / "deployer.ps1"
    recovery_deployer = repository / "recovery-deployer.ps1"
    lineage = repository / "lineage.json"
    v1_evidence = repository / "evidence-v1.json"
    v2_evidence = repository / "evidence-v2.json"
    legacy_activation = repository / "legacy-activation.json"
    deployment_activation = repository / "deployment-activation.json"
    recovery_activation = repository / "recovery-activation.json"
    activation = repository / "renewal-activation.json"

    contract.write_text("synthetic renewal contract\n", encoding="utf-8")
    plan.write_text("synthetic fail-closed renewal plan\n", encoding="utf-8")
    _write_json(package, {"asset_preimage_allowlist": _asset_allowlist(module)})
    _write_json(single_use, {"synthetic": "single-use"})
    _write_json(deployment_package, {"synthetic": "deployment-package"})
    old_collector.write_text("# synthetic predecessor collector\n", encoding="utf-8")
    deployer.write_text("# synthetic predecessor deployer\n", encoding="utf-8")
    recovery_deployer.write_text("# synthetic recovery deployer\n", encoding="utf-8")
    _write_json(lineage, {"deployment_enabled": False})
    _write_json(v1_evidence, {"synthetic": "historical-v1"})
    _write_json(deployment_activation, {"synthetic": "preserved-deployment-activation"})

    path_bindings = {
        "CONTRACT": contract,
        "PLAN": plan,
        "PACKAGE": package,
        "SINGLE_USE_PACKAGE": single_use,
        "DEPLOYMENT_PACKAGE": deployment_package,
        "OLD_COLLECTOR": old_collector,
        "DEPLOYER": deployer,
        "RECOVERY_DEPLOYER": recovery_deployer,
        "LINEAGE": lineage,
        "PREDECESSOR_EVIDENCE": v1_evidence,
        "LEGACY_COLLECTION_AUTHORIZATION": legacy_activation,
        "DEPLOYMENT_AUTHORIZATION": deployment_activation,
        "RECOVERY_AUTHORIZATION": recovery_activation,
        "RENEWAL_AUTHORIZATION": activation,
        "RENEWAL_EVIDENCE": v2_evidence,
    }
    for name, value in path_bindings.items():
        monkeypatch.setattr(module, name, value)

    hash_bindings = {
        "CONTRACT_HASH": _normalized_hash(contract),
        "PLAN_HASH": _normalized_hash(plan),
        "PACKAGE_HASH": _normalized_hash(package),
        "SINGLE_USE_PACKAGE_HASH": _normalized_hash(single_use),
        "DEPLOYMENT_PACKAGE_HASH": _normalized_hash(deployment_package),
        "OLD_COLLECTOR_HASH": _normalized_hash(old_collector),
        "DEPLOYER_HASH": _normalized_hash(deployer),
        "RECOVERY_DEPLOYER_HASH": _normalized_hash(recovery_deployer),
        "PREDECESSOR_EVIDENCE_HASH": _normalized_hash(v1_evidence),
        "DEPLOYMENT_AUTHORIZATION_HASH": _normalized_hash(deployment_activation),
        "LEGACY_COLLECTION_AUTHORIZATION_HASH": "c" * 64,
    }
    for name, value in hash_bindings.items():
        monkeypatch.setattr(module, name, value)

    collection_root = tmp_path / "local-state/collection"
    deployment_root = tmp_path / "local-state/deployment"
    collection_root.mkdir(parents=True)
    deployment_root.mkdir(parents=True)
    collection_lock = collection_root / "operation.lock"
    deployment_lock = deployment_root / "operation.lock"
    collection_lock.write_bytes(b"\0")
    deployment_lock.write_bytes(b"")
    collection_claim = collection_root / module.LEGACY_COLLECTION_CLAIM_NAME
    deployment_claim = deployment_root / module.DEPLOYMENT_CLAIM_NAME
    renewal_claim = collection_root / module.RENEWAL_CLAIM_NAME
    recovery_claim = deployment_root / module.RECOVERY_CLAIM_NAME
    collection_raw = _write_json(
        collection_claim,
        {
            "state": "consumed_before_transport",
            "authorization_id": "11111111-1111-1111-1111-111111111111",
            "authorization_sha256": module.LEGACY_COLLECTION_AUTHORIZATION_HASH,
            "package_sha256": module.PACKAGE_HASH,
            "collector_sha256": module.OLD_COLLECTOR_HASH,
            "consumed_at": "2026-09-17T08:05:01+00:00",
        },
    )
    deployment_raw = _write_json(
        deployment_claim,
        {
            "state": "consumed_before_transport",
            "authorization_id": "4f06b6ca-3377-48ae-a643-aefc3fb90dbc",
            "authorization_sha256": module.DEPLOYMENT_AUTHORIZATION_HASH,
            "package_sha256": module.DEPLOYMENT_PACKAGE_HASH,
            "deployer_sha256": module.DEPLOYER_HASH,
            "consumed_at": "2026-09-17T08:20:37.8800486+00:00",
        },
    )
    monkeypatch.setattr(module, "_collection_state_root", lambda: collection_root)
    monkeypatch.setattr(module, "_deployment_state_root", lambda: deployment_root)
    monkeypatch.setattr(module, "_executor_binding", lambda: SYNTHETIC_BINDING)
    monkeypatch.setattr(module.sys, "argv", ["collector"])

    preserved = {
        collection_claim: collection_raw,
        deployment_claim: deployment_raw,
        collection_lock: collection_lock.read_bytes(),
        deployment_lock: deployment_lock.read_bytes(),
        v1_evidence: v1_evidence.read_bytes(),
        deployment_activation: deployment_activation.read_bytes(),
    }
    return Runtime(
        module=module,
        repository=repository,
        collection_root=collection_root,
        deployment_root=deployment_root,
        collection_lock=collection_lock,
        deployment_lock=deployment_lock,
        collection_claim=collection_claim,
        deployment_claim=deployment_claim,
        renewal_claim=renewal_claim,
        recovery_claim=recovery_claim,
        activation=activation,
        v1_evidence=v1_evidence,
        v2_evidence=v2_evidence,
        deployment_activation=deployment_activation,
        preserved=preserved,
    )


def _activation_record(runtime: Runtime, **overrides: object) -> dict[str, object]:
    module = runtime.module
    now = datetime.now(UTC)
    record: dict[str, object] = {
        "schema_version": 2,
        "record_kind": "explicit_remote_identity_preimage_renewal_authorization",
        "status": "APPROVED",
        "renewal_generation": "collection-renewal-v1",
        "contract_normalized_lf_sha256": module.CONTRACT_HASH,
        "package_normalized_lf_sha256": module.PACKAGE_HASH,
        "collector_normalized_lf_sha256": module.normalized_hash(COLLECTOR),
        "repository_implementation_commit": SYNTHETIC_COMMIT,
        "predecessor_evidence_normalized_lf_sha256": module.PREDECESSOR_EVIDENCE_HASH,
        "predecessor_collection_claim_sha256": hashlib.sha256(
            runtime.collection_claim.read_bytes()
        ).hexdigest(),
        "predecessor_deployment_claim_sha256": hashlib.sha256(
            runtime.deployment_claim.read_bytes()
        ).hexdigest(),
        "predecessor_deployment_authorization_normalized_lf_sha256": (
            module.DEPLOYMENT_AUTHORIZATION_HASH
        ),
        "executor_binding_rule": "windows_username_pipe_machineguid_sha256_v1",
        "executor_binding": SYNTHETIC_BINDING,
        "authorization_id": "22222222-2222-2222-2222-222222222222",
        "not_before": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "max_uses": 1,
        "remote_identity_preimage_collection_authorized": True,
    }
    record.update(overrides)
    return record


def _authorize(runtime: Runtime, **overrides: object) -> dict[str, object]:
    record = _activation_record(runtime, **overrides)
    _write_json(runtime.activation, record)
    return record


def _valid_remote_output(runtime: Runtime, absent_index: int | None = None) -> bytes:
    module = runtime.module
    lines = [
        "WP14_ID\tcadence\tbuet\t/home/buet/cds_work/.cadence_mcp\t"
        "/home/buet/cds_work/.cadence_mcp\ttrue\tfalse\ttrue"
    ]
    for index, (repository_path, _, required) in enumerate(module.ASSETS):
        if index == absent_index:
            assert required == "file_or_absent"
            lines.append(f"WP14_ASSET\t{index}\tabsent\t-\t-\t-\t-\t-\tfalse\ttrue")
            continue
        digest = hashlib.sha256(repository_path.encode()).hexdigest()
        mode = "700" if index < 7 else "600"
        lines.append(
            f"WP14_ASSET\t{index}\tfile\t{digest}\t{mode}\tbuet\tregular_file\t1\tfalse\ttrue"
        )
    lines.append("WP14_END")
    return ("\n".join(lines) + "\n").encode()


def _assert_preserved(runtime: Runtime) -> None:
    for path, expected in runtime.preserved.items():
        assert path.read_bytes() == expected


def _run_error(runtime: Runtime) -> str:
    with pytest.raises(runtime.module.CollectorError) as raised:
        runtime.module._run()
    return raised.value.code


def _transport_spy() -> tuple[list[str], Any]:
    calls: list[str] = []

    def invoke(command: str, _expiry: datetime, _deadline: float) -> bytes:
        calls.append(command)
        return b""

    return calls, invoke


def test_production_collector_has_fixed_non_mcp_boundary() -> None:
    text = COLLECTOR.read_text(encoding="utf-8")
    assert "collection-renewal-v1.json" in text
    assert "WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_RENEWAL_AUTHORIZATION_V1.json" in text
    assert "WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_V2.json" in text
    assert "windows_username_pipe_machineguid_sha256_v1" in text
    assert "FileMode" not in text
    assert "shell=True" not in text
    assert "paramiko" not in text.lower()
    assert "mcp.tool" not in text.lower()
    assert "WP14_RENEWAL_SCENARIO" not in text
    assert "virtuoso" not in text.lower()
    assert "spectre" not in text.lower()
    assert "ocean" not in text.lower()
    assert "unlink(" not in text and "rmtree(" not in text and "os.remove" not in text
    assert not (
        ROOT / "docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_RENEWAL_AUTHORIZATION_V1.json"
    ).exists()
    assert not (ROOT / "docs/evidence/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_V2.json").exists()


def test_accepted_activation_holds_both_locks_and_consumes_before_transport(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = runtime.module
    authorization = _authorize(runtime)
    order: list[Path] = []
    original_open = module._open_exclusive_existing_lock

    def ordered_open(path: Path) -> Any:
        order.append(path)
        return original_open(path)

    def fake_transport(command: str, _expiry: datetime, _deadline: float) -> bytes:
        assert runtime.renewal_claim.is_file()
        claim = json.loads(runtime.renewal_claim.read_text(encoding="utf-8"))
        assert claim["state"] == "consumed_before_transport"
        assert claim["renewal_generation"] == "collection-renewal-v1"
        assert claim["authorization_id"] == authorization["authorization_id"]
        for lock_path in (runtime.deployment_lock, runtime.collection_lock):
            with pytest.raises(module.CollectorError) as raised:
                original_open(lock_path)
            assert raised.value.code == "LOCK_UNAVAILABLE"
        assert command == module._fixed_remote_command()
        return _valid_remote_output(runtime)

    monkeypatch.setattr(module, "_open_exclusive_existing_lock", ordered_open)
    monkeypatch.setattr(module, "_invoke_bounded_ssh", fake_transport)
    evidence = json.loads(module._run())
    assert order[:2] == [runtime.deployment_lock, runtime.collection_lock]
    assert evidence["schema_version"] == 2
    assert evidence["record_kind"] == "wp14_renewed_remote_identity_preimage_evidence"
    assert evidence["repository_implementation_commit"] == SYNTHETIC_COMMIT
    assert len(evidence["preimages"]) == 11
    assert evidence["blockers"] == []
    serialized = json.dumps(evidence).lower()
    for forbidden in ("authorization_id", "executor_binding", "machineguid", "claim_sha256"):
        assert forbidden not in serialized
    assert not runtime.v2_evidence.exists()
    _assert_preserved(runtime)


def test_optional_absence_is_closed_and_explicit(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _authorize(runtime)
    monkeypatch.setattr(
        runtime.module,
        "_invoke_bounded_ssh",
        lambda *_args: _valid_remote_output(runtime, absent_index=3),
    )
    evidence = json.loads(runtime.module._run())
    absent = evidence["preimages"][3]
    assert absent == {
        "path": "remote/lib/run-wp14-role-discovery.sh",
        "presence": "absent",
        "sha256": None,
        "mode": None,
        "owner": None,
        "file_type": None,
        "hard_link_count": None,
        "is_symlink": False,
        "resolved_under_root": True,
    }
    _assert_preserved(runtime)


def test_missing_activation_stops_before_identity_ledger_or_transport(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, transport = _transport_spy()
    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
    monkeypatch.setattr(
        runtime.module,
        "_executor_binding",
        lambda: pytest.fail("actual identity must not be read without activation"),
    )
    assert _run_error(runtime) == "ACTIVATION_MISSING"
    assert calls == []
    assert not runtime.renewal_claim.exists()
    _assert_preserved(runtime)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"schema_version": 1}, "ACTIVATION_INVALID"),
        ({"max_uses": True}, "ACTIVATION_INVALID"),
        ({"renewal_generation": "collection-renewal-v2"}, "ACTIVATION_INVALID"),
        ({"contract_normalized_lf_sha256": "0" * 64}, "ACTIVATION_INVALID"),
        ({"collector_normalized_lf_sha256": "0" * 64}, "ACTIVATION_INVALID"),
        ({"repository_implementation_commit": "0" * 40}, "ACTIVATION_INVALID"),
        ({"executor_binding_rule": "other"}, "ACTIVATION_INVALID"),
        ({"executor_binding": "d" * 64}, "IDENTITY_BINDING_INVALID"),
        ({"remote_identity_preimage_collection_authorized": False}, "ACTIVATION_INVALID"),
    ],
)
def test_invalid_activation_never_consumes_or_calls_transport(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    expected: str,
) -> None:
    _authorize(runtime, **overrides)
    calls, transport = _transport_spy()
    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
    assert _run_error(runtime) == expected
    assert calls == []
    assert not runtime.renewal_claim.exists()
    _assert_preserved(runtime)


def test_expired_or_overlong_activation_is_rejected_before_consumption(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    _authorize(
        runtime,
        not_before=(now - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=(now + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    calls, transport = _transport_spy()
    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
    assert _run_error(runtime) == "ACTIVATION_TIME_INVALID"
    assert calls == [] and not runtime.renewal_claim.exists()


def test_extra_or_duplicate_activation_key_is_rejected(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _activation_record(runtime)
    record["extra"] = "denied"
    _write_json(runtime.activation, record)
    calls, transport = _transport_spy()
    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
    assert _run_error(runtime) == "ACTIVATION_INVALID"
    assert calls == [] and not runtime.renewal_claim.exists()

    runtime.activation.write_text('{"schema_version":2,"schema_version":2}', encoding="utf-8")
    assert _run_error(runtime) == "ACTIVATION_INVALID"
    assert calls == [] and not runtime.renewal_claim.exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-collection",
        "partial-collection",
        "extra-collection-field",
        "wrong-collection-field",
        "missing-deployment",
        "recovery-claim",
        "existing-renewal-empty",
        "existing-renewal-partial",
        "missing-deployment-lock",
        "missing-collection-lock",
    ],
)
def test_lineage_failures_stop_before_transport_without_modifying_predecessors(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    _authorize(runtime)
    if mutation == "missing-collection":
        runtime.collection_claim.unlink()
    elif mutation == "partial-collection":
        runtime.collection_claim.write_bytes(b"{")
    elif mutation == "extra-collection-field":
        value = json.loads(runtime.collection_claim.read_text(encoding="utf-8"))
        value["extra"] = "denied"
        _write_json(runtime.collection_claim, value)
    elif mutation == "wrong-collection-field":
        value = json.loads(runtime.collection_claim.read_text(encoding="utf-8"))
        value["collector_sha256"] = "0" * 64
        _write_json(runtime.collection_claim, value)
    elif mutation == "missing-deployment":
        runtime.deployment_claim.unlink()
    elif mutation == "recovery-claim":
        runtime.recovery_claim.write_bytes(b"preserved")
    elif mutation == "existing-renewal-empty":
        runtime.renewal_claim.write_bytes(b"")
    elif mutation == "existing-renewal-partial":
        runtime.renewal_claim.write_bytes(b"{")
    elif mutation == "missing-deployment-lock":
        runtime.deployment_lock.unlink()
    elif mutation == "missing-collection-lock":
        runtime.collection_lock.unlink()
    calls, transport = _transport_spy()
    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
    code = _run_error(runtime)
    assert code in {"LINEAGE_INVALID", "ATTEMPT_CONSUMED", "LOCK_UNAVAILABLE"}
    assert calls == []
    if mutation not in {"existing-renewal-empty", "existing-renewal-partial"}:
        assert not runtime.renewal_claim.exists()
    deliberately_changed: set[Path] = set()
    if "collection" in mutation and "lock" not in mutation:
        deliberately_changed.add(runtime.collection_claim)
    if mutation == "missing-deployment":
        deliberately_changed.add(runtime.deployment_claim)
    if mutation == "missing-deployment-lock":
        deliberately_changed.add(runtime.deployment_lock)
    if mutation == "missing-collection-lock":
        deliberately_changed.add(runtime.collection_lock)
    for path, expected in runtime.preserved.items():
        if path.exists() and path not in deliberately_changed:
            assert path.read_bytes() == expected


def test_claim_digest_pins_private_predecessor_bytes(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _authorize(runtime)
    runtime.collection_claim.write_bytes(runtime.collection_claim.read_bytes() + b" ")
    calls, transport = _transport_spy()
    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
    assert _run_error(runtime) == "LINEAGE_INVALID"
    assert calls == [] and not runtime.renewal_claim.exists()


@pytest.mark.parametrize("mutation", ["extra", "duplicate"])
def test_claim_closed_schema_rejects_extra_or_duplicate_even_with_matching_digest(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    if mutation == "extra":
        value = json.loads(runtime.collection_claim.read_text(encoding="utf-8"))
        value["extra"] = "denied"
        _write_json(runtime.collection_claim, value)
    else:
        text = runtime.collection_claim.read_text(encoding="utf-8")
        runtime.collection_claim.write_text(
            text.replace(
                '{"state":"consumed_before_transport",',
                '{"state":"consumed_before_transport","state":"consumed_before_transport",',
            ),
            encoding="utf-8",
        )
    _authorize(runtime)
    calls, transport = _transport_spy()
    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
    assert _run_error(runtime) == "LINEAGE_INVALID"
    assert calls == [] and not runtime.renewal_claim.exists()


@pytest.mark.parametrize("lock_name", ["deployment_lock", "collection_lock"])
def test_concurrent_lock_holder_blocks_without_consumption(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, lock_name: str
) -> None:
    _authorize(runtime)
    lock_path = getattr(runtime, lock_name)
    held = runtime.module._open_exclusive_existing_lock(lock_path)
    try:
        calls, transport = _transport_spy()
        monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
        assert _run_error(runtime) == "LOCK_UNAVAILABLE"
        assert calls == [] and not runtime.renewal_claim.exists()
    finally:
        runtime.module._release_lock(held)
    probe = runtime.module._open_exclusive_existing_lock(runtime.deployment_lock)
    runtime.module._release_lock(probe)
    _assert_preserved(runtime)


def test_lock_is_compatible_with_legacy_python_byte_range_holder(runtime: Runtime) -> None:
    with runtime.collection_lock.open("r+b", buffering=0) as legacy:
        legacy.seek(0)
        msvcrt.locking(legacy.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            with pytest.raises(runtime.module.CollectorError) as raised:
                runtime.module._open_exclusive_existing_lock(runtime.collection_lock)
            assert raised.value.code == "LOCK_UNAVAILABLE"
        finally:
            legacy.seek(0)
            msvcrt.locking(legacy.fileno(), msvcrt.LK_UNLCK, 1)


def test_reparse_lock_path_fails_before_consumption(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _authorize(runtime)
    calls, transport = _transport_spy()
    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
    original_stat = runtime.module.os.stat

    class ReparseStat:
        def __init__(self, wrapped: os.stat_result) -> None:
            self._wrapped = wrapped
            self.st_file_attributes = runtime.module.stat.FILE_ATTRIBUTE_REPARSE_POINT

        def __getattr__(self, name: str) -> object:
            return getattr(self._wrapped, name)

    def synthetic_stat(path: object, *args: object, **kwargs: object) -> object:
        result = original_stat(path, *args, **kwargs)
        if Path(path) == runtime.collection_root:
            return ReparseStat(result)
        return result

    with monkeypatch.context() as local:
        local.setattr(runtime.module.os, "stat", synthetic_stat)
        assert _run_error(runtime) == "LEDGER_INVALID"
    assert calls == [] and not runtime.renewal_claim.exists()


def test_lock_is_compatible_with_powershell_fileshare_none(runtime: Runtime) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")
    ready = runtime.repository / "lock-ready"
    stop = runtime.repository / "lock-stop"
    escaped_lock = str(runtime.deployment_lock).replace("'", "''")
    escaped_ready = str(ready).replace("'", "''")
    escaped_stop = str(stop).replace("'", "''")
    script = (
        f"$f=[IO.File]::Open('{escaped_lock}',[IO.FileMode]::Open,"
        "[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);"
        f"[IO.File]::WriteAllText('{escaped_ready}','ready');"
        f"while(-not (Test-Path -LiteralPath '{escaped_stop}'))"
        "{Start-Sleep -Milliseconds 20};$f.Dispose()"
    )
    process = subprocess.Popen(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    try:
        # Cold PowerShell startup on a hosted Windows worker can exceed five
        # seconds. Wait for its explicit ready signal before testing the lock;
        # the production lock denial and retry behavior are unchanged.
        deadline = time.monotonic() + 15
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "synthetic PowerShell lock holder did not signal readiness"
        with pytest.raises(runtime.module.CollectorError) as raised:
            runtime.module._open_exclusive_existing_lock(runtime.deployment_lock)
        assert raised.value.code == "LOCK_UNAVAILABLE"
    finally:
        stop.write_text("stop", encoding="ascii")
        process.wait(timeout=5)
    assert process.returncode == 0


def test_fsync_failure_leaves_attempt_consumed_and_no_retry(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _authorize(runtime)
    calls, transport = _transport_spy()
    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", transport)
    with monkeypatch.context() as local:
        local.setattr(runtime.module.os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError()))
        assert _run_error(runtime) == "CLAIM_WRITE_FAILED"
    assert runtime.renewal_claim.exists()
    assert calls == []
    assert _run_error(runtime) == "ATTEMPT_CONSUMED"
    assert calls == []
    _assert_preserved(runtime)


def test_launch_failure_consumes_once_without_cleanup_or_retry(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _authorize(runtime)
    calls: list[str] = []

    def fail(command: str, _expiry: datetime, _deadline: float) -> bytes:
        calls.append(command)
        raise runtime.module.CollectorError("TRANSPORT_LAUNCH_FAILED")

    monkeypatch.setattr(runtime.module, "_invoke_bounded_ssh", fail)
    assert _run_error(runtime) == "TRANSPORT_LAUNCH_FAILED"
    assert runtime.renewal_claim.exists() and len(calls) == 1
    assert _run_error(runtime) == "ATTEMPT_CONSUMED"
    assert len(calls) == 1
    _assert_preserved(runtime)


def test_consumed_slot_cannot_be_reset_by_new_uuid_or_commit(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _authorize(runtime)
    monkeypatch.setattr(
        runtime.module,
        "_invoke_bounded_ssh",
        lambda *_args: _valid_remote_output(runtime),
    )
    runtime.module._run()
    first_claim = runtime.renewal_claim.read_bytes()
    _authorize(
        runtime,
        authorization_id="33333333-3333-3333-3333-333333333333",
        repository_implementation_commit="d" * 40,
    )
    assert _run_error(runtime) == "ATTEMPT_CONSUMED"
    assert runtime.renewal_claim.read_bytes() == first_claim
    _assert_preserved(runtime)


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("launch-nonzero", "TRANSPORT_NONZERO"),
        ("stderr", "TRANSPORT_STDERR"),
        ("invalid-utf8", "TRANSPORT_UTF8_INVALID"),
        ("flood-stdout", "TRANSPORT_OUTPUT_LIMIT"),
        ("flood-stderr", "TRANSPORT_OUTPUT_LIMIT"),
        ("flood-both", "TRANSPORT_OUTPUT_LIMIT"),
    ],
)
def test_fake_transport_failure_is_bounded_consumed_and_not_retried(
    runtime: Runtime,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected: str,
) -> None:
    _authorize(runtime)
    call_file = runtime.repository / "calls.jsonl"
    monkeypatch.setenv("WP14_RENEWAL_SCENARIO", scenario)
    monkeypatch.setenv("WP14_RENEWAL_CALL_FILE", str(call_file))
    monkeypatch.setattr(runtime.module, "_ssh_prefix", lambda: [sys.executable, str(FAKE_SSH)])
    monkeypatch.setattr(runtime.module, "MAX_OUTPUT_BYTES", 8192)
    assert _run_error(runtime) == expected
    assert runtime.renewal_claim.exists()
    assert len(call_file.read_text(encoding="utf-8").splitlines()) == 1
    assert _run_error(runtime) == "ATTEMPT_CONSUMED"
    assert len(call_file.read_text(encoding="utf-8").splitlines()) == 1
    _assert_preserved(runtime)


def test_timeout_during_streaming_consumes_without_retry(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    _authorize(runtime)
    call_file = runtime.repository / "calls.jsonl"
    monkeypatch.setenv("WP14_RENEWAL_SCENARIO", "hang")
    monkeypatch.setenv("WP14_RENEWAL_CALL_FILE", str(call_file))
    monkeypatch.setattr(runtime.module, "_ssh_prefix", lambda: [sys.executable, str(FAKE_SSH)])
    monkeypatch.setattr(runtime.module, "MAX_WALL_SECONDS", 0.25)
    assert _run_error(runtime) == "TRANSPORT_TIMEOUT"
    assert runtime.renewal_claim.exists()
    assert len(call_file.read_text(encoding="utf-8").splitlines()) == 1
    _assert_preserved(runtime)


def test_activation_expiry_during_streaming_consumes_without_retry(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    _authorize(
        runtime,
        not_before=(now - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires_at=(now + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    call_file = runtime.repository / "calls.jsonl"
    monkeypatch.setenv("WP14_RENEWAL_SCENARIO", "hang")
    monkeypatch.setenv("WP14_RENEWAL_CALL_FILE", str(call_file))
    monkeypatch.setattr(runtime.module, "_ssh_prefix", lambda: [sys.executable, str(FAKE_SSH)])
    monkeypatch.setattr(runtime.module, "MAX_WALL_SECONDS", 5)
    assert _run_error(runtime) == "TRANSPORT_TIMEOUT"
    assert runtime.renewal_claim.exists()
    assert len(call_file.read_text(encoding="utf-8").splitlines()) == 1
    _assert_preserved(runtime)


@pytest.mark.parametrize(
    "scenario",
    [
        "wrong-host",
        "wrong-user",
        "wrong-root",
        "root-symlink",
        "missing-required",
        "bad-hash",
        "wrong-mode",
        "wrong-owner",
        "wrong-type",
        "wrong-links",
        "asset-symlink",
        "outside-root",
        "duplicate-index",
        "missing-line",
        "extra-line",
        "wrong-end",
        "protected-content",
    ],
)
def test_malformed_or_sensitive_remote_output_fails_closed_after_one_attempt(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    _authorize(runtime)
    call_file = runtime.repository / "calls.jsonl"
    monkeypatch.setenv("WP14_RENEWAL_SCENARIO", scenario)
    monkeypatch.setenv("WP14_RENEWAL_CALL_FILE", str(call_file))
    monkeypatch.setattr(runtime.module, "_ssh_prefix", lambda: [sys.executable, str(FAKE_SSH)])
    assert _run_error(runtime) == "EVIDENCE_INVALID"
    assert runtime.renewal_claim.exists()
    assert len(call_file.read_text(encoding="utf-8").splitlines()) == 1
    _assert_preserved(runtime)


def test_v1_is_never_overwritten_and_existing_v2_blocks_before_identity(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime.v2_evidence.write_bytes(b"preserved-v2-collision")
    monkeypatch.setattr(
        runtime.module,
        "_executor_binding",
        lambda: pytest.fail("identity must not be read on evidence collision"),
    )
    _authorize(runtime)
    assert _run_error(runtime) == "EVIDENCE_COLLISION"
    assert runtime.v2_evidence.read_bytes() == b"preserved-v2-collision"
    assert runtime.v1_evidence.read_bytes() == runtime.preserved[runtime.v1_evidence]
    assert not runtime.renewal_claim.exists()


def test_old_activation_or_active_recovery_authority_is_rejected(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = runtime.module.LEGACY_COLLECTION_AUTHORIZATION
    legacy.write_bytes(b"historical activation must remain absent")
    _authorize(runtime)
    assert _run_error(runtime) == "REPOSITORY_BOUNDARY_INVALID"
    assert not runtime.renewal_claim.exists()
    legacy.unlink()
    runtime.module.RECOVERY_AUTHORIZATION.write_bytes(b"synthetic active recovery authority")
    assert _run_error(runtime) == "REPOSITORY_BOUNDARY_INVALID"
    assert not runtime.renewal_claim.exists()
    monkeypatch.setattr(runtime.module.sys, "argv", ["collector", "unexpected"])
    assert _run_error(runtime) == "ARGUMENTS_REJECTED"


def test_repository_tamper_stops_before_identity_and_consumption(
    runtime: Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime.module.CONTRACT.write_text("tampered\n", encoding="utf-8")
    _authorize(runtime)
    monkeypatch.setattr(
        runtime.module,
        "_executor_binding",
        lambda: pytest.fail("identity must not be read after repository tamper"),
    )
    assert _run_error(runtime) == "REPOSITORY_BOUNDARY_INVALID"
    assert not runtime.renewal_claim.exists()


def test_public_evidence_filter_rejects_private_or_sensitive_fields(runtime: Runtime) -> None:
    evidence = {
        "schema_version": 2,
        "record_kind": "wp14_renewed_remote_identity_preimage_evidence",
        "renewal_contract_normalized_lf_sha256": "0" * 64,
        "source_package_normalized_lf_sha256": "0" * 64,
        "collector_normalized_lf_sha256": "0" * 64,
        "repository_implementation_commit": "0" * 40,
        "predecessor_evidence_normalized_lf_sha256": "0" * 64,
        "collection_started_at": "2026-09-28T00:00:00Z",
        "observed_at": "2026-09-28T00:00:00Z",
        "remote_identity": {},
        "preimages": [],
        "blockers": ["MachineGuid=SYNTHETIC_SECRET"],
    }
    with pytest.raises(runtime.module.CollectorError) as raised:
        runtime.module._assert_public_evidence(evidence)
    assert raised.value.code == "EVIDENCE_INVALID"
