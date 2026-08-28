from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

import pytest

from cadence_mcp_bridge.errors import (
    BackendUnavailableError,
    InvalidInputError,
    OperationTimeoutError,
)
from cadence_mcp_bridge.models import (
    CellList,
    CellViewInspection,
    HealthReport,
    JobLogTail,
    JobResult,
    JobState,
    JobStatus,
    JobSummary,
    LibraryList,
    LibraryMetadata,
    LicenseEnvironment,
    RcTransientVariables,
    ToolAvailability,
)
from cadence_mcp_bridge.service import CadenceService


def health_report() -> HealthReport:
    return HealthReport(
        ssh="ok",
        remote_host="cadence",
        remote_user="buet",
        remote_root_accessible=True,
        virtuoso=ToolAvailability(available=True, version="IC6.1.5.500.15"),
        spectre=ToolAvailability(available=True, version="12.1.0.347.isr3"),
        ocean=ToolAvailability(available=True),
        license_env=LicenseEnvironment(CDS_LIC_FILE="SET"),
        runner_version="test",
    )


class FakeBackend:
    def __init__(self) -> None:
        self.cancelled: UUID | None = None

    async def health(self) -> HealthReport:
        return health_report()

    async def submit_smoke(self, job_id: UUID) -> JobStatus:
        return job_status(job_id)

    async def status(self, job_id: UUID) -> JobStatus:
        return job_status(job_id)

    async def log_tail(
        self, job_id: UUID, stream: Literal["stdout", "stderr"], lines: int = 100
    ) -> JobLogTail:
        text = f"{job_id}:{stream}:{lines}"
        return JobLogTail(
            job_id=job_id,
            stream=stream,
            lines_requested=lines,
            text=text,
            original_bytes=len(text.encode("utf-8")),
            returned_bytes=len(text.encode("utf-8")),
        )

    async def result(self, job_id: UUID) -> JobResult:
        return JobResult(
            job_id=job_id,
            state=JobState.SUCCEEDED,
            exit_code=0,
            summary=JobSummary(text="complete", errors=0, warnings=0, notices=1),
        )

    async def cancel(self, job_id: UUID) -> JobStatus:
        self.cancelled = job_id
        return job_status(job_id, state=JobState.CANCELLING)

    async def list_libraries(self) -> LibraryList:
        return LibraryList(libraries=(LibraryMetadata(name="MyFirstDesign", allowed_cell_count=1),))

    async def list_cells(self, library: str) -> CellList:
        return CellList(library=library, cells=("NOT_gate",))

    async def inspect_cellview(self, library: str, cell: str, view: str) -> CellViewInspection:
        return CellViewInspection(library=library, cell=cell, view=view, exists=True)

    async def submit_profile(
        self,
        job_id: UUID,
        profile_id: str,
        corner: str,
        variables: RcTransientVariables,
    ) -> JobStatus:
        return job_status(job_id).model_copy(update={"profile": profile_id})


class FailingBackend(FakeBackend):
    async def health(self) -> HealthReport:
        raise RuntimeError("sensitive backend details")


class TimeoutAfterCreateBackend(FakeBackend):
    def __init__(self, *, recoverable: bool) -> None:
        super().__init__()
        self.recoverable = recoverable
        self.created: UUID | None = None

    async def submit_smoke(self, job_id: UUID) -> JobStatus:
        self.created = job_id
        raise OperationTimeoutError("Remote operation timed out")

    async def status(self, job_id: UUID) -> JobStatus:
        if not self.recoverable:
            raise BackendUnavailableError("status unavailable")
        assert job_id == self.created
        return job_status(job_id)


