"""Synthetic lifecycle/scientific security checks; never physical qualification."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

import pytest
from mcp import Client
from pydantic import ValidationError
from test_bias_range import payload
from test_sweeps import finish

from cadence_mcp_bridge.amplifier_sweeps import (
    DEFINITION_SHA,
    DESIGN,
    GRID,
    PROFILE,
    REGISTRY_SHA,
    AmplifierChild,
    AmplifierQuery,
    AmplifierSubmission,
    AmplifierSupervisor,
    AmplifierSweepRequest,
    make_amplifier_plan,
)
from cadence_mcp_bridge.designs import load_design_registry, reference_contract_registry
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.models import JobState, JobStatus
from cadence_mcp_bridge.pdk_adapters import PdkRegistry
from cadence_mcp_bridge.pdk_reference import reference_adapter
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.sweeps import SweepStore
from cadence_mcp_bridge.variable_contracts import canonical_digest

ROOT = Path(__file__).resolve().parents[2]


def request(mode: str = "dc", **changes: Any) -> AmplifierSweepRequest:
    return AmplifierSweepRequest.model_validate({
        "design_id": DESIGN, "variable_id": "vbiasn", "analysis_id": "grid-" + mode + "-v1",
        "measurement_id": "dc-supply-power-grid-v2" if mode == "dc" else "gain-10hz-grid-v1",
        "values": list(GRID), "unit": "V", "fixed": {"vbiasp": "0.702", "vdd": "1"},
        **changes,
    })


def child(job: UUID, mode: str, value: str, plan_hash: str, count: int) -> AmplifierChild:
    r = payload()["cases"][0 if mode == "dc" else 1]
    r.pop("case")
    r.update(schema_version=2, definition_sha256=DEFINITION_SHA,
             revision_id="reference-amplifier-bias-grid-v1", job_id=job, plan_hash=plan_hash,
             requested_vbiasn_v=value, counter={"campaign_id": "AUTO-PHASE-01", "count": count,
             "result_reserved_bytes": 8993636352 + (count - 76) * 128 * 1024**2})
    if mode == "dc":
        r["scalars"]["Vbiasn"] = float(value)
        r["sources"][2]["voltage_v"] = float(value)
    return AmplifierChild.model_validate(r)


class Transport:
    def __init__(self) -> None:
        self.records: dict[UUID, tuple[str, str, str, int]] = {}
        self.launched: set[UUID] = set()
        self.calls = 0
        self.hold = False
        self.failure = ""
        self.fail_first = False

    async def amplifier_reserve(self, j: UUID, mode: str, v: str, h: str) -> None:
        if self.failure == "budget":
            raise RemoteFailureError("budget/disk unavailable")
        assert j not in self.records
        self.records[j] = (mode, v, h, 77 + len(self.records))
        if self.failure == "reservation-response":
            raise RemoteFailureError("lost reservation response")

    async def amplifier_lookup_reservation(self, j: UUID) -> bool:
        return j in self.records

    async def amplifier_submit(self, j: UUID) -> JobStatus:
        assert j in self.records and j not in self.launched
        self.launched.add(j)
        self.calls += 1
        if self.failure == "submit-response":
            raise RemoteFailureError("lost submission response")
        return await self.amplifier_status(j)

    async def amplifier_status(self, j: UUID) -> JobStatus:
        if j not in self.launched:
            raise RemoteFailureError("not launched")
        state = JobState.RUNNING if self.hold else JobState.SUCCEEDED
        if self.fail_first and j == next(iter(self.records)):
            state = JobState.FAILED
        return JobStatus(job_id=j, state=state, profile=PROFILE, updated_at=datetime.now(UTC))

    async def amplifier_effective_values(self, j: UUID) -> dict[str, str]:
        return {"vbiasn": "0.33" if self.failure == "effective" else self.records[j][1],
                "vbiasp": "0.702", "vdd": "1"}

    async def amplifier_result(self, j: UUID) -> AmplifierChild:
        if self.failure == "result":
            raise RemoteFailureError("missing result")
        m, v, h, c = self.records[j]
        if self.failure == "plan":
            h = "f" * 64
        return child(j, m, v, h, c)


def setup(tmp: Path, transport: Transport) -> AmplifierSupervisor:
    registry = load_design_registry(ROOT / "docs/config/reference-amplifier-finite-grid-v1.json")[0]
    assert canonical_digest(registry) == REGISTRY_SHA
    return AmplifierSupervisor(
        registry, PdkRegistry(schema_version=2, adapters=(reference_adapter(),)),
        transport, tmp / "shared.db",
    )


def submission(mode: str = "dc") -> AmplifierSubmission:
    req = request(mode)
    return AmplifierSubmission(request=req, expected_plan_hash=make_amplifier_plan(req).plan_hash,
                               experiment_key=uuid4())


@pytest.mark.parametrize("changes", [
    {"design_id": "unknown"}, {"variable_id": "VBIASN"}, {"unit": "mV"},
    {"values": []}, {"values": ["0.319", "0.3190"]}, {"values": ["0.3195"]},
    {"values": ["0.318"]}, {"values": ["0.319"] * 4}, {"values": [float("nan")]},
    {"values": [0.32]}, {"values": ["1e999999999"]}, {"values": "0.32"},
    {"analysis_id": "tran"}, {"measurement_id": "gain-10hz-grid-v1"},
    {"fixed": {"vdd": "1"}}, {"fixed": {"vdd": "1.1", "vbiasp": "0.702"}},
    {"script": "x"}, {"path": "/tmp/x"}, {"linear": {}},
])
def test_closed_numeric_binding(changes: dict[str, Any]) -> None:
    with pytest.raises((ValidationError, InvalidInputError)):
        request(**changes)


def test_definition_registry_and_plan_gates(tmp_path: Path) -> None:
    t = Transport()
    svc = setup(tmp_path, t)
    assert svc.prepare(request()).engine_plan == make_amplifier_plan(
        request(values=[".319", ".320", ".321"])
    )
    svc.registry = reference_contract_registry()
    with pytest.raises(InvalidInputError):
        svc.prepare(request())


@pytest.mark.parametrize("mode", ["dc", "ac"])
async def test_real_codec_replay_restart_and_shared_journal(tmp_path: Path, mode: str) -> None:
    t = Transport()
    svc = setup(tmp_path, t)
    s = submission(mode)
    first = await svc.submit(s)
    await finish(svc.engine, first.sweep_id)
    q = AmplifierQuery(design_id=DESIGN, sweep_id=first.sweep_id)
    r = await svc.result(q)
    assert r.engine.state == "SUCCEEDED" and len(r.measurements) == 3
    assert [m.value for m in r.measurements] == ([0.002] * 3 if mode == "dc" else [60] * 3)
    assert all(p.applied_value == v for p, v in zip(r.engine.points, GRID, strict=True))
    restarted = setup(tmp_path, t)
    assert await restarted.result(q) == r
    await restarted.submit(s)
    await finish(restarted.engine, first.sweep_id)
    assert t.calls == 3
    assert (await restarted.cancel(q)).state == "SUCCEEDED"
    with pytest.raises(InvalidInputError):
        SweepStore(tmp_path / "shared.db").get(first.sweep_id)
    changed = submission("ac" if mode == "dc" else "dc").model_copy(
        update={"experiment_key": s.experiment_key}
    )
    with pytest.raises(InvalidInputError):
        await restarted.submit(changed)


@pytest.mark.parametrize("failure", [
    "budget", "reservation-response", "submit-response", "effective", "result",
])
async def test_uncertainty_never_blind_replays(tmp_path: Path, failure: str) -> None:
    t = Transport()
    t.failure = failure
    svc = setup(tmp_path, t)
    s = submission()
    first = await svc.submit(s)
    await finish(svc.engine, first.sweep_id)
    q = AmplifierQuery(design_id=DESIGN, sweep_id=first.sweep_id)
    if failure == "submit-response":
        assert (await svc.result(q)).engine.state == "SUCCEEDED" and t.calls == 3
    else:
        assert (await svc.status(q)).state == "UNKNOWN"
    old_calls = t.calls
    if failure not in ("reservation-response",):
        await svc.submit(s)
        await finish(svc.engine, first.sweep_id)
        assert t.calls == old_calls
    else:
        t.failure = ""
        await svc.submit(s)
        await finish(svc.engine, first.sweep_id)
        assert (await svc.result(q)).engine.state == "SUCCEEDED" and len(t.records) == 3


async def test_pending_cancel_active_completion_and_restart(tmp_path: Path) -> None:
    t = Transport()
    t.hold = True
    svc = setup(tmp_path, t)
    s = submission()
    first = await svc.submit(s)
    for _ in range(10):
        await asyncio.sleep(0)
        if t.calls:
            break
    q = AmplifierQuery(design_id=DESIGN, sweep_id=first.sweep_id)
    cancelled = await svc.cancel(q)
    assert cancelled.state == "RUNNING" and t.calls == 1
    assert [p.state for p in cancelled.points] == ["RUNNING", "CANCELLED", "CANCELLED"]
    svc.engine.tasks[first.sweep_id].cancel()
    await asyncio.gather(svc.engine.tasks[first.sweep_id], return_exceptions=True)
    t.hold = False
    restarted = setup(tmp_path, t)
    await restarted.submit(s)
    await finish(restarted.engine, first.sweep_id)
    r = await restarted.result(q)
    assert r.engine.state == "CANCELLED" and len(r.measurements) == 1 and t.calls == 1


async def test_partial_failure_and_bound_result(tmp_path: Path) -> None:
    t = Transport()
    t.fail_first = True
    svc = setup(tmp_path, t)
    first = await svc.submit(submission())
    await finish(svc.engine, first.sweep_id)
    r = await svc.result(AmplifierQuery(design_id=DESIGN, sweep_id=first.sweep_id))
    assert r.engine.state == "FAILED" and len(r.measurements) == 2
    assert len(r.model_dump_json()) < 65536 and r.spec_evaluation == "not_evaluated"


@pytest.mark.parametrize("change", [
    "hash", "value", "counter", "current", "source", "voltage", "gain",
])
def test_scientific_and_admission_drift(change: str) -> None:
    j = uuid5(uuid4(), "child")
    data = child(j, "ac" if change == "gain" else "dc", "0.319", "d" * 64, 77).model_dump(
        mode="json"
    )
    if change == "hash":
        data["definition_sha256"] = "f" * 64
    elif change == "value":
        data["requested_vbiasn_v"] = "0.32"
    elif change == "counter":
        data["counter"]["result_reserved_bytes"] += 1
    elif change == "current":
        data["sources"][0]["current_a"] = None
    elif change == "source":
        data["sources"].pop()
    elif change == "voltage":
        data["sources"][0]["voltage_v"] = 0.9
    elif change == "gain":
        data["spectrum"][0]["gain_db"] = 63
    with pytest.raises(ValidationError):
        AmplifierChild.model_validate(data)


def test_power_preserves_current_sign_instead_of_absolute_value() -> None:
    from cadence_mcp_bridge.power_measurements import delivered_power

    data = child(uuid5(uuid4(), "child"), "dc", "0.319", "d" * 64, 77).model_dump(mode="json")
    data["sources"][0]["current_a"] = 0.002
    assert delivered_power(AmplifierChild.model_validate(data).sources)[0] == -0.002


async def test_plan_response_substitution(tmp_path: Path) -> None:
    t = Transport()
    svc = setup(tmp_path, t)
    first = await svc.submit(submission())
    await finish(svc.engine, first.sweep_id)
    t.failure = "plan"
    with pytest.raises(InvalidInputError):
        await svc.result(AmplifierQuery(design_id=DESIGN, sweep_id=first.sweep_id))


async def test_mcp_closed_schema_and_default_denial(tmp_path: Path) -> None:
    svc = setup(tmp_path, Transport())
    service = CadenceService(
        cast(CadenceBackend, svc.transport), designs=svc.registry, pdks=svc.pdks,
        analysis_journal=tmp_path / "analysis.db", sweep_journal=tmp_path / "shared.db",
    )
    async with Client(create_server(service)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        schema = tools["cadence_prepare_amplifier_sweep"].input_schema
        assert schema["additionalProperties"] is False
        p = await client.call_tool("cadence_prepare_amplifier_sweep", {
            "request": request().model_dump(mode="json"),
        })
        assert not p.is_error and p.structured_content["execution_eligible"]
        for change in ({"path": "/tmp/x"}, {"values": ["0.3195"]}, {"design_id": "unknown"}):
            bad = request().model_dump(mode="json") | change
            r = await client.call_tool("cadence_prepare_amplifier_sweep", {"request": bad})
            assert r.is_error
        r = await client.call_tool("cadence_submit_amplifier_sweep", {
            "submission": submission().model_dump(mode="json") | {"expected_plan_hash": "f" * 64},
        })
        assert r.is_error
    service._amplifier_sweeps.registry = reference_contract_registry()
    with pytest.raises(InvalidInputError):
        await service.prepare_amplifier_sweep(request())
