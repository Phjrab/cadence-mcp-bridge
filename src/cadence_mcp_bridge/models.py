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


class JobOrigin(StrEnum):
    MCP = "mcp"
    OPERATOR = "operator"


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


class LibraryMetadata(ContractModel):
    name: Annotated[str, Field(min_length=1, max_length=64)]
    allowed_cell_count: Annotated[int, Field(ge=0)]


class LibraryList(ContractModel):
    libraries: tuple[LibraryMetadata, ...]
    allowlist_enforced: Literal[True] = True
    proprietary_content_included: Literal[False] = False


class CellList(ContractModel):
    library: Annotated[str, Field(min_length=1, max_length=64)]
    cells: tuple[Annotated[str, Field(min_length=1, max_length=64)], ...]
    allowlist_enforced: Literal[True] = True
    proprietary_content_included: Literal[False] = False


class CellViewInspection(ContractModel):
    library: Annotated[str, Field(min_length=1, max_length=64)]
    cell: Annotated[str, Field(min_length=1, max_length=64)]
    view: Annotated[str, Field(min_length=1, max_length=64)]
    exists: bool
    kind: Literal["cellview"] = "cellview"
    allowlist_enforced: Literal[True] = True
    proprietary_content_included: Literal[False] = False


class ProfileVariableSpec(ContractModel):
    name: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
    unit: Annotated[str, Field(min_length=1, max_length=16)]
    minimum: float
    maximum: float
    default: float

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if not self.minimum <= self.default <= self.maximum:
            raise ValueError("profile variable default must be within its range")
        return self


class ProfileSummary(ContractModel):
    profile_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    classification: Literal["fixture", "actual"]
    analyses: tuple[Annotated[str, Field(min_length=1, max_length=32)], ...]
    corners: tuple[Annotated[str, Field(min_length=1, max_length=32)], ...]
    outputs: tuple[Annotated[str, Field(min_length=1, max_length=64)], ...]


class ProfileList(ContractModel):
    registry_version: Literal[1] = 1
    profiles: tuple[ProfileSummary, ...]


class AdeProfileMetadata(ContractModel):
    library: Annotated[str, Field(min_length=1, max_length=64)]
    cell: Annotated[str, Field(min_length=1, max_length=64)]
    view: Annotated[str, Field(min_length=1, max_length=64)]
    ade_product: Literal["ADE L"]
    state: Annotated[str, Field(min_length=1, max_length=64)]
    pdk: Annotated[str, Field(min_length=1, max_length=64)]
    pdk_version: Annotated[str, Field(min_length=1, max_length=32)]
    model_section: Annotated[str, Field(min_length=1, max_length=32)]
    temperature_c: float
    spectre_stop_time: Annotated[str, Field(pattern=r"^[0-9]+(?:\.[0-9]+)?[munpf]$")]
    stop_time_s: Annotated[float, Field(gt=0)]


class SimulationProfile(ProfileSummary):
    netlist_source: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
    variables: tuple[ProfileVariableSpec, ...]
    timeout_seconds: Annotated[int, Field(ge=1, le=300)]
    allowed_warning_codes: tuple[Annotated[str, Field(min_length=1, max_length=32)], ...] = ()
    maximum_warning_count: Annotated[int, Field(ge=0, le=100)] = 0
    ade: AdeProfileMetadata | None = None


class RcTransientVariables(ContractModel):
    resistance_ohm: Annotated[float, Field(ge=100.0, le=10_000.0)] = 1_000.0
    capacitance_f: Annotated[float, Field(ge=1e-13, le=1e-10)] = 1e-12
    stop_time_s: Annotated[float, Field(ge=1e-10, le=1e-7)] = 1e-9


class NoProfileVariables(ContractModel):
    """Explicitly empty variable object for reviewed profiles with no design variables."""


type ProfileVariables = NoProfileVariables | RcTransientVariables


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
    origin: JobOrigin = JobOrigin.MCP
    submitted_at: datetime | None = None
    updated_at: datetime
    message: Annotated[str, Field(max_length=512)] | None = None

    @field_validator("submitted_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value


class JobSummary(ContractModel):
    text: Annotated[str, Field(max_length=512)]
    errors: Annotated[int, Field(ge=-1)]
    warnings: Annotated[int, Field(ge=-1)]
    notices: Annotated[int, Field(ge=-1)]


class JobStorageMetadata(ContractModel):
    contained: Literal[True]
    directory_mode: Literal["0700"]


class ResultLimitMetadata(ContractModel):
    response_limit_bytes: Literal[65_536] = 65_536
    artifacts_total: Annotated[int, Field(ge=0)] = 0
    artifacts_returned: Annotated[int, Field(ge=0, le=16)] = 0
    artifacts_truncated: bool = False
    summary_original_chars: Annotated[int, Field(ge=0)] = 0
    summary_returned_chars: Annotated[int, Field(ge=0, le=512)] = 0
    summary_truncated: bool = False

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.artifacts_returned > self.artifacts_total:
            raise ValueError("returned artifacts cannot exceed total artifacts")
        if self.summary_returned_chars > self.summary_original_chars:
            raise ValueError("returned summary cannot exceed original summary")
        return self


class JobResult(ContractModel):
    job_id: UUID
    state: JobState
    exit_code: int | None = None
    summary: JobSummary
    artifacts: tuple[ArtifactMetadata, ...] = ()
    storage: JobStorageMetadata | None = None
    origin: JobOrigin = JobOrigin.MCP
    limits: ResultLimitMetadata = Field(default_factory=ResultLimitMetadata)

    @model_validator(mode="after")
    def validate_exit_code(self) -> Self:
        if self.state is JobState.SUCCEEDED and self.exit_code != 0:
            raise ValueError("a succeeded job must have exit_code 0")
        if self.state is JobState.FAILED and self.exit_code is None:
            raise ValueError("a failed job must include an exit code")
        return self


class JobLogTail(ContractModel):
    job_id: UUID
    stream: Literal["stdout", "stderr"]
    lines_requested: Annotated[int, Field(ge=1, le=200)]
    text: Annotated[str, Field(max_length=65_536)]
    limit_bytes: Literal[65_536] = 65_536
    original_bytes: Annotated[int, Field(ge=0)] | None = None
    returned_bytes: Annotated[int, Field(ge=0, le=65_536)] = 0
    truncated: bool = False
    redacted: bool = False


class ErrorEnvelope(ContractModel):
    code: ErrorCode
    message: Annotated[str, Field(min_length=1, max_length=1_024)]
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ContractModel):
    ok: Literal[False] = False
    error: ErrorEnvelope
