"""Synthetic stdio observation tests; no Cadence or actual desktop evidence."""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "client_stdio_observer", ROOT / "scripts/observe_client_stdio.py"
)
assert SPEC and SPEC.loader
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


@pytest.mark.parametrize("handshake", ["initialize", "server/discover"])
def test_transparent_frames_metadata_hashes_and_eof(tmp_path: Path, handshake: str) -> None:
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": handshake, "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "cadence_read", "arguments": {"opaque_id": "private-input"}}},
    ]
    code = """
import sys,json
for line in sys.stdin.buffer:
 m=json.loads(line)
 if 'id' not in m:continue
 if m['method'] in ['initialize','server/discover']:
  result={'serverInfo':{'name':'fixture','version':'1'},'protocolVersion':'2025-11-25'}
 elif m['method']=='tools/list':
  result={'tools':[{'name':'cadence_read','inputSchema':{'type':'object'}}]}
 else:result={'structuredContent':{'private_value':'private-result'},'isError':False}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
sys.stderr.write('private-stderr')
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    incoming = io.BytesIO(b"".join(observer.canonical(r) + b"\n" for r in requests))
    outgoing = io.BytesIO()
    errors = io.BytesIO()
    path = tmp_path / "audit.jsonl"
    with path.open("xb") as stream:
        audit = observer.Audit(stream, {"cadence_read"})
        assert observer.observe(child, audit, incoming, outgoing, errors) == 0
    responses = [json.loads(line) for line in outgoing.getvalue().splitlines()]
    assert [r["id"] for r in responses] == [1, 2, 3]
    assert responses[2]["result"]["structuredContent"]["private_value"] == "private-result"
    assert errors.getvalue() == b"private-stderr"
    raw = path.read_text()
    secrets = ["private-input", "private-result", "private-stderr"]
    assert not any(secret in raw for secret in secrets)
    records = [json.loads(line) for line in raw.splitlines()]
    response_records = [r for r in records if r["event"] == "server_response"]
    field = "initialize_result" if handshake == "initialize" else "discover_result"
    assert response_records[0][field] == responses[0]["result"]
    assert response_records[1]["tools_list_result"] == responses[1]["result"]
    assert response_records[2]["structured_content_sha256"] == observer.digest(
        responses[2]["result"]["structuredContent"]
    )
    assert any(r["event"] == "client_stdin_eof" for r in records)
    assert any(r["event"] == "child_stdout_eof" for r in records)
    assert records[-1]["event"] == "child_exit"
    assert records[-1]["return_code"] == 0 and records[-1]["normal_stdin_eof"]


@pytest.mark.parametrize("line", [
    b"not-json\n", b'{"jsonrpc":"1.0"}\n', b'{"jsonrpc":"2.0"}',
    b'{"jsonrpc":"2.0","value":NaN}\n',
])
def test_malformed_or_incomplete_frame_rejected(line: bytes) -> None:
    with pytest.raises((ValueError, json.JSONDecodeError)):
        observer.read_message(io.BytesIO(line))


def test_line_bound_and_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observer, "MAX_LINE", 8)
    with pytest.raises(ValueError):
        observer.read_message(io.BytesIO(b"123456789\n"))
    assert observer.read_message(io.BytesIO()) is None


def test_duplicate_and_pending_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with (tmp_path / "audit").open("xb") as stream:
        audit = observer.Audit(stream, {"cadence_read"})
        request = {"jsonrpc": "2.0", "method": "ping", "id": 1}
        audit.request(request)
        with pytest.raises(ValueError):
            audit.request(request)
        monkeypatch.setattr(observer, "MAX_PENDING", 1)
        with pytest.raises(ValueError):
            audit.request({**request, "id": 2})


def test_audit_limits_and_payload_minimization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (tmp_path / "audit").open("xb") as stream:
        audit = observer.Audit(stream, {"cadence_read"})
        monkeypatch.setattr(observer, "MAX_EVENTS", 1)
        audit.request({"jsonrpc": "2.0", "method": "secret-method", "params": {
            "name": "secret-tool", "token": "secret-token",
        }})
        with pytest.raises(ValueError):
            audit.write("overflow")
    content = (tmp_path / "audit").read_text()
    assert not any(value in content for value in ["secret-method", "secret-tool", "secret-token"])
    monkeypatch.setattr(observer, "MAX_AUDIT", 1)
    with (tmp_path / "small").open("xb") as stream, pytest.raises(ValueError):
        observer.Audit(stream, set()).write("event")
    assert (tmp_path / "small").stat().st_size == 0


def test_source_manifest_only_fixed_public_inputs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("x=1")
    (tmp_path / "src/private.txt").write_text("excluded")
    (tmp_path / "pyproject.toml").write_text("test")
    (tmp_path / "uv.lock").write_text("test")
    manifest = observer.source_manifest(tmp_path)
    assert set(manifest) == {"src/a.py", "pyproject.toml", "uv.lock"}
    old = observer.digest(manifest)
    (tmp_path / "src/a.py").write_text("x=2")
    assert observer.digest(observer.source_manifest(tmp_path)) != old


def test_audit_sessions_exclusive_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(observer, "AUDIT_ROOT", tmp_path / "runs")
    monkeypatch.setattr(observer, "MAX_SESSIONS", 2)
    with observer.reserve_audit() as first:
        first.write(b"preserved")
    with observer.reserve_audit() as second:
        second.write(b"second")
    with pytest.raises(ValueError):
        observer.reserve_audit()
    assert (tmp_path / "runs/session-01.private.jsonl").read_bytes() == b"preserved"


def test_missing_activation_fails_before_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(observer, "ACTIVATION", tmp_path / "missing")
    with pytest.raises(ValueError):
        observer.validate_activation()


def test_invalid_child_output_kills_child_and_preserves_audit(tmp_path: Path) -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "print('not protocol',flush=True)"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    with (tmp_path / "audit").open("xb") as stream, pytest.raises(ValueError):
        observer.observe(
            child, observer.Audit(stream, set()), io.BytesIO(), io.BytesIO(), io.BytesIO(),
        )
    assert child.poll() is not None


def test_fixed_child_has_no_caller_script_command_or_path() -> None:
    source = (ROOT / "scripts/observe_client_stdio.py").read_text()
    assert '[sys.executable, "-m", "cadence_mcp_bridge", "serve"]' in source
    assert "argparse" not in source and "sys.argv" not in source
    assert "shell=True" not in source and "os.environ" not in source


def test_activation_source_and_authority_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib

    (tmp_path / "src").mkdir()
    for name in ["src/a.py", "pyproject.toml", "uv.lock"]:
        (tmp_path / name).write_text("test")
    activation = tmp_path / "activation.json"
    record = {
        "phase": "CLIENT-LIFECYCLE-QUAL-01", "user_delegation": "explicit-current-task",
        "observer_sha256": hashlib.sha256(Path(observer.__file__).read_bytes()).hexdigest(),
        "source_manifest": observer.source_manifest(tmp_path),
        "interpreter_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        "enabled_read_tools": [f"cadence_read_{i}" for i in range(26)],
        "expected_tool_schemas_sha256": "a" * 64,
        "new_simulations": 0, "deletion_authority": False,
    }
    monkeypatch.setattr(observer, "ROOT", tmp_path)
    monkeypatch.setattr(observer, "ACTIVATION", activation)
    activation.write_text(json.dumps(record))
    assert observer.validate_activation() == record
    for key, value in [
        ("user_delegation", "repository-only"),
        ("interpreter_sha256", "0" * 64), ("observer_sha256", "0" * 64),
        ("deletion_authority", True), ("new_simulations", 1),
        ("enabled_read_tools", ["cadence_execute_storage_cleanup"] * 26),
    ]:
        activation.write_text(json.dumps({**record, key: value}))
        with pytest.raises(ValueError):
            observer.validate_activation()
    activation.write_text(json.dumps(record))
    (tmp_path / "src/a.py").write_text("changed")
    with pytest.raises(ValueError):
        observer.validate_activation()


def test_startup_audit_failure_cleans_spawned_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    monkeypatch.setattr(observer, "validate_activation", lambda: {
        "enabled_read_tools": ["cadence_read"], "source_manifest": {},
        "interpreter_sha256": "a" * 64, "observer_sha256": "b" * 64,
        "expected_tool_schemas_sha256": "c" * 64,
    })
    monkeypatch.setattr(observer, "reserve_audit", lambda: (tmp_path / "audit").open("xb"))
    monkeypatch.setattr(observer, "MAX_EVENTS", 0)
    child = MagicMock()
    child.poll.return_value = None
    monkeypatch.setattr(observer.subprocess, "Popen", lambda *args, **kwargs: child)
    assert observer.main() == 1
    child.kill.assert_called_once()
    child.wait.assert_called_once_with(timeout=10)
