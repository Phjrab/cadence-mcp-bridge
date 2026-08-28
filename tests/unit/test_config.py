from __future__ import annotations

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.config import BridgeConfig


def test_secure_defaults() -> None:
    config = BridgeConfig()

    assert config.ssh_alias == "cadence-vm"
    assert config.remote_root == "/home/buet/cds_work/.cadence_mcp"
    assert config.runner_path == "/home/buet/cds_work/.cadence_mcp/bin/cadence-runner"
    assert config.default_concurrency == 1
    assert config.max_output_bytes == 65_536


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ssh_alias", "attacker"),
        ("remote_root", "../tmp"),
        ("remote_root", "/tmp/x;id"),
        ("remote_root", "/tmp/path with spaces"),
        ("runner_path", "/home/buet/cds_work/.cadence_mcp/../runner"),
        ("default_concurrency", 2),
    ],
)
def test_rejects_unsafe_configuration(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        BridgeConfig.model_validate({field: value})


def test_runner_must_be_inside_remote_bin() -> None:
    with pytest.raises(ValidationError, match="contained"):
        BridgeConfig(runner_path="/home/buet/cds_work/.cadence_mcp/runner")


def test_operation_timeout_covers_connect_timeout() -> None:
    with pytest.raises(ValidationError, match="shorter"):
        BridgeConfig(connect_timeout_seconds=30, operation_timeout_seconds=10)
