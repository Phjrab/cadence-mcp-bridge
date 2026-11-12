"""Link independently planned candidate analyses using their retained identities."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.candidate_contracts import (
    CandidateBatchPlan,
    CandidateFixedEvidence,
    SuppliedValue,
)
from cadence_mcp_bridge.candidate_reports import (
    CandidateObservation,
    CandidateReportRow,
    CandidateStatus,
    compare_candidate_reports,
)
from cadence_mcp_bridge.domain_provisioning import _canonical, _closed_document
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_runtime import KIND
from cadence_mcp_bridge.operator_operations import ExplicitValue, OperationRejected
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest


class CandidateAnalysisManifest(VariableModel):
    """A local index of existing batch plans for one fixed source and candidate set."""

    batches: Annotated[tuple[CandidateBatchPlan, ...], Field(min_length=1, max_length=3)]

    @model_validator(mode="after")
    def same_candidates(self) -> Self:
        first = self.batches[0]
        seen_ids: set[str] = set()
        seen_analyses: set[str] = set()
        for batch in self.batches:
            analysis = batch.plans[0].analysis
            ids = {batch.request.batch_id, *(c.operation_id for c in batch.request.candidates)}
            if analysis in seen_analyses or ids & seen_ids:
                raise ValueError("distinct analyses and operation identities required")
            seen_analyses.add(analysis)
            seen_ids.update(ids)
            if _source_identity(batch) != _source_identity(first):
                raise ValueError("candidate source, model or runtime binding differs")
            if _candidate_values(batch) != _candidate_values(first):
                raise ValueError("complete candidate inventories differ across analyses")
        return self

    @property
    def manifest_sha256(self) -> str:
        return canonical_digest(self)

    @property
    def expected_executions(self) -> int:
        return sum(batch.expected_executions for batch in self.batches)

    @property
    def result_reservation_bytes(self) -> int:
        return sum(batch.result_reservation_bytes for batch in self.batches)


def _source_identity(batch: CandidateBatchPlan) -> tuple[object, ...]:
    child = batch.plans[0]
    evidence = batch.request.fixed_evidence
    return (
        child.resource_domain_sha256,
        child.ledger_ref,
        child.runner_sha256,
        child.environment_sha256,
        child.design_sha256,
        child.pdk_sha256,
        child.grant_sha256,
        child.request.design_id,
        evidence.source_revision_sha256,
        evidence.testbench_revision_sha256,
        evidence.source_baseline_sha256,
        evidence.design_profile_sha256,
        evidence.conditions.source_tree_sha256,
        evidence.conditions.model_file_sha256,
        evidence.variable_bindings,
        batch.varied_variables,
        batch.request.baseline_candidate_id,
    )


def _candidate_values(
    batch: CandidateBatchPlan,
) -> tuple[tuple[str, tuple[ExplicitValue, ...]], ...]:
    return tuple(
        (candidate.candidate_id, child.request.values)
        for candidate, child in zip(batch.request.candidates, batch.plans, strict=True)
    )


def validate_cross_analysis_conditions(
    manifest: CandidateAnalysisManifest,
    runtime_manifest: bytes,
    runtime_registration: bytes,
    *,
    analyses: frozenset[str],
) -> None:
    """Check shared circuit conditions against the existing hash-bound runtime assets."""
    manifest = CandidateAnalysisManifest.model_validate_json(manifest.model_dump_json())
    batches = {batch.plans[0].analysis: batch for batch in manifest.batches}
    if len(analyses) < 2 or analyses - batches.keys():
        raise OperationRejected("candidate_cross_analysis_inventory_invalid")
    first = manifest.batches[0].plans[0]
    try:
        _closed_document(runtime_manifest)
        _closed_document(runtime_registration)
        registration_sha = hashlib.sha256(runtime_registration).hexdigest()
        bundle = json.loads(runtime_manifest)
        registration = json.loads(runtime_registration)
        if (
            hashlib.sha256(runtime_manifest).hexdigest() != first.runner_sha256
            or bundle["schema_version"] != 3
            or bundle["kind"] != KIND
            or bundle["profile_sha256"] != first.environment_sha256
            or bundle["registration_sha256"] != registration_sha
            or bundle["files"]["registration.json"]
            != {
                "sha256": registration_sha,
                "bytes": len(runtime_registration),
            }
            or type(registration["schema_version"]) is not int
            or registration["schema_version"] != 1
            or (
                registration["environment_sha256"],
                registration["design_sha256"],
                registration["pdk_sha256"],
            )
            != (
                first.environment_sha256,
                first.design_sha256,
                first.pdk_sha256,
            )
        ):
            raise ValueError("runtime identity")
        routes = {(r["design_id"], r["analysis_id"]): r for r in registration["routes"]}
        if len(routes) != len(registration["routes"]):
            raise ValueError("duplicate runtime route")
    except (KeyError, TypeError, ValueError):
        raise OperationRejected("candidate_cross_analysis_runtime_binding_invalid") from None

    static_conditions = set()
    source_models = set()
    for analysis, batch in batches.items():
        if analysis not in analyses:
            continue
        child = batch.plans[0]
        request = child.request
        fixed = batch.request.fixed_evidence
        conditions = fixed.conditions
        try:
            route = routes[request.design_id, request.analysis_id]
            ade = AdeExecutionRegistration.model_validate_json(_canonical(route["ade"]))
            reader = GenericReaderRegistration.model_validate_json(_canonical(route["reader"]))
            if (
                (ade.design_id, ade.analysis_id, ade.design_profile_sha256)
                != (request.design_id, request.analysis_id, fixed.design_profile_sha256)
                or (reader.design_id, reader.analysis_id, reader.measurement_id)
                != (request.design_id, request.analysis_id, fixed.measurement_id)
                or reader.ade_registration_sha256 != canonical_digest(ade)
                or canonical_digest(reader) != fixed.reader_registration_sha256
                or ade.inputs != conditions.analysis_inputs
                or ade.source_tree_sha256 != conditions.source_tree_sha256
                or ade.ade_state_tree_sha256 != conditions.ade_state_tree_sha256
                or ade.static_statements_sha256 != conditions.static_statements_sha256
                or tuple(model.file_sha256 for model in ade.model_includes)
                != conditions.model_file_sha256
                or reader.transfer != conditions.transfer
            ):
                raise ValueError("route conditions")
            static_conditions.add(ade.static_statements_sha256)
            source_models.add(
                _canonical(
                    [
                        route["source_cell"],
                        [model.model_dump(mode="json") for model in ade.model_includes],
                        route["model_files"],
                    ]
                )
            )
        except (KeyError, TypeError, ValueError):
            raise OperationRejected("candidate_cross_analysis_route_binding_invalid") from None
    if len(static_conditions) != 1:
        raise OperationRejected("candidate_cross_analysis_static_conditions_mismatch")
    if len(source_models) != 1:
        raise OperationRejected("candidate_cross_analysis_source_or_model_mismatch")


class CandidateRevision(VariableModel):
    """Logical V/A candidate revision over a retained source and testbench revision."""

    design_id: LogicalId
    source_revision_sha256: Digest
    testbench_revision_sha256: Digest
    source_baseline_sha256: Digest
    source_tree_sha256: Digest
    values: tuple[ExplicitValue, ...]
    evidence_status: Literal["PLANNED_SOURCE_REFERENCE"] = "PLANNED_SOURCE_REFERENCE"

    @property
    def revision_sha256(self) -> str:
        return canonical_digest(self)


class CandidateAnalysisResult(VariableModel):
    analysis: Literal["dc", "ac", "tran"]
    analysis_id: LogicalId
    operation_id: OperationId
    plan_sha256: Digest
    batch_plan_sha256: Digest
    planned_evidence: CandidateFixedEvidence
    requested_values: tuple[SuppliedValue, ...]
    status: CandidateStatus | Literal["NOT_OBSERVED"]
    reason: str | None
    row: CandidateReportRow | None


class CandidateRevisionResult(VariableModel):
    candidate_id: LogicalId
    label: str
    revision: CandidateRevision
    revision_sha256: Digest
    analyses: tuple[CandidateAnalysisResult, ...]
    verification_at_read: Literal["LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"] = (
        "LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"
    )


def collect_candidate_analyses(
    manifest: CandidateAnalysisManifest,
    expected_manifest_sha256: str,
    observations: dict[str, tuple[CandidateObservation, ...]],
) -> tuple[CandidateRevisionResult, ...]:
    """Join existing captures by batch and candidate ID without contacting a provider."""
    manifest = CandidateAnalysisManifest.model_validate_json(manifest.model_dump_json())
    if expected_manifest_sha256 != manifest.manifest_sha256:
        raise OperationRejected("candidate_analysis_manifest_digest_mismatch")
    if observations.keys() - {batch.request.batch_id for batch in manifest.batches}:
        raise OperationRejected("candidate_analysis_observation_batch_unknown")

    first = manifest.batches[0]
    evidence = first.request.fixed_evidence
    analyses: dict[str, list[CandidateAnalysisResult]] = {
        candidate.candidate_id: [] for candidate in first.request.candidates
    }
    for batch in manifest.batches:
        captures = observations.get(batch.request.batch_id, ())
        captured_ids = {capture.candidate_id for capture in captures}
        comparison = compare_candidate_reports(
            batch,
            batch.plan_sha256,
            captures,
        )
        for child, row in zip(batch.plans, comparison.rows, strict=True):
            captured = row.candidate_id in captured_ids
            analyses[row.candidate_id].append(
                CandidateAnalysisResult(
                    analysis=child.analysis,
                    analysis_id=child.request.analysis_id,
                    operation_id=row.operation_id,
                    plan_sha256=row.plan_sha256,
                    batch_plan_sha256=batch.plan_sha256,
                    planned_evidence=batch.request.fixed_evidence,
                    requested_values=row.requested_values,
                    status=row.status if captured else "NOT_OBSERVED",
                    reason=row.reason if captured else "retained_observation_not_supplied",
                    row=row if captured else None,
                )
            )

    results = []
    for candidate, child in zip(first.request.candidates, first.plans, strict=True):
        revision = CandidateRevision(
            design_id=child.request.design_id,
            source_revision_sha256=evidence.source_revision_sha256,
            testbench_revision_sha256=evidence.testbench_revision_sha256,
            source_baseline_sha256=evidence.source_baseline_sha256,
            source_tree_sha256=evidence.conditions.source_tree_sha256,
            values=child.request.values,
        )
        results.append(
            CandidateRevisionResult(
                candidate_id=candidate.candidate_id,
                label=candidate.label,
                revision=revision,
                revision_sha256=revision.revision_sha256,
                analyses=tuple(analyses[candidate.candidate_id]),
            )
        )
    return tuple(results)
