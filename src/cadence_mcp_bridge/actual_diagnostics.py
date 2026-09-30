"""Closed, versioned contract for the pinned WP14 work-copy diagnostics."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import Field, model_validator

from cadence_mcp_bridge.models import ContractModel, JobState

REVISION: Final = "wp14-copied-netlist-v1"
OPERATING_POINT: Final = "candidate-320-702mv-v1"
PROFILE_DC: Final = "actual-wp14-dc-v1"
PROFILE_AC: Final = "actual-wp14-ac-v1"
SOURCE_SHA256 = "046021f90f70d85d05d59e4f80842f0742d6ca38c186d42ba27106a89b81d714"
COPY_SHA256 = "a02d83653f26f2e34f1f4e402531e66e9d34b5ecc41d29ed6d38a70ed8c6983f"
NETLIST_SHA256 = "6189aa9d647671c05a9f03d815530697560c00b661cad95c87f7f415d482192a"


class ActualDiagnosticRequest(ContractModel):
    revision_id: Literal["wp14-copied-netlist-v1"]
    analysis: Literal["dc", "ac"]
    operating_point_id: Literal["candidate-320-702mv-v1"]
    output_id: Literal["dc-node-scalars-v1", "ac-differential-spectrum-v1"]

    @model_validator(mode="after")
    def validate_pair(self) -> ActualDiagnosticRequest:
        expected = "dc-node-scalars-v1" if self.analysis == "dc" else "ac-differential-spectrum-v1"
        if self.output_id != expected:
            raise ValueError("output_id does not match analysis")
        return self


class ActualDiagnosticProfile(ContractModel):
    profile_id: Literal["actual-wp14-dc-v1", "actual-wp14-ac-v1"]
    revision_id: Literal["wp14-copied-netlist-v1"] = REVISION
    analysis: Literal["dc", "ac"]
    operating_point_id: Literal["candidate-320-702mv-v1"] = OPERATING_POINT
    output_id: Literal["dc-node-scalars-v1", "ac-differential-spectrum-v1"]
    corner: Literal["NN"] = "NN"
    vdd_v: float = 1.0
    input_vcm_v: float = 0.5
    capability: Literal["bounded-workcopy-simulation"] = "bounded-workcopy-simulation"


class ActualDiagnosticProfiles(ContractModel):
    contract_version: Literal[1] = 1
    profiles: tuple[ActualDiagnosticProfile, ActualDiagnosticProfile] = (
        ActualDiagnosticProfile(
            profile_id=PROFILE_DC, analysis="dc", output_id="dc-node-scalars-v1"
        ),
        ActualDiagnosticProfile(
            profile_id=PROFILE_AC, analysis="ac", output_id="ac-differential-spectrum-v1"
        ),
    )


class ActualDiagnosticStatus(ContractModel):
    job_id: UUID
    state: JobState
    profile_id: Literal["actual-wp14-dc-v1", "actual-wp14-ac-v1"]
    revision_id: Literal["wp14-copied-netlist-v1"]
    operating_point_id: Literal["candidate-320-702mv-v1"]
    updated_at: datetime
    simulator: Literal["not_started", "running", "succeeded", "failed"]
    extraction: Literal["not_started", "running", "succeeded", "failed"]


class DiagnosticScalar(ContractModel):
    logical_id: Literal[
        "vop", "vom", "vdd", "vp", "vm", "output_common_mode", "output_differential"
    ]
    unit: Literal["V"] = "V"
    value: Annotated[float, Field(allow_inf_nan=False)]


class SpectrumPoint(ContractModel):
    frequency_hz: Annotated[float, Field(ge=10, le=100_000_000, allow_inf_nan=False)]
    gain_v_per_v: Annotated[float, Field(ge=0, le=1e12, allow_inf_nan=False)]
    gain_db: Annotated[float, Field(allow_inf_nan=False)] | None
    phase_deg: Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class ActualDiagnosticResult(ContractModel):
    job_id: UUID
    state: JobState
    profile_id: Literal["actual-wp14-dc-v1", "actual-wp14-ac-v1"]
    revision_id: Literal["wp14-copied-netlist-v1"]
    operating_point_id: Literal["candidate-320-702mv-v1"]
    simulator: Literal["succeeded", "failed"]
    extraction: Literal["succeeded", "failed", "not_started"]
    quality: Literal["valid", "invalid"]
    spec_evaluation: Literal["not_evaluated"]
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    copy_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    netlist_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    wrapper_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    psf_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    vdd_v: float
    input_vcm_v: float
    applied_bias_values_v: tuple[float, float]
    scalars: tuple[DiagnosticScalar, ...]
    spectrum: Annotated[tuple[SpectrumPoint, ...], Field(max_length=72)]
    artifact_names: tuple[Literal["profile.scs", "spectre.log", "psf", "scalars.txt"], ...]

    @model_validator(mode="after")
    def validate_result(self) -> ActualDiagnosticResult:
        if (
            self.vdd_v != 1.0
            or self.input_vcm_v != 0.5
            or self.applied_bias_values_v != (0.32, 0.702)
        ):
            raise ValueError("work-copy operating point mismatch")
        if self.quality == "valid":
            if self.psf_sha256 is None or self.artifact_names != (
                "profile.scs",
                "spectre.log",
                "psf",
                "scalars.txt",
            ):
                raise ValueError("diagnostic artifacts missing")
            if (
                self.state != JobState.SUCCEEDED
                or self.simulator != "succeeded"
                or self.extraction != "succeeded"
            ):
                raise ValueError("valid diagnostic requires simulation and extraction success")
            if self.profile_id == PROFILE_DC and (len(self.scalars) != 7 or self.spectrum):
                raise ValueError("DC measurement shape invalid")
            if self.profile_id == PROFILE_AC and (
                self.scalars or not 70 <= len(self.spectrum) <= 72
            ):
                raise ValueError("AC measurement shape invalid")
            if self.profile_id == PROFILE_DC:
                names = tuple(scalar.logical_id for scalar in self.scalars)
                if names != (
                    "vop",
                    "vom",
                    "vdd",
                    "vp",
                    "vm",
                    "output_common_mode",
                    "output_differential",
                ):
                    raise ValueError("DC scalar identities invalid")
                values = [scalar.value for scalar in self.scalars]
                if (
                    abs(values[2] - 1.0) > 1e-6
                    or abs(values[3] - 0.5) > 2e-7
                    or abs(values[4] - 0.5) > 2e-7
                    or abs(values[5] - (values[0] + values[1]) / 2) > 1e-6
                    or abs(values[6] - (values[0] - values[1])) > 1e-6
                ):
                    raise ValueError("DC scalar relationship invalid")
            else:
                points = self.spectrum
                if (
                    abs(points[0].frequency_hz - 10) > 1e-4
                    or abs(points[-1].frequency_hz - 1e8) > 100
                ):
                    raise ValueError("AC spectrum endpoints invalid")
                for index, point in enumerate(points):
                    if index and not points[index - 1].frequency_hz < point.frequency_hz:
                        raise ValueError("AC spectrum order invalid")
                    expected_db = (
                        20 * math.log10(point.gain_v_per_v) if point.gain_v_per_v else None
                    )
                    if expected_db is None and point.gain_db is not None:
                        raise ValueError("AC zero-gain dB invalid")
                    if expected_db is not None and (
                        point.gain_db is None or abs(point.gain_db - expected_db) > 1e-6
                    ):
                        raise ValueError("AC gain relationship invalid")
        return self
