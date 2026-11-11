"""Mocked registered-result boundary tests; no VM or authentication qualification."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from test_cmos_delay import payload

import cadence_mcp_bridge.cmos_delay_service as service_module
from cadence_mcp_bridge.cmos_delay_service import CmosDelayResultQuery, CmosDelayService
from cadence_mcp_bridge.operator_lifecycle import ProviderObservation
from cadence_mcp_bridge.operator_operations import (
    DurableOperation,
    OperationPlan,
    OperationProgress,
    OperationRejected,
    OperationRequest,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext


@pytest.fixture
def connected(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, ...]:
    sample = payload()
    definition = sample["definition"]
    for name in ("phl_window", "plh_window"):
        definition[name] = {k: v / 10 for k, v in definition[name].items()}
    for name in ("maximum_sample_gap_s", "maximum_crossing_bracket_s"):
        definition[name] /= 10
    waves = sample["tran_waveforms"]
    for wave in waves.values():
        for point in wave:
            point["time_s"] /= 10
    waves["vdd"] = [{"time_s": p["time_s"], "value_v": 1.0} for p in waves["vin"]]
    plan = OperationPlan(
        resource_domain_sha256="a" * 64, runner_sha256="b" * 64, ledger_ref="retained",
        environment_sha256="c" * 64, design_sha256="d" * 64, pdk_sha256="e" * 64,
        grant_sha256="f" * 64, analysis="tran",
        request=OperationRequest(schema_version=1, design_id="cmos", analysis_id="tran",
                                 values=(), result_reservation_bytes=1048576),
    )
    operation_id = sample["evidence"]["operation_id"]
    record = DurableOperation(
        operation_id=operation_id, plan=plan, event_count=5,
        progress=OperationProgress(phase="SUCCEEDED", remote_revision=4,
                                   provider_receipt_sha256="a" * 64),
    )
    observed = ProviderObservation(
        operation_id=operation_id, plan_sha256=plan.plan_sha256,
        resource_domain_sha256=plan.resource_domain_sha256, ledger_ref=plan.ledger_ref,
        progress=record.progress,
    )
    summaries = []
    for name, wave in waves.items():
        values = [p["value_v"] for p in wave]
        mean = sum((a["value_v"] / 2 + b["value_v"] / 2)
                   * (b["time_s"] - a["time_s"])
                   for a, b in zip(wave, wave[1:], strict=False)) / 2
        summaries.append(dict(logical_id=name, unit="V", minimum=min(values), maximum=max(values),
                              first=values[0], last=values[-1], time_weighted_mean=mean,
                              sample_count=len(wave), start_s=0, stop_s=2))
    data = dict(
        status="NATIVE_RESULT_RETRIEVED", operation_id=operation_id, plan_sha256=plan.plan_sha256,
        design_id="cmos", analysis="tran", measurement_id="tran-summary",
        native_provenance="FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
        remote_contact=True, originals_preserved=True, transient=summaries, tran_waveforms=waves,
        reader_registration_sha256="1" * 64, execution_input_sha256="2" * 64,
        extraction_receipt_sha256="3" * 64, frame_sha256="4" * 64,
        report_conditions=dict(
            analysis_inputs=dict(analysis="tran", stop_s="2", maxstep_s="0.025", method="trap"),
            source_tree_sha256="5" * 64, ade_state_tree_sha256="6" * 64,
            static_statements_sha256="7" * 64, model_file_sha256=[], transfer=None,
        ),
    )
    native = SimpleNamespace(
        context=SimpleNamespace(
            resource_domain_sha256=plan.resource_domain_sha256,
            binding=SimpleNamespace(**{name: getattr(plan, name) for name in (
                "ledger_ref", "runner_sha256", "environment_sha256", "design_sha256", "pdk_sha256",
            )}),
        ),
        current=Mock(), lifecycle=SimpleNamespace(
            read=Mock(return_value=record), reconcile=AsyncMock(return_value=record),
            submit=AsyncMock(), cancel_pending=AsyncMock(),
        ),
        provider=SimpleNamespace(analog_result=AsyncMock(return_value=(observed, data)),
                                 accept=AsyncMock(), authorize=AsyncMock()),
    )
    factory = Mock(return_value=native)
    monkeypatch.setattr(service_module, "NativeOperationService", factory)
    context = cast(ExecutionContext, object())
    service = CmosDelayService(context)
    factory.assert_called_once_with(context)
    query = CmosDelayResultQuery.model_validate_json(json.dumps(dict(
        operation_id=operation_id, expected_plan_sha256=plan.plan_sha256,
        definition=definition, supply_signal="vdd",
    )))
    return service, native, query, record, observed, data


def no_dispatch(native: Any) -> None:
    native.lifecycle.submit.assert_not_called()
    native.lifecycle.cancel_pending.assert_not_called()
    native.provider.accept.assert_not_called()
    native.provider.authorize.assert_not_called()


@pytest.mark.asyncio
async def test_registered_factory_read_only_boundary_and_local_evaluation(connected: Any) -> None:
    service, native, query, record, _, data = connected
    before = copy.deepcopy(data)
    result = await service.result(query)
    native.lifecycle.reconcile.assert_awaited_once_with(query.operation_id, record.plan.plan_sha256)
    native.provider.analog_result.assert_awaited_once_with(query.operation_id, record.plan)
    assert native.current.call_count == 2 and native.lifecycle.read.call_count == 2
    no_dispatch(native)
    assert result.evaluation.tphl.delay_s == pytest.approx(0.2)
    assert result.evaluation.tplh.delay_s == pytest.approx(0.3)
    assert result.evaluation.native_authentication == "NOT_ATTESTED"
    assert result.vm_logic_physical_qualification == "NOT_ASSESSED"
    assert result.source.provider_boundary == "REGISTERED_RESULT_IDENTITY_CHECKS_PASSED"
    assert result.source.evidence.static_statements_sha256 == "7" * 64
    assert result.source.evidence.frame_sha256 == "4" * 64
    assert result.evaluation.power == "UNSUPPORTED"
    assert result.new_simulations == result.new_extractions == result.new_reservations == 0
    assert "tran_waveforms" not in result.model_dump_json() and data == before


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["operation", "plan", "phase", "analysis", "context"])
async def test_rejects_preconditions_before_provider_contact(connected: Any, bad: str) -> None:
    service, native, query, record, _, _ = connected
    if bad == "operation":
        query = query.model_copy(update={"operation_id": "00000000-0000-4000-8000-000000000001"})
    elif bad == "plan":
        query = query.model_copy(update={"expected_plan_sha256": "0" * 64})
    elif bad == "phase":
        record = record.model_copy(update={"progress": record.progress.model_copy(
            update={"phase": "RUNNING"},
        )})
    elif bad == "analysis":
        record = record.model_copy(update={
            "plan": record.plan.model_copy(update={"analysis": "dc"}),
        })
        query = query.model_copy(update={"expected_plan_sha256": record.plan.plan_sha256})
    else:
        native.context.binding.runner_sha256 = "0" * 64
    native.lifecycle.read.return_value = record
    with pytest.raises(OperationRejected):
        await service.result(query)
    native.lifecycle.reconcile.assert_not_called()
    native.provider.analog_result.assert_not_called()
    no_dispatch(native)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["observed_operation", "terminal", "reconciled", "post_read"])
async def test_exact_terminal_identity_before_and_after_read(connected: Any, bad: str) -> None:
    service, native, query, record, observed, data = connected
    changed = record.model_copy(update={"progress": record.progress.model_copy(
        update={"remote_revision": 5},
    )})
    if bad == "observed_operation":
        observed = observed.model_copy(update={
            "operation_id": "00000000-0000-4000-8000-000000000001",
        })
    elif bad == "terminal":
        observed = observed.model_copy(update={"progress": changed.progress})
    elif bad == "reconciled":
        native.lifecycle.reconcile.return_value = changed
    else:
        native.lifecycle.read.side_effect = [record, changed]
    native.provider.analog_result.return_value = (observed, data)
    with pytest.raises(OperationRejected):
        await service.result(query)
    if bad == "reconciled":
        native.provider.analog_result.assert_not_called()
    no_dispatch(native)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    "operation", "plan", "analysis", "provenance", "remote", "originals", "missing_wave",
    "missing_supply", "supply", "vdd", "stop", "maxstep", "axes", "window", "oversize",
])
async def test_returned_identity_and_conditions_fail_closed(connected: Any, bad: str) -> None:
    service, native, query, _, _, data = connected
    if bad in ("operation", "plan", "analysis"):
        key, value = {"operation": ("operation_id", "00000000-0000-4000-8000-000000000001"),
                      "plan": ("plan_sha256", "0" * 64), "analysis": ("analysis", "dc")}[bad]
        data[key] = value
    elif bad == "provenance":
        data["native_provenance"] = "NOT_ATTESTED"
    elif bad == "remote":
        data["remote_contact"] = False
    elif bad == "originals":
        data["originals_preserved"] = False
    elif bad == "missing_wave":
        del data["tran_waveforms"]["vin"]
    elif bad == "missing_supply":
        del data["tran_waveforms"]["vdd"]
    elif bad == "supply":
        data["tran_waveforms"]["vdd"][10]["value_v"] = 0.8
    elif bad == "vdd":
        query = query.model_copy(update={"definition": query.definition.model_copy(
            update={"vdd_v": 1.2},
        )})
    elif bad in ("stop", "maxstep"):
        inputs = data["report_conditions"]["analysis_inputs"]
        inputs["stop_s" if bad == "stop" else "maxstep_s"] = "3" if bad == "stop" else "0.01"
    elif bad == "axes":
        data["tran_waveforms"]["vout"][5]["time_s"] += 0.01
    elif bad == "window":
        query = query.model_copy(update={"definition": query.definition.model_copy(update={
            "plh_window": query.definition.plh_window.model_copy(update={"stop_s": 3.0}),
        })})
    else:
        data["tran_waveforms"]["vin"] *= 4
    with pytest.raises(OperationRejected) as caught:
        await service.result(query)
    if bad == "missing_supply":
        assert caught.value.reason == "missing_supply_evidence"
    no_dispatch(native)


@pytest.mark.asyncio
async def test_numerical_nonqualification_is_separate_from_provider_boundary(
    connected: Any,
) -> None:
    service, native, query, _, _, _ = connected
    query = query.model_copy(update={"definition": query.definition.model_copy(
        update={"minimum_delay_resolution_ratio": 100.0},
    )})
    result = await service.result(query)
    assert result.evaluation.status == "NOT_EVALUATED"
    assert result.evaluation.tphl.delay_s is None
    assert result.source.provider_boundary == "REGISTERED_RESULT_IDENTITY_CHECKS_PASSED"
    no_dispatch(native)


def test_query_accepts_no_caller_waveforms_or_digest_and_requires_distinct_supply(
    connected: Any,
) -> None:
    _, _, query, _, _, _ = connected
    mutations: tuple[dict[str, Any], ...] = (
        {"tran_waveforms": {}}, {"frame_sha256": "a" * 64}, {"supply_signal": "vin"},
    )
    for changes in mutations:
        with pytest.raises(ValidationError):
            CmosDelayResultQuery.model_validate_json(json.dumps(
                query.model_dump(mode="json") | changes,
            ))
