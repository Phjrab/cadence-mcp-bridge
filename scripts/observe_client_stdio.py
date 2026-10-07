"""Operator-only bounded stdio observation; never an MCP execution interface.

The fixed child is the existing bridge serve command. A private, hash-bound
activation is required. Tool-call payloads, stderr, environment and paths are
not copied into the audit. initialize/tools/list responses are protocol evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

ROOT = Path(__file__).resolve().parents[1]
ACTIVATION = ROOT / ".codex/client-lifecycle01-observer-activation-v3.private.json"
AUDIT_ROOT = ROOT / ".codex/client-lifecycle01-observer"
MAX_LINE = 1024 * 1024
MAX_AUDIT = 4 * 1024 * 1024
MAX_EVENTS = 256
MAX_PENDING = 64
MAX_SESSIONS = 4


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def source_manifest(root: Path) -> dict[str, str]:
    """Fingerprint only fixed public Python sources and packaging inputs."""
    names = sorted(
        [p.relative_to(root).as_posix() for p in (root / "src").rglob("*.py")]
        + ["pyproject.toml", "uv.lock"]
    )
    if len(names) > 256:
        raise ValueError("source count exceeds bound")
    result = {}
    total = 0
    for name in names:
        path = root / name
        if path.is_symlink() or any(
            p.is_symlink() or p.is_junction() for p in [path, *path.parents] if p != root
        ):
            raise ValueError("linked source")
        with path.open("rb") as source:
            data = source.read(8 * 1024 * 1024 + 1)
        total += len(data)
        if total > 8 * 1024 * 1024:
            raise ValueError("source bytes exceed bound")
        result[name] = hashlib.sha256(data).hexdigest()
    return result


class Audit:
    def __init__(self, stream: BinaryIO, read_tools: set[str]) -> None:
        self.stream = stream
        self.read_tools = read_tools
        self.lock = threading.Lock()
        self.pending: dict[str, tuple[str, str | None]] = {}
        self.events = 0
        self.bytes = 0

    def _write(self, event: str, **fields: Any) -> None:
        data = canonical(
            {"event": event, "timestamp": datetime.now(UTC).isoformat(), **fields}
        ) + b"\n"
        if self.events >= MAX_EVENTS or self.bytes + len(data) > MAX_AUDIT:
            raise ValueError("audit bound reached")
        self.stream.write(data)
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.events += 1
        self.bytes += len(data)

    def write(self, event: str, **fields: Any) -> None:
        with self.lock:
            self._write(event, **fields)

    def request(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if not isinstance(method, str):
            return
        params = message.get("params", {})
        tool = params.get("name") if isinstance(params, dict) else None
        if tool not in self.read_tools:
            tool = None
        with self.lock:
            if "id" in message:
                key = digest(message["id"])
                if len(self.pending) >= MAX_PENDING or key in self.pending:
                    raise ValueError("pending identity bound or duplicate")
                self.pending[key] = (method, tool)
            self._write(
                "client_request",
                method=method if method in {
                    "initialize", "server/discover", "tools/list", "tools/call", "ping"
                }
                else "other",
                tool_name=tool,
                message_sha256=digest(message),
            )

    def response(self, message: dict[str, Any]) -> None:
        with self.lock:
            key = digest(message.get("id"))
            method, tool = self.pending.pop(key, ("notification", None))
            fields: dict[str, Any] = {
                "method": method if method in {
                    "initialize", "server/discover", "tools/list", "tools/call", "ping"
                }
                else "other",
                "tool_name": tool,
                "message_sha256": digest(message),
            }
            result = message.get("result")
            if method in {"initialize", "server/discover"} and isinstance(result, dict):
                key = "initialize_result" if method == "initialize" else "discover_result"
                fields[key] = result
            elif method == "tools/list" and isinstance(result, dict):
                fields["tools_list_result"] = result
            elif method == "tools/call" and isinstance(result, dict):
                fields["result_sha256"] = digest(result)
                if "structuredContent" in result:
                    fields["structured_content_sha256"] = digest(result["structuredContent"])
                fields["is_error"] = result.get("isError", False)
            self._write("server_response", **fields)


def read_message(stream: BinaryIO) -> tuple[bytes, dict[str, Any]] | None:
    line = stream.readline(MAX_LINE + 1)
    if not line:
        return None
    if len(line) > MAX_LINE or not line.endswith(b"\n"):
        raise ValueError("protocol line exceeds bound or is incomplete")
    value = json.loads(line)
    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
        raise ValueError("invalid protocol envelope")
    canonical(value)  # Reject nonfinite JSON before forwarding.
    return line, value


def validate_activation() -> dict[str, Any]:
    if (
        ACTIVATION.parent.is_symlink() or ACTIVATION.parent.is_junction()
        or ACTIVATION.is_symlink() or not ACTIVATION.is_file()
    ):
        raise ValueError("private activation missing")
    data = ACTIVATION.read_bytes()
    if len(data) > 65536:
        raise ValueError("activation too large")
    value = json.loads(data)
    expected = {
        "phase", "user_delegation", "observer_sha256", "source_manifest",
        "interpreter_sha256", "enabled_read_tools", "expected_tool_schemas_sha256",
        "new_simulations", "deletion_authority",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("activation shape")
    if (
        value["phase"] != "CLIENT-LIFECYCLE-QUAL-01"
        or value["user_delegation"] != "explicit-current-task"
        or value["new_simulations"] != 0
        or value["deletion_authority"] is not False
        or value["observer_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        or value["source_manifest"] != source_manifest(ROOT)
        or value["interpreter_sha256"] != hashlib.sha256(
            Path(sys.executable).read_bytes()
        ).hexdigest()
    ):
        raise ValueError("activation identity mismatch")
    tools = value["enabled_read_tools"]
    if (
        not isinstance(tools, list) or len(tools) != 26 or len(set(tools)) != 26
        or any(not isinstance(t, str) or not t.startswith("cadence_") for t in tools)
        or "cadence_execute_storage_cleanup" in tools
    ):
        raise ValueError("reviewed read profile required")
    return value


def reserve_audit() -> BinaryIO:
    if (
        AUDIT_ROOT.parent.is_symlink() or AUDIT_ROOT.parent.is_junction()
        or AUDIT_ROOT.is_symlink() or AUDIT_ROOT.is_junction()
    ):
        raise ValueError("linked audit root")
    AUDIT_ROOT.mkdir(mode=0o700, exist_ok=True)
    for number in range(1, MAX_SESSIONS + 1):
        try:
            return (AUDIT_ROOT / f"session-{number:02d}.private.jsonl").open("xb")
        except FileExistsError:
            continue
    raise ValueError("observation session allowance exhausted")


def observe(
    child: subprocess.Popen[bytes], audit: Audit, incoming: BinaryIO,
    outgoing: BinaryIO, errors: BinaryIO,
) -> int:
    assert child.stdin is not None and child.stdout is not None and child.stderr is not None
    failures: list[str] = []

    def fail() -> None:
        failures.append("observation_failed")
        child.kill()

    def input_reader() -> None:
        try:
            while (item := read_message(incoming)) is not None:
                line, message = item
                audit.request(message)
                assert child.stdin is not None
                child.stdin.write(line)
                child.stdin.flush()
            audit.write("client_stdin_eof")
            child.stdin.close()
        except (OSError, ValueError, TypeError):
            fail()

    def error_reader() -> None:
        size = 0
        h = hashlib.sha256()
        try:
            assert child.stderr is not None
            while chunk := child.stderr.read(4096):
                size += len(chunk)
                if size > 65536:
                    raise ValueError("stderr exceeds bound")
                h.update(chunk)
                errors.write(chunk)
                errors.flush()
            audit.write("child_stderr_eof", size_bytes=size, sha256=h.hexdigest())
        except (OSError, ValueError, TypeError):
            fail()

    readers = [threading.Thread(target=f, daemon=True) for f in (input_reader, error_reader)]
    for thread in readers:
        thread.start()
    try:
        while (item := read_message(child.stdout)) is not None:
            line, message = item
            audit.response(message)
            outgoing.write(line)
            outgoing.flush()
        audit.write("child_stdout_eof")
        result = child.wait(timeout=20)
        for thread in readers:
            thread.join(timeout=5)
        if failures or any(t.is_alive() for t in readers):
            raise ValueError("observation thread failed")
        audit.write("child_exit", return_code=result, normal_stdin_eof=True)
        return result
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream and not stream.closed:
                stream.close()


def main() -> int:
    try:
        activation = validate_activation()
        with reserve_audit() as stream:
            audit = Audit(stream, set(activation["enabled_read_tools"]))
            # Fixed child, unchanged interpreter, inherited cwd/env and stdio only.
            child = subprocess.Popen(
                [sys.executable, "-m", "cadence_mcp_bridge", "serve"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            try:
                audit.write(
                    "observer_start", observer_pid=os.getpid(), parent_pid=os.getppid(),
                    child_pid=child.pid,
                    source_manifest_sha256=digest(activation["source_manifest"]),
                    source_scope="reviewed_on_disk_sources_at_child_launch_not_loaded_memory",
                    interpreter_sha256=activation["interpreter_sha256"],
                    observer_sha256=activation["observer_sha256"],
                    expected_tool_schemas_sha256=activation["expected_tool_schemas_sha256"],
                )
                return observe(child, audit, sys.stdin.buffer, sys.stdout.buffer, sys.stderr.buffer)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        sys.stderr.write(
            "Bounded client lifecycle observation failed; private evidence preserved.\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
