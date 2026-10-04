"""Closed native ADE execution and bounded measurement contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import Field, model_validator

from cadence_mcp_bridge.actual_diagnostics import (
    COPY_SHA256,
    NETLIST_SHA256,
    SOURCE_SHA256,
    ActualDiagnosticResult,
    DiagnosticScalar,
    SpectrumPoint,
)
from cadence_mcp_bridge.models import ContractModel, JobState

Analysis = Literal["dc", "ac", "tran"]
REVISION: Final = "wp14-native-ade-v1"
OPERATING_POINT: Final = "candidate-320-702mv-v1"
STATE_SHA256 = "085b7dae004fc0f88d23fd1507a3de49285927ec870d6a2d6a12001bbf0c1193"
MODEL_SHA256 = "029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f"
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
OperationId = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
]
Finite = Annotated[float, Field(ge=-1e12, le=1e12, allow_inf_nan=False)]


class NativeDiagnosticRequest(ContractModel):
    operation_id: OperationId
    revision_id: Literal["wp14-native-ade-v1"]
    operating_point_id: Literal["candidate-320-702mv-v1"]
    analysis: Analysis


class NativeSettings(ContractModel):
    corner: Literal["NN"] = "NN"
    temperature_c: Literal[27] = 27
    vdd_v: Annotated[float, Field(ge=1.0, le=1.0, allow_inf_nan=False)] = 1.0
    input_vcm_v: Annotated[float, Field(ge=0.5, le=0.5, allow_inf_nan=False)] = 0.5
    saved_bias_values_v: tuple[
        Annotated[float, Field(ge=0.3, le=0.3, allow_inf_nan=False)],
        Annotated[float, Field(ge=0.65, le=0.65, allow_inf_nan=False)],
    ] = (0.3, 0.65)
    applied_bias_values_v: tuple[
        Annotated[float, Field(ge=0.32, le=0.32, allow_inf_nan=False)],
        Annotated[float, Field(ge=0.702, le=0.702, allow_inf_nan=False)],
    ] = (0.32, 0.702)
    saved_enabled_analyses: tuple[Literal["dc"]] = ("dc",)
    ac_start_hz: Literal[10] = 10
    ac_stop_hz: Literal[100000000] = 100000000
    ac_points_per_decade: Literal[10] = 10
    tran_stop_s: Annotated[float, Field(ge=0.004, le=0.004, allow_inf_nan=False)] = 0.004
    tran_maxstep_s: Annotated[float, Field(ge=0.00001, le=0.00001, allow_inf_nan=False)] = 0.00001
    tran_method: Literal["trap"] = "trap"
    stimulus: Literal["existing_opposed_1khz_50mv_peak_inputs"] = (
        "existing_opposed_1khz_50mv_peak_inputs"
    )
    load: Literal["existing_topology_no_added_external_load"] = (
        "existing_topology_no_added_external_load"
    )


class NativeDiagnosticProfiles(ContractModel):
    contract_version: Literal[2] = 2
    campaign_max_spectre_attempts: Literal[500] = 500
    campaign_max_result_bytes: Literal[5368709120] = 5368709120
    reservation_bytes_per_job: Literal[134217728] = 134217728
    revision_id: Literal["wp14-native-ade-v1"] = REVISION
    operating_point_id: Literal["candidate-320-702mv-v1"] = OPERATING_POINT
    analyses: tuple[Literal["dc"], Literal["ac"], Literal["tran"]] = ("dc", "ac", "tran")
    settings: NativeSettings = NativeSettings()
    submission_identity: Literal["caller_uuid4_durable_no_replay"] = (
        "caller_uuid4_durable_no_replay"
    )
    execution: Literal["owned_state_copy_native_netlist_spectre_psf_reader"] = (
        "owned_state_copy_native_netlist_spectre_psf_reader"
    )
    spec_evaluation: Literal["not_evaluated"] = "not_evaluated"


class NativeDiagnosticStatus(ContractModel):
    job_id: UUID
    revision_id: Literal["wp14-native-ade-v1"] = REVISION
    operating_point_id: Literal["candidate-320-702mv-v1"] = OPERATING_POINT
    analysis: Analysis
    state: JobState
    stage: Literal[
        "queued",
        "netlisting",
        "netlist_failed",
        "netlisted",
        "reserving",
        "reservation_failed",
        "simulating",
        "simulator_failed",
        "extracting",
        "extraction_failed",
        "verifying",
        "verification_failed",
        "succeeded",
        "failed",
    ]
    simulator: Literal["not_started", "running", "succeeded", "failed"]
    extraction: Literal["not_started", "running", "succeeded", "failed"]
    updated_at: datetime

    @model_validator(mode="after")
    def lifecycle(self) -> NativeDiagnosticStatus:
        if self.stage == "succeeded":
            if (self.state, self.simulator, self.extraction) != (
                JobState.SUCCEEDED,
                "succeeded",
                "succeeded",
            ):
                raise ValueError("native completion state mismatch")
        elif self.state == JobState.SUCCEEDED:
            raise ValueError("native success requires completed stage")
        elif self.stage.endswith("failed") and self.state != JobState.FAILED:
            raise ValueError("native failure requires failed state")
        elif self.state not in (
            JobState.QUEUED,
            JobState.RUNNING,
            JobState.UNKNOWN,
            JobState.FAILED,
        ):
            raise ValueError("unqualified native lifecycle state")
        return self


class NativeTransient(ContractModel):
    point_count: Annotated[int, Field(ge=401, le=3000, strict=True)]
    start_s: Annotated[float, Field(ge=0.0, le=0.0, allow_inf_nan=False)]
    stop_s: Annotated[float, Field(ge=0.004, le=0.004, allow_inf_nan=False)]
    max_observed_step_s: Annotated[float, Field(gt=0, le=1.00001e-5, allow_inf_nan=False)]
    output_differential_min_v: Finite
    output_differential_max_v: Finite
    output_common_mode_min_v: Finite
    output_common_mode_max_v: Finite
    input_vcm_v: Annotated[float, Field(ge=0.5, le=0.5, allow_inf_nan=False)]
    input_differential_peak_v: Annotated[float, Field(ge=0.1, le=0.1, allow_inf_nan=False)]
    input_tone_hz: Literal[1000]
    vdd_v: Annotated[float, Field(ge=1.0, le=1.0, allow_inf_nan=False)]
    sampling: Literal["adaptive_native_no_fft"]
    stimulus_verified: Literal[True]

    @model_validator(mode="after")
    def ordered_extrema(self) -> NativeTransient:
        if (
            self.output_differential_min_v > self.output_differential_max_v
            or self.output_common_mode_min_v > self.output_common_mode_max_v
        ):
            raise ValueError("native transient extrema order")
        return self


class NativeDiagnosticResult(ContractModel):
    job_id: UUID
    revision_id: Literal["wp14-native-ade-v1"] = REVISION
    operating_point_id: Literal["candidate-320-702mv-v1"] = OPERATING_POINT
    analysis: Analysis
    state: Literal["succeeded"]
    simulator: Literal["succeeded"]
    extraction: Literal["succeeded"]
    quality: Literal["valid"]
    spec_evaluation: Literal["not_evaluated"]
    execution_mode: Literal["native_ade_owned_candidate_state"]
    settings: NativeSettings
    source_sha256: Hash
    copy_sha256: Hash
    state_sha256: Hash
    model_sha256: Hash
    circuit_sha256: Hash
    input_sha256: Hash
    owned_variables_sha256: Hash
    psf_sha256: Hash
    measurement_frame_sha256: Hash
    result_selector: Literal["dcOp", "ac", "tran"]
    protected_unchanged: Literal[True]
    source_copy_signature_equal: Literal[True]
    state_loaded: Literal[True]
    netlist_valid: Literal[True]
    warnings: Annotated[int, Field(ge=0, le=2, strict=True)]
    notices: Literal[0]
    scalars: Annotated[tuple[DiagnosticScalar, ...], Field(max_length=7)] = ()
    spectrum: Annotated[tuple[SpectrumPoint, ...], Field(max_length=72)] = ()
    transient: NativeTransient | None = None

    @model_validator(mode="after")
    def evidence_and_shape(self) -> NativeDiagnosticResult:
        if (
            self.source_sha256,
            self.copy_sha256,
            self.state_sha256,
            self.model_sha256,
            self.circuit_sha256,
        ) != (SOURCE_SHA256, COPY_SHA256, STATE_SHA256, MODEL_SHA256, NETLIST_SHA256):
            raise ValueError("native pinned source/state/model/circuit drift")
        expected = "dcOp" if self.analysis == "dc" else self.analysis
        if self.result_selector != expected:
            raise ValueError("native analysis selector mismatch")
        if self.analysis == "tran":
            if self.transient is None or self.scalars or self.spectrum:
                raise ValueError("native transient shape")
        else:
            if self.transient is not None:
                raise ValueError("unexpected native transient")
            # Reuse the qualified scalar/spectrum arithmetic and shape checks.
            ActualDiagnosticResult.model_validate(
                {
                    "job_id": self.job_id,
                    "state": "succeeded",
                    "profile_id": "actual-wp14-" + self.analysis + "-v1",
                    "revision_id": "wp14-copied-netlist-v1",
                    "operating_point_id": OPERATING_POINT,
                    "simulator": "succeeded",
                    "extraction": "succeeded",
                    "quality": "valid",
                    "spec_evaluation": "not_evaluated",
                    "source_sha256": self.source_sha256,
                    "copy_sha256": self.copy_sha256,
                    "netlist_sha256": self.circuit_sha256,
                    "wrapper_sha256": self.input_sha256,
                    "psf_sha256": self.psf_sha256,
                    "vdd_v": 1.0,
                    "input_vcm_v": 0.5,
                    "applied_bias_values_v": (0.32, 0.702),
                    "scalars": self.scalars,
                    "spectrum": self.spectrum,
                    "artifact_names": ("profile.scs", "spectre.log", "psf", "scalars.txt"),
                }
            )
        return self
