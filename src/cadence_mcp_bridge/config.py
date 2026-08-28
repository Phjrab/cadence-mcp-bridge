"""Typed configuration with narrow, validated security defaults."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_FORBIDDEN_REMOTE_CHARACTERS = frozenset("\x00\r\n;`$*?<>|&")


class BridgeConfig(BaseSettings):
    """Operator-owned bridge settings; none are exposed as MCP path inputs."""

    model_config = SettingsConfigDict(
        env_prefix="CADENCE_MCP_",
        extra="forbid",
        frozen=True,
    )

    ssh_alias: Literal["cadence-vm"] = "cadence-vm"
    remote_root: str = "/home/buet/cds_work/.cadence_mcp"
    runner_path: str = "/home/buet/cds_work/.cadence_mcp/bin/cadence-runner"
    connect_timeout_seconds: Annotated[int, Field(ge=1, le=60)] = 10
    operation_timeout_seconds: Annotated[int, Field(ge=1, le=3_600)] = 120
    max_output_bytes: Annotated[int, Field(ge=1_024, le=1_048_576)] = 65_536
    default_concurrency: Literal[1] = 1

    @field_validator("remote_root", "runner_path")
    @classmethod
    def validate_remote_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("remote paths must be absolute")
        if ".." in value.split("/") or any(char in value for char in _FORBIDDEN_REMOTE_CHARACTERS):
            raise ValueError("remote path contains a forbidden component")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_security_relationships(self) -> Self:
        expected_prefix = f"{self.remote_root}/bin/"
        if not self.runner_path.startswith(expected_prefix):
            raise ValueError("runner_path must be contained in remote_root/bin")
        if self.operation_timeout_seconds < self.connect_timeout_seconds:
            raise ValueError("operation timeout must not be shorter than connect timeout")
        return self

