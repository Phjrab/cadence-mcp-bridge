from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.measurement_models import (
    ContractId,
    CornerComparisonRequest,
    DcPowerRequest,
    FftMeasurementRequest,
    LinearityRequest,
    MonteCarloRequest,
    OffsetRequest,
    SettlingRequest,
)
from cadence_mcp_bridge.measurements import (
    compare_corner_results,
    get_measurement_contract,
    measure_dc_power,
    measure_fft_metrics,
    measure_linearity,
    measure_offset,
    measure_settling,
    summarize_monte_carlo,
)

CONTRACT_ID: ContractId = "adc-synthetic-v1"


def test_contract_contains_every_required_definition_and_fft_choice() -> None:
    contract = get_measurement_contract(CONTRACT_ID)

    assert {definition.name for definition in contract.definitions} == {
        "dc_power",
        "offset",
        "settling_time",
        "snr",
        "sndr",
        "thd",
        "enob",
        "dnl",
        "inl",
        "corner_comparison",
        "monte_carlo_summary",
    }
    assert contract.fft.sample_frequency_hz == 1024.0
    assert contract.fft.input_tone_frequency_hz == 64.0
    assert contract.fft.sample_count == 1024
    assert contract.fft.analysis_time_window_s == (0.0, 0.9990234375)
    assert contract.fft.initial_transient_exclusion_samples == 0
    assert contract.fft.window_function == "rectangular"
    assert contract.fft.dc_bin_policy == "exclude-bin-0"
    assert contract.fft.fundamental_bin_policy == "exact-coherent-bin"
    assert contract.fft.harmonic_count == 4
    assert contract.fft.noise_bin_policy.startswith("positive-bins")
    assert contract.fft.differential_signal_expression == "fixture:adc_output"
    assert contract.fft.enob_equation == "(SNDR_dB - 1.76) / 6.02"


def test_missing_or_unknown_contract_is_rejected() -> None:
    with pytest.raises(InvalidInputError, match="contract"):
        get_measurement_contract("unknown")
    with pytest.raises(ValidationError, match="contract_id"):
        DcPowerRequest.model_validate(
            {"supply_voltage_v": [1.8, 1.8], "supply_current_a": [0.001, 0.001]}
        )


def test_dc_power_and_offset_match_known_fixture() -> None:
    power = measure_dc_power(
        DcPowerRequest(
            contract_id=CONTRACT_ID,
            supply_voltage_v=(1.8, 1.8, 1.8, 1.8),
            supply_current_a=(0.001, 0.001, 0.001, 0.001),
        )
    )
    offset = measure_offset(
        OffsetRequest(
            contract_id=CONTRACT_ID,
            observed_voltage_v=(0.01, -0.01, 0.02, -0.02),
        )
    )

    assert power.value == pytest.approx(0.0018)
    assert power.unit == "W"
    assert power.manifest.contract_version == 1
    assert power.manifest.post_processor == "windows-python"
    assert len(power.manifest.input_sha256) == 64
    assert offset.value == pytest.approx(0.0, abs=1e-15)
    assert offset.unit == "V"
    assert "mean" in power.formula


def test_settling_requires_stay_within_band() -> None:
    result = measure_settling(
        SettlingRequest(
            contract_id=CONTRACT_ID,
            time_s=(0.0, 1e-6, 2e-6, 3e-6, 4e-6),
            output_voltage_v=(0.0, 0.98, 0.995, 1.005, 1.0),
        )
    )

    assert result.settled is True
    assert result.value == pytest.approx(2e-6)
    assert result.target_v == 1.0
    assert result.tolerance_v == 0.01


def test_fft_metrics_match_coherent_synthetic_waveform_and_repeat() -> None:
    sample_count = 1024
    samples = tuple(
        math.sin(2.0 * math.pi * 64 * index / sample_count)
        + 0.01 * math.sin(2.0 * math.pi * 128 * index / sample_count)
        + 0.001 * math.sin(2.0 * math.pi * 7 * index / sample_count)
        + 0.001 * math.sin(2.0 * math.pi * 11 * index / sample_count)
        for index in range(sample_count)
    )
    request = FftMeasurementRequest(contract_id=CONTRACT_ID, samples_v=samples)

    first = measure_fft_metrics(request)
    second = measure_fft_metrics(request)

    assert first.model_dump() == second.model_dump()
    assert first.fundamental_bin == 64
    assert first.harmonic_bins == (128, 192, 256, 320)
    assert first.snr_db == pytest.approx(56.9897000434, abs=1e-8)
    assert first.thd_db == pytest.approx(-40.0, abs=1e-8)
    assert first.sndr_db == pytest.approx(39.9139982824, abs=1e-8)
    assert first.enob_bits == pytest.approx(6.33787346883, abs=1e-8)
    assert first.units == {"snr": "dB", "sndr": "dB", "thd": "dB", "enob": "bit"}


def test_linearity_matches_ideal_three_bit_transitions() -> None:
    result = measure_linearity(
        LinearityRequest(
            contract_id=CONTRACT_ID,
            transition_voltage_v=tuple(code / 8 for code in range(1, 8)),
        )
    )

    assert result.lsb_v == 0.125
    assert result.dnl_lsb == pytest.approx((0.0,) * 8)
    assert result.inl_lsb == pytest.approx((0.0,) * 7)
    assert result.max_abs_dnl_lsb == 0.0
    assert result.max_abs_inl_lsb == 0.0
    assert result.method == "endpoint"
    assert result.units == {"lsb": "V", "dnl": "LSB", "inl": "LSB"}


def test_corner_and_monte_carlo_summaries_are_explicit() -> None:
    corners = compare_corner_results(
        CornerComparisonRequest(
            contract_id=CONTRACT_ID,
            values={"NN": 1.0, "FF": 1.1, "SS": 0.9},
            unit="V",
        )
    )
    monte_carlo = summarize_monte_carlo(
        MonteCarloRequest(
            contract_id=CONTRACT_ID,
            values=(1.0, 2.0, 3.0, 4.0, 5.0),
            unit="mV",
        )
    )

    assert corners.delta_from_reference == pytest.approx({"NN": 0.0, "FF": 0.1, "SS": -0.1})
    assert corners.relative_percent == pytest.approx({"NN": 0.0, "FF": 10.0, "SS": -10.0})
    assert corners.minimum_corner == "SS"
    assert corners.maximum_corner == "FF"
    assert monte_carlo.mean == 3.0
    assert monte_carlo.sample_stddev == pytest.approx(math.sqrt(2.5))
    assert monte_carlo.p05 == pytest.approx(1.2)
    assert monte_carlo.median == 3.0
    assert monte_carlo.p95 == pytest.approx(4.8)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "contract_id": CONTRACT_ID,
            "supply_voltage_v": [1.8, float("nan")],
            "supply_current_a": [0.001, 0.001],
        },
        {
            "contract_id": CONTRACT_ID,
            "supply_voltage_v": [1.8, 1.8, 1.8],
            "supply_current_a": [0.001, 0.001],
        },
    ],
)
def test_power_input_rejects_nonfinite_or_mismatched_series(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DcPowerRequest.model_validate(payload)
