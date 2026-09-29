from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import msvcrt
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/verify-wp14-renewal-local.py"
WORKER = ROOT / "tests/fixtures/wp14_local_preflight_worker.py"
IDENTITY = ("synthetic-operator", "synthetic-operator", "11111111-2222-3333-4444-555555555555")


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("wp14_local_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw.decode("utf-8").replace("\r\n", "\n").encode()).hexdigest()


@pytest.fixture
def fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    module = load()
    repository = tmp_path / "repository"
    deployment = tmp_path / "private/deployment"
    collection = tmp_path / "private/collection"
    for folder in (repository, deployment, collection):
        folder.mkdir(parents=True)
    monkeypatch.setattr(module, "ROOT", repository)
    # All public contents and all identities are synthetic; no production provider runs.
    hashes = {}
    for relative in module.PUBLIC_HASHES:
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic fixture\n")
        hashes[relative] = digest(path.read_bytes())
    monkeypatch.setattr(module, "PUBLIC_HASHES", hashes)
    lineage = repository / "remote/config/runner-lineage.json"
    lineage.parent.mkdir(parents=True)
    lineage.write_bytes(b'{"deployment_enabled":false}')
    activation = repository / module.DEPLOYMENT_AUTHORIZATION
    activation.write_bytes(b'{"synthetic":"preserved consumed activation"}')
    monkeypatch.setattr(module, "DEPLOYMENT_AUTHORIZATION_HASH", digest(activation.read_bytes()))
    monkeypatch.setattr(module, "_read_identity", lambda: IDENTITY)
    monkeypatch.setattr(module, "_private_roots", lambda: (deployment, collection))

    def forbid(*args, **kwargs):
        raise AssertionError("forbidden external process")

    monkeypatch.setattr(module.subprocess, "Popen", forbid)
    claims = []
    for is_deployment, parent, filename in (
        (False, collection, module.COLLECTION_CLAIM),
        (True, deployment, module.DEPLOYMENT_CLAIM),
    ):
        path = parent / filename
        record = {
            "state": "consumed_before_transport",
            "authorization_id": module.DEPLOYMENT_ID
            if is_deployment
            else "1" * 8 + "-1111" * 3 + "-" + "1" * 12,
            "authorization_sha256": module.DEPLOYMENT_AUTHORIZATION_HASH
            if is_deployment
            else module.COLLECTION_AUTHORIZATION_HASH,
            "package_sha256": hashes[
                module.DEPLOYMENT_PACKAGE if is_deployment else module.PACKAGE
            ],
            "deployer_sha256" if is_deployment else "collector_sha256": hashes[
                module.DEPLOYER if is_deployment else module.OLD_COLLECTOR
            ],
            "consumed_at": module.DEPLOYMENT_CONSUMED_AT
            if is_deployment
            else "2026-09-17T08:05:01Z",
        }
        path.write_text(json.dumps(record), encoding="utf-8")
        claims.append(path)
    for parent in (deployment, collection):
        (parent / "operation.lock").write_bytes(b"" if parent == deployment else b"\0")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    return SimpleNamespace(
        module=module,
        root=tmp_path,
        repo=repository,
        deployment=deployment,
        collection=collection,
        lineage=lineage,
        activation=activation,
        claims=claims,
        before=before,
    )


def assert_preserved(fixture: SimpleNamespace) -> None:
    assert {p: p.read_bytes() for p in fixture.root.rglob("*") if p.is_file()} == fixture.before


def test_local_success_is_read_only(fixture: SimpleNamespace) -> None:
    fixture.module._check()
    assert_preserved(fixture)
    # Compatible empty deployment and one-byte legacy collection locks are reusable,
    # but no attempt slot is created or consumed by this check.
    fixture.module._check()
    assert_preserved(fixture)


def test_lock_order_and_reverse_release(fixture: SimpleNamespace, monkeypatch: pytest.MonkeyPatch):
    import contextlib

    module = fixture.module
    held = module._held_lock
    calls = []

    @contextlib.contextmanager
    def observed(path):
        with held(path):
            calls.append(("enter", path.parent.name))
            try:
                yield
            finally:
                calls.append(("exit", path.parent.name))

    monkeypatch.setattr(module, "_held_lock", observed)
    module._check()
    assert calls == [
        ("enter", "deployment"),
        ("enter", "collection"),
        ("exit", "collection"),
        ("exit", "deployment"),
    ]
    assert_preserved(fixture)


@pytest.mark.parametrize("which", ["deployment", "collection"])
def test_existing_lock_contention(fixture, which):
    module = fixture.module
    with (
        module._held_lock(getattr(fixture, which) / "operation.lock"),
        pytest.raises(module.CheckError, match="LOCK_UNAVAILABLE"),
    ):
        module._check()
    module._check()
    assert_preserved(fixture)


@pytest.mark.parametrize("which", ["deployment", "collection"])
def test_legacy_byte_lock_compatible(fixture, which):
    path = getattr(fixture, which) / "operation.lock"
    with path.open("r+b") as holder:
        msvcrt.locking(holder.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            with pytest.raises(fixture.module.CheckError, match="LOCK_UNAVAILABLE"):
                fixture.module._check()
        finally:
            holder.seek(0)
            msvcrt.locking(holder.fileno(), msvcrt.LK_UNLCK, 1)
    assert_preserved(fixture)


@pytest.mark.parametrize("which", ["deployment", "collection"])
def test_missing_lock_is_not_created(fixture, which):
    path = getattr(fixture, which) / "operation.lock"
    path.unlink()  # Synthetic temporary fixture only.
    fixture.before.pop(path)
    with pytest.raises(fixture.module.CheckError, match="LOCK_UNAVAILABLE"):
        fixture.module._check()
    assert_preserved(fixture)


@pytest.mark.parametrize("index", range(6))
@pytest.mark.parametrize("content", [b"", b"partial"])
def test_collisions_never_reset_or_fallback(fixture, index, content):
    module = fixture.module
    paths = [
        *(fixture.repo / p for p in module.ABSENT_REPOSITORY),
        fixture.deployment / "recovery-v1.json",
        fixture.collection / "collection-renewal-v1.json",
    ]
    paths[index].write_bytes(content)
    fixture.before[paths[index]] = content
    with pytest.raises(module.CheckError, match="COLLISION"):
        module._check()
    assert_preserved(fixture)


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "extra",
        "wrong_type",
        "wrong_state",
        "wrong_hash",
        "wrong_id",
        "wrong_time",
        "future",
        "naive",
        "duplicate",
        "invalid_utf8",
        "oversize",
        "empty",
        "partial",
    ],
)
@pytest.mark.parametrize("index", [0, 1])
def test_invalid_claim_fail_closed(fixture, index, change):
    path = fixture.claims[index]
    record = json.loads(path.read_text(encoding="utf-8"))
    if change == "missing":
        record.pop("state")
    elif change == "extra":
        record["unexpected"] = "x"
    elif change == "wrong_type":
        record["authorization_id"] = 1
    elif change == "wrong_state":
        record["state"] = "available"
    elif change == "wrong_hash":
        record["package_sha256"] = "a" * 64
    elif change == "wrong_id":
        record["authorization_id"] = "not-a-uuid"
    elif change == "wrong_time":
        record["consumed_at"] = "not-a-time"
    elif change == "future":
        record["consumed_at"] = "2999-01-01T00:00:00Z"
    elif change == "naive":
        record["consumed_at"] = "2026-09-17T00:00:00"
    raw = json.dumps(record).encode()
    if change == "duplicate":
        raw = raw[:-1] + b',"STATE":"consumed_before_transport"}'
    raw = {"invalid_utf8": b"\xff", "oversize": b"x" * 4097, "empty": b"", "partial": b"{"}.get(
        change, raw
    )
    path.write_bytes(raw)
    fixture.before[path] = raw
    with pytest.raises((fixture.module.CheckError, ValueError, UnicodeError)):
        fixture.module._check()
    assert_preserved(fixture)


