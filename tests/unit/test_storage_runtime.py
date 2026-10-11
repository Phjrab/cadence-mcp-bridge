"""Exact packaged standalone assets; all remote operations are synthetic."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge import _storage_worker as worker
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.storage import StorageSnapshot, snapshot_digest
from cadence_mcp_bridge.storage_runtime import reference_storage_bundle


def test_reference_runtime_is_complete_deterministic_and_packaged() -> None:
    pin, payloads = reference_storage_bundle()
    assert (pin, payloads) == reference_storage_bundle()
    prefix = f"runtime/{pin}/"
    assert set(payloads) == {
        "run.sh", prefix + "storage.py", prefix + "reservations.py", prefix + "manifest.json",
    }
    manifest = json.loads(payloads[prefix + "manifest.json"])
    assert hashlib.sha256(payloads[prefix + "manifest.json"]).hexdigest() == pin
    assert manifest["kind"] == "REFERENCE_STORAGE_RUNTIME"
    for name, identity in manifest["files"].items():
        raw = payloads[prefix + name]
        assert identity == {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    assert payloads[prefix + "storage.py"] == Path(worker.__file__).read_bytes()
    assert b'"$RUNTIME/storage.py" "$2" "$3"' in payloads["run.sh"]
    assert b'"$RUNTIME/manifest.json"' in payloads["run.sh"]
    assert b'exec /usr/bin/python -E -s -B ' in payloads["run.sh"]


@pytest.mark.parametrize("pin", ["", "a" * 63, "A" * 64, "a" * 64 + ";echo", "$(id)"])
def test_reference_storage_pin_is_closed(pin: str) -> None:
    with pytest.raises(ValidationError):
        BridgeConfig(reference_storage_manifest_sha256=pin)
    with pytest.raises(ValidationError):
        BridgeConfig(runtime_mode="operator", reference_storage_manifest_sha256="a" * 64)


@pytest.mark.parametrize("pinned", [False, True])
async def test_storage_backend_routes_only_explicit_exact_pin(
    monkeypatch: pytest.MonkeyPatch, pinned: bool,
) -> None:
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.shutil.which", lambda _: "ssh")
    pin, _payloads = reference_storage_bundle()
    config = BridgeConfig(reference_storage_manifest_sha256=pin if pinned else None)
    backend = OpenSshBackend(config)
    invoke = Mock(return_value="{}")
    monkeypatch.setattr(backend, "_invoke_at_path", invoke)
    assert await backend._storage_request("inventory", {}) == "{}"
    runner = config.remote_root + f"/phase-campaign/storage-mgmt-v{7 if pinned else 6}/run.sh"
    expected = (runner, pin, "inventory", "7b7d") if pinned else (runner, "inventory", "7b7d")
    invoke.assert_called_once_with(*expected)


@pytest.fixture
def exact_posix_runtime(tmp_path: Path) -> tuple[Path, Path, str]:
    """Real code/hash/permissions/flock; only synthetic account/root constants vary."""
    if os.name == "nt":
        pytest.skip("Requires real Linux standalone layout; Ubuntu CI exercises it")
    from cadence_mcp_bridge import _shared_reservations as accounting

    root = tmp_path / "managed"
    root.mkdir(mode=0o700)
    for name in (
        "sim-mcp-v2-jobs", accounting.JOBS, accounting.REGISTRY, ".cadence_mcp-domain",
        worker.CONTROL, worker.SPOOL,
    ):
        (root / name).mkdir(mode=0o700)
    for name in ("registrations", "approvals", "operations"):
        (root / worker.CONTROL / name).mkdir(mode=0o700)
    campaign = str(uuid4())
    counter = dict(campaign_id=campaign, count=0, result_reserved_bytes=0)
    anchor = dict(
        schema_version=2, root_sha256=accounting.digest(str(root).encode()),
        resource_domain_sha256="a" * 64, ledger_ref=accounting.LEDGER,
        baseline=counter, legacy_operation_ids=[],
        policy=dict(campaign_id=campaign, attempt_ceiling=2, result_ceiling_bytes=131072),
    )
    records = {
        accounting.LEDGER: counter,
        accounting.REGISTRY + "/manifest.json": anchor,
        ".cadence_mcp-domain/manifest.json": dict(
            schema_version=1, root=str(root), resource_domain_sha256="a" * 64,
            identity_manifest_sha256=accounting.digest(accounting.canonical(anchor)),
            plan_sha256="b" * 64,
        ),
    }
    for name, value in records.items():
        path = root / name
        path.write_bytes(accounting.canonical(value))
        path.chmod(0o600)
    (root / "run.lock").write_bytes(b"retained-lock")
    (root / "run.lock").chmod(0o600)
    pin, payloads = reference_storage_bundle()
    version = tmp_path / "storage-mgmt-v7"
    for name, raw in payloads.items():
        path = version / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(raw)
        path.chmod(0o700 if name == "run.sh" else 0o600)
    return root, version / "runtime" / pin / "storage.py", pin


def standalone(
    root: Path, script: Path, action: str = "inventory", request: Any = None,
    environment: dict[str, str] | None = None,
) -> Any:
    # Exact deployment code is loaded as a script, with no package import path.
    # Bind only the disposable test root and isolated account-home fixture.
    harness = """
