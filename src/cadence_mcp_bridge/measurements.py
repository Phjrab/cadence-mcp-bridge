"""Deterministic local calculations for the versioned synthetic ADC contract."""

from __future__ import annotations

import cmath
import hashlib
import json
import math
from statistics import fmean, median, stdev

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.measurement_models import (
    AdcMeasurementContract,
    ContractId,
    ContractRequest,
    CornerComparison,
    CornerComparisonRequest,
    DcPowerRequest,
    FftMeasurementRequest,
    FftMetrics,
    LinearityMetrics,
    LinearityRequest,
    MeasurementManifest,
    MetricDefinition,
    MonteCarloRequest,
    MonteCarloSummary,
    OffsetRequest,
    ScalarMetric,
    SettlingMetric,
    SettlingRequest,
)

SYNTHETIC_CONTRACT_ID: ContractId = "adc-synthetic-v1"

SYNTHETIC_CONTRACT = AdcMeasurementContract(
    definitions=(
        MetricDefinition(
            name="dc_power",
            unit="W",
            formula="mean(v_supply[n] * i_supply_into_circuit[n])",
        ),
        MetricDefinition(
            name="offset",
            unit="V",
            formula="mean(v_observed[n] - 0 V)",
        ),
        MetricDefinition(
            name="settling_time",
            unit="s",
            formula="earliest t >= 0 s after which |v(t)-1 V| <= 0.01 V through final sample",
        ),
        MetricDefinition(
            name="snr",
            unit="dB",
            formula="10*log10(Pfundamental/Pnoise)",
        ),
        MetricDefinition(
            name="sndr",
            unit="dB",
            formula="10*log10(Pfundamental/(Pnoise+Pharmonics))",
        ),
        MetricDefinition(
            name="thd",
            unit="dB",
            formula="10*log10(Pharmonics/Pfundamental)",
        ),
        MetricDefinition(
            name="enob",
            unit="bit",
            formula="(SNDR_dB - 1.76) / 6.02",
        ),
        MetricDefinition(
            name="dnl",
            unit="LSB",
            formula="code_width/ideal_LSB - 1",
        ),
        MetricDefinition(
            name="inl",
            unit="LSB",
            formula="(transition[k] - ideal_transition[k]) / ideal_LSB",
        ),
        MetricDefinition(
            name="corner_comparison",
            unit="caller-specified",
            formula="corner_value - NN_reference_value",
        ),
        MetricDefinition(
            name="monte_carlo_summary",
            unit="caller-specified",
            formula="mean and sample standard deviation with linear-interpolated percentiles",
        ),
    )
)


def get_measurement_contract(contract_id: str) -> AdcMeasurementContract:
    _require_contract(contract_id)
    return SYNTHETIC_CONTRACT


def measure_dc_power(request: DcPowerRequest) -> ScalarMetric:
    _require_contract(request.contract_id)
    values = tuple(
        voltage * current
        for voltage, current in zip(request.supply_voltage_v, request.supply_current_a, strict=True)
    )
    return ScalarMetric(
        contract_id=request.contract_id,
        name="dc_power",
        value=fmean(values),
        unit="W",
        formula="mean(v_supply[n] * i_supply_into_circuit[n])",
        manifest=_manifest(request),
    )


def measure_offset(request: OffsetRequest) -> ScalarMetric:
    _require_contract(request.contract_id)
    return ScalarMetric(
        contract_id=request.contract_id,
        name="offset",
        value=fmean(request.observed_voltage_v),
        unit="V",
        formula="mean(v_observed[n] - 0 V)",
        manifest=_manifest(request),
    )


def measure_settling(request: SettlingRequest) -> SettlingMetric:
    _require_contract(request.contract_id)
    target = SYNTHETIC_CONTRACT.settling_target_v
    tolerance = SYNTHETIC_CONTRACT.settling_tolerance_v
    start = SYNTHETIC_CONTRACT.settling_start_time_s
    settling_time: float | None = None
    for index, timestamp in enumerate(request.time_s):
        if timestamp < start:
            continue
        if all(
            abs(value - target) <= tolerance
            for value in request.output_voltage_v[index:]
        ):
            settling_time = timestamp - start
            break
    return SettlingMetric(
        contract_id=request.contract_id,
        name="settling_time",
        value=settling_time,
        unit="s",
        formula=(
            "earliest t >= 0 s after which |v(t)-1 V| <= 0.01 V through final sample"
        ),
        settled=settling_time is not None,
        target_v=target,
        tolerance_v=tolerance,
        manifest=_manifest(request),
    )


