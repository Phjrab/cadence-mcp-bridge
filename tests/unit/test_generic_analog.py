"""Synthetic numerical and read-only identity tests, not Cadence qualification."""

import math
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from test_generic_measurements import frame_for, reader_for
from test_generic_measurements import operator as operator
from test_generic_measurements import operator_base as operator_base

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.generic_analog import SampledBandwidthDefinition, sampled_crossing
from cadence_mcp_bridge.generic_measurements import project_frame
from cadence_mcp_bridge.operator_operations import OperationRejected


def spectrum(db):
    return [{"frequency_hz": 10.0 ** (i + 1), "real_v_per_v": 10 ** (v / 20),
             "imag_v_per_v": 0.0} for i, v in enumerate(db)]


def test_log_interpolation_first_downward_and_exact_crossing():
    definition = SampledBandwidthDefinition(reference_frequency_hz=10)
    result = sampled_crossing(spectrum([6, 0, 6, -6]), definition)
    assert result["value"] == pytest.approx(math.sqrt(10 * 100))
    assert result["bracket_hz"] == [10, 100]
    assert result["native_provenance"] == "NOT_ATTESTED"
    exact = sampled_crossing(spectrum([6, 3, 0]), definition)
    assert exact["value"] == 100


def test_nonfirst_explicit_reference_and_no_extrapolation():
    result = sampled_crossing(spectrum([0, 12, 11]),
                              SampledBandwidthDefinition(reference_frequency_hz=100))
    assert result["value"] is None
    assert result["status"] == "NOT_OBSERVED_IN_SAMPLED_RANGE"
    assert result["reference_gain_db"] == pytest.approx(12)


@pytest.mark.parametrize("frequency", [0, -1, float("nan"), float("inf")])
def test_invalid_reference(frequency):
    with pytest.raises(ValidationError):
        SampledBandwidthDefinition(reference_frequency_hz=frequency)


@pytest.mark.parametrize("drop", [0, -1, 121, float("nan")])
def test_invalid_drop(drop):
    with pytest.raises(ValidationError):
        SampledBandwidthDefinition(reference_frequency_hz=10, drop_db=drop)


@pytest.mark.parametrize("reference", [11, 1000])
def test_missing_or_last_reference(reference):
    with pytest.raises(OperationRejected):
        sampled_crossing(spectrum([6, 3, 0]),
                         SampledBandwidthDefinition(reference_frequency_hz=reference))


@pytest.mark.parametrize("bad", ["zero", "nonfinite", "duplicate", "order", "short"])
def test_invalid_spectrum(bad):
    samples = spectrum([6, 3, 0])
    if bad == "zero":
        samples[1]["real_v_per_v"] = 0
    elif bad == "nonfinite":
        samples[1]["imag_v_per_v"] = float("inf")
    elif bad == "duplicate":
        samples[1]["frequency_hz"] = 10
    elif bad == "order":
        samples.reverse()
    else:
        samples = samples[:1]
    with pytest.raises(OperationRejected):
        sampled_crossing(samples, SampledBandwidthDefinition(reference_frequency_hz=10))


def test_complete_projection_is_opt_in_and_uses_measured_complex_input(operator):
    args = reader_for(operator, "ac")
    body = ("P|input|0|1000|0|2\nP|input|1|2000|0|4\n"
            "P|output|0|1000|0|4\nP|output|1|2000|0|4")
    frame = frame_for(args, body)
    before = project_frame(*args, frame)
    after = project_frame(*args, frame, include_ac_spectrum=True)
    assert "ac_spectrum" not in before
    assert after["transfer"] == before["transfer"]
    assert after["reader_script_sha256"] == before["reader_script_sha256"]
    assert [s["gain_v_per_v"] for s in after["ac_spectrum"]] == [2, 1]
    assert [s["frequency_hz"] for s in after["ac_spectrum"]] == [1000, 2000]
    assert after["native_provenance"] == "NOT_ATTESTED"


def test_unselected_zero_input_rejected_before_analog_use(operator):
    args = reader_for(operator, "ac")
    frame = frame_for(args, "P|input|0|1000|2|0\nP|input|1|2000|0|0\n"
                      "P|output|0|1000|4|0\nP|output|1|2000|4|0")
    assert len(project_frame(*args, frame)["transfer"]) == 1
    with pytest.raises(OperationRejected) as rejected:
        project_frame(*args, frame, include_ac_spectrum=True)
    assert rejected.value.reason == "reader_ac_input_zero"


def test_requirements_never_claim_pm_offset_slew_qualification(capsys):
    assert main(["operator-analog", "requirements"]) == 0
    import json
    data = json.loads(capsys.readouterr().out)
    assert data["new_simulations"] == data["new_extractions"] == 0
    assert all(data["requirements"][m]["status"] == "BLOCKED"
               for m in ("phase_margin", "offset", "slew"))


@pytest.mark.asyncio
async def test_capture_rejects_wrong_plan_before_remote_contact(monkeypatch):
    from contextlib import nullcontext

    from cadence_mcp_bridge.generic_analog import capture_bandwidth
    record = SimpleNamespace(operation_id="00000000-0000-4000-8000-000000000001",
                             plan=SimpleNamespace(plan_sha256="a" * 64))
    store = SimpleNamespace(connection=lambda **kwargs: nullcontext(None),
                            _read_operation=lambda *args: record)
    provider = SimpleNamespace(analog_result=AsyncMock())
    native = SimpleNamespace(current=lambda: None, lifecycle=SimpleNamespace(store=store),
                             provider=provider)
    with pytest.raises(OperationRejected):
        await capture_bandwidth(native, record.operation_id, "b" * 64,
                                SampledBandwidthDefinition(reference_frequency_hz=10))
    provider.analog_result.assert_not_called()
