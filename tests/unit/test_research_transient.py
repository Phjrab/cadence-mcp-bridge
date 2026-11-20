import json
from contextlib import nullcontext
from unittest.mock import Mock
from uuid import uuid4

import pytest
from test_cmos_delay_service import connected, no_dispatch

from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.research_transient import (
    MAX_RESULT_BYTES,
    ResearchTransientQuery,
    capture_research_transient,
    evaluate_research_transient,
    research_transient_export_bytes,
)

__all__ = ["connected"]


def _query(**updates):
    fields = {
        "operation_id": str(uuid4()),
        "expected_plan_sha256": "a" * 64,
        "window": {"start_s": 0, "stop_s": 5, "maximum_gap_s": 1},
        "signals": ["vin", "vout"],
        "delay": {
            "trigger": {"signal": "vin", "threshold_v": 0.5, "direction": "rising"},
            "response": {"signal": "vout", "threshold_v": 0.5, "direction": "falling"},
        },
        "slew": {"signal": "vout"},
        "settling": {"signal": "vout", "target_v": 0, "tolerance_v": 0.1, "minimum_hold_s": 1},
        "maximum_display_points": 2,
    }
    return ResearchTransientQuery.model_validate_json(json.dumps(fields | updates))


def _wave(values):
    return [{"time_s": t, "value_v": v} for t, v in enumerate(values)]


def test_window_metrics_use_saved_samples_before_display_reduction():
    result = evaluate_research_transient(
        _query(),
        {"vin": _wave([0, 1, 1, 1, 1, 1]), "vout": _wave([1, 1, 0, 0, 0, 0])},
        sample_kind="NATIVE_SAVED_VECTOR",
    )
    assert result["signals"]["vout"]["display_downsampled"]
    assert len(result["signals"]["vout"]["points"]) == 2
    metrics = result["measurements"]
    assert metrics["delay"]["value"] == pytest.approx(1)
    assert metrics["slew"]["value"] == pytest.approx(-0.2)
    assert metrics["settling"]["value"] == pytest.approx(1.9)
    assert metrics["average_supply_power"]["value"] is None
    assert json.loads(research_transient_export_bytes(result)) == result


@pytest.mark.parametrize(
    "series,maximum_gap,sample_kind,reason",
    [
        ([1, 0, 0, 0, 1, 0], 1, "NATIVE_SAVED_VECTOR", "insufficient_hold_duration"),
        ([1, 0, 0, 0, 0, 1], 1, "NATIVE_SAVED_VECTOR", "outside_tolerance_at_window_end"),
        ([1, 0, 0, 0, 0], 1, "NATIVE_SAVED_VECTOR", "insufficient_observation_duration"),
        ([1, 0, 0, 0, 0, 0], 0.1, "NATIVE_SAVED_VECTOR", "insufficient_time_resolution"),
        ([1, 0, 0, 0, 0, 0], 1, "DISPLAY_DOWNSAMPLED", "original_saved_resolution_unverified"),
        ([], 1, "NATIVE_SAVED_VECTOR", "missing_registered_signal"),
    ],
)
def test_settling_reports_unavailable_instead_of_inventing_values(
    series, maximum_gap, sample_kind, reason,
):
    query = _query(window={"start_s": 0, "stop_s": 5, "maximum_gap_s": maximum_gap})
    result = evaluate_research_transient(
        query, {"vout": _wave(series)} if series else {}, sample_kind=sample_kind,
    )
    assert result["measurements"]["settling"]["reason"] == reason
    assert result["measurements"]["settling"]["value"] is None


def test_export_rejects_oversize_result():
    with pytest.raises(OperationRejected) as error:
        research_transient_export_bytes({"field": "x" * MAX_RESULT_BYTES})
    assert error.value.reason == "research_transient_export_exceeds_limit"


@pytest.mark.asyncio
async def test_same_id_reads_registered_result_without_reconcile_or_submit(connected):
    _, native, original, record, _, data = connected
    store = native.lifecycle.store = Mock()
    store.connection.side_effect = lambda **_: nullcontext("read connection")
    store._read_operation.return_value = record
    query = _query(
        operation_id=original.operation_id,
        expected_plan_sha256=original.expected_plan_sha256,
        window={"start_s": 0, "stop_s": 2, "maximum_gap_s": 0.025},
    )
    for _ in range(2):
        result = await capture_research_transient(native, query)
        assert result["source"]["operation_id"] == original.operation_id
        assert result["source"]["frame_sha256"] == data["frame_sha256"]
        assert result["sample_kind"] == "NATIVE_SAVED_VECTOR"
        assert result["new_simulations"] == result["new_reservations"] == 0
    assert native.provider.analog_result.await_count == 2
    store.connection.assert_called_with(create=False, read_only=True)
    native.lifecycle.reconcile.assert_not_called()
    no_dispatch(native)

    data["tran_waveforms"]["vout"].pop(1)
    with pytest.raises(OperationRejected) as error:
        await capture_research_transient(native, query)
    assert error.value.reason == "research_transient_saved_vector_inventory_mismatch"
