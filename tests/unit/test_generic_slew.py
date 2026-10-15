"""Synthetic saved-grid rejection and slope tests, not Cadence qualification."""

import pytest
from pydantic import ValidationError
from test_generic_measurements import frame_for, reader_for
from test_generic_measurements import operator as operator
from test_generic_measurements import operator_base as operator_base

from cadence_mcp_bridge.generic_measurements import project_frame
from cadence_mcp_bridge.generic_slew import SampledSlewDefinition, sampled_slew
from cadence_mcp_bridge.operator_operations import OperationRejected


def definition(**changes):
    values = dict(static_statements_sha256="a" * 64, input_signal="input",
                  output_signal="output", load_description="QA registered static load",
                  input_initial_v=0, input_final_v=1, initial_start_s=0,
                  initial_stop_s=2, final_start_s=14, final_stop_s=16,
                  plateau_tolerance_v=0.01, minimum_output_step_v=0.1)
    return SampledSlewDefinition(**(values | changes))


def waves(falling=False):
    output = [max(0, min(1, (t - 3) / 10)) for t in range(17)]
    if falling:
        output = [1 - v for v in output]
    return {
        "input": [{"time_s": t, "value_v": int(t >= 3)} for t in range(17)],
        "output": [{"time_s": t, "value_v": v} for t, v in enumerate(output)],
    }


@pytest.mark.parametrize("falling,sign", [(False, 1), (True, -1)])
def test_signed_10_90_average_preserves_brackets(falling, sign):
    result = sampled_slew(waves(falling), definition())
    assert result["status"] == "OBSERVED_SAMPLED_STEP_SLOPE"
    assert result["value"] == pytest.approx(sign * 0.1)
    assert [c["time_s"] for c in result["crossings"]] == [4, 12]
    assert result["largest_crossing_sample_gap_s"] == 1
    assert result["native_provenance"] == "NOT_ATTESTED"


@pytest.mark.parametrize("change", [
    {"initial_stop_s": 14}, {"upper_fraction": 0.05}, {"input_signal": "output"},
    {"input_final_v": 0.01}, {"minimum_crossing_intervals": 3},
    {"plateau_tolerance_v": float("nan")},
])
def test_invalid_definition(change):
    with pytest.raises(ValidationError):
        definition(**change)


@pytest.mark.parametrize("bad", ["missing", "axes", "nan", "duplicate", "complex"])
def test_incomplete_or_nonfinite_saved_grid_rejects(bad):
    data = waves()
    if bad == "missing":
        del data["input"]
    elif bad == "axes":
        data["output"][4]["time_s"] = 4.5
    elif bad == "nan":
        data["output"][4]["value_v"] = float("nan")
    elif bad == "complex":
        data["output"][4]["value_v"] = complex(1, 1)
    else:
        for wave in data.values():
            wave[4]["time_s"] = 3
    with pytest.raises(OperationRejected):
        sampled_slew(data, definition())


def test_unsettled_and_wrong_stimulus_fail():
    data = waves()
    data["output"][0]["value_v"] = 0.1
    with pytest.raises(OperationRejected):
        sampled_slew(data, definition())
    with pytest.raises(OperationRejected):
        sampled_slew(waves(), definition(input_final_v=2))


def test_missing_response_and_inadequate_resolution_do_not_invent_slope():
    data = waves()
    for point in data["output"]:
        point["value_v"] = 0.2
    assert sampled_slew(data, definition())["value"] is None
    data = waves()
    for point in data["output"]:
        point["value_v"] = int(point["time_s"] >= 5)
    result = sampled_slew(data, definition())
    assert result["status"] == "INSUFFICIENT_SAVED_TIME_RESOLUTION"
    assert result["value"] is None and result["crossings"]


def test_repeated_threshold_crossing_is_ambiguous():
    data = waves()
    data["output"][5]["value_v"] = 0
    assert sampled_slew(data, definition())["status"] == "AMBIGUOUS_OR_MISSING_SAMPLED_CROSSING"


def test_output_transition_before_input_step_is_rejected():
    data = waves()
    for point in data["input"]:
        point["value_v"] = int(point["time_s"] >= 13)
    with pytest.raises(OperationRejected) as caught:
        sampled_slew(data, definition())
    assert caught.value.reason == "slew_output_transition_precedes_measured_input_step"


