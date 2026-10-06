"""Versioned real point facts and operator goals using the existing comparator."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cadence_mcp_bridge.amplifier_sweeps import (
    DEFINITION_SHA,
    DESIGN,
    GRID,
    REGISTRY_SHA,
    REVISION,
    AmplifierEnginePlan,
    AmplifierMetric,
    AmplifierQuery,
    AmplifierSupervisor,
    AmplifierSweepResult,
)
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.specifications import (
    SpecificationConditions,
    SpecificationContract,
    evaluate_fact,
)
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

MeasurementId = Literal["dc-supply-power-grid-v2", "gain-10hz-grid-v1"]
AnalysisId = Literal["grid-dc-v1", "grid-ac-v1"]
Status = Literal[
    "PASS",
    "FAIL",
    "NOT_EVALUATED",
    "UNQUALIFIED",
    "MISSING_MEASUREMENT",
    "CONDITION_MISMATCH",
    "SIMULATION_ERROR",
    "SOURCE_UNAVAILABLE",
]


class AmplifierFactSettings(ContractModel):
    schema_version: Literal[1] = 1
    analysis_id: AnalysisId
    corner: Literal["NN"] = "NN"
    temperature_c: Literal[27] = 27
    vdd_v: Annotated[float, Field(ge=1, le=1, allow_inf_nan=False)] = 1.0
    input_vcm_v: Annotated[float, Field(ge=0.5, le=0.5, allow_inf_nan=False)] = 0.5
    applied_bias_values_v: tuple[
        Annotated[float, Field(allow_inf_nan=False)],
        Annotated[float, Field(ge=0.702, le=0.702, allow_inf_nan=False)],
    ]
    saved_bias_values_v: tuple[
        Annotated[float, Field(ge=0.3, le=0.3, allow_inf_nan=False)],
        Annotated[float, Field(ge=0.65, le=0.65, allow_inf_nan=False)],
    ] = (0.3, 0.65)
    load: Literal["existing_topology_no_added_external_load"] = (
        "existing_topology_no_added_external_load"
    )
    source_input_policy: Literal["only_owned_VBIASN_token_reversed_to_pinned_native_input"] = (
        "only_owned_VBIASN_token_reversed_to_pinned_native_input"
    )
    reader: Literal["signed_dc_six_sources_or_original_bounded_differential_AC_v2"] = (
        "signed_dc_six_sources_or_original_bounded_differential_AC_v2"
    )
    qualification: Literal["finite_nominal_simulation_grid_only"] = (
        "finite_nominal_simulation_grid_only"
    )

    @model_validator(mode="after")
    def finite_grid(self) -> Self:
        if self.applied_bias_values_v[0] not in (0.319, 0.32, 0.321):
            raise ValueError("qualified finite grid settings required")
        return self


class AmplifierFactProvenance(ContractModel):
    schema_version: Literal[1] = 1
    job_id: UUID
    analysis_plan_hash: Digest
    revision_id: Literal["reference-amplifier-bias-grid-v1"] = REVISION
    operating_point_id: Literal["bias-n-319mv-v1", "bias-n-320mv-v1", "bias-n-321mv-v1"]
    settings: AmplifierFactSettings
    definition_sha256: Digest = DEFINITION_SHA
    input_sha256: Digest
    psf_sha256: Digest
    frame_sha256: Digest
    source_result_sha256: Digest
    measurement_result_sha256: Digest
    protected_unchanged: Literal[True] = True

    @model_validator(mode="after")
    def bound_identity(self) -> Self:
        expected = {
            0.319: "bias-n-319mv-v1",
            0.32: "bias-n-320mv-v1",
            0.321: "bias-n-321mv-v1",
        }[self.settings.applied_bias_values_v[0]]
        if (
            self.job_id.version != 5
            or self.definition_sha256 != DEFINITION_SHA
            or self.operating_point_id != expected
        ):
            raise ValueError("versioned fact point/definition identity")
        return self


class AmplifierMeasurementBinding(ContractModel):
    schema_version: Literal[1] = 1
    design_id: Literal["reference-differential-amplifier-tb2"] = DESIGN
    measurement_id: MeasurementId
    analysis_id: AnalysisId
    definition_sha256: Digest = DEFINITION_SHA
    revision_id: Literal["reference-amplifier-bias-grid-v1"] = REVISION
    registry_sha256: Digest = REGISTRY_SHA


def binding(measurement_id: MeasurementId) -> AmplifierMeasurementBinding:
    return AmplifierMeasurementBinding(
        measurement_id=measurement_id,
        analysis_id="grid-dc-v1" if measurement_id == "dc-supply-power-grid-v2" else "grid-ac-v1",
    )


def provenance(metric: AmplifierMetric, plan_hash: str) -> AmplifierFactProvenance:
    b = binding(metric.measurement_id)
    index = GRID.index(metric.requested_vbiasn_v)
    return AmplifierFactProvenance(
        job_id=metric.job_id,
        analysis_plan_hash=plan_hash,
        operating_point_id=("bias-n-319mv-v1", "bias-n-320mv-v1", "bias-n-321mv-v1")[index],
        settings=AmplifierFactSettings(
            analysis_id=b.analysis_id,
            applied_bias_values_v=(float(metric.requested_vbiasn_v), 0.702),
        ),
        input_sha256=metric.input_sha256,
        psf_sha256=metric.psf_sha256,
        frame_sha256=metric.frame_sha256,
        source_result_sha256=metric.source_result_sha256,
        measurement_result_sha256=canonical_digest(metric),
    )


def conditions(p: AmplifierFactProvenance) -> SpecificationConditions:
    return SpecificationConditions(
        analysis_id=p.settings.analysis_id,
        analysis_plan_hash=p.analysis_plan_hash,
        revision_id=p.revision_id,
        operating_point_id=p.operating_point_id,
        corner=p.settings.corner,
        temperature_c="27",
        vdd_v="1",
        applied_bias_values_v=(str(p.settings.applied_bias_values_v[0]), "0.702"),
        effective_settings_sha256=canonical_digest(p.settings),
    )


class AmplifierSpecificationContract(SpecificationContract):
    contract_version: Literal[3] = 3  # type: ignore[assignment]
    design_id: Literal["reference-differential-amplifier-tb2"] = DESIGN
    measurement_id: MeasurementId
    unit: Literal["dB", "W"]

    @model_validator(mode="after")
    def bound_definition(self) -> Self:
        b = binding(self.measurement_id)
        if (
            self.measurement_contract_sha256 != canonical_digest(b)
            or self.definition_sha256 != DEFINITION_SHA
            or self.conditions.analysis_id != b.analysis_id
            or self.unit != ("W" if self.measurement_id == "dc-supply-power-grid-v2" else "dB")
        ):
            raise ValueError("versioned measurement/definition/unit/analysis binding required")
        return self


class AmplifierSpecificationRegistry(VariableModel):
    schema_version: Literal[1] = 1
    specifications: Annotated[tuple[AmplifierSpecificationContract, ...], Field(max_length=16)] = ()

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("integer target registry version required")
        return value

    @model_validator(mode="after")
    def unique_goals(self) -> Self:
        if len({c.spec_id for c in self.specifications}) != len(self.specifications):
            raise ValueError("duplicate specification ID")
        return self


def load_amplifier_specifications(path: Path) -> AmplifierSpecificationRegistry:
    """Local operator file only, not an MCP input or an execution capability."""
    try:
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError("no-follow target catalog required")
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 65536:
            raise ValueError("bounded regular target catalog required")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            actual = os.fstat(stream.fileno())
            if (actual.st_dev, actual.st_ino, actual.st_size) != (
                before.st_dev,
                before.st_ino,
                before.st_size,
            ):
                raise ValueError("target catalog changed during read")
            data = stream.read(65537)
            after = os.fstat(stream.fileno())
            if (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ) != (
                actual.st_dev,
                actual.st_ino,
                actual.st_size,
                actual.st_mtime_ns,
                actual.st_ctime_ns,
            ):
                raise ValueError("target catalog changed during read")
        if len(data) > 65536:
            raise ValueError("bounded target catalog required")

        def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for k, v in items:
                if k in result:
                    raise ValueError("duplicate target catalog field")
                result[k] = v
            return result

        def constant(_: str) -> None:
            raise ValueError("nonfinite target catalog")

        json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
        return AmplifierSpecificationRegistry.model_validate_json(data)
    except (OSError, ValueError):
        raise InvalidInputError("Operator amplifier target catalog is invalid") from None


class AmplifierSpecificationCatalog(ContractModel):
    contract_version: Literal[1] = 1
    design_id: Literal["reference-differential-amplifier-tb2"] = DESIGN
    registry_sha256: Digest
    specifications: Annotated[tuple[AmplifierSpecificationContract, ...], Field(max_length=16)]
    target_status: Literal["not_registered", "not_selected", "registered"]
    execution_authorized: Literal[False] = False


class AmplifierEvaluationQuery(AmplifierQuery):
    expected_sweep_result_sha256: Digest
    expected_specification_registry_sha256: Digest


class AmplifierPointEvaluation(ContractModel):
    child_job_id: UUID
    requested_vbiasn_v: str
    measurement_id: MeasurementId
    spec_id: LogicalId | None = None
    specification_sha256: Digest | None = None
    measurement_result_sha256: Digest | None = None
    status: Status
    reason: Literal[
        "no_operator_target_registered",
        "target_not_selected",
        "target_met",
        "target_not_met",
        "measurement_unqualified",
        "measurement_conditions_differ",
        "source_not_completed",
        "source_cancelled",
        "simulator_failed",
        "source_outcome_uncertain",
    ]
    unit: Literal["W", "dB"]
    observed_value: float | None = Field(allow_inf_nan=False)
    comparison: Literal[">=", "<=", ">", "<", "range"] | None = None
    target: str | None = None
    upper_target: str | None = None


class AmplifierSpecificationEvaluation(ContractModel):
    contract_version: Literal[1] = 1
    source: AmplifierSweepResult
    source_result_sha256: Digest
    specification_registry_sha256: Digest
    target_status: Literal["not_registered", "not_selected", "registered"]
    provenance: Annotated[tuple[AmplifierFactProvenance, ...], Field(max_length=3)]
    evaluations: Annotated[tuple[AmplifierPointEvaluation, ...], Field(max_length=48)]
    scope: Literal["per_point_exact_nominal_conditions_not_PVT_or_optimization"] = (
        "per_point_exact_nominal_conditions_not_PVT_or_optimization"
    )
    execution_authorized: Literal[False] = False


def evaluate_source(
    source: AmplifierSweepResult,
    registry: AmplifierSpecificationRegistry,
    measurement_id: MeasurementId,
) -> AmplifierSpecificationEvaluation:
    """No targets/facts from MCP; inputs are already validated operator/reader models."""
    if (
        source.definition_sha256 != DEFINITION_SHA
        or canonical_digest(source.definition) != DEFINITION_SHA
    ):
        raise InvalidInputError("Sweep measurement definition is stale")
    metrics = {m.job_id: m for m in source.measurements}
    expected = {p.child_job_id for p in source.engine.points if p.state == "SUCCEEDED"}
    if len(metrics) != len(source.measurements) or set(metrics) != expected:
        raise RemoteFailureError("Sweep measurement/point inventory differs")
    facts = []
    rows = []
    for point in source.engine.points:
        m = metrics.get(point.child_job_id)
        if m is not None:
            if m.requested_vbiasn_v != point.requested_value or m.measurement_id != measurement_id:
                raise RemoteFailureError("Sweep point fact identity differs")
            p = provenance(m, source.engine.plan_hash)
            facts.append(p)
        else:
            p = None
        selected: list[AmplifierSpecificationContract | None] = [
            c for c in registry.specifications if c.measurement_id == measurement_id
        ]
        for c in selected or [None]:
            status: Status
            if c is None:
                status, reason = "NOT_EVALUATED", "no_operator_target_registered"
            elif c.target is None:
                status, reason = "NOT_EVALUATED", "target_not_selected"
            elif m is None:
                status, reason = (
                    ("SIMULATION_ERROR", "simulator_failed")
                    if point.state == "FAILED"
                    else ("SOURCE_UNAVAILABLE", "source_outcome_uncertain")
                    if point.state == "UNKNOWN"
                    else ("MISSING_MEASUREMENT", "source_cancelled")
                    if point.state == "CANCELLED"
                    else ("MISSING_MEASUREMENT", "source_not_completed")
                )
            else:
                status = evaluate_fact(c, m.status, m.value, p)
                reason = {
                    "PASS": "target_met",
                    "FAIL": "target_not_met",
                    "UNQUALIFIED": "measurement_unqualified",
                    "CONDITION_MISMATCH": "measurement_conditions_differ",
                }[status]
            rows.append(
                AmplifierPointEvaluation(
                    child_job_id=point.child_job_id,
                    requested_vbiasn_v=point.requested_value,
                    measurement_id=measurement_id,
                    spec_id=c.spec_id if c else None,
                    specification_sha256=canonical_digest(c) if c else None,
                    measurement_result_sha256=canonical_digest(m) if m else None,
                    status=status,
                    reason=reason,  # type: ignore[arg-type]
                    observed_value=m.value if m else None,
                    unit="W" if measurement_id == "dc-supply-power-grid-v2" else "dB",
                    comparison=c.comparison if c else None,
                    target=c.target if c else None,
                    upper_target=c.upper_target if c else None,
                )
            )
    target_status: Literal["registered", "not_selected", "not_registered"] = (
        "registered"
        if any(c.target is not None for c in registry.specifications)
        else "not_selected"
        if registry.specifications
        else "not_registered"
    )
    result = AmplifierSpecificationEvaluation(
        source=source,
        source_result_sha256=canonical_digest(source),
        specification_registry_sha256=canonical_digest(registry),
        target_status=target_status,
        provenance=tuple(facts),
        evaluations=tuple(rows),
    )
    if len(result.model_dump_json().encode("utf-8")) > 65536:
        raise RemoteFailureError("Bounded specification result exceeded limit")
    return result


class AmplifierSpecificationSupervisor:
    def __init__(
        self,
        sweeps: AmplifierSupervisor,
        registry: AmplifierSpecificationRegistry,
    ) -> None:
        self.sweeps, self.registry = sweeps, registry

    def catalog(self, design_id: str) -> AmplifierSpecificationCatalog:
        if design_id != DESIGN:
            raise InvalidInputError("Unknown amplifier specification design")
        self.sweeps.require_contract()
        selected = self.registry.specifications
        return AmplifierSpecificationCatalog(
            registry_sha256=canonical_digest(self.registry),
            specifications=selected,
            target_status="registered"
            if any(c.target is not None for c in selected)
            else "not_selected"
            if selected
            else "not_registered",
        )

    async def result(self, request: AmplifierEvaluationQuery) -> AmplifierSpecificationEvaluation:
        catalog = self.catalog(request.design_id)
        if request.expected_specification_registry_sha256 != catalog.registry_sha256:
            raise InvalidInputError("Specification catalog changed")
        source = await self.sweeps.result(
            AmplifierQuery(
                design_id=request.design_id,
                sweep_id=request.sweep_id,
            )
        )
        if request.expected_sweep_result_sha256 != canonical_digest(source):
            raise InvalidInputError("Sweep source result changed")
        plan = AmplifierEnginePlan.model_validate(
            self.sweeps.engine.store.get(request.sweep_id)["plan"]
        )
        if plan.plan_hash != source.engine.plan_hash:
            raise RemoteFailureError("Sweep source journal binding changed")
        return evaluate_source(source, self.registry, plan.request.binding.measurement_id)