def job_status(job_id: UUID, *, state: JobState = JobState.QUEUED) -> JobStatus:
    now = datetime.now(UTC)
    return JobStatus(
        job_id=job_id,
        state=state,
        profile="spectre-smoke",
        submitted_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_service_uses_typed_fake_backend() -> None:
    report = await CadenceService(FakeBackend()).health()

    assert report.ssh == "ok"
    assert report.license_env.CDS_LIC_FILE == "SET"


@pytest.mark.asyncio
async def test_service_maps_unexpected_backend_failure() -> None:
    with pytest.raises(BackendUnavailableError, match="unavailable"):
        await CadenceService(FailingBackend()).health()


@pytest.mark.asyncio
async def test_service_generates_and_owns_submitted_job_id() -> None:
    backend = FakeBackend()
    service = CadenceService(backend)

    submitted = await service.submit_smoke()
    cancelled = await service.cancel_job(str(submitted.job_id))

    assert cancelled.state is JobState.CANCELLING
    assert backend.cancelled == submitted.job_id


@pytest.mark.asyncio
async def test_submit_timeout_recovers_with_same_idempotency_key() -> None:
    backend = TimeoutAfterCreateBackend(recoverable=True)
    service = CadenceService(backend)

    submitted = await service.submit_smoke()
    await service.cancel_job(str(submitted.job_id))

    assert submitted.job_id == backend.created
    assert backend.cancelled == backend.created


@pytest.mark.asyncio
async def test_submit_timeout_is_preserved_when_recovery_fails() -> None:
    with pytest.raises(OperationTimeoutError, match="timed out"):
        await CadenceService(TimeoutAfterCreateBackend(recoverable=False)).submit_smoke()


@pytest.mark.asyncio
async def test_service_rejects_unowned_cancel() -> None:
    with pytest.raises(InvalidInputError, match="not owned"):
        await CadenceService(FakeBackend()).cancel_job(str(uuid4()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "job_id",
    [
        "../x",
        "ABC",
        "{00000000-0000-4000-8000-000000000000}",
        "00000000-0000-0000-0000-000000000000",
    ],
)
async def test_service_rejects_noncanonical_job_id(job_id: str) -> None:
    with pytest.raises(InvalidInputError, match="UUID"):
        await CadenceService(FakeBackend()).job_status(job_id)


@pytest.mark.asyncio
async def test_service_validates_log_tail_inputs() -> None:
    service = CadenceService(FakeBackend())
    job_id = str(uuid4())

    with pytest.raises(InvalidInputError, match="stream"):
        await service.job_log_tail(job_id, "combined", 10)
    with pytest.raises(InvalidInputError, match="lines"):
        await service.job_log_tail(job_id, "stdout", 201)


@pytest.mark.asyncio
async def test_service_returns_only_allowlisted_discovery_metadata() -> None:
    service = CadenceService(FakeBackend())

    libraries = await service.list_libraries()
    cells = await service.list_cells("MyFirstDesign")
    cellview = await service.inspect_cellview("MyFirstDesign", "NOT_gate", "schematic")

    assert libraries.proprietary_content_included is False
    assert cells.cells == ("NOT_gate",)
    assert cellview.exists is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda service: service.list_cells("gpdk090"), "library"),
        (lambda service: service.inspect_cellview("MyFirstDesign", "Other", "schematic"), "cell"),
        (lambda service: service.inspect_cellview("MyFirstDesign", "NOT_gate", "layout"), "view"),
    ],
)
async def test_service_rejects_discovery_outside_allowlist(
    operation: Callable[[CadenceService], Awaitable[object]], message: str
) -> None:
    service = CadenceService(FakeBackend())

    with pytest.raises(InvalidInputError, match=message):
        await operation(service)


@pytest.mark.asyncio
async def test_service_profile_registry_and_submission() -> None:
    service = CadenceService(FakeBackend())

    listing = await service.list_profiles()
    profile = await service.get_profile("fixture-rc-transient")
    submitted = await service.submit_profile(
        "fixture-rc-transient", "nominal", RcTransientVariables()
    )

    assert listing.registry_version == 1
    assert profile.classification == "fixture"
    assert submitted.profile == "fixture-rc-transient"


@pytest.mark.asyncio
async def test_service_rejects_unknown_profile_and_corner() -> None:
    service = CadenceService(FakeBackend())

    with pytest.raises(InvalidInputError, match="profile"):
        await service.get_profile("unknown")
    with pytest.raises(InvalidInputError, match="corner"):
        await service.submit_profile("fixture-rc-transient", "fast", RcTransientVariables())