def test_output_crossing_inside_unresolved_input_onset_bracket_is_rejected():
    data = waves()
    # First observed input change is at3s, but output10% interpolation is2.5s.
    # Output90% stays much later, so edge-ratio/resolution alone cannot reject it.
    for point in data["output"]:
        point["value_v"] = max(0, min(1, .2 if point["time_s"] == 3
                                    else (point["time_s"] - 1) / 10))
    data["output"][2]["value_v"] = 0
    with pytest.raises(OperationRejected) as caught:
        sampled_slew(data, definition())
    assert caught.value.reason == "slew_output_transition_precedes_measured_input_step"


def test_full_tran_projection_keeps_normal_contract(operator):
    args = reader_for(operator, "tran")
    frame = frame_for(args, "P|input|0|0|0|0\nP|input|1|0.004|1|0\n"
                      "P|output|0|0|1|0\nP|output|1|0.004|0|0")
    normal = project_frame(*args, frame)
    complete = project_frame(*args, frame, include_tran_waveforms=True)
    assert "tran_waveforms" not in normal
    assert complete["transient"] == normal["transient"]
    assert complete["reader_script_sha256"] == normal["reader_script_sha256"]
    assert complete["tran_waveforms"]["output"] == [
        {"time_s": 0, "value_v": 1}, {"time_s": 0.004, "value_v": 0},
    ]


def test_monotonic_slow_input_ramp_cannot_qualify_step_slope():
    data = waves()
    for point in data["input"]:
        point["value_v"] = max(0, min(1, (point["time_s"] - 3) / 10))
    result = sampled_slew(data, definition())
    assert result["status"] == "INPUT_EDGE_NOT_FAST_ENOUGH_FOR_SAMPLED_STEP_RESPONSE"
    assert result["value"] is None and result["input_fraction_crossings"]
    assert result["input_edge_duration_upper_bound_s"] > (
        .25 * result["output_crossing_duration_lower_bound_s"]
    )


def test_input_edge_bound_cannot_be_widened_to_hide_ramp():
    with pytest.raises(ValidationError):
        definition(maximum_input_edge_ratio=.5)


@pytest.mark.parametrize("falling", [False, True])
def test_cumulative_small_input_reversals_reject_overshooting_step(falling):
    data = waves()
    # Every reversal is below tolerance, but the cumulative return from1.05V
    # is five times the tolerance. The edge remains above the90% threshold.
    for point in data["input"]:
        t = point["time_s"]
        value = 0 if t < 3 else 1 + max(0, .05 - .005 * (t - 3))
        point["value_v"] = 1 - value if falling else value
    with pytest.raises(OperationRejected) as caught:
        sampled_slew(data, definition(input_initial_v=int(falling),
                                      input_final_v=int(not falling)))
    assert caught.value.reason == "slew_multiple_or_reversed_input_step"


@pytest.mark.parametrize("falling", [False, True])
def test_small_input_noise_within_running_extremum_tolerance_is_allowed(falling):
    data = waves()
    for point in data["input"]:
        value = point["value_v"]
        if 4 <= point["time_s"] <= 12:
            value += .005
        point["value_v"] = 1 - value if falling else value
    result = sampled_slew(data, definition(input_initial_v=int(falling),
                                          input_final_v=int(not falling)))
    assert result["status"] == "OBSERVED_SAMPLED_STEP_SLOPE"


@pytest.mark.parametrize("falling", [False, True])
@pytest.mark.parametrize("reversal,accepted", [(1 / 64, True), (3 / 128, False)])
def test_running_extremum_tolerance_boundary(falling, reversal, accepted):
    data = waves()
    # Exactly representable values distinguish equality from the next larger
    # reversal, without a float-rounding tolerance hiding the boundary.
    for point in data["input"]:
        value = point["value_v"]
        if 3 <= point["time_s"] <= 5:
            value += reversal
        point["value_v"] = 1 - value if falling else value
    contract = definition(input_initial_v=int(falling), input_final_v=int(not falling),
                          plateau_tolerance_v=1 / 64)
    if accepted:
        assert sampled_slew(data, contract)["status"] == "OBSERVED_SAMPLED_STEP_SLOPE"
    else:
        with pytest.raises(OperationRejected) as caught:
            sampled_slew(data, contract)
        assert caught.value.reason == "slew_multiple_or_reversed_input_step"
