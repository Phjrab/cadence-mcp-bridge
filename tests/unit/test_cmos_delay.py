"""Analytic synthetic grids only; never actual CMOS or native qualification."""

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.cmos_delay import CmosDelayRequest, evaluate_cmos_delay
from cadence_mcp_bridge.variable_contracts import canonical_digest


def payload() -> dict[str, Any]:
    def ramp(t: float, start: float) -> float:
        return max(0.0, min(1.0, (t - start) / 0.5))

    times = [i / 4 for i in range(81)]
    return {
        "evidence": {
            "operation_id": "f154d798-0f7f-47d6-9323-6b046394eef6",
            **dict.fromkeys((
                "plan_sha256", "frame_sha256", "reader_registration_sha256",
                "execution_input_sha256", "static_statements_sha256",
            ), "a" * 64),
        },
        "definition": {
            "input_signal": "vin", "output_signal": "vout", "vdd_v": 1.0,
            "phl_window": {"start_s": 0, "initial_stop_s": 1,
                           "final_start_s": 7, "stop_s": 8},
            "plh_window": {"start_s": 10, "initial_stop_s": 11,
                           "final_start_s": 19, "stop_s": 20},
            "plateau_tolerance_v": 0.01, "minimum_plateau_samples": 2,
            "maximum_sample_gap_s": 0.3, "maximum_crossing_bracket_s": 0.3,
            "minimum_delay_resolution_ratio": 2.0,
        },
        "tran_waveforms": {
            "vin": [{"time_s": t, "value_v": ramp(t, 2.875) if t < 10
                     else 1 - ramp(t, 12.875)} for t in times],
            "vout": [{"time_s": t, "value_v": 1 - ramp(t, 4.875) if t < 10
                      else ramp(t, 15.875)} for t in times],
        },
    }


def evaluate(data: dict[str, Any]) -> Any:
    return evaluate_cmos_delay(CmosDelayRequest.model_validate_json(json.dumps(data)))


def test_analytic_pair_retains_actual_brackets_and_local_evidence() -> None:
    data = payload()
    before = copy.deepcopy(data)
    request = CmosDelayRequest.model_validate_json(json.dumps(data))
    result = evaluate_cmos_delay(request)
    assert result.status == "OBSERVED_SAMPLED_DELAY"
    assert result.tphl.delay_s == 2.0 and result.tplh.delay_s == 3.0
    assert result.tphl.delay_bracket_s == (1.75, 2.25)
    assert result.tphl.input_crossing is not None and result.tphl.output_crossing is not None
    assert result.tphl.input_crossing.time_s == 3.125
    assert result.tphl.input_crossing.bracket_s == (3.0, 3.25)
    assert result.tphl.output_crossing.bracket_s == (5.0, 5.25)
    assert result.tphl.output_crossing.direction == "falling"
    assert result.tplh.output_crossing is not None
    assert result.tplh.output_crossing.direction == "rising"
    assert result.native_authentication == "NOT_ATTESTED" and result.power == "UNSUPPORTED"
    assert result.evidence == request.evidence
    assert result.request_sha256 == canonical_digest(request)
    assert evaluate(data).model_dump() == result.model_dump() and data == before
    data["evidence"]["frame_sha256"] = "b" * 64
    assert evaluate(data).request_sha256 != result.request_sha256


@pytest.mark.parametrize("bad", ["node", "axes", "duplicate", "reverse", "coverage"])
def test_missing_nodes_or_invalid_time_grid_never_invent_delay(bad: str) -> None:
    data = payload()
    waves = data["tran_waveforms"]
    if bad == "node":
        del waves["vin"]
    elif bad == "axes":
        waves["vout"][4]["time_s"] += 0.01
    elif bad in ("duplicate", "reverse"):
        waves["vin"][4]["time_s"] = 0.75 if bad == "duplicate" else 0.5
    else:
        for name in waves:
            waves[name] = waves[name][1:]
    result = evaluate(data)
    assert result.status == "NOT_EVALUATED" and result.tphl.delay_s is None
    assert result.tphl.reason == {
        "node": "missing_nodes", "coverage": "window_outside_samples",
    }.get(bad, "invalid_time_grid")