@pytest.mark.parametrize(
    "identity",
    [
        ("", "", IDENTITY[2]),
        ("spoof", "native", IDENTITY[2]),
        ("bad|name", "bad|name", IDENTITY[2]),
        ("bad\nname", "bad\nname", IDENTITY[2]),
        ("x" * 257, "x" * 257, IDENTITY[2]),
        (IDENTITY[0], IDENTITY[1], "not-guid"),
        (1, 1, IDENTITY[2]),
        (IDENTITY[0], IDENTITY[1], None),
    ],
)
def test_identity_rejected_without_output(fixture, monkeypatch, identity):
    monkeypatch.setattr(fixture.module, "_read_identity", lambda: identity)
    with pytest.raises(fixture.module.CheckError, match="IDENTITY_INVALID"):
        fixture.module._check()
    assert_preserved(fixture)


def test_binding_rule_exact_unicode_and_no_normalization():
    module = load()
    identity = ("테스트", "테스트", IDENTITY[2].upper())
    assert (
        module._binding(identity)
        == hashlib.sha256((identity[0] + "|" + identity[2]).encode("utf-8")).digest()
    )


def test_identity_drift(fixture, monkeypatch):
    identities = iter([IDENTITY, ("second", "second", IDENTITY[2])])
    monkeypatch.setattr(fixture.module, "_read_identity", lambda: next(identities))
    with pytest.raises(fixture.module.CheckError, match="IDENTITY_INVALID"):
        fixture.module._check()
    assert_preserved(fixture)


