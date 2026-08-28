from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.e2e import verify_lifecycle
from cadence_mcp_bridge.models import (
    ArtifactMetadata,
    HealthReport,
    JobLogTail,
    JobResult,
    JobState,
    JobStatus,
    JobStorageMetadata,
    JobSummary,
    LicenseEnvironment,
    ToolAvailability,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService


class LifecycleBackend:
    def __init__(self, final_state: JobState = JobState.SUCCEEDED) -> None:
        self.final_state = final_state

    async def health(self) -> HealthReport:
        return HealthReport(
            ssh="ok",
            remote_host="cadence",
            remote_user="buet",
            remote_root_accessible=True,
            virtuoso=ToolAvailability(available=True),
            spectre=ToolAvailability(available=True),
            ocean=ToolAvailability(available=True),
            license_env=LicenseEnvironment(CDS_LIC_FILE="SET"),
            runner_version="0.4.0",
        )

    async def submit_smoke(self, job_id: UUID) -> JobStatus:
        return self._status(job_id, JobState.QUEUED)

    async def status(self, job_id: UUID) -> JobStatus:
        return self._status(job_id, self.final_state)

    async def log_tail(
        self, job_id: UUID, stream: Literal["stdout", "stderr"], lines: int = 100
    ) -> JobLogTail:
        return JobLogTail(
            job_id=job_id,
            stream=stream,
            lines_requested=lines,
            text="bounded\n",
            original_bytes=8,
            returned_bytes=8,
        )

    async def result(self, job_id: UUID) -> JobResult:
        return JobResult(
            job_id=job_id,
            state=self.final_state,
            exit_code=0 if self.final_state is JobState.SUCCEEDED else 2,
            summary=JobSummary(text="complete", errors=0, warnings=0, notices=1),
            artifacts=(
                ArtifactMetadata(
                    name="smoke.log",
                    relative_path="artifacts/smoke.log",
                    media_type="text/plain",
                    size_bytes=8,
                ),
            ),
            storage=JobStorageMetadata(contained=True, directory_mode="0700"),
        )

    async def cancel(self, job_id: UUID) -> JobStatus:
        return self._status(job_id, JobState.CANCELLED)

    @staticmethod
    def _status(job_id: UUID, state: JobState) -> JobStatus:
        now = datetime.now(UTC)
        return JobStatus(
            job_id=job_id,
            state=state,
            profile="spectre-smoke",
            submitted_at=now,
            updated_at=now,
        )


@pytest.mark.asyncio
async def test_verify_lifecycle_accepts_bounded_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cadence_mcp_bridge.e2e.asyncio.sleep", AsyncMock())
    server = create_server(CadenceService(LifecycleBackend()))

    report = await verify_lifecycle(server=server, config=BridgeConfig())

    assert report.observed_states == (JobState.QUEUED, JobState.SUCCEEDED)
    assert report.exit_code == 0
    assert report.artifact_count == 1
    assert report.storage_contained is True
    assert report.log_lines_requested == 50


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [JobState.FAILED, JobState.CANCELLED, JobState.UNKNOWN])
async def test_verify_lifecycle_reports_safe_terminal_failure(
    monkeypatch: pytest.MonkeyPatch, state: JobState
) -> None:
    monkeypatch.setattr("cadence_mcp_bridge.e2e.asyncio.sleep", AsyncMock())
    server = create_server(CadenceService(LifecycleBackend(state)))

    with pytest.raises(RuntimeError, match=f"safe terminal state {state.value}"):
        await verify_lifecycle(server=server, config=BridgeConfig())
