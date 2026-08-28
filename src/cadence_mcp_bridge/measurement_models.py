"""Versioned, bounded models for deterministic ADC measurement contracts."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.models import ContractModel

ContractId = Literal["adc-synthetic-v1"]
FiniteSeries = Annotated[tuple[float, ...], Field(min_length=2, max_length=4096)]


class MetricDefinition(ContractModel):
    name: str
    unit: str
    formula: str


class FftContract(ContractModel):
    sample_frequency_hz: float = 1024.0
    input_tone_frequency_hz: float = 64.0
    sample_count: Literal[1024] = 1024
    analysis_time_window_s: tuple[float, float] = (
        0.0,
        0.9990234375,
    )
    initial_transient_exclusion_samples: Literal[0] = 0
    window_function: Literal["rectangular"] = "rectangular"
    dc_bin_policy: Literal["exclude-bin-0"] = "exclude-bin-0"
    fundamental_bin_policy: Literal["exact-coherent-bin"] = "exact-coherent-bin"
    harmonic_count: Literal[4] = 4
    harmonic_policy: Literal["integer-multiples-folded-at-nyquist"] = (
        "integer-multiples-folded-at-nyquist"
    )
    noise_bin_policy: Literal["positive-bins-excluding-dc-fundamental-harmonics"] = (
        "positive-bins-excluding-dc-fundamental-harmonics"
    )
    differential_signal_expression: Literal["fixture:adc_output"] = "fixture:adc_output"
    enob_equation: Literal["(SNDR_dB - 1.76) / 6.02"] = "(SNDR_dB - 1.76) / 6.02"


class AdcMeasurementContract(ContractModel):
    contract_id: ContractId = "adc-synthetic-v1"
    version: Literal[1] = 1
    classification: Literal["fixture"] = "fixture"
    post_processor: Literal["windows-python"] = "windows-python"
    numeric_tolerance: float = 1e-9
    fft: FftContract = Field(default_factory=FftContract)
    settling_target_v: float = 1.0
    settling_tolerance_v: float = 0.01
    settling_start_time_s: float = 0.0
    offset_reference_v: float = 0.0
    adc_bits: Literal[3] = 3
    adc_input_range_v: tuple[float, float] = (0.0, 1.0)
    linearity_method: Literal["endpoint"] = "endpoint"
    corner_names: tuple[Literal["NN"], Literal["FF"], Literal["SS"]] = (
        "NN",
        "FF",
        "SS",
    )
    corner_reference: Literal["NN"] = "NN"
    monte_carlo_stddev: Literal["sample-n-minus-1"] = "sample-n-minus-1"
    definitions: tuple[MetricDefinition, ...]


class ContractRequest(ContractModel):
    contract_id: ContractId


class DcPowerRequest(ContractRequest):
    supply_voltage_v: FiniteSeries
    supply_current_a: FiniteSeries

    @model_validator(mode="after")
    def validate_lengths(self) -> Self:
        _finite(self.supply_voltage_v, "supply_voltage_v")
        _finite(self.supply_current_a, "supply_current_a")
        if len(self.supply_voltage_v) != len(self.supply_current_a):
            raise ValueError("voltage and current series must have equal length")
        return self


class OffsetRequest(ContractRequest):
    observed_voltage_v: FiniteSeries

    @field_validator("observed_voltage_v")
    @classmethod
    def validate_observed(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        return _finite(value, "observed_voltage_v")


class SettlingRequest(ContractRequest):
    time_s: FiniteSeries
    output_voltage_v: FiniteSeries

    @model_validator(mode="after")
    def validate_series(self) -> Self:
        _finite(self.time_s, "time_s")
        _finite(self.output_voltage_v, "output_voltage_v")
        if len(self.time_s) != len(self.output_voltage_v):
            raise ValueError("time and output series must have equal length")
        if any(
            right <= left for left, right in zip(self.time_s, self.time_s[1:], strict=False)
        ):
            raise ValueError("time_s must be strictly increasing")
        return self


class FftMeasurementRequest(ContractRequest):
    samples_v: Annotated[tuple[float, ...], Field(min_length=1024, max_length=1024)]

    @field_validator("samples_v")
    @classmethod
    def validate_samples(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        return _finite(value, "samples_v")


class LinearityRequest(ContractRequest):
    transition_voltage_v: Annotated[tuple[float, ...], Field(min_length=7, max_length=7)]

    @field_validator("transition_voltage_v")
    @classmethod
    def validate_transitions(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        _finite(value, "transition_voltage_v")
        if any(right <= left for left, right in zip(value, value[1:], strict=False)):
            raise ValueError("transition voltages must be strictly increasing")
        if value[0] <= 0.0 or value[-1] >= 1.0:
            raise ValueError("transition voltages must stay inside the ADC input range")
        return value


class CornerComparisonRequest(ContractRequest):
    values: dict[Literal["NN", "FF", "SS"], float]
    unit: Annotated[str, Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        if set(self.values) != {"NN", "FF", "SS"}:
            raise ValueError("corner values must contain exactly NN, FF, and SS")
        if any(not math.isfinite(value) for value in self.values.values()):
            raise ValueError("corner values must be finite")
        return self


class MonteCarloRequest(ContractRequest):
    values: Annotated[tuple[float, ...], Field(min_length=2, max_length=4096)]
    unit: Annotated[str, Field(min_length=1, max_length=32)]

    @field_validator("values")
    @classmethod
    def validate_values(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        return _finite(value, "values")


class MeasurementManifest(ContractModel):
    contract_id: ContractId
    contract_version: Literal[1] = 1
    post_processor: Literal["windows-python"] = "windows-python"
    input_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ScalarMetric(ContractModel):
    contract_id: ContractId
    contract_version: Literal[1] = 1
    name: str
    value: float
    unit: str
    formula: str
    manifest: MeasurementManifest


class SettlingMetric(ContractModel):
    contract_id: ContractId
    contract_version: Literal[1] = 1
    name: Literal["settling_time"] = "settling_time"
    value: float | None
    unit: Literal["s"] = "s"
    formula: str
    settled: bool
    target_v: float
    tolerance_v: float
    manifest: MeasurementManifest


class FftMetrics(ContractModel):
    contract_id: ContractId
    contract_version: Literal[1] = 1
    snr_db: float
    sndr_db: float
    thd_db: float
    enob_bits: float
    fundamental_bin: int
    harmonic_bins: tuple[int, ...]
    units: dict[str, str]
    formulas: dict[str, str]
    manifest: MeasurementManifest


class LinearityMetrics(ContractModel):
    contract_id: ContractId
    contract_version: Literal[1] = 1
    lsb_v: float
    dnl_lsb: tuple[float, ...]
    inl_lsb: tuple[float, ...]
    max_abs_dnl_lsb: float
    max_abs_inl_lsb: float
    method: Literal["endpoint"] = "endpoint"
    units: dict[str, str]
    formulas: dict[str, str]
    manifest: MeasurementManifest


class CornerComparison(ContractModel):
    contract_id: ContractId
    contract_version: Literal[1] = 1
    reference_corner: Literal["NN"] = "NN"
    unit: str
    values: dict[str, float]
    delta_from_reference: dict[str, float]
    relative_percent: dict[str, float | None]
    minimum_corner: str
    maximum_corner: str
    worst_absolute_delta_corner: str
    formula: str
    manifest: MeasurementManifest


class MonteCarloSummary(ContractModel):
    contract_id: ContractId
    contract_version: Literal[1] = 1
    unit: str
    count: int
    mean: float
    sample_stddev: float
    minimum: float
    maximum: float
    p05: float
    median: float
    p95: float
    formula: str
    manifest: MeasurementManifest


def _finite(values: tuple[float, ...], label: str) -> tuple[float, ...]:
    if any(not math.isfinite(value) for value in values):
        raise ValueError(f"{label} must contain only finite values")
    return values
