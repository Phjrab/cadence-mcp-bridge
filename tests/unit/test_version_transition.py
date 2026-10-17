"""Offline release-harness failures preserve their captured diagnostic evidence."""

from __future__ import annotations

import importlib.util
import json
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
