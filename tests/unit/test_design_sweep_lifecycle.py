"""Registered bindings must reach only the proven engine and its guarded children."""

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from mcp import Client
from test_sweeps import FakeSweepBackend, finish

from cadence_mcp_bridge.design_sweep_service import (
    DesignSweepQuery,
    DesignSweepSubmission,
    fixture_pdk_adapter,
)
from cadence_mcp_bridge.designs import load_design_registry, reference_measurement_registry
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.pdk_adapters import PdkRegistry
from cadence_mcp_bridge.registered_sweeps import DesignSweepRequest, DesignSweepSelection
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.sweep_registry import DesignSweepRegistry, fixture_sweep_registry


def setup(tmp_path: Path, backend: FakeSweepBackend | None = None) -> CadenceService:
    return CadenceService(
        cast(CadenceBackend, backend or FakeSweepBackend()),
        designs=fixture_sweep_registry(),
        pdks=PdkRegistry(schema_version=2, adapters=(fixture_pdk_adapter(),)),
        analysis_journal=tmp_path / "analyses.db",
        sweep_journal=tmp_path / "sweeps.db",
    )


async def request(svc: CadenceService, **changes: object) -> DesignSweepRequest:
    selected = DesignSweepSelection(
        design_id="registered-rc-fixture",
        analysis_id="fixture-tran",
        variable_id="resistance",
        measurement_ids=("completion",),
    )
    contract = await svc.describe_design_sweep(selected)
    return DesignSweepRequest.model_validate_json(
        json.dumps(
            {
                **selected.model_dump(mode="json"),
                "expected_contract_sha256": contract.contract_sha256,
                "unit": "ohm",
                "values": ["900", "1000", "1100"],
                "fixed": {
                    "capacitance": {"value": "1e-12", "unit": "F"},
                    "stop-time": {"value": "1e-9", "unit": "s"},
                },
                **changes,
            }
        )
    )


async def submission(
    svc: CadenceService, req: DesignSweepRequest | None = None
) -> DesignSweepSubmission:
    req = req or await request(svc)
    plan = await svc.prepare_design_sweep(req)
    return DesignSweepSubmission(
        request=req, expected_plan_hash=plan.plan_hash, experiment_key=uuid4()
    )


def test_v5_loader_and_recomputed_redirect_rejected(tmp_path: Path) -> None:
    registry = fixture_sweep_registry()
    path = tmp_path / "registry.json"
    path.write_text(registry.model_dump_json(), encoding="utf-8")
    assert load_design_registry(path)[0] == registry
    for part, key, value in (
        ("designs", "environment_id", "other-host"),
        ("analysis_contracts", "adapter_contract_sha256", "0" * 64),
        ("measurement_contracts", "definition_sha256", "0" * 64),
    ):
        payload = registry.model_dump(mode="json")
        payload[part][0][key] = value
        with pytest.raises(ValueError):
            DesignSweepRegistry.model_validate_json(json.dumps(payload))


