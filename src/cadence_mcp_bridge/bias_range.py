"""Finite nominal simulation grid review, distinct from continuous safety."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.actual_diagnostics import SpectrumPoint
from cadence_mcp_bridge.designs import DesignContractRegistry, reference_contract_registry
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.power_measurements import PowerCounter, SignedSource, delivered_power
from cadence_mcp_bridge.variable_contracts import (
    Digest,
    RangeReview,
    VariableContract,
    canonical_digest,
)

CASES = ("lowerdc", "lowerac", "upperdc", "upperac")
VALUES = ("0.319", "0.320", "0.321")
BASE_COUNT = 72
BASE_BYTES = 8456765440
RESERVATION = 128 * 1024**2
SOURCES = {
    "dc": (
        "f154d798-0f7f-47d6-9323-6b046394eef6",
        "c9bcf3e3bd8a9329ff0bb1513df2a08f8a4f60e314f04075e15a3422c03e4006",
        "e5f58c16be9db1c672915d9be455c4ef083ca760908bb20bf4991675e3d77cfc",
    ),
    "ac": (
        "1afa2677-e264-4e80-a23d-dc722e34bb4a",
        "53dd6c3bdee80808bfd67880f7e43be289fb275abf4f5486adf5b13f6aad275a",
        "5f13ca23a7d49aacaef51a59c0922e570da5dc2639baef5719956499ce5909fc",
    ),
}
Finite = Annotated[float, Field(allow_inf_nan=False)]


class BiasEndpoint(ContractModel):
    schema_version: Literal[1]
    case: Literal["lowerdc", "lowerac", "upperdc", "upperac"]
    analysis: Literal["dc", "ac"]
    requested_vbiasn_v: Literal["0.319", "0.321"]
    source_job_id: str
    source_input_sha256: Digest
    source_psf_sha256: Digest
    input_sha256: Digest
    psf_sha256: Digest
    frame_sha256: Digest
    counter: PowerCounter
    warnings: Annotated[int, Field(ge=0, le=2, strict=True)]
    notices: Literal[0]
    protected_unchanged: Literal[True]
    scalars: dict[str, Finite] = Field(default_factory=dict, max_length=7)
    sources: Annotated[tuple[SignedSource, ...], Field(max_length=6)] = ()
    spectrum: Annotated[tuple[SpectrumPoint, ...], Field(max_length=72)] = ()

    @model_validator(mode="after")
    def bound_evidence(self) -> Self:
        value = "0.319" if self.case.startswith("lower") else "0.321"
        if self.analysis != self.case[-2:] or self.requested_vbiasn_v != value:
            raise ValueError("case/analysis/effective bias binding")
        if (self.source_job_id, self.source_input_sha256, self.source_psf_sha256) != (
            SOURCES[self.analysis]
        ):
            raise ValueError("pinned native source required")
        i = CASES.index(self.case) + 1
        if self.counter.count != BASE_COUNT + i or self.counter.result_reserved_bytes != (
            BASE_BYTES + i * RESERVATION
        ):
            raise ValueError("exact cumulative admission required")
        if self.input_sha256 == self.source_input_sha256:
            raise ValueError("endpoint input must reflect the applied parameter")
        if self.analysis == "dc":
            if self.spectrum or set(self.scalars) != {
                "Vop", "Vom", "Vp", "Vm", "VDD", "Vbiasn", "Vbiasp"
            }:
                raise ValueError("complete DC frame required")
            expected = {"Vp": 0.5, "Vm": 0.5, "VDD": 1, "Vbiasn": float(value),
                        "Vbiasp": 0.702}
            if any(abs(self.scalars[n] - v) > 1e-9 for n, v in expected.items()):
                raise ValueError("effective DC inputs mismatch")
            specs = (("vdd", "supply", 1), ("vss", "supply", 0),
                     ("bias-n", "bias", float(value)), ("bias-p", "bias", 0.702),
                     ("input-p", "stimulus", 0.5), ("input-m", "stimulus", 0.5))
            if len(self.sources) != 6:
                raise ValueError("complete signed source inventory required")
            for source, (identity, role, voltage) in zip(self.sources, specs, strict=True):
                if (source.source_id != identity or source.role != role
                    or source.voltage_v is None or source.current_a is None
                    or abs(source.voltage_v - voltage) > 1e-9):
                    raise ValueError("signed source identity/voltage/current mismatch")
            delivered_power(self.sources)
        else:
            if self.scalars or self.sources or not 70 <= len(self.spectrum) <= 72:
                raise ValueError("bounded AC frame required")
            if abs(self.spectrum[0].frequency_hz - 10) > 1e-4 or abs(
                self.spectrum[-1].frequency_hz - 1e8
            ) > 100:
                raise ValueError("qualified AC endpoints required")
            for a, b in zip(self.spectrum, self.spectrum[1:], strict=False):
                if b.frequency_hz <= a.frequency_hz or b.frequency_hz / a.frequency_hz > 1.4:
                    raise ValueError("AC frequency progression")
            for point in self.spectrum:
                expected_db = (20 * math.log10(point.gain_v_per_v)
                               if point.gain_v_per_v else None)
                if (expected_db is None) != (point.gain_db is None) or (
                    expected_db is not None and point.gain_db is not None
                    and abs(expected_db - point.gain_db) > 1e-9
                ):
                    raise ValueError("AC differential gain unit arithmetic")
        return self


class BiasExtraction(ContractModel):
    schema_version: Literal[1]
    cases: Annotated[tuple[BiasEndpoint, ...], Field(min_length=4, max_length=4)]

    @model_validator(mode="after")
    def complete(self) -> Self:
        if tuple(p.case for p in self.cases) != CASES:
            raise ValueError("complete ordered four-case evidence required")
        return self


def finite_grid_registry(evidence: BiasExtraction) -> DesignContractRegistry:
    """Operator-only v2 artifact. No executable adapter or default promotion."""
    base = reference_contract_registry()
    profile, old = base.designs[0], base.variable_sets[0]
    variable = VariableContract(
        logical_id="vbiasn", cadence_binding="VBIASN", unit="V", value_type="real",
        default="0.320", mutation_policy="owned_copy_only", range_status="qualified",
        minimum="0.319", maximum="0.321", step_policy="grid", step="0.001",
        fixed_value=None, review_id="bias-n-finite-three-point-v1",
    )
    fixed_p = VariableContract(
        logical_id="vbiasp", cadence_binding="VBIASP", unit="V", value_type="real",
        default="0.702", mutation_policy="fixed", range_status="unqualified", minimum=None,
        maximum=None, step_policy="fixed", step=None, fixed_value="0.702", review_id=None,
    )
    review = RangeReview(
        review_id="bias-n-finite-three-point-v1", design_id=profile.design_id,
        design_profile_sha256=canonical_digest(profile),
        variable_contract_sha256=canonical_digest(variable),
        evidence_id="bias-n-finite-nn-27c-vdd1-v1", evidence_sha256=canonical_digest(evidence),
        scope="operator_reviewed_project_numeric_contract",
    )
    return DesignContractRegistry(
        schema_version=2, designs=base.designs, range_reviews=(review,),
        variable_sets=(
            old.model_copy(update={"variables": (variable, fixed_p, old.variables[2])}),
        ),
    )