def measure_fft_metrics(request: FftMeasurementRequest) -> FftMetrics:
    _require_contract(request.contract_id)
    contract = SYNTHETIC_CONTRACT.fft
    spectrum = _fft(tuple(complex(value, 0.0) for value in request.samples_v))
    fundamental_bin = round(
        contract.input_tone_frequency_hz * contract.sample_count / contract.sample_frequency_hz
    )
    harmonic_bins = tuple(
        _fold_bin(multiplier * fundamental_bin, contract.sample_count)
        for multiplier in range(2, contract.harmonic_count + 2)
    )
    harmonic_bins = tuple(dict.fromkeys(harmonic_bins))
    positive_bins = range(1, contract.sample_count // 2 + 1)
    excluded = {fundamental_bin, *harmonic_bins}
    fundamental_power = abs(spectrum[fundamental_bin]) ** 2
    harmonic_power = sum(abs(spectrum[index]) ** 2 for index in harmonic_bins)
    noise_power = sum(abs(spectrum[index]) ** 2 for index in positive_bins if index not in excluded)
    if fundamental_power <= 0.0 or harmonic_power <= 0.0 or noise_power <= 0.0:
        raise InvalidInputError(
            "FFT samples must contain nonzero fundamental, harmonic, and noise power"
        )
    snr_db = 10.0 * math.log10(fundamental_power / noise_power)
    thd_db = 10.0 * math.log10(harmonic_power / fundamental_power)
    sndr_db = 10.0 * math.log10(fundamental_power / (harmonic_power + noise_power))
    enob_bits = (sndr_db - 1.76) / 6.02
    return FftMetrics(
        contract_id=request.contract_id,
        snr_db=snr_db,
        sndr_db=sndr_db,
        thd_db=thd_db,
        enob_bits=enob_bits,
        fundamental_bin=fundamental_bin,
        harmonic_bins=harmonic_bins,
        units={"snr": "dB", "sndr": "dB", "thd": "dB", "enob": "bit"},
        formulas={
            "snr": "10*log10(Pfundamental/Pnoise)",
            "sndr": "10*log10(Pfundamental/(Pnoise+Pharmonics))",
            "thd": "10*log10(Pharmonics/Pfundamental)",
            "enob": "(SNDR_dB - 1.76) / 6.02",
        },
        manifest=_manifest(request),
    )


def measure_linearity(request: LinearityRequest) -> LinearityMetrics:
    _require_contract(request.contract_id)
    lower, upper = SYNTHETIC_CONTRACT.adc_input_range_v
    levels = 2**SYNTHETIC_CONTRACT.adc_bits
    lsb = (upper - lower) / levels
    transitions = request.transition_voltage_v
    widths = (transitions[0] - lower,) + tuple(
        right - left for left, right in zip(transitions, transitions[1:], strict=False)
    ) + (upper - transitions[-1],)
    dnl = tuple(width / lsb - 1.0 for width in widths)
    inl = tuple(
        (transition - (lower + code * lsb)) / lsb
        for code, transition in enumerate(transitions, start=1)
    )
    return LinearityMetrics(
        contract_id=request.contract_id,
        lsb_v=lsb,
        dnl_lsb=dnl,
        inl_lsb=inl,
        max_abs_dnl_lsb=max(abs(value) for value in dnl),
        max_abs_inl_lsb=max(abs(value) for value in inl),
        units={"lsb": "V", "dnl": "LSB", "inl": "LSB"},
        formulas={
            "dnl": "code_width/ideal_LSB - 1",
            "inl": "(transition[k] - ideal_transition[k]) / ideal_LSB",
        },
        manifest=_manifest(request),
    )


def compare_corner_results(request: CornerComparisonRequest) -> CornerComparison:
    _require_contract(request.contract_id)
    reference = request.values["NN"]
    values: dict[str, float] = {
        str(corner): value for corner, value in request.values.items()
    }
    deltas: dict[str, float] = {
        corner: value - reference for corner, value in values.items()
    }
    relative: dict[str, float | None] = {
        corner: (delta / reference * 100.0 if reference != 0.0 else None)
        for corner, delta in deltas.items()
    }
    return CornerComparison(
        contract_id=request.contract_id,
        unit=request.unit,
        values=values,
        delta_from_reference=deltas,
        relative_percent=relative,
        minimum_corner=min(values, key=values.__getitem__),
        maximum_corner=max(values, key=values.__getitem__),
        worst_absolute_delta_corner=max(deltas, key=lambda corner: abs(deltas[corner])),
        formula="corner_value - NN_reference_value",
        manifest=_manifest(request),
    )


def summarize_monte_carlo(request: MonteCarloRequest) -> MonteCarloSummary:
    _require_contract(request.contract_id)
    ordered = tuple(sorted(request.values))
    return MonteCarloSummary(
        contract_id=request.contract_id,
        unit=request.unit,
        count=len(ordered),
        mean=fmean(ordered),
        sample_stddev=stdev(ordered),
        minimum=ordered[0],
        maximum=ordered[-1],
        p05=_percentile(ordered, 0.05),
        median=median(ordered),
        p95=_percentile(ordered, 0.95),
        formula="sample stddev uses n-1; percentiles use linear interpolation",
        manifest=_manifest(request),
    )


def _require_contract(contract_id: str) -> None:
    if contract_id != SYNTHETIC_CONTRACT_ID:
        raise InvalidInputError("measurement contract is missing or outside the registry")


def _manifest(request: ContractRequest) -> MeasurementManifest:
    canonical_input = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return MeasurementManifest(
        contract_id=request.contract_id,
        input_sha256=hashlib.sha256(canonical_input).hexdigest(),
    )


def _fold_bin(index: int, sample_count: int) -> int:
    wrapped = index % sample_count
    return sample_count - wrapped if wrapped > sample_count // 2 else wrapped


def _percentile(values: tuple[float, ...], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _fft(values: tuple[complex, ...]) -> tuple[complex, ...]:
    length = len(values)
    if length == 0 or length & (length - 1):
        raise InvalidInputError("FFT sample count must be a nonzero power of two")
    output = list(values)
    destination = 0
    for source in range(1, length):
        bit = length >> 1
        while destination & bit:
            destination ^= bit
            bit >>= 1
        destination ^= bit
        if source < destination:
            output[source], output[destination] = output[destination], output[source]
    size = 2
    while size <= length:
        step = cmath.exp(-2j * math.pi / size)
        half = size // 2
        for start in range(0, length, size):
            factor = 1.0 + 0.0j
            for offset in range(half):
                even = output[start + offset]
                odd = factor * output[start + offset + half]
                output[start + offset] = even + odd
                output[start + offset + half] = even - odd
                factor *= step
        size *= 2
    return tuple(output)
