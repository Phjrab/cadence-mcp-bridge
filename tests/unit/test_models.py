from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.models import ArtifactMetadata, JobResult, JobState, JobStatus, JobSummary


def test_job_status_requires_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        JobStatus(
            job_id=uuid4(),
            state=JobState.QUEUED,
            profile="spectre-smoke",
            submitted_at=datetime(2026, 8, 28),
            updated_at=datetime.now(UTC),
        )


def test_artifact_rejects_path_traversal() -> None:
    with pytest.raises(ValidationError, match="relative"):
        ArtifactMetadata(
            name="result.json",
            relative_path="../result.json",
            media_type="application/json",
            size_bytes=10,
        )


def test_succeeded_result_requires_zero_exit_code() -> None:
    with pytest.raises(ValidationError, match="exit_code 0"):
        JobResult(
            job_id=uuid4(),
            state=JobState.SUCCEEDED,
            exit_code=1,
            summary=JobSummary(text="unexpected", errors=1, warnings=0, notices=0),
        )


def test_valid_succeeded_result() -> None:
    result = JobResult(
        job_id=uuid4(),
        state=JobState.SUCCEEDED,
        exit_code=0,
        summary=JobSummary(text="smoke.raw", errors=0, warnings=0, notices=0),
    )

    assert result.state is JobState.SUCCEEDED
