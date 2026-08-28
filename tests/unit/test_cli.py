from __future__ import annotations

from cadence_mcp_bridge.__main__ import main


def test_config_check(capsys: object) -> None:
    assert main(["config-check"]) == 0

