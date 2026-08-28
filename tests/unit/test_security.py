from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

import pytest

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER = PROJECT_ROOT / "remote" / "bin" / "cadence-runner"
COMMON = PROJECT_ROOT / "remote" / "lib" / "runner-common.sh"
WORKER = PROJECT_ROOT / "remote" / "lib" / "run-smoke-job.sh"
HELPER = PROJECT_ROOT / "remote" / "py26" / "result_json.py"
CLEANUP = PROJECT_ROOT / "scripts" / "cleanup-remote-jobs.ps1"
SSH_EXE = r"C:\Windows\System32\OpenSSH\ssh.exe"


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> OpenSshBackend:
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.shutil.which", lambda _: SSH_EXE)
    return OpenSshBackend(BridgeConfig())


def completed(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> Any:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malicious",
    [
        "../../etc/passwd",
        "$(touch pwned)",
        "x; id",
        "x|id",
        "x&&id",
        "line1\nline2",
        "line1\r\nline2",
        "\x00",
        "ｅｔｃ／ｐａｓｓｗｄ",
        "작업-💥",
        "--option",
    ],
)
async def test_hostile_and_unicode_job_ids_never_reach_ssh(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch, malicious: str
) -> None:
    run = Mock()
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    with pytest.raises(InvalidInputError):
        await backend.status(cast(Any, malicious))

    run.assert_not_called()


@pytest.mark.asyncio
async def test_secret_fixture_is_redacted_from_log_result(
    backend: OpenSshBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = uuid4()
    token = "ghp_" + ("s" * 32)
    license_value = "27000@" + "fixture.invalid"
    log_payload = {
        "job_id": str(job_id),
        "limit_bytes": 65536,
        "lines_requested": 10,
        "original_bytes": 100,
        "returned_bytes": 100,
        "stream": "stdout",
        "text": f"token={token} CDS_LIC_FILE={license_value}",
        "truncated": False,
    }
    result_payload = {
        "artifacts": [],
        "exit_code": 0,
        "job_id": str(job_id),
        "limits": {
            "artifacts_returned": 0,
            "artifacts_total": 0,
            "artifacts_truncated": False,
            "response_limit_bytes": 65536,
            "summary_original_chars": 100,
            "summary_returned_chars": 100,
            "summary_truncated": False,
        },
        "origin": "mcp",
        "state": "succeeded",
        "storage": None,
        "summary": {
            "errors": 0,
            "notices": 0,
            "text": f"token={token} CDS_LIC_FILE={license_value}",
            "warnings": 0,
        },
    }
    run = Mock(
        side_effect=[
            completed(json.dumps(log_payload).encode()),
            completed(json.dumps(result_payload).encode()),
        ]
    )
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", run)

    log = await backend.log_tail(job_id, "stdout", 10)
    result = await backend.result(job_id)

    serialized = log.model_dump_json() + result.model_dump_json()
    assert token not in serialized
    assert license_value not in serialized
    assert log.redacted is True
    assert log.limit_bytes == 65536
    assert result.limits.response_limit_bytes == 65536


def test_log_tail_helper_reports_truncation_metadata(tmp_path: Path) -> None:
    log = tmp_path / "stdout.log"
    log.write_bytes((b"a" * 70000) + "끝\n".encode())
    job_id = str(uuid4())

    completed_process = subprocess.run(
        [sys.executable, str(HELPER), "log-tail", str(log), job_id, "stdout", "1"],
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(completed_process.stdout)

    assert payload["truncated"] is True
    assert payload["limit_bytes"] == 65536
    assert payload["returned_bytes"] <= 65536
    assert payload["text"].endswith("끝\n")


def test_audit_jsonl_contains_only_safe_attribution_fields(tmp_path: Path) -> None:
    audit = tmp_path / "events.jsonl"
    job_id = str(uuid4())
    subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "audit",
            str(audit),
            "job_submitted",
            job_id,
            "mcp",
            "cadence-mcp-bridge",
            "2026-08-28T00:00:00Z",
            "spectre-smoke",
        ],
        check=True,
    )

    record = json.loads(audit.read_text(encoding="utf-8"))
    assert record == {
        "actor": "cadence-mcp-bridge",
        "event": "job_submitted",
        "job_id": job_id,
        "origin": "mcp",
        "profile": "spectre-smoke",
        "timestamp": "2026-08-28T00:00:00Z",
    }
    assert not ({"secret", "license", "netlist", "path", "circuit"} & set(record))


def test_cleanup_is_fixed_root_dry_run_without_delete_primitive() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    helper = HELPER.read_text(encoding="utf-8")
    script = CLEANUP.read_text(encoding="utf-8")

    assert "cleanup-dry-run" in runner
    assert 'expected_root = "/home/buet/cds_work/.cadence_mcp/jobs"' in helper
    assert '"dry_run": True' in helper
    assert "os.path.islink(path)" in helper
    assert 'state not in ("succeeded", "failed", "cancelled", "unknown")' in helper
    for forbidden in ("Remove-Item", "rm -", "rmtree", "os.remove", "unlink("):
        assert forbidden not in script + helper


def test_worker_recovery_fails_closed_for_stale_or_reused_pid() -> None:
    common = COMMON.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    assert 'kill -0 "$pid"' in common
    assert 'case "$process_state" in Z*|"") return 1' in common
    assert '"$stored_marker" = "$current_marker"' in common
    assert '"$current_pgid" = "$pgid"' in common
    assert '"$pid" = "$pgid"' in common
    assert 'unknown "job worker is unavailable; operator review required"' in runner


def test_partial_write_and_power_loss_recovery_use_atomic_final_files() -> None:
    common = COMMON.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    assert '.status.$$.tmp' in common
    assert '.result.$$.tmp' in common
    assert 'mv -f "$temporary" "$job_dir/status.json"' in common
    assert 'mv -f "$temporary" "$job_dir/result.json"' in common
    assert '.request.$$.tmp' in runner
    assert 'mv -f "$request_temporary" "$job_dir/request.json"' in runner
    assert 'job state recovered from result' in runner


def test_concurrency_is_fixed_at_one_and_submit_origin_is_closed() -> None:
    worker = WORKER.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")

    assert 'exec 9> "$CADENCE_MCP_ROOT/run.lock"' in worker
    assert "flock 9" in worker
    assert "cadence_mcp_audit job_started" in worker
    assert "cadence_mcp_audit job_finished" in worker
    assert "mcp) submitted_by=cadence-mcp-bridge" in runner
    assert "operator) submitted_by=$(id -un)" in runner
    assert '*) cadence_mcp_fail "invalid job origin" 64' in runner
