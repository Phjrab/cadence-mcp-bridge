"""Offline release-harness failures preserve their captured diagnostic evidence."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/verify-version-transition.py"
SPEC = importlib.util.spec_from_file_location("verify_version_transition", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
TRANSITION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRANSITION)


@pytest.mark.parametrize("stdout,stderr", [
    (b"partial stdout\n", b"partial stderr\n"),
    (None, None),
])
def test_timeout_preserves_partial_output_and_explicit_outcome(
    tmp_path, monkeypatch, stdout, stderr,
):
    def timeout(command, **kwargs):
        assert kwargs["timeout"] == 0.5
        raise subprocess.TimeoutExpired(command, 0.5, output=stdout, stderr=stderr)

    monkeypatch.setattr(TRANSITION.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="timed out; retained logs: upgrade-probe"):
        TRANSITION.run(["synthetic-child"], tmp_path, "upgrade-probe", timeout=0.5)
    assert (tmp_path / "upgrade-probe.stdout.log").read_bytes() == (stdout or b"")
    assert (tmp_path / "upgrade-probe.stderr.log").read_bytes() == (stderr or b"")
    assert json.loads((tmp_path / "upgrade-probe.timeout.json").read_bytes()) == {
        "status": "TIMEOUT", "timeout_seconds": 0.5, "partial_output_preserved": True,
    }


def test_failed_cli_step_keeps_both_streams_without_success_receipt(tmp_path, monkeypatch):
    def failed(command, **kwargs):
        assert kwargs["env"] == {"SYNTHETIC_ONLY": "1"}
        assert kwargs["timeout"] == 30
        return subprocess.CompletedProcess(command, 7, b"version output", b"version failure")

    monkeypatch.setattr(TRANSITION.subprocess, "run", failed)
    with pytest.raises(ValueError, match="step failed; retained logs: restored-cli-version"):
        TRANSITION.run(
            ["synthetic-child", "--version"], tmp_path, "restored-cli-version",
            environment={"SYNTHETIC_ONLY": "1"}, timeout=30,
        )
    assert (tmp_path / "restored-cli-version.stdout.log").read_bytes() == b"version output"
    assert (tmp_path / "restored-cli-version.stderr.log").read_bytes() == b"version failure"
    assert not (tmp_path / "restored-cli-version-receipt.json").exists()


def test_successful_step_returns_captured_result_and_keeps_diagnostics(tmp_path, monkeypatch):
    result = subprocess.CompletedProcess(["synthetic-child"], 0, b"2.1.0\n", b"")
    monkeypatch.setattr(TRANSITION.subprocess, "run", lambda *args, **kwargs: result)
    assert TRANSITION.run(["synthetic-child"], tmp_path, "ok") is result
    assert (tmp_path / "ok.stdout.log").read_bytes() == b"2.1.0\n"
    assert (tmp_path / "ok.stderr.log").read_bytes() == b""
    assert not (tmp_path / "ok.timeout.json").exists()


def test_missing_executable_preserves_explicit_start_failure_without_private_filename(tmp_path):
    executable = str(tmp_path / "does-not-exist-transition-program")
    with pytest.raises(ValueError, match="could not start; retained logs: missing-executable"):
        TRANSITION.run([executable], tmp_path, "missing-executable")
    receipt = (tmp_path / "missing-executable.launch-error.json").read_text(encoding="utf-8")
    assert executable not in receipt
    assert json.loads(receipt)["status"] == "START_FAILED"
    assert json.loads(receipt)["error_type"] == "FileNotFoundError"
    assert (tmp_path / "missing-executable.stdout.log").read_bytes() == b""
    assert (tmp_path / "missing-executable.stderr.log").read_bytes() == b""


def test_populated_sweep_replay_preserves_failed_unknown_rows_and_child_ids(tmp_path):
    state = tmp_path / "state"
    with TRANSITION.ordinary_fixture_owner():
        TRANSITION.create_state(state)
        before = TRANSITION.snapshot(state)
        for _ in range(2):
            TRANSITION.state_replay(state)
            assert TRANSITION.snapshot(state) == before
        with sqlite3.connect(state / "analysis.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM admissions").fetchone()[0] == 3
            assert connection.execute("SELECT COUNT(*) FROM native_sweeps_v1").fetchone()[0] == 1
        with sqlite3.connect(state / "sweep.sqlite3") as connection:
            assert connection.execute("SELECT COUNT(*) FROM sweeps").fetchone()[0] == 1


@pytest.mark.parametrize("native", [False, True])
def test_unreadable_populated_sweep_cannot_certify_transition(tmp_path, native):
    from cadence_mcp_bridge.errors import InvalidInputError

    state = tmp_path / "state"
    with TRANSITION.ordinary_fixture_owner():
        TRANSITION.create_state(state)
        database, table = ("analysis.sqlite3", "native_sweeps_v1") if native else (
            "sweep.sqlite3", "sweeps"
        )
        with sqlite3.connect(state / database) as connection:
            connection.execute(f"UPDATE {table} SET document='{{}}'")
        with pytest.raises(InvalidInputError):
            TRANSITION.state_replay(state)