async def test_lifecycle_replay_restart_and_legacy_identity(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    backend.float_roundtrip = True
    svc = setup(tmp_path, backend)
    proposed = await submission(svc)
    prepared = await svc.prepare_design_sweep(proposed.request)
    assert prepared.execution_eligible and prepared.qualification_scope == "compiled_rc_fixture"
    assert not prepared.local_plan.execution_authorized  # v1 contract remains preparation only
    linear = await request(svc, values=None, linear={"start": "900", "stop": "1100", "step": "100"})
    assert await svc.prepare_design_sweep(linear) == prepared
    first = await svc.submit_design_sweep(proposed)
    await finish(svc._sweeps, first.engine.sweep_id)
    query = DesignSweepQuery(design_id=proposed.request.design_id, sweep_id=first.engine.sweep_id)
    result = await svc.design_sweep_result(query)
    assert result.engine.state == "SUCCEEDED" and backend.submit_calls == 3
    assert (
        result.definition.analog_measurement is False and result.spec_evaluation == "not_evaluated"
    )
    assert all(p.applied_fixed and p.quality == "valid" for p in result.engine.points)
    restarted = setup(tmp_path, backend)
    assert await restarted.design_sweep_result(query) == result
    again = await restarted.submit_design_sweep(proposed)
    await finish(restarted._sweeps, again.engine.sweep_id)
    assert backend.submit_calls == 3 and again.engine.sweep_id == first.engine.sweep_id
    assert (await svc.sweep_result(str(query.sweep_id))).plan_hash == result.engine.plan_hash
    cancelled = await svc.cancel_design_sweep(query)
    assert cancelled.engine.state == "SUCCEEDED" and not backend.cancelled
    assert cancelled.engine.updated_at == result.engine.updated_at
    changed = await submission(svc, await request(svc, values=["1200"]))
    with pytest.raises(InvalidInputError):
        await svc.submit_design_sweep(
            changed.model_copy(update={"experiment_key": proposed.experiment_key})
        )


async def test_reservation_failure_never_submits(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    backend.fail_reserve = True
    svc = setup(tmp_path, backend)
    first = await svc.submit_design_sweep(await submission(svc))
    await finish(svc._sweeps, first.engine.sweep_id)
    result = await svc.design_sweep_result(
        DesignSweepQuery(
            design_id=first.design_id,
            sweep_id=first.engine.sweep_id,
        )
    )
    assert result.engine.state == "UNKNOWN" and backend.submit_calls == 0
    assert result.engine.points[0].measurement_value is None


async def test_cancel_and_unknown_identity_are_bounded(tmp_path: Path) -> None:
    backend = FakeSweepBackend()
    backend.hold = True
    svc = setup(tmp_path, backend)
    first = await svc.submit_design_sweep(await submission(svc))
    await asyncio.sleep(0)
    query = DesignSweepQuery(design_id=first.design_id, sweep_id=first.engine.sweep_id)
    result = await svc.cancel_design_sweep(query)
    await finish(svc._sweeps, query.sweep_id)
    assert result.engine.state == "CANCELLED"
    assert len(backend.cancelled) == 1 and backend.submit_calls == 1
    for changed in (
        query.model_copy(update={"design_id": "unknown"}),
        query.model_copy(update={"sweep_id": uuid4()}),
    ):
        with pytest.raises(InvalidInputError):
            await svc.cancel_design_sweep(changed)
    assert len(backend.cancelled) == 1


async def test_corrupt_admission_and_effective_inputs_fail_closed(tmp_path: Path) -> None:
    class Mismatch(FakeSweepBackend):
        async def effective_sweep_values(self, job_id):
            return {"resistance_ohm": "999", "capacitance_f": "1e-12", "stop_time_s": "1e-9"}

    backend = Mismatch()
    svc = setup(tmp_path, backend)
    first = await svc.submit_design_sweep(await submission(svc))
    await finish(svc._sweeps, first.engine.sweep_id)
    query = DesignSweepQuery(design_id=first.design_id, sweep_id=first.engine.sweep_id)
    assert (await svc.design_sweep_result(query)).engine.state == "UNKNOWN"
    with sqlite3.connect(svc._sweeps.store.path) as connection:
        connection.execute("UPDATE registered_sweep_admissions SET plan='{}'")
    with pytest.raises(InvalidInputError):
        await svc.cancel_design_sweep(query)
    assert not backend.cancelled


async def test_unqualified_real_design_never_admitted(tmp_path: Path) -> None:
    from test_registered_sweeps import request as real_request

    svc = CadenceService(
        cast(CadenceBackend, FakeSweepBackend()),
        designs=reference_measurement_registry(),
        sweep_journal=tmp_path / "sweeps.db",
        analysis_journal=tmp_path / "analyses.db",
    )
    req = await real_request(svc)
    plan = await svc.prepare_design_sweep(req)
    assert not plan.execution_eligible and plan.blocking_reason == "numeric_contract_denied"
    before = svc._sweeps.store.path.read_bytes()
    with pytest.raises(InvalidInputError):
        await svc.submit_design_sweep(
            DesignSweepSubmission(
                request=req,
                expected_plan_hash=plan.plan_hash,
                experiment_key=uuid4(),
            )
        )
    assert svc._sweeps.store.path.read_bytes() == before


async def test_mcp_closed_schema_and_submission(tmp_path: Path) -> None:
    svc = setup(tmp_path)
    proposed = await submission(svc)
    async with Client(create_server(svc)) as client:
        tools = (await client.list_tools()).tools
        assert len(tools) == 70
        prepared = await client.call_tool(
            "cadence_prepare_design_sweep",
            {
                "request": proposed.request.model_dump(mode="json"),
            },
        )
        assert not prepared.is_error and prepared.structured_content["execution_eligible"]
        denied = await client.call_tool(
            "cadence_prepare_design_sweep",
            {
                "request": {**proposed.request.model_dump(mode="json"), "path": "/tmp/anything"},
            },
        )
        assert denied.is_error
        submitted = await client.call_tool(
            "cadence_submit_design_sweep",
            {"submission": proposed.model_dump(mode="json")},
        )
        assert not submitted.is_error
        parent = __import__("uuid").UUID(submitted.structured_content["engine"]["sweep_id"])
        await finish(svc._sweeps, parent)
        for name in (
            "cadence_design_sweep_status",
            "cadence_design_sweep_result",
            "cadence_cancel_design_sweep",
        ):
            response = await client.call_tool(
                name,
                {
                    "request": {
                        "design_id": proposed.request.design_id,
                        "sweep_id": str(parent),
                    }
                },
            )
            assert (
                not response.is_error
                and response.structured_content["engine"]["state"] == "SUCCEEDED"
            )
        denied = await client.call_tool(
            "cadence_prepare_design_sweep",
            {"request": proposed.request.model_dump(mode="json"), "script": "anything"},
        )
        assert denied.is_error


@pytest.mark.parametrize(
    "changes",
    [
        {"values": ["99"]},
        {"values": ["10001"]},
        {"values": ["900", "900.0"]},
        {"values": [str(100 + i) for i in range(17)]},
        {"unit": "V"},
        {"variable_id": "unknown"},
        {"analysis_id": "unknown"},
        {"design_id": "unknown"},
        {"measurement_ids": ["unknown"]},
        {"fixed": {}},
        {"values": ["NaN"]},
    ],
)
async def test_invalid_bindings_never_reach_admission(tmp_path: Path, changes: dict) -> None:
    svc = setup(tmp_path)
    before = svc._sweeps.store.path.read_bytes()
    try:
        req = await request(svc, **changes)
        prepared = await svc.prepare_design_sweep(req)
        assert not prepared.execution_eligible
        with pytest.raises(InvalidInputError):
            await svc.submit_design_sweep(
                DesignSweepSubmission(
                    request=req,
                    expected_plan_hash=prepared.plan_hash,
                    experiment_key=uuid4(),
                )
            )
    except (ValueError, InvalidInputError):
        pass
    assert svc._sweeps.store.path.read_bytes() == before


async def test_admission_crash_before_engine_is_resumable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = FakeSweepBackend()
    svc = setup(tmp_path, backend)
    proposed = await submission(svc)

    async def interrupted(_):
        raise RuntimeError("synthetic interruption before engine admission")

    monkeypatch.setattr(svc._sweeps, "submit", interrupted)
    with pytest.raises(RuntimeError):
        await svc.submit_design_sweep(proposed)
    assert backend.submit_calls == 0
    restored = setup(tmp_path, backend)
    first = await restored.submit_design_sweep(proposed)
    await finish(restored._sweeps, first.engine.sweep_id)
    assert backend.submit_calls == 3


async def test_corrupt_success_axis_and_missing_pdk_are_denied(tmp_path: Path) -> None:
    svc = setup(tmp_path)
    proposed = await submission(svc)
    first = await svc.submit_design_sweep(proposed)
    await finish(svc._sweeps, first.engine.sweep_id)
    with sqlite3.connect(svc._sweeps.store.path) as connection:
        raw = connection.execute("SELECT document FROM sweeps").fetchone()[0]
        document = json.loads(raw)
        document["points"][0]["applied_value"] = "999"
        connection.execute("UPDATE sweeps SET document=?", (json.dumps(document),))
    with pytest.raises(InvalidInputError):
        await svc.design_sweep_result(
            DesignSweepQuery(
                design_id=first.design_id,
                sweep_id=first.engine.sweep_id,
            )
        )
    other = setup(tmp_path / "missing")
    from cadence_mcp_bridge.design_sweep_service import DesignSweepSupervisor

    other._design_sweep_lifecycle = DesignSweepSupervisor(
        other._registered_sweeps,
        other._sweeps,
        PdkRegistry(schema_version=2, adapters=()),
    )
    plan = await other.prepare_design_sweep(await request(other))
    assert plan.blocking_reason == "pdk_mismatch" and not plan.execution_eligible
