import hashlib
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from test_cmos_delay_service import connected, no_dispatch
from test_generic_measurements import operator, operator_base, reader_for

from cadence_mcp_bridge._native_eda_worker import EdaWorker
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration, project_frame
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.research_transient import (
    MAX_RESULT_BYTES,
    ResearchTransientQuery,
    TransientSupplyEvidence,
    capture_research_transient,
    evaluate_research_transient,
    research_transient_export_bytes,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["connected", "operator", "operator_base"]


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


def _supplies(currents):
    def source(source_id, positive, negative):
        return {
            "source_id": source_id, "role": "supply", "positive_node": positive,
            "negative_node": negative, "current_selector": f"/{source_id}/PLUS",
            "current_convention": "positive_into_source_positive_terminal_A",
        }

    return TransientSupplyEvidence.model_validate_json(json.dumps({
        "sources": [source("supply", "pos", "neg"), source("absorb", "neg", None)],
        "currents": currents,
    }))


def _current(values):
    return [{"time_s": t, "value_a": value} for t, value in enumerate(values)]


@pytest.mark.parametrize(
    "case,expected",
    [
        ("complete", None),
        ("missing", "missing_registered_supply_current"),
        ("shifted", "supply_voltage_current_time_axes_differ"),
        ("coarse", "insufficient_time_resolution"),
        ("short", "insufficient_observation_duration"),
        ("missing_voltage", "missing_registered_supply_voltage"),
        ("display_only", "original_saved_resolution_unverified"),
    ],
)
def test_average_signed_supply_power_requires_complete_registered_vectors(case, expected):
    query = _query(
        window={"start_s": 0.5, "stop_s": 2.5 if case == "short" else 1.5,
                "maximum_gap_s": 0.2 if case == "coarse" else 1},
        signals=["pos"], delay=None, slew=None, settling=None,
    )
    waves = {"pos": _wave([1, 2, 3]), "neg": _wave([1, 1, 1])}
    currents = {"supply": _current([-1, -2, -3]), "absorb": _current([1, 1, 1])}
    if case == "missing":
        del currents["supply"]
    elif case == "shifted":
        currents["supply"][1]["time_s"] = 0.9
    elif case == "missing_voltage":
        del waves["neg"]
    result = evaluate_research_transient(
        query, waves, supply=_supplies(currents),
        sample_kind="DISPLAY_DOWNSAMPLED" if case == "display_only" else "NATIVE_SAVED_VECTOR",
    )
    power = result["measurements"]["average_supply_power"]
    if case == "complete":
        assert power["unit"] == "W" and power["status"] == "ESTIMATED"
        assert power["sources"][0]["value"] == pytest.approx(2 + 1 / 12)
        assert power["sources"][1]["value"] == pytest.approx(-1)
        assert power["value"] == pytest.approx(1 + 1 / 12)
    elif case == "display_only":
        assert power["value"] is None and power["reason"] == expected
    else:
        assert power["value"] is None and power["reason"] == "incomplete_registered_supply_evidence"
        assert power["sources"][0]["reason"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("with_current", [False, True])
async def test_same_id_reads_registered_result_without_reconcile_or_submit(connected, with_current):
    _, native, original, record, _, data = connected
    store = native.lifecycle.store = Mock()
    store.connection.side_effect = lambda **_: nullcontext("read connection")
    store._read_operation.return_value = record
    if with_current:
        supply = _supplies({
            key: [{"time_s": p["time_s"], "value_a": amps} for p in data["tran_waveforms"]["vin"]]
            for key, amps in (("supply", -0.002), ("absorb", 0.001))
        })
        data["tran_waveforms"]["pos"] = data["tran_waveforms"]["vdd"]
        data["tran_waveforms"]["neg"] = [
            {"time_s": p["time_s"], "value_v": 0} for p in data["tran_waveforms"]["vin"]
        ]
        vdd = next(row for row in data["transient"] if row["logical_id"] == "vdd")
        data["transient"].extend([
            {**vdd, "logical_id": "pos"},
            {**vdd, "logical_id": "neg", "minimum": 0, "maximum": 0,
             "first": 0, "last": 0, "time_weighted_mean": 0},
        ])
        data["tran_supply_evidence"] = supply.model_dump(mode="json")
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
        power = result["measurements"]["average_supply_power"]
        if with_current:
            assert power["value"] == pytest.approx(0.002)
            assert result["tran_supply_evidence_sha256"] == canonical_digest(supply)
        else:
            assert power["reason"] == "registered_tran_supply_current_unavailable"
    assert native.provider.analog_result.await_count == 2
    store.connection.assert_called_with(create=False, read_only=True)
    native.lifecycle.reconcile.assert_not_called()
    no_dispatch(native)

    data["tran_waveforms"]["vout"].pop(1)
    with pytest.raises(OperationRejected) as error:
        await capture_research_transient(native, query)
    assert error.value.reason == "research_transient_saved_vector_inventory_mismatch"


@pytest.mark.parametrize("version", [1, 2])
def test_compiled_tran_supply_frame_and_legacy_projection(operator, version):
    context, plan, ade, reader, operation, execution = reader_for(operator, "tran")
    dc_source = reader_for(operator, "dc")[3].sources[0]
    reader = GenericReaderRegistration.model_validate_json(json.dumps({
        **reader.model_dump(mode="json"), "schema_version": version,
        "sources": [dc_source.model_dump(mode="json")] if version == 2 else [],
    }))
    reader_document = reader.model_dump(mode="json")
    header = "|".join((
        "MCP_GREL_FRAME", str(version), operation, plan.plan_sha256, execution,
        canonical_digest(reader),
    ))
    rows = ["P|input|0|0|3|0", "P|input|1|0.004|3|0",
            "P|output|0|0|1|0", "P|output|1|0.004|1|0"]
    if version == 2:
        rows.extend(["C|rail|0|0|-0.001|0", "C|rail|1|0.004|-0.002|0"])
    frame = "\n".join([header, *rows, "END", ""]).encode()
    worker = SimpleNamespace(
        operations=SimpleNamespace(
            canonical=_canonical, digest=lambda raw: hashlib.sha256(raw).hexdigest(),
        ),
        operation_id=operation,
        finite=float,
    )
    EdaWorker.frame(
        worker, frame, plan.model_dump(mode="json"), {"reader": reader_document}, execution,
    )
    args = context, plan, ade, reader, operation, execution
    projected = project_frame(*args, frame, include_tran_waveforms=True)
    assert ("tran_supply_evidence" in projected) == (version == 2)
    if version == 2:
        query = _query(
            window={"start_s": 0, "stop_s": 0.004, "maximum_gap_s": 0.004},
            signals=["input"], delay=None, slew=None, settling=None,
        )
        evidence = TransientSupplyEvidence.model_validate_json(
            json.dumps(projected["tran_supply_evidence"]),
        )
        result = evaluate_research_transient(
            query, projected["tran_waveforms"], sample_kind="NATIVE_SAVED_VECTOR", supply=evidence,
        )
        assert result["measurements"]["average_supply_power"]["value"] == pytest.approx(0.003)
        for changed in (
            frame.replace(b"C|rail|1|0.004", b"C|rail|1|0.003"),
            frame.replace(b"C|rail|1|0.004|-0.002|0", b"C|rail|1|0.004|-0.002|1"),
            frame.replace(b"C|rail|1|0.004|-0.002|0\n", b""),
        ):
            with pytest.raises(OperationRejected):
                project_frame(*args, changed, include_tran_waveforms=True)
            with pytest.raises(ValueError):
                EdaWorker.frame(
                    worker, changed, plan.model_dump(mode="json"),
                    {"reader": reader_document}, execution,
                )
