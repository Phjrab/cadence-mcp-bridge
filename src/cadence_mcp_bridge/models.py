"""Stable domain models shared by service and future MCP adapters."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ErrorCode(StrEnum):
    INVALID_CONFIGURATION = "invalid_configuration"
    INVALID_INPUT = "invalid_input"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    HOST_KEY_FAILED = "host_key_failed"
    TIMEOUT = "timeout"
    REMOTE_FAILURE = "remote_failure"
    INTERNAL_ERROR = "internal_error"


class ToolAvailability(ContractModel):
    available: bool
    version: str | None = None


class LicenseEnvironment(ContractModel):
    CDS_LIC_FILE: Literal["SET", "UNSET"]


class HealthReport(ContractModel):
    ssh: Literal["ok", "error"]
    remote_host: str
    remote_user: str
    remote_root_accessible: bool
    virtuoso: ToolAvailability
    spectre: ToolAvailability
    ocean: ToolAvailability
    license_env: LicenseEnvironment
    runner_version: str


class ArtifactMetadata(ContractModel):
    name: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")]
    relative_path: Annotated[str, Field(min_length=1, max_length=512)]
    media_type: Annotated[str, Field(min_length=1, max_length=128)]
    size_bytes: Annotated[int, Field(ge=0)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    @field_validator("relative_path")
    @classmethod
    def reject_unsafe_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or ".." in normalized.split("/"):
            raise ValueError("artifact path must stay relative to the job directory")
        if any(char in normalized for char in ("\x00", "\r", "\n")):
            raise ValueError("artifact path contains control characters")
        return normalized


class JobStatus(ContractModel):
    job_id: UUID
    state: JobState
    profile: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    submitted_at: datetime
    updated_at: datetime
    message: Annotated[str, Field(max_length=512)] | None = None

    @field_validator("submitted_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value


class JobResult(ContractModel):
    job_id: UUID
    state: JobState
    exit_code: int | None = None
    summary: Annotated[str, Field(max_length=2_048)]
    artifacts: tuple[ArtifactMetadata, ...] = ()

    @model_validator(mode="after")
    def validate_exit_code(self) -> Self:
        if self.state is JobState.SUCCEEDED and self.exit_code != 0:
            raise ValueError("a succeeded job must have exit_code 0")
        if self.state is JobState.FAILED and self.exit_code is None:
            raise ValueError("a failed job must include an exit code")
        return self


class ErrorEnvelope(ContractModel):
    code: ErrorCode
    message: Annotated[str, Field(min_length=1, max_length=1_024)]
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ContractModel):
    ok: Literal[False] = False
    error: ErrorEnvelope
