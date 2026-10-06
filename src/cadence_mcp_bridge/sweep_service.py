"""Sweep supervisor: deterministic children, durable recovery, no blind replay."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, cast
from uuid import UUID

from cadence_mcp_bridge.errors import BridgeError, InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.models import JobResult, JobState, JobStatus, RcTransientVariables
from cadence_mcp_bridge.sweeps import (
    PointState,
    SweepPlan,
    SweepRequest,
    SweepResult,
    SweepStatus,
    SweepStore,
    SweepSubmission,
    decimal_text,
    make_plan,
)


class SweepBackend(Protocol):
    async def reserve_sweep_attempt(self, job_id: UUID) -> None: ...
    async def lookup_sweep_reservation(self, job_id: UUID) -> bool: ...
    async def effective_sweep_values(self, job_id: UUID) -> dict[str, str]: ...
    async def submit_profile(
        self, job_id: UUID, profile_id: str, corner: str, variables: RcTransientVariables
    ) -> JobStatus: ...
    async def status(self, job_id: UUID) -> JobStatus: ...
    async def result(self, job_id: UUID) -> JobResult: ...
    async def cancel(self, job_id: UUID) -> JobStatus: ...


class SweepSupervisor:
    STORE_TYPE: ClassVar[type[SweepStore]] = SweepStore
    STATUS_MODEL: ClassVar[type[SweepStatus]] = SweepStatus
    RESULT_MODEL: ClassVar[type[SweepResult]] = SweepResult
    STOP_ACTIVE_ON_CANCEL: ClassVar[bool] = True

    def __init__(self, backend: SweepBackend, journal: Path) -> None:
        self.backend = backend
        self.store = self.STORE_TYPE(journal)
        self.tasks: dict[UUID, asyncio.Task[None]] = {}
        self.locks: dict[UUID, asyncio.Lock] = {}

    async def plan(self, request: SweepRequest) -> SweepPlan:
        return make_plan(request)

    async def submit(self, submission: SweepSubmission) -> SweepStatus:
        document = self.store.create_or_get(submission)
        parent = UUID(document["sweep_id"])
        if not document["cancel_requested"] and (
            parent not in self.tasks or self.tasks[parent].done()
        ):
            self.tasks[parent] = asyncio.create_task(self._run(parent))
        return self._status(document)

    async def status(self, sweep_id: UUID) -> SweepStatus:
        return self._status(self.store.get(sweep_id))

    async def result(self, sweep_id: UUID) -> SweepResult:
        document = self.store.get(sweep_id)
        plan = self.store.PLAN_MODEL.model_validate(document["plan"])
        return self.RESULT_MODEL(
            **self._status(document).model_dump(),
            profile_id=plan.request.profile_id,
            axis=plan.request.axis,
            unit=plan.request.unit,
            fixed=plan.canonical_fixed,
        )

    async def cancel(self, sweep_id: UUID) -> SweepStatus:
        lock = self.locks.setdefault(sweep_id, asyncio.Lock())
        async with lock:
            document = self.store.get(sweep_id)
            document["cancel_requested"] = True
            for point in document["points"]:
                if point["state"] == PointState.NOT_RUN and point.get("phase") != "sending":
                    point["state"] = PointState.CANCELLED
                    point["phase"] = "cancelled"
                    point["quality"] = "not_available"
                elif point.get("phase") == "sending":
                    point["state"] = PointState.UNKNOWN
                    point["error"] = "submission outcome uncertain during cancellation"
            self.store.put(document)
            active = [
                point
                for point in document["points"]
                if point["state"] == PointState.RUNNING or point.get("phase") == "sending"
            ]
            plan = self.store.PLAN_MODEL.model_validate(document["plan"])
        for point in active:
            try:
                observed = await self.backend.status(UUID(point["child_job_id"]))
                if (
                    observed.job_id != UUID(point["child_job_id"])
                    or observed.profile != plan.request.profile_id
                ):
                    raise RemoteFailureError("cancel target identity mismatch")
                response = await self.backend.cancel(UUID(point["child_job_id"]))
                if response.job_id != UUID(point["child_job_id"]):
                    raise RemoteFailureError("cancel returned another child job")
                for _ in range(120):
                    if response.state in (
                        JobState.SUCCEEDED,
                        JobState.FAILED,
                        JobState.CANCELLED,
                        JobState.UNKNOWN,
                    ):
                        break
                    await asyncio.sleep(1)
                    response = await self.backend.status(UUID(point["child_job_id"]))
                    if response.job_id != UUID(point["child_job_id"]):
                        raise RemoteFailureError("cancel status returned another child job")
                if response.state == JobState.CANCELLED:
                    self._update_point(
                        sweep_id,
                        point["point_id"],
                        state=PointState.CANCELLED,
                        phase="cancelled",
                        quality="invalid",
                        measurement_value=False,
                        error="owned child cancelled",
                    )
                elif response.state == JobState.FAILED:
                    self._update_point(
                        sweep_id,
                        point["point_id"],
                        state=PointState.FAILED,
                        phase="complete",
                        quality="invalid",
                        measurement_value=False,
                        error="owned child failed while cancelling",
                    )
                else:
                    self._update_point(
                        sweep_id,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="cancellation terminal result needs reconciliation",
                    )
            except BridgeError:
                # Preserve uncertainty. Never signal another process or claim cancellation.
                self._update_point(
                    sweep_id,
                    point["point_id"],
                    state=PointState.UNKNOWN,
                    error="cancellation outcome uncertain",
                )
        return self._status(self.store.get(sweep_id))

    async def _run(self, parent: UUID) -> None:
        document = self.store.get(parent)
        plan = self.store.PLAN_MODEL.model_validate(document["plan"])
        for index in range(plan.point_count):
            document = self.store.get(parent)
            point = document["points"][index]
            if (
                document["cancel_requested"]
                and (self.STOP_ACTIVE_ON_CANCEL or point.get("phase") not in ("sending", "running"))
            ) or point["state"] in (
                PointState.SUCCEEDED,
                PointState.FAILED,
                PointState.CANCELLED,
            ):
                continue
            if point["state"] == PointState.UNKNOWN and point.get("phase") not in (
                "sending",
                "running",
                "reserving",
                "reserved",
            ):
                return
            child = UUID(point["child_job_id"])
            phase = point.get("phase", "not_run")
            if phase == "sending":
                # A lost submit response may have created the child. Lookup only.
                try:
                    remote = await self.backend.status(child)
                except BridgeError:
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="submit outcome uncertain; operator reconciliation required",
                    )
                    return
                if remote.job_id != child or remote.profile != plan.request.profile_id:
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="remote child identity mismatch",
                    )
                    return
                try:
                    applied, applied_fixed = await self._check_effective(child, plan, point)
                except (BridgeError, ValueError):
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="effective child inputs could not be verified",
                    )
                    return
                self._update_point(
                    parent,
                    point["point_id"],
                    state=PointState.RUNNING,
                    phase="running",
                    applied_value=applied,
                    applied_fixed=applied_fixed,
                    provenance="remote_spectre_profile",
                )
            elif phase == "not_run":
                self._update_point(parent, point["point_id"], phase="reserving")
                try:
                    await self._reserve_child(child, plan, point)
                except BridgeError:
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="budget reservation uncertain or unavailable",
                    )
                    return
                self._update_point(parent, point["point_id"], phase="reserved")
            if phase in ("not_run", "reserved", "reserving"):
                # Recovery of an uncertain reservation is lookup-only.
                if phase == "reserving":
                    try:
                        reserved = await self.backend.lookup_sweep_reservation(child)
                    except BridgeError:
                        self._update_point(
                            parent,
                            point["point_id"],
                            state=PointState.UNKNOWN,
                            error="budget reservation reconciliation failed",
                        )
                        return
                    if not reserved:
                        self._update_point(
                            parent,
                            point["point_id"],
                            state=PointState.UNKNOWN,
                            error="budget reservation outcome unknown",
                        )
                        return
                current = self.store.get(parent)
                if current["cancel_requested"]:
                    self._update_point(
                        parent, point["point_id"], state=PointState.CANCELLED, phase="cancelled"
                    )
                    continue
                self._update_point(parent, point["point_id"], phase="sending")
                try:
                    remote = await self._submit_child(child, plan, point)
                except BridgeError:
                    # Query the exact deterministic child. Absence does not authorize retry.
                    try:
                        remote = await self.backend.status(child)
                    except BridgeError:
                        self._update_point(
                            parent,
                            point["point_id"],
                            state=PointState.UNKNOWN,
                            error="submit outcome uncertain; operator reconciliation required",
                        )
                        return
                if remote.job_id != child or remote.profile != plan.request.profile_id:
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="remote child identity mismatch",
                    )
                    return
                try:
                    applied, applied_fixed = await self._check_effective(child, plan, point)
                except (BridgeError, ValueError):
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="effective child inputs could not be verified",
                    )
                    return
                self._update_point(
                    parent,
                    point["point_id"],
                    state=PointState.RUNNING,
                    phase="running",
                    applied_value=applied,
                    applied_fixed=applied_fixed,
                    provenance="remote_spectre_profile",
                )
            for _ in range(600):
                if self.STOP_ACTIVE_ON_CANCEL and self.store.get(parent)["cancel_requested"]:
                    break
                try:
                    remote = await self.backend.status(child)
                except BridgeError:
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="remote status unavailable",
                    )
                    return
                if remote.job_id != child or remote.profile != plan.request.profile_id:
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="remote status identity mismatch",
                    )
                    return
                if remote.state in (
                    JobState.SUCCEEDED,
                    JobState.FAILED,
                    JobState.CANCELLED,
                    JobState.UNKNOWN,
                ):
                    break
                await asyncio.sleep(1)
            else:
                self._update_point(
                    parent,
                    point["point_id"],
                    state=PointState.UNKNOWN,
                    error="bounded status polling ended",
                )
                return
            if self.STOP_ACTIVE_ON_CANCEL and self.store.get(parent)["cancel_requested"]:
                return
            if remote.state == JobState.SUCCEEDED:
                try:
                    result = await self.backend.result(child)
                except BridgeError:
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="completed child result missing",
                    )
                    return
                if (
                    result.job_id != child
                    or result.state != JobState.SUCCEEDED
                    or result.exit_code != 0
                ):
                    self._update_point(
                        parent,
                        point["point_id"],
                        state=PointState.UNKNOWN,
                        error="completed child result identity or quality mismatch",
                    )
                    return
                self._update_point(
                    parent,
                    point["point_id"],
                    state=PointState.SUCCEEDED,
                    phase="complete",
                    measurement_value=True,
                    quality="valid",
                )
            else:
                self._update_point(
                    parent,
                    point["point_id"],
                    state=PointState(remote.state.upper()),
                    phase="complete",
                    measurement_value=False,
                    quality="invalid",
                    error="remote simulation did not succeed",
                )

    def _update_point(self, parent: UUID, point_id: str, **fields: object) -> None:
        document = self.store.get(parent)
        point = next((item for item in document["points"] if item["point_id"] == point_id), None)
        if point is None:
            raise InvalidInputError("point identity missing from checkpoint")
        point.update(fields)
        self.store.put(document)

    async def _reserve_child(
        self, child: UUID, plan: SweepPlan, point: dict[str, Any]
    ) -> None:
        await self.backend.reserve_sweep_attempt(child)

    async def _submit_child(
        self, child: UUID, plan: SweepPlan, point: dict[str, Any]
    ) -> JobStatus:
        variables = dict(plan.canonical_fixed)
        variables[plan.request.axis] = point["requested_value"]
        return await self.backend.submit_profile(
            child, plan.request.profile_id, plan.request.corner,
            RcTransientVariables(**{k: float(v) for k, v in variables.items()}),
        )

    async def _check_effective(
        self, child: UUID, plan: SweepPlan, point: dict[str, object]
    ) -> tuple[str, dict[str, str]]:
        remote = await self.backend.effective_sweep_values(child)
        expected = dict(plan.canonical_fixed)
        expected[plan.request.axis] = str(point["requested_value"])
        if set(remote) != set(expected):
            raise RemoteFailureError("effective variable set mismatch")
        applied = {name: decimal_text(value) for name, value in remote.items()}
        # The existing runner writes its reviewed numeric values through a
        # 17-digit float round trip. Keep the exact applied string in results,
        # while comparing the represented binary float to the requested one.
        if any(float(applied[name]) != float(Decimal(value)) for name, value in expected.items()):
            raise RemoteFailureError("effective variable values mismatch")
        return applied[plan.request.axis], {name: applied[name] for name in plan.canonical_fixed}

    @classmethod
    def _status(cls, document: dict[str, Any]) -> SweepStatus:
        points = tuple(cls.STORE_TYPE.POINT_MODEL.model_validate(p) for p in document["points"])
        if any(point.state == PointState.UNKNOWN for point in points):
            state = "UNKNOWN"
        elif any(point.state == PointState.FAILED for point in points):
            state = "FAILED"
        elif document["cancel_requested"]:
            state = "CANCELLED"
        elif all(point.state == PointState.SUCCEEDED for point in points):
            state = "SUCCEEDED"
        else:
            state = "RUNNING"
        return cls.STATUS_MODEL(
            sweep_id=UUID(document["sweep_id"]),
            plan_hash=document["plan_hash"],
            experiment_key=UUID(document["experiment_key"]),
            state=cast(Literal["RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"], state),
            points=points,
            updated_at=document["updated_at"],
        )
