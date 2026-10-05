"""Bounded, persistent one-variable sweeps of reviewed simulation profiles.

The original actual-circuit profile has no variable binding.  Coupled historical
bias pairs are deliberately not registered here as a one-variable sweep.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid5

from pydantic import Field, model_validator

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.models import ContractModel, ProfileVariableSpec
from cadence_mcp_bridge.profiles import FIXTURE_PROFILE, FIXTURE_PROFILE_ID

SWEEP_NAMESPACE = UUID("5d34bc53-2894-4e63-b931-790d0eb2b487")
MAX_POINTS = 16


def decimal_text(value: str) -> str:
    if not isinstance(value, str) or len(value) > 48:
        raise InvalidInputError("sweep values must be bounded decimal strings")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidInputError("invalid sweep decimal") from exc
    if not number.is_finite():
        raise InvalidInputError("sweep value must be finite")
    if number == 0:
        return "0"
    exponent = number.as_tuple().exponent
    if not isinstance(exponent, int) or abs(number.adjusted()) > 30 or abs(exponent) > 40:
        raise InvalidInputError("sweep decimal precision or exponent exceeds limit")
    return format(number.normalize(), "f")


class LinearValues(ContractModel):
    start: str
    stop: str
    step: str


class SweepRequest(ContractModel):
    profile_id: Literal["fixture-rc-transient"]
    corner: Literal["nominal"] = "nominal"
    axis: Literal["resistance_ohm", "capacitance_f", "stop_time_s"]
    unit: Literal["ohm", "F", "s"]
    values: Annotated[tuple[str, ...] | None, Field(max_length=MAX_POINTS)] = None
    linear: LinearValues | None = None
    fixed: dict[Literal["resistance_ohm", "capacitance_f", "stop_time_s"], str]
    measurements: tuple[Literal["simulation_completion"], ...] = ("simulation_completion",)
    initial_condition: Literal["independent"] = "independent"

    @model_validator(mode="after")
    def validate_shape(self) -> SweepRequest:
        if (self.values is None) == (self.linear is None):
            raise ValueError("select explicit values or linear range")
        if self.measurements != ("simulation_completion",):
            raise ValueError("only the reviewed completion measurement is available")
        return self


class SweepPlan(ContractModel):
    plan_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    request: SweepRequest
    canonical_values: tuple[str, ...]
    canonical_fixed: dict[str, str]
    revision_id: Literal["fixture-rc-transient-v1"] = "fixture-rc-transient-v1"
    point_count: Annotated[int, Field(ge=1, le=MAX_POINTS)]
    classification: Literal["one_variable_fixture"] = "one_variable_fixture"


class SweepSubmission(ContractModel):
    plan: SweepPlan
    experiment_key: UUID


class PointState(StrEnum):
    NOT_RUN = "NOT_RUN"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class SweepPoint(ContractModel):
    point_id: UUID
    child_job_id: UUID
    operation_key: UUID
    state: PointState
    requested_value: str
    applied_value: str | None = None
    applied_fixed: dict[str, str] | None = None
    unit: Literal["ohm", "F", "s"]
    measurement_id: Literal["simulation_completion"] = "simulation_completion"
    measurement_value: bool | None = None
    measurement_unit: Literal["1"] = "1"
    quality: Literal["valid", "invalid", "not_available"] = "not_available"
    error: Annotated[str, Field(max_length=160)] | None = None
    revision_id: Literal["fixture-rc-transient-v1"] = "fixture-rc-transient-v1"
    provenance: Literal["remote_spectre_profile", "not_run"] = "not_run"
    phase: Literal[
        "not_run", "reserving", "reserved", "sending", "running", "complete", "cancelled"
    ] = "not_run"

    @model_validator(mode="after")
    def validate_state_evidence(self) -> SweepPoint:
        if self.state == PointState.SUCCEEDED and (
            self.applied_value is None
            or self.applied_fixed is None
            or self.measurement_value is not True
            or self.quality != "valid"
            or self.provenance != "remote_spectre_profile"
            or self.phase != "complete"
        ):
            raise ValueError("successful point lacks verified simulation evidence")
        if self.state == PointState.FAILED and (
            self.measurement_value is not False or self.quality != "invalid" or not self.error
        ):
            raise ValueError("failed point lacks explicit failure evidence")
        if self.state == PointState.NOT_RUN and self.measurement_value is not None:
            raise ValueError("not-run point cannot have a measurement")
        return self


class SweepStatus(ContractModel):
    sweep_id: UUID
    plan_hash: str
    experiment_key: UUID
    state: Literal["RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"]
    points: tuple[SweepPoint, ...]
    updated_at: datetime
    initial_condition: Literal["independent"] = "independent"
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class SweepResult(SweepStatus):
    profile_id: Literal["fixture-rc-transient"] = "fixture-rc-transient"
    axis: Literal["resistance_ohm", "capacitance_f", "stop_time_s"]
    unit: Literal["ohm", "F", "s"]
    fixed: dict[str, str]


def make_plan(request: SweepRequest) -> SweepPlan:
    if request.profile_id != FIXTURE_PROFILE_ID:
        raise InvalidInputError("actual-circuit sweep has no approved one-variable binding")
    specs = {spec.name: spec for spec in FIXTURE_PROFILE.variables}
    if request.unit != specs[request.axis].unit:
        raise InvalidInputError("axis unit mismatch")
    if set(request.fixed) != set(specs) - {request.axis}:
        raise InvalidInputError("fixed variables must contain exactly the non-axis variables")
    fixed: dict[str, str] = {
        name: decimal_text(value) for name, value in sorted(request.fixed.items())
    }
    for name, value in fixed.items():
        _range(name, value, specs)
    if request.values is not None:
        values = tuple(decimal_text(value) for value in request.values)
    else:
        assert request.linear is not None
        start = Decimal(decimal_text(request.linear.start))
        stop = Decimal(decimal_text(request.linear.stop))
        step = Decimal(decimal_text(request.linear.step))
        if step == 0 or (stop - start) * step < 0:
            raise InvalidInputError("zero or wrong-direction sweep step")
        values_list: list[str] = []
        current = start
        while (current <= stop if step > 0 else current >= stop) and len(values_list) <= MAX_POINTS:
            values_list.append(decimal_text(str(current)))
            current += step
        if current - step != stop:
            raise InvalidInputError("linear sweep must land exactly on stop")
        values = tuple(values_list)
    if not 1 <= len(values) <= MAX_POINTS or len(set(values)) != len(values):
        raise InvalidInputError("sweep point count or duplicate values invalid")
    for value in values:
        _range(request.axis, value, specs)
    canonical = {
        "profile_id": request.profile_id,
        "corner": request.corner,
        "axis": request.axis,
        "unit": request.unit,
        "values": values,
        "fixed": fixed,
        "measurements": request.measurements,
        "initial_condition": request.initial_condition,
        "revision_id": "fixture-rc-transient-v1",
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return SweepPlan(
        plan_hash=digest,
        request=request,
        canonical_values=values,
        canonical_fixed=fixed,
        point_count=len(values),
    )


def _range(name: str, value: str, specs: dict[str, ProfileVariableSpec]) -> None:
    numeric = Decimal(value)
    spec = specs[name]
    if numeric < Decimal(str(spec.minimum)) or numeric > Decimal(str(spec.maximum)):
        raise InvalidInputError("sweep value outside reviewed profile range")
    if not math.isfinite(float(numeric)):
        raise InvalidInputError("sweep value cannot be represented as finite float")


def sweep_id(plan_hash: str, key: UUID) -> UUID:
    return uuid5(SWEEP_NAMESPACE, plan_hash + ":" + str(key))


def point_id(parent: UUID, index: int) -> UUID:
    return uuid5(parent, "point:" + str(index))


def child_id(parent: UUID, index: int) -> UUID:
    return uuid5(parent, "child:" + str(index))


def operation_key(parent: UUID, index: int) -> UUID:
    return uuid5(parent, "operation:" + str(index))


def now() -> str:
    return datetime.now(UTC).isoformat()


class SweepStore:
    """Private SQLite journal; a corrupt checkpoint fails closed."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or path.parent.is_symlink():
            raise InvalidInputError("sweep journal path is unsafe")
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sweeps (id TEXT PRIMARY KEY, "
                "experiment_key TEXT UNIQUE NOT NULL, plan_hash TEXT NOT NULL, "
                "document TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def create_or_get(self, submission: SweepSubmission) -> dict[str, Any]:
        expected = make_plan(submission.plan.request)
        if expected != submission.plan:
            raise InvalidInputError("sweep plan was modified after planning")
        parent = sweep_id(expected.plan_hash, submission.experiment_key)
        points = [
            {
                "point_id": str(point_id(parent, i)),
                "child_job_id": str(child_id(parent, i)),
                "operation_key": str(operation_key(parent, i)),
                "state": PointState.NOT_RUN,
                "requested_value": value,
                "unit": submission.plan.request.unit,
            }
            for i, value in enumerate(expected.canonical_values)
        ]
        document = {
            "sweep_id": str(parent),
            "plan_hash": expected.plan_hash,
            "experiment_key": str(submission.experiment_key),
            "plan": expected.model_dump(mode="json"),
            "points": points,
            "updated_at": now(),
            "cancel_requested": False,
        }
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT document FROM sweeps WHERE experiment_key=?",
                (str(submission.experiment_key),),
            ).fetchone()
            if row is not None:
                found = self._parse(row[0])
                if found["plan_hash"] != expected.plan_hash:
                    raise InvalidInputError("experiment key already belongs to another plan")
                return found
            connection.execute(
                "INSERT INTO sweeps VALUES (?,?,?,?)",
                (
                    str(parent),
                    str(submission.experiment_key),
                    expected.plan_hash,
                    json.dumps(document, sort_keys=True),
                ),
            )
        return document

    def get(self, parent: UUID) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT document FROM sweeps WHERE id=?", (str(parent),)
            ).fetchone()
        if row is None:
            raise InvalidInputError("unknown sweep id")
        return self._parse(row[0])

    def put(self, document: dict[str, Any]) -> None:
        document["updated_at"] = now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE sweeps SET document=? WHERE id=? AND plan_hash=?",
                (json.dumps(document, sort_keys=True), document["sweep_id"], document["plan_hash"]),
            )
            if cursor.rowcount != 1:
                raise InvalidInputError("sweep journal identity changed")

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        try:
            document = json.loads(raw)
            expected = make_plan(SweepRequest.model_validate(document["plan"]["request"]))
            parent = sweep_id(expected.plan_hash, UUID(document["experiment_key"]))
            if (
                document["sweep_id"] != str(parent)
                or document["plan_hash"] != expected.plan_hash
                or type(document["cancel_requested"]) is not bool
                or SweepPlan.model_validate(document["plan"]) != expected
                or len(document["points"]) != expected.point_count
            ):
                raise ValueError("identity mismatch")
            for i, point in enumerate(document["points"]):
                if (
                    point["point_id"] != str(point_id(parent, i))
                    or point["child_job_id"] != str(child_id(parent, i))
                    or point["operation_key"] != str(operation_key(parent, i))
                    or point["requested_value"] != expected.canonical_values[i]
                    or point["unit"] != expected.request.unit
                ):
                    raise ValueError("point mismatch")
                validated = SweepPoint.model_validate(point)
                if validated.state == PointState.SUCCEEDED:
                    applied = validated.applied_fixed
                    if applied is None or set(applied) != set(expected.canonical_fixed):
                        raise ValueError("effective fixed set mismatch")
                    if any(
                        float(Decimal(applied[n])) != float(Decimal(v))
                        for n, v in expected.canonical_fixed.items()
                    ):
                        raise ValueError("effective fixed value mismatch")
                    if float(Decimal(validated.applied_value or "NaN")) != float(
                        Decimal(expected.canonical_values[i])
                    ):
                        raise ValueError("effective axis mismatch")
            return cast(dict[str, Any], document)
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidInputError(
                "sweep checkpoint is corrupt; operator review required"
            ) from exc
