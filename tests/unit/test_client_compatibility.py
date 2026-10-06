"""Independent JSON-RPC subprocess client; no Cadence contact or desktop claims."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.onboarding import OnboardingRejected, export_client_config
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.sweeps import SweepStore

EXAMPLES = Path(__file__).resolve().parents[2] / "docs/examples/onboarding"


@pytest.mark.parametrize("identity", ["independent-wire-a", "independent-wire-b"])
def test_wire_protocol_without_sdk_or_client_context(tmp_path: Path, identity: str) -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "cadence_mcp_bridge", "serve"],
        cwd=tmp_path,
        env={
            **{k: v for k, v in os.environ.items() if not k.startswith("CADENCE_MCP_")},
            "PYTHONUTF8": "1",
            "CADENCE_MCP_DESIGN_REGISTRY_PATH": str(EXAMPLES / "designs.json"),
            "CADENCE_MCP_PDK_REGISTRY_PATH": str(EXAMPLES / "pdks.json"),
            "CADENCE_MCP_ANALYSIS_JOURNAL_PATH": str(tmp_path / "analysis.sqlite3"),
            "CADENCE_MCP_SWEEP_JOURNAL_PATH": str(tmp_path / "sweep.sqlite3"),
        },
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin and process.stdout and process.stderr
    lines: queue.Queue[bytes] = queue.Queue()
    stderr: list[bytes] = []

    def read_stdout() -> None:
        assert process.stdout
        for line in process.stdout:
            lines.put(line)

    def read_stderr() -> None:
        assert process.stderr
        stderr.append(process.stderr.read(65537))

    readers = [threading.Thread(target=f, daemon=True) for f in (read_stdout, read_stderr)]
    for reader in readers:
        reader.start()

    def send(method: str, params: dict[str, Any], request_id: int | None) -> None:
        assert process.stdin
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if request_id is not None:
            message["id"] = request_id
        process.stdin.write(json.dumps(message).encode() + b"\n")
        process.stdin.flush()

    def receive() -> dict[str, Any]:
        line = lines.get(timeout=30)
        assert len(line) <= 1048576
        message = cast(dict[str, Any], json.loads(line))
        assert message["jsonrpc"] == "2.0"
        return message

    try:
        send("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                            "clientInfo": {"name": identity, "version": "1.0"}}, 1)
        initialized = receive()
        assert initialized["id"] == 1
        init = initialized["result"]
        assert init["protocolVersion"]
        assert init["serverInfo"]["name"] == "cadence-mcp-bridge"
        assert "tools" in init["capabilities"]
        send("notifications/initialized", {}, None)
        send("tools/list", {}, 2)
        listing = receive()["result"]["tools"]
        assert len(listing) == 76 and len({t["name"] for t in listing}) == 76
        for tool in listing:
            assert tool["description"] and "codex" not in json.dumps(tool).lower()
            assert tool["inputSchema"]["type"] == "object"
            assert tool["outputSchema"]["type"] == "object"
        # Requests may complete out of order. Correlate by JSON-RPC ID.
        send("tools/call", {"name": "cadence_list_designs", "arguments": {}}, 3)
        send("tools/call", {"name": "cadence_list_designs", "arguments": {}}, 4)
        results = {m["id"]: m["result"] for m in (receive(), receive())}
        assert results[3] == results[4]
        data = results[3]["structuredContent"]
        assert data["designs"][0]["design_id"] == "example-amplifier"
        assert json.loads(results[3]["content"][0]["text"]) == data
        send("tools/call", {"name": "cadence_describe_design", "arguments": {
            "design_id": "example-amplifier", "path": "/private"}}, 5)
        assert receive()["result"]["isError"] is True
        send("tools/call", {"name": "cadence_describe_design", "arguments": {
            "design_id": "missing-design"}}, 6)
        failure = receive()["result"]
        assert failure["isError"] is True and "error" in failure["structuredContent"]
        send("nonexistent/method", {}, 7)
        assert receive()["error"]["code"] == -32601
        send("ping", {}, 8)
        assert receive()["result"] == {}
        send("tools/call", {"name": "cadence_runtime_info", "arguments": {}}, 9)
        send("tools/call", {"name": "cadence_runtime_info", "arguments": {}}, 10)
        runtime_results = {m["id"]: m["result"] for m in (receive(), receive())}
        assert runtime_results[9] == runtime_results[10]
        runtime = runtime_results[9]["structuredContent"]
        assert runtime["bridge_version"] == init["serverInfo"]["version"]
        assert runtime["designs"]["source"] == "operator_supplied"
        assert runtime["designs"]["schema_version"] == 3
        assert runtime["journals"]["sweep"] == "operator_supplied"
        assert not runtime["remote_contact"] and not runtime["journals"]["health_assessed"]
        assert str(tmp_path) not in json.dumps(runtime) and len(json.dumps(runtime)) < 2048
        assert json.loads(runtime_results[9]["content"][0]["text"]) == runtime
        send("tools/call", {"name": "cadence_runtime_info", "arguments": {"path": "../x"}}, 11)
        assert receive()["result"]["isError"] is True
        process.stdin.close()
        assert process.wait(timeout=20) == 0
        for reader in readers:
            reader.join(timeout=5)
        assert lines.empty(), "Non-protocol output or unexpected notification"
        assert stderr and b"invalid_input" in stderr[0] and len(stderr[0]) <= 65536
        assert not (tmp_path / "analysis.sqlite3").exists()
        assert (tmp_path / "sweep.sqlite3").is_file()  # Existing eager local initialization.
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream and not stream.closed:
                stream.close()


def test_explicit_sweep_storage_preserves_existing_bytes(tmp_path: Path) -> None:
    journal = tmp_path / "sweep.sqlite3"
    SweepStore(journal)
    before = journal.read_bytes()
    config = BridgeConfig(sweep_journal_path=journal)
    service = CadenceService(MagicMock(), sweep_journal=config.sweep_journal_path)
    assert service._sweeps.store.path == journal
    assert journal.read_bytes() == before


def test_claude_alias_same_server_and_operator_storage(tmp_path: Path) -> None:
    paths = tuple(EXAMPLES / name for name in ("environment.json", "designs.json", "pdks.json"))
    outputs = []
    for format in ("mcp-json", "claude-desktop"):
        output = tmp_path / (format + ".json")
        export_client_config(
            *paths, tmp_path / "analysis.sqlite3", output,
            format=cast(Any, format), sweep_journal=tmp_path / "sweep.sqlite3",
        )
        outputs.append(output.read_bytes())
    assert outputs[0] == outputs[1]
    env = json.loads(outputs[1])["mcpServers"]["cadence-mcp-bridge"]["env"]
    assert env["CADENCE_MCP_SWEEP_JOURNAL_PATH"] == str(tmp_path / "sweep.sqlite3")
    assert not (tmp_path / "sweep.sqlite3").exists()
    for collision in (*paths, tmp_path / "analysis.sqlite3", tmp_path / "bad.json"):
        with pytest.raises(OnboardingRejected):
            export_client_config(
                *paths, tmp_path / "analysis.sqlite3", tmp_path / "bad.json",
                format="claude-desktop", sweep_journal=collision,
            )
