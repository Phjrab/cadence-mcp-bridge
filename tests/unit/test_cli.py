from __future__ import annotations

import pytest

import cadence_mcp_bridge.__main__ as cli


def test_config_check() -> None:
    assert cli.main(["config-check"]) == 0


def test_default_command_runs_stdio_server(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_run() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(cli, "run_stdio_server", fake_run)

    assert cli.main([]) == 0
    assert called is True