import json, runpy, sys
assert sys.flags.ignore_environment == 1
assert sys.flags.no_user_site == 1
assert sys.dont_write_bytecode
namespace = runpy.run_path(sys.argv[1], run_name='fixed_standalone_test')
assert namespace['__package__'] == ''
globals_ = namespace['main'].__globals__
original = globals_['PosixIO']
isolated_home = sys.argv[2]
class IsolatedAccount(original):
    def account_home(self):
        return isolated_home
globals_['PosixIO'] = IsolatedAccount
globals_['ROOT'] = sys.argv[2]
args = ['storage', sys.argv[3], sys.argv[4]]
sys.argv = args
namespace['main']()
"""
    return subprocess.run(
        [sys.executable, "-E", "-s", "-B", "-c", harness, str(script), str(root), action,
         worker.canonical({} if request is None else request).hex()],
        capture_output=True, check=False, timeout=30, env=environment, cwd=script.parent,
    )


def test_exact_empty_package_standalone_inventory_and_restart(
    exact_posix_runtime: tuple[Path, Path, str],
) -> None:
    root, script, _pin = exact_posix_runtime
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    for _attempt in range(2):
        reply = standalone(root, script)
        assert reply.returncode == 0, reply.stderr.decode()
        parsed = StorageSnapshot.model_validate_json(reply.stdout)
        assert parsed.snapshot_id == snapshot_digest(parsed)
        assert parsed.result_ceiling_bytes == 131072
        assert parsed.spectre_attempts == parsed.reserved_result_bytes == 0
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert not list(script.parent.glob("*.pyc"))


@pytest.mark.parametrize("change", ["missing", "changed", "manifest", "writable", "wrong-name"])
def test_exact_standalone_rejects_untrusted_accounting_before_import(
    exact_posix_runtime: tuple[Path, Path, str], change: str,
) -> None:
    root, script, _pin = exact_posix_runtime
    helper = script.with_name("reservations.py")
    if change == "missing":
        helper.rename(helper.with_suffix(".retained"))
    elif change == "changed":
        helper.write_bytes(b"raise AssertionError('untrusted import executed')\n")
    elif change == "manifest":
        manifest = script.with_name("manifest.json")
        manifest.write_bytes(b'{}')
    elif change == "writable":
        helper.chmod(0o620)
    else:
        wrong = script.with_name("worker.py")
        script.rename(wrong)
        script = wrong
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    reply = standalone(root, script)
    assert reply.returncode != 0
    assert b"untrusted import executed" not in reply.stderr
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


async def test_backend_pin_to_exact_standalone_production_layout(
    exact_posix_runtime: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, script, pin = exact_posix_runtime
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.shutil.which", lambda _: "ssh")
    backend = OpenSshBackend(BridgeConfig(reference_storage_manifest_sha256=pin))
    calls = []

    def transport(runner: str, manifest_pin: str, action: str, encoded: str) -> str:
        assert runner.endswith("/storage-mgmt-v7/run.sh") and manifest_pin == pin
        calls.append((action, encoded))
        reply = standalone(root, script, action, json.loads(bytes.fromhex(encoded)))
        assert reply.returncode == 0, reply.stderr.decode()
        return reply.stdout.decode()

    monkeypatch.setattr(backend, "_invoke_at_path", transport)
    result = await backend.storage_snapshot()
    assert result.result_ceiling_bytes == 131072 and calls == [("inventory", "7b7d")]



def test_exact_standalone_cleanup_dry_run_keeps_payload_ledger_and_restart(
    exact_posix_runtime: tuple[Path, Path, str],
) -> None:
    root, script, _pin = exact_posix_runtime
    identity = str(uuid4())
    disposable = root / worker.SPOOL / identity
    disposable.mkdir(mode=0o700)
    payload = disposable / "payload.bin"
    payload.write_bytes(b"synthetic disposable" * 100)
    payload.chmod(0o600)
    io = worker.PosixIO()
    fd = io.root(str(disposable))
    try:
        fingerprint, _info, content = worker.payload_fingerprint(io, fd, [0])
    finally:
        os.close(fd)
    record = dict(
        contract_version=1, artifact_uuid=identity, analysis_type="tran",
        measurement_extracted=True, replay_dependency=False, evidence_dependency=False,
        active_dependency=False, fingerprint=fingerprint, content_sha256=content,
    )
    registration = root / worker.CONTROL / "registrations" / (identity + ".json")
    registration.write_bytes(worker.canonical(record))
    registration.chmod(0o600)
    reply = standalone(root, script)
    assert reply.returncode == 0, reply.stderr.decode()
    snapshot = json.loads(reply.stdout)
    selection = dict(snapshot_id=snapshot["snapshot_id"], artifact_ids=[
        "sa-" + worker.digest(["disposable", identity]),
    ])
    plan = worker.plan(snapshot, selection)
    request = dict(
        selection=selection, cleanup_plan_id=plan["cleanup_plan_id"],
        plan_sha256=plan["plan_sha256"], selected_artifact_ids=selection["artifact_ids"],
        operation_id=str(uuid4()), dry_run=True,
    )
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    for _retry in range(2):
        result = standalone(root, script, "cleanup", request)
        assert result.returncode == 0, result.stderr.decode()
        outcome = json.loads(result.stdout)
        assert outcome["state"] == "DRY_RUN" and outcome["removed_artifact_ids"] == []
        assert outcome["reservation_refunded_bytes"] == 0
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert not list((root / worker.CONTROL / "operations").iterdir())



def test_exact_standalone_ignores_python_environment_and_user_site(
    exact_posix_runtime: tuple[Path, Path, str], tmp_path: Path,
) -> None:
    root, script, _pin = exact_posix_runtime
    overrides = tmp_path / "untrusted-python"
    overrides.mkdir(mode=0o700)
    marker = overrides / "executed.private"
    malicious = f"open({str(marker)!r}, 'w').write('untrusted')\nraise RuntimeError('override')\n"
    for name in ("sitecustomize.py", "usercustomize.py", "json.py", "hashlib.py", "types.py"):
        (overrides / name).write_text(malicious, encoding="utf-8")
    environment = dict(os.environ)
    environment.update(PYTHONPATH=str(overrides), PYTHONUSERBASE=str(overrides),
                       PYTHONSTARTUP=str(overrides / "sitecustomize.py"))
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    reply = standalone(root, script, environment=environment)
    assert reply.returncode == 0, reply.stderr.decode()
    assert not marker.exists()
    parsed = StorageSnapshot.model_validate_json(reply.stdout)
    assert parsed.result_ceiling_bytes == 131072 and parsed.spectre_attempts == 0
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