@pytest.mark.parametrize("bad", ["gap", "bracket", "ratio", "plateau_count", "unsettled"])
def test_explicit_resolution_and_endpoint_conditions(bad: str) -> None:
    data = payload()
    definition = data["definition"]
    if bad == "gap":
        definition["maximum_sample_gap_s"] = 0.2
    elif bad == "bracket":
        definition["maximum_crossing_bracket_s"] = 0.2
    elif bad == "ratio":
        definition["minimum_delay_resolution_ratio"] = 5
    elif bad == "plateau_count":
        definition["minimum_plateau_samples"] = 6
    else:
        data["tran_waveforms"]["vout"][0]["value_v"] = 0.8
    result = evaluate(data)
    assert result.status == "NOT_EVALUATED" and result.tphl.delay_s is None
    assert result.tphl.reason == (
        "unsettled_endpoints" if bad == "unsettled" else "insufficient_sampling"
    )


@pytest.mark.parametrize("bad", ["missing", "multiple", "threshold_plateau", "early"])
def test_missing_ambiguous_or_early_crossings(bad: str) -> None:
    data = payload()
    wave = data["tran_waveforms"]["vout"]
    if bad == "missing":
        # Put response between the transition and final plateau, never extrapolate it.
        for p in wave:
            if 1 <= p["time_s"] <= 7:
                p["value_v"] = 1.0
        data["definition"]["phl_window"]["final_start_s"] = 7.125
    elif bad == "multiple":
        wave[24]["value_v"] = 1.0
    elif bad == "threshold_plateau":
        wave[20]["value_v"] = wave[21]["value_v"] = 0.5
    else:
        for p in wave:
            t = p["time_s"]
            if t < 10:
                p["value_v"] = 1 - max(0.0, min(1.0, (t - 1.875) / 0.5))
    result = evaluate(data)
    assert result.tphl.delay_s is None and result.status == "NOT_EVALUATED"
    assert result.tphl.reason == {
        "missing": "missing_crossing", "early": "output_before_input",
    }.get(bad, "ambiguous_crossings")
    assert result.tplh.delay_s == 3.0


def test_exact_threshold_saved_hits_are_single_conservative_crossings() -> None:
    data = payload()
    for name in ("vin", "vout"):
        for point in data["tran_waveforms"][name]:
            if point["value_v"] == 0.25:
                point["value_v"] = 0.5
    data["definition"]["maximum_crossing_bracket_s"] = 0.6
    result = evaluate(data)
    assert result.status == "OBSERVED_SAMPLED_DELAY"
    assert result.tphl.input_crossing is not None
    assert result.tphl.input_crossing.bracket_s == (2.75, 3.25)


@pytest.mark.parametrize("bad", ["nan", "inf", "boolean", "extra", "too_many", "invalid_node"])
def test_closed_finite_bounded_waveform_schema(bad: str) -> None:
    data = payload()
    point = data["tran_waveforms"]["vin"][0]
    if bad in ("nan", "inf", "boolean"):
        point["value_v"] = {"nan": float("nan"), "inf": float("inf"), "boolean": True}[bad]
    elif bad == "extra":
        point["current_a"] = 1
    elif bad == "too_many":
        data["tran_waveforms"]["vin"] *= 4
    else:
        data["tran_waveforms"]["/raw/path"] = data["tran_waveforms"].pop("vin")
    with pytest.raises(ValidationError):
        evaluate(data)


@pytest.mark.parametrize("field,value", [
    ("vdd_v", 0), ("vdd_v", float("inf")), ("plateau_tolerance_v", 0.5),
    ("maximum_sample_gap_s", 0), ("minimum_delay_resolution_ratio", 0.5),
    ("input_signal", "vout"),
])
def test_invalid_qualification_contract(field: str, value: Any) -> None:
    data = payload()
    data["definition"][field] = value
    with pytest.raises(ValidationError):
        evaluate(data)