@pytest.mark.parametrize("kind", ["claim", "activation", "public", "lineage", "collision"])
def test_mid_check_drift_cannot_succeed(fixture, monkeypatch, kind):
    calls = 0

    def identity():
        nonlocal calls
        calls += 1
        if calls == 2:
            path = {
                "claim": fixture.claims[0],
                "activation": fixture.activation,
                "public": fixture.repo / fixture.module.CONTRACT,
                "lineage": fixture.lineage,
                "collision": fixture.collection / "collection-renewal-v1.json",
            }[kind]
            path.write_bytes(b"synthetic concurrent mutation")
        return IDENTITY

    monkeypatch.setattr(fixture.module, "_read_identity", identity)
    with pytest.raises(fixture.module.CheckError, match="CHANGED|COLLISION"):
        fixture.module._check()


def test_disabled_gate_required(fixture):
    fixture.lineage.write_bytes(b'{"deployment_enabled":true}')
    with pytest.raises(fixture.module.CheckError, match="REPOSITORY_INVALID"):
        fixture.module._check()


def test_public_hash_tamper(fixture):
    (fixture.repo / fixture.module.CONTRACT).write_bytes(b"changed")
    with pytest.raises(fixture.module.CheckError, match="REPOSITORY_INVALID"):
        fixture.module._check()


def test_private_activation_tamper(fixture):
    fixture.activation.write_bytes(b"changed")
    with pytest.raises(fixture.module.CheckError, match="LINEAGE_INVALID"):
        fixture.module._check()


def test_leaf_hardlink_rejected(fixture):
    os.link(fixture.claims[0], fixture.root / "extra-hardlink")
    with pytest.raises(fixture.module.CheckError, match="PATH_INVALID"):
        fixture.module._check()


