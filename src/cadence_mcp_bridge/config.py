"""Typed configuration with narrow, validated security defaults."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_FORBIDDEN_REMOTE_CHARACTERS = frozenset("\x00\r\n;`$*?<>|&")
_REMOTE_PATH = re.compile(r"^/[A-Za-z0-9._/-]+$")


class BridgeConfig(BaseSettings):
    """Operator-owned bridge settings; none are exposed as MCP path inputs."""

    model_config = SettingsConfigDict(
        env_prefix="CADENCE_MCP_",
        extra="forbid",
        frozen=True,
    )

    # Legacy launch stays explicit through the original serve/export workflow.
    runtime_mode: Literal["legacy_reference", "operator"] = "legacy_reference"
    runtime_settings_path: Path | None = None
    runtime_context_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")] | None = None
    ssh_alias: Literal["cadence-vm"] = "cadence-vm"
    design_registry_path: Path | None = None
    pdk_registry_path: Path | None = None
    analysis_journal_path: Path | None = None
    sweep_journal_path: Path | None = None
    amplifier_specification_registry_path: Path | None = None
    remote_root: str = "/home/buet/cds_work/.cadence_mcp"
    runner_path: str = "/home/buet/cds_work/.cadence_mcp/bin/cadence-runner"
    connect_timeout_seconds: Annotated[int, Field(ge=1, le=60)] = 10
    operation_timeout_seconds: Annotated[int, Field(ge=1, le=3_600)] = 120
    max_output_bytes: Annotated[int, Field(ge=1_024, le=1_048_576)] = 65_536
    default_concurrency: Literal[1] = 1
    poll_interval_seconds: Annotated[float, Field(ge=0.1, le=10.0)] = 1.0
    max_poll_seconds: Annotated[int, Field(ge=10, le=1_800)] = 300
    submit_target_seconds: Annotated[float, Field(ge=1.0, le=60.0)] = 10.0

    @field_validator("default_concurrency", mode="before")
    @classmethod
    def parse_fixed_concurrency(cls, value: object) -> object:
        # Environment settings arrive as strings. Only the same fixed constant
        # is accepted; no numeric coercion or alternate concurrency is allowed.
        return 1 if isinstance(value, str) and value == "1" else value

    @field_validator("remote_root", "runner_path")
    @classmethod
    def validate_remote_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("remote paths must be absolute")
        if (
            ".." in value.split("/")
            or any(char in value for char in _FORBIDDEN_REMOTE_CHARACTERS)
            or _REMOTE_PATH.fullmatch(value) is None
        ):
            raise ValueError("remote path contains a forbidden component")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_security_relationships(self) -> Self:
        if self.runtime_mode == "legacy_reference" and (
            self.runtime_settings_path is not None or self.runtime_context_id is not None
        ):
            raise ValueError("operator context requires explicit operator mode")
        if self.runtime_mode == "operator" and any(
            value is not None
            for value in (
                self.design_registry_path,
                self.pdk_registry_path,
                self.analysis_journal_path,
                self.sweep_journal_path,
                self.amplifier_specification_registry_path,
            )
        ):
            raise ValueError("operator context cannot inherit legacy catalog or journal overrides")
        if self.runtime_mode == "operator" and (
            self.remote_root != BridgeConfig.model_fields["remote_root"].default
            or self.runner_path != BridgeConfig.model_fields["runner_path"].default
        ):
            raise ValueError("operator transport must resolve from its environment")
        expected_prefix = f"{self.remote_root}/bin/"
        if not self.runner_path.startswith(expected_prefix):
            raise ValueError("runner_path must be contained in remote_root/bin")
        if self.operation_timeout_seconds < self.connect_timeout_seconds:
            raise ValueError("operation timeout must not be shorter than connect timeout")
        if self.max_poll_seconds <= self.poll_interval_seconds:
            raise ValueError("maximum poll time must exceed the polling interval")
        return self


@dataclass(frozen=True)
class OperatorTransport:
    """Transport parameters resolved only from an immutable operator context."""

    ssh_alias: str
    remote_root: str
    runner_path: str
    connect_timeout_seconds: int = 10
    operation_timeout_seconds: int = 120
    max_output_bytes: int = 65_536
