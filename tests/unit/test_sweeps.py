"""Sweep identity and recovery tests use only an in-memory remote transport."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from mcp import Client

from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.models import (
    JobResult,
    JobState,
    JobStatus,
    JobSummary,
    RcTransientVariables,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.sweep_service import SweepSupervisor
from cadence_mcp_bridge.sweeps import (
    LinearValues,
    PointState,
    SweepRequest,
    SweepSubmission,
    make_plan,
)


def request(**changes: object) -> SweepRequest:
    base: dict[str, object] = {
        "profile_id": "fixture-rc-transient",
        "axis": "resistance_ohm",
        "unit": "ohm",
        "values": ("900", "1000", "1100"),
        "fixed": {"capacitance_f": "1e-12", "stop_time_s": "1e-9"},
    }
    base.update(changes)
    return SweepRequest.model_validate(base)


class FakeSweepBackend:
    def __init__(self) -> None:
        self.reserved: set[UUID] = set()
        self.submitted: dict[UUID, object] = {}
        self.submit_calls = 0
        self.cancelled: list[UUID] = []
        self.fail_reserve = False
        self.fail_point: UUID | None = None
        self.missing_result: UUID | None = None
        self.hold = False
        self.float_roundtrip = False

    async def reserve_sweep_attempt(self, job_id: UUID) -> None:
        if self.fail_reserve:
            raise RemoteFailureError("budget exhausted")
        self.reserved.add(job_id)

    async def lookup_sweep_reservation(self, job_id: UUID) -> bool:
        return job_id in self.reserved

    async def submit_profile(
        self, job_id: UUID, profile_id: str, corner: str, variables: object
    ) -> JobStatus:
        assert (
            job_id in self.reserved and profile_id == "fixture-rc-transient" and corner == "nominal"
        )
        self.submit_calls += 1
        self.submitted[job_id] = variables
        return self._status(job_id)

    def _status(self, job_id: UUID) -> JobStatus:
        if job_id not in self.submitted:
            raise RemoteFailureError("job missing")
        state = (
            JobState.CANCELLED
            if job_id in self.cancelled
            else JobState.RUNNING
            if self.hold
            else JobState.FAILED
            if job_id == self.fail_point
            else JobState.SUCCEEDED
        )
        return JobStatus(
            job_id=job_id, state=state, profile="fixture-rc-transient", updated_at=datetime.now(UTC)
        )

    async def status(self, job_id: UUID) -> JobStatus:
        return self._status(job_id)

    async def effective_sweep_values(self, job_id: UUID) -> dict[str, str]:
        variables = self.submitted[job_id]
        return {
            name: (
                format(getattr(variables, name), ".17g")
                if self.float_roundtrip
                else str(getattr(variables, name))
            )
            for name in ("resistance_ohm", "capacitance_f", "stop_time_s")
        }

    async def result(self, job_id: UUID) -> JobResult:
        if job_id == self.missing_result:
            raise RemoteFailureError("result missing")
        return JobResult(
            job_id=job_id,
            state=JobState.SUCCEEDED,
            exit_code=0,
            summary=JobSummary(text="0 errors", errors=0, warnings=0, notices=0),
        )

    async def cancel(self, job_id: UUID) -> JobStatus:
        if job_id not in self.submitted:
            raise RemoteFailureError("not owned")
        self.cancelled.append(job_id)
        return self._status(job_id)


async def finish(supervisor: SweepSupervisor, parent: UUID) -> None:
    await asyncio.wait_for(supervisor.tasks[parent], 5)


def test_plan_canonicalizes_and_rejects_invalid_axes() -> None:
    explicit = make_plan(request(values=("900.0", "1000", "1100.00")))
    linear = make_plan(
        request(values=None, linear=LinearValues(start="900", stop="1100", step="100"))
    )
    assert explicit.plan_hash == linear.plan_hash
    assert explicit.canonical_values == ("900", "1000", "1100")
    for changes in (
        {"values": ("900", "900.0")},
        {"values": ("NaN",)},
        {"values": ("1e999999999",)},
        {"values": ("99",)},
        {"unit": "s"},
        {"values": None, "linear": LinearValues(start="900", stop="1100", step="0")},
        {"values": None, "linear": LinearValues(start="900", stop="1100", step="-100")},
        {"values": None, "linear": LinearValues(start="900", stop="1050", step="100")},
        {"values": tuple(str(i + 900) for i in range(17))},
    ):
        with pytest.raises((InvalidInputError, ValueError)):
            make_plan(request(**changes))


@pytest.mark.asyncio
async def test_three_point_lifecycle_and_duplicate_request(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    supervisor = SweepSupervisor(backend, tmp_path / "journal.sqlite3")
    plan = await supervisor.plan(request())
    submission = SweepSubmission(plan=plan, experiment_key=uuid4())
    first = await supervisor.submit(submission)
    await finish(supervisor, first.sweep_id)
    result = await supervisor.result(first.sweep_id)
    assert result.state == "SUCCEEDED"
    assert [point.requested_value for point in result.points] == ["900", "1000", "1100"]
    assert [point.applied_value for point in result.points] == ["900", "1000", "1100"]
    assert all(point.applied_fixed == plan.canonical_fixed for point in result.points)
    assert all(
        point.measurement_value is True and point.quality == "valid" for point in result.points
    )
    assert len({point.point_id for point in result.points}) == 3
    assert len({point.child_job_id for point in result.points}) == 3
    assert len({point.operation_key for point in result.points}) == 3
    assert backend.submit_calls == 3
    again = await supervisor.submit(submission)
    await finish(supervisor, first.sweep_id)
    assert again.sweep_id == first.sweep_id and backend.submit_calls == 3
    with pytest.raises(InvalidInputError):
        await supervisor.submit(
            SweepSubmission(
                plan=make_plan(request(values=("1200",))), experiment_key=submission.experiment_key
            )
        )


@pytest.mark.asyncio
async def test_remote_float_roundtrip_is_recorded_not_misclassified(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    backend.float_roundtrip = True
    supervisor = SweepSupervisor(backend, tmp_path / "journal.sqlite3")
    submission = SweepSubmission(plan=make_plan(request(values=("900",))), experiment_key=uuid4())
    started = await supervisor.submit(submission)
    await finish(supervisor, started.sweep_id)
    point = (await supervisor.result(started.sweep_id)).points[0]
    assert point.state == PointState.SUCCEEDED
    assert point.applied_fixed is not None
    assert point.applied_fixed["capacitance_f"] != submission.plan.canonical_fixed["capacitance_f"]
    assert float(point.applied_fixed["capacitance_f"]) == float(
        submission.plan.canonical_fixed["capacitance_f"]
    )


@pytest.mark.asyncio
async def test_restart_reconciles_sent_child_without_duplicate(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    path = tmp_path / "journal.sqlite3"
    first = SweepSupervisor(backend, path)
    plan = make_plan(request(values=("900",)))
    submission = SweepSubmission(plan=plan, experiment_key=uuid4())
    record = first.store.create_or_get(submission)
    point = record["points"][0]
    child = UUID(point["child_job_id"])
    point["phase"] = "sending"
    first.store.put(record)
    backend.reserved.add(child)
    await backend.submit_profile(
        child,
        plan.request.profile_id,
        plan.request.corner,
        RcTransientVariables(resistance_ohm=900),
    )
    resumed = SweepSupervisor(backend, path)
    state = await resumed.submit(submission)
    await finish(resumed, state.sweep_id)
    assert (await resumed.status(state.sweep_id)).state == "SUCCEEDED"
    assert backend.submit_calls == 1


@pytest.mark.asyncio
async def test_unknown_submission_never_replays(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    supervisor = SweepSupervisor(backend, tmp_path / "journal.sqlite3")
    submission = SweepSubmission(plan=make_plan(request(values=("900",))), experiment_key=uuid4())
    record = supervisor.store.create_or_get(submission)
    record["points"][0]["phase"] = "sending"
    supervisor.store.put(record)
    state = await supervisor.submit(submission)
    await finish(supervisor, state.sweep_id)
    assert (await supervisor.status(state.sweep_id)).points[0].state == PointState.UNKNOWN
    assert backend.submit_calls == 0
    await supervisor.submit(submission)
    await finish(supervisor, state.sweep_id)
    assert backend.submit_calls == 0


@pytest.mark.asyncio
async def test_partial_failure_missing_result_and_exhausted_budget(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    supervisor = SweepSupervisor(backend, tmp_path / "journal.sqlite3")
    submission = SweepSubmission(plan=make_plan(request()), experiment_key=uuid4())
    first = supervisor.store.create_or_get(submission)
    backend.fail_point = UUID(first["points"][1]["child_job_id"])
    state = await supervisor.submit(submission)
    await finish(supervisor, state.sweep_id)
    points = (await supervisor.result(state.sweep_id)).points
    assert [point.state for point in points] == [
        PointState.SUCCEEDED,
        PointState.FAILED,
        PointState.SUCCEEDED,
    ]
    assert points[1].error and points[1].measurement_value is False
    next_submission = SweepSubmission(
        plan=make_plan(request(values=("1200",))), experiment_key=uuid4()
    )
    second = supervisor.store.create_or_get(next_submission)
    backend.missing_result = UUID(second["points"][0]["child_job_id"])
    next_state = await supervisor.submit(next_submission)
    await finish(supervisor, next_state.sweep_id)
    assert (await supervisor.result(next_state.sweep_id)).points[0].state == PointState.UNKNOWN
    backend.fail_reserve = True
    exhausted = await supervisor.submit(
        SweepSubmission(plan=make_plan(request(values=("1300",))), experiment_key=uuid4())
    )
    await finish(supervisor, exhausted.sweep_id)
    assert (await supervisor.result(exhausted.sweep_id)).points[0].state == PointState.UNKNOWN


def test_corrupt_checkpoint_fails_closed(tmp_path: Path) -> None:
    supervisor = SweepSupervisor(FakeSweepBackend(), tmp_path / "journal.sqlite3")
    submission = SweepSubmission(plan=make_plan(request()), experiment_key=uuid4())
    record = supervisor.store.create_or_get(submission)
    with sqlite3.connect(supervisor.store.path) as connection:
        record["points"][0]["requested_value"] = "9999"
        connection.execute("UPDATE sweeps SET document=?", (json.dumps(record),))
    with pytest.raises(InvalidInputError, match="corrupt"):
        supervisor.store.get(UUID(record["sweep_id"]))


@pytest.mark.asyncio
async def test_cancel_signals_only_recorded_child(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    backend.hold = True
    supervisor = SweepSupervisor(backend, tmp_path / "journal.sqlite3")
    submission = SweepSubmission(plan=make_plan(request()), experiment_key=uuid4())
    state = await supervisor.submit(submission)
    for _ in range(100):
        current = await supervisor.status(state.sweep_id)
        if current.points[0].state == PointState.RUNNING:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("first child did not start")
    cancelled = await supervisor.cancel(state.sweep_id)
    assert cancelled.state == "CANCELLED"
    assert cancelled.points[0].state == PointState.CANCELLED
    assert all(point.state == PointState.CANCELLED for point in cancelled.points[1:])
    assert backend.cancelled == [cancelled.points[0].child_job_id]
    assert backend.submit_calls == 1


@pytest.mark.asyncio
async def test_three_point_typed_mcp_flow(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    service = CadenceService(backend)  # type: ignore[arg-type]
    service._sweeps = SweepSupervisor(backend, tmp_path / "journal.sqlite3")
    async with Client(create_server(service)) as client:
        planned = await client.call_tool(
            "cadence_plan_sweep", {"request": request().model_dump(mode="json")}
        )
        assert not planned.is_error and isinstance(planned.structured_content, dict)
        submission = {"plan": planned.structured_content, "experiment_key": str(uuid4())}
        started = await client.call_tool("cadence_submit_sweep", {"submission": submission})
        assert not started.is_error and isinstance(started.structured_content, dict)
        sweep_id = started.structured_content["sweep_id"]
        await finish(service._sweeps, UUID(sweep_id))
        result = await client.call_tool("cadence_sweep_result", {"sweep_id": sweep_id})
        assert not result.is_error and isinstance(result.structured_content, dict)
        assert result.structured_content["state"] == "SUCCEEDED"
        assert len(result.structured_content["points"]) == 3