def test_reparse_attributes_rejected(fixture, monkeypatch):
    module = fixture.module
    original = Path.lstat

    def attributes(path):
        if path == fixture.collection:
            return SimpleNamespace(st_file_attributes=module.stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return original(path)

    monkeypatch.setattr(Path, "lstat", attributes)
    with pytest.raises(module.CheckError, match="PATH_INVALID"):
        module._check()


def test_bounded_reads(fixture):
    path = fixture.claims[0]
    with pytest.raises(fixture.module.CheckError, match="LINEAGE_INVALID"):
        fixture.module._read(path, 3)


@pytest.mark.parametrize("code", ["LOCAL_PREFLIGHT_READY", "TIMEOUT", "synthetic-private-canary"])
def test_closed_envelope(code):
    module = load()
    raw = module._envelope(code)
    value = json.loads(raw)
    assert set(value) == {"success", "code"}
    assert type(value["success"]) is bool
    assert value["code"] in module.ERRORS | {module.SUCCESS}
    assert len(raw) <= 512
    assert b"synthetic-private-canary" not in raw


def test_main_argument_rejection_before_private_or_child(monkeypatch, capsys):
    module = load()
    monkeypatch.setattr(module.sys, "argv", ["checker", "--help"])
    monkeypatch.setattr(module, "_supervise", lambda: pytest.fail("must not launch"))
    assert module.main() == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {"success": False, "code": "ARGUMENTS_REJECTED"}
    assert output.err == ""


def test_worker_sanitizes_private_exception(fixture, monkeypatch, capsys):
    def fail():
        raise RuntimeError("synthetic-private-canary")

    monkeypatch.setattr(fixture.module, "_check", fail)
    assert fixture.module._worker() == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {"success": False, "code": "INTERNAL_ERROR"}
    assert output.err == ""
    assert_preserved(fixture)


def test_worker_synthetic_success(fixture, capsys):
    assert fixture.module._worker() == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {"success": True, "code": "LOCAL_PREFLIGHT_READY"}
    assert len(output.out.encode()) <= 512 and output.err == ""
    assert_preserved(fixture)


def test_main_sanitizes_launch_failure(monkeypatch, capsys):
    module = load()
    monkeypatch.setattr(module.sys, "argv", ["checker"])

    def fail(*args, **kwargs):
        raise OSError("synthetic-private-canary")

    monkeypatch.setattr(module.subprocess, "Popen", fail)
    assert module.main() == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {"success": False, "code": "INTERNAL_ERROR"}
    assert output.err == ""


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("success", "LOCAL_PREFLIGHT_READY"),
        ("failure", "LINEAGE_INVALID"),
        ("extra", "WORKER_FAILED"),
        ("secret", "WORKER_FAILED"),
        ("invalid_utf8", "WORKER_FAILED"),
        ("exact_limit", "WORKER_FAILED"),
        ("over_limit", "OUTPUT_LIMIT"),
        ("stderr", "WORKER_FAILED"),
        ("flood", "OUTPUT_LIMIT"),
        ("stderr_flood", "OUTPUT_LIMIT"),
        ("timeout", "TIMEOUT"),
        ("partial_timeout", "TIMEOUT"),
        ("wrong_exit", "WORKER_FAILED"),
        ("empty", "WORKER_FAILED"),
    ],
)
def test_supervisor_fake_local_child_only(monkeypatch, mode, expected):
    module = load()
    real_popen = subprocess.Popen
    children = []

    def launch(argv, **kwargs):
        assert argv[:3] == [sys.executable, "-I", "-B"]
        assert "runpy.run_path" in argv[4]
        assert "verify-wp14-renewal-local.py" in argv[4]
        assert kwargs["shell"] is False
        child = real_popen([sys.executable, "-I", "-B", str(WORKER), mode], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(module.subprocess, "Popen", launch)
    monkeypatch.setattr(module, "MAX_SECONDS", 2)
    start = time.monotonic()
    assert module._supervise() == expected
    assert time.monotonic() - start < 3.5
    assert len(children) == 1 and children[0].poll() is not None


def test_launch_delay_counts_against_deadline(monkeypatch):
    module = load()
    real_popen = subprocess.Popen
    children = []

    def launch(argv, **kwargs):
        time.sleep(0.3)
        child = real_popen([sys.executable, "-I", "-B", str(WORKER), "timeout"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(module.subprocess, "Popen", launch)
    monkeypatch.setattr(module, "MAX_SECONDS", 0.1)
    assert module._supervise() == "TIMEOUT"
    assert len(children) == 1 and children[0].poll() is not None


def test_default_ten_second_deadline_fake_child(monkeypatch):
    module = load()
    real_popen = subprocess.Popen
    children = []

    def launch(argv, **kwargs):
        child = real_popen([sys.executable, "-I", "-B", str(WORKER), "timeout"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(module.subprocess, "Popen", launch)
    started = time.monotonic()
    assert module._supervise() == "TIMEOUT"
    # The ten-second budget reserves 0.75 seconds for termination/reaping.
    assert 9 <= time.monotonic() - started < 10
    assert len(children) == 1 and children[0].poll() is not None


def test_repository_contract_static_only():
    module = load()
    assert module.MAX_SECONDS == 10 and module.MAX_OUTPUT == 512
    for relative, expected in module.PUBLIC_HASHES.items():
        assert module._normalized((ROOT / relative).read_bytes()) == expected
    tree = ast.parse(CHECKER.read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any("collector" in str(name) or "deploy" in str(name) for name in imports)
    calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    for forbidden in ("mkdir", "unlink", "rename", "replace", "write_bytes", "write_text"):
        if forbidden == "replace":  # String newline normalization, not file replacement.
            continue
        assert forbidden not in calls
    assert calls.count("Popen") == 1
