"""Explicit operator candidate workflow; importing or planning never dispatches."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field, TypeAdapter, model_validator

from cadence_mcp_bridge.candidate_contracts import (
    CandidateBatchPlan,
    CandidateBatchRequest,
    prepare_candidate_plan,
)
from cadence_mcp_bridge.candidate_reports import (
    CandidateComparison,
    CandidateObservation,
    candidate_metric_delta,
    compare_candidate_reports,
    render_candidate_csv,
)
from cadence_mcp_bridge.domain_provisioning import _closed_document
from cadence_mcp_bridge.errors import BridgeError
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import OperationRejected, load_grant
from cadence_mcp_bridge.parameter_changes import AmplifierPm0InputEvidence
from cadence_mcp_bridge.result_reports import _publish_report
from cadence_mcp_bridge.result_reports import capture as capture_report
from cadence_mcp_bridge.runtime_context import ExecutionContext, load_runtime
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel, canonical_digest

if TYPE_CHECKING:
    from cadence_mcp_bridge.candidate_execution import (
        PmosDcOperation,
        PmosDefaultChangeResult,
        PmosDefaultChangeService,
    )

DOCUMENT_LIMIT = 1048576
AMPLIFIER_EVIDENCE = ("dc-result", "dc-intent", "ac-result", "ac-intent", "specification")
CHANGE_READBACK_STAGES = ("baseline", "reopened", "netlist")
OBSERVATIONS: TypeAdapter[tuple[CandidateObservation, ...]] = TypeAdapter(
    Annotated[tuple[CandidateObservation, ...], Field(max_length=16)]
)


class _PinnedComparisonFile(VariableModel):
    path: Path
    sha256: Digest


class _RetainedAnalysisOperation(VariableModel):
    operation_id: OperationId
    plan_sha256: Digest
    terminal_sha256: Digest | None = None
    journal: _PinnedComparisonFile | None = None
    runtime_manifest: _PinnedComparisonFile
    runtime_registration: _PinnedComparisonFile
    design_registry: _PinnedComparisonFile
    report: _PinnedComparisonFile | None = None


class _PmosDcSide(_RetainedAnalysisOperation):
    journal: _PinnedComparisonFile = Field()
    terminal_sha256: Digest = Field()
    report: _PinnedComparisonFile = Field()


class _PmosDcComparisonRequest(VariableModel):
    change_plan: _PinnedComparisonFile
    change_plan_sha256: Digest
    readback: _PinnedComparisonFile
    baseline_input: _PinnedComparisonFile
    candidate_input: _PinnedComparisonFile
    copy_receipt: _PinnedComparisonFile
    copy_scope_sha256: Digest
    copy_id: OperationId
    reopen_receipt_sha256: Digest
    baseline: _PmosDcSide
    candidate: _PmosDcSide


class _AmplifierWidthChild(_RetainedAnalysisOperation):
    effective_input: _PinnedComparisonFile
    execution_plan: _PinnedComparisonFile | None = None

    @model_validator(mode="after")
    def retained_source(self) -> _AmplifierWidthChild:
        if (self.journal is None) == (self.execution_plan is None):
            raise ValueError("provide one retained journal or unobserved execution plan")
        if self.journal is None and (self.report is not None or self.terminal_sha256 is not None):
            raise ValueError("terminal evidence requires an original journal")
        if self.report is not None and self.terminal_sha256 is None:
            raise ValueError("a retained report requires a terminal pin")
        return self


class _AmplifierWidthSide(VariableModel):
    baseline_result: _PinnedComparisonFile
    baseline_result_sha256: Digest
    baseline_input: _PinnedComparisonFile
    child: _AmplifierWidthChild | None = None


class _AmplifierWidthComparisonRequest(VariableModel):
    change_plan: _PinnedComparisonFile
    change_plan_sha256: Digest
    readback: _PinnedComparisonFile
    baseline_input: _PinnedComparisonFile
    candidate_input: _PinnedComparisonFile
    registration_evidence: _PinnedComparisonFile
    dc: _AmplifierWidthSide
    ac: _AmplifierWidthSide


class _AmplifierPm0ObservationRequest(VariableModel):
    baseline_input: Path
    child_input: Path
    baseline: AmplifierPm0InputEvidence
    child: AmplifierPm0InputEvidence
    diagnostic_receipt_sha256: Digest
    footprint_receipt_sha256: Digest
    dfm_evidence_sha256: Digest
    baseline_effective_dfm: Literal["Minimum"]
    child_effective_dfm: Literal["DFM"]


def add_candidates_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    parser = subparsers.add_parser(
        "operator-candidates",
        help="Experimental registered V/A candidates and retained reports.",
    )
    actions = parser.add_subparsers(dest="candidates_action", required=True)
    schema = actions.add_parser("schema")
    schema.add_argument(
        "--action",
        choices=("select", "amplifier-select", "amplifier-width-compare", "observe-amplifier-pm0"),
        dest="schema_action",
    )
    for name in ("plan", "submit", "advance", "status", "result", "capture"):
        action = actions.add_parser(name)
        action.add_argument("--settings", type=Path, required=True)
        action.add_argument("--context", required=True)
        if name == "plan":
            action.add_argument("--request", type=Path, required=True)
            action.add_argument("--output", type=Path, required=True)
        else:
            action.add_argument("--plan", type=Path, required=True)
            action.add_argument("--expected-plan-sha256", required=True)
        if name == "capture":
            action.add_argument("--output", type=Path, required=True)
        if name in ("submit", "advance"):
            action.add_argument("--experimental-candidates", action="store_true", required=True)
    comparison = actions.add_parser(
        "compare", help="Compare local retained records; no VM contact."
    )
    comparison.add_argument("--plan", type=Path, required=True)
    comparison.add_argument("--expected-plan-sha256", required=True)
    comparison.add_argument("--observations", type=Path, required=True)
    comparison.add_argument("--output", type=Path, required=True)
    csv = actions.add_parser("csv", help="Export an existing comparison as BOM UTF-8 CSV.")
    csv.add_argument("--comparison", type=Path, required=True)
    csv.add_argument("--output", type=Path, required=True)
    selection = actions.add_parser("select", help="Evaluate explicit goals on a local comparison.")
    selection.add_argument("--comparison", type=Path, required=True)
    selection.add_argument("--expected-comparison-sha256", required=True)
    selection.add_argument("--request", type=Path, required=True)
    selection.add_argument("--output", type=Path, required=True)
    amplifier = actions.add_parser(
        "amplifier-select",
        help="Evaluate retained finite-grid amplifier results locally.",
    )
    for name in AMPLIFIER_EVIDENCE:
        amplifier.add_argument(f"--{name}", nargs=2, metavar=("FILE", "SHA256"), required=True)
    amplifier.add_argument("--request", type=Path, required=True)
    amplifier.add_argument("--output", type=Path, required=True)
    readback = actions.add_parser(
        "verify-change-readback", help="Compare local parameter change readback evidence."
    )
    readback.add_argument("--plan", type=Path, required=True)
    readback.add_argument("--expected-plan-sha256", required=True)
    for stage in CHANGE_READBACK_STAGES:
        readback.add_argument(f"--{stage}", nargs=2, metavar=("FILE", "SHA256"))
    readback.add_argument("--output", type=Path, required=True)
    pmos = actions.add_parser("pmos-dc-compare", help="Compare two retained PMOS DC results.")
    pmos.add_argument("--request", nargs=2, metavar=("FILE", "SHA256"), required=True)
    pmos.add_argument("--output", type=Path, required=True)
    amplifier_width = actions.add_parser(
        "amplifier-width-compare", help="Compare retained amplifier width DC and AC evidence."
    )
    amplifier_width.add_argument("--request", nargs=2, metavar=("FILE", "SHA256"), required=True)
    amplifier_width.add_argument("--output", type=Path, required=True)
    pm0_observation = actions.add_parser(
        "observe-amplifier-pm0", help="Observe retained PM0 netlist inputs without qualification."
    )
    pm0_observation.add_argument("--request", nargs=2, metavar=("FILE", "SHA256"), required=True)
    pm0_observation.add_argument("--output", type=Path, required=True)
    pmos_apply = actions.add_parser(
        "apply-pmos-default", help="Apply or read back one registered PMOS default change."
    )
    pmos_apply.add_argument("--settings", type=Path, required=True)
    pmos_apply.add_argument("--context", required=True)
    pmos_apply.add_argument("--request", type=Path, required=True)
    compose = actions.add_parser("compose", help="Group existing local analysis plans.")
    compose.add_argument(
        "--batch",
        action="append",
        nargs=2,
        metavar=("PLAN", "EXPECTED_PLAN_SHA256"),
        required=True,
    )
    compose.add_argument("--output", type=Path, required=True)
    collect = actions.add_parser(
        "collect", help="Associate local captures with an analysis manifest."
    )
    collect.add_argument("--manifest", type=Path, required=True)
    collect.add_argument("--expected-manifest-sha256", required=True)
    collect.add_argument(
        "--capture",
        action="append",
        nargs=2,
        metavar=("BATCH_ID", "OBSERVATIONS_FILE"),
        default=[],
    )
    collect.add_argument("--output", type=Path, required=True)


def _read_candidate_bytes(
    path: Path, *, expected_sha256: str | None = None, limit: int = DOCUMENT_LIMIT
) -> bytes:
    """Read one bounded regular local file with an optional exact raw digest."""
    path = _local_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
        raise OperationRejected("candidate_document_invalid")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise OperationRejected("candidate_document_changed")
        raw = stream.read(limit + 1)
    after = path.stat()

    def signature(info: os.stat_result) -> tuple[int, ...]:
        return (
            info.st_dev,
            info.st_ino,
            info.st_nlink,
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
        )

    if signature(before) != signature(opened) or signature(before) != signature(after):
        raise OperationRejected("candidate_document_changed")
    if len(raw) > limit:
        raise OperationRejected("candidate_document_invalid")
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise OperationRejected("candidate_document_digest_mismatch")
    return raw


def read_candidate_document(path: Path, *, expected_sha256: str | None = None) -> bytes:
    """Bound a regular local content record, without claiming remote authenticity."""
    raw = _read_candidate_bytes(path, expected_sha256=expected_sha256)
    _closed_document(raw, max_bytes=DOCUMENT_LIMIT)
    return raw


def dispatch_pmos_default_change(
    path: Path, service: PmosDefaultChangeService
) -> PmosDefaultChangeResult:
    """Parse and dispatch once through a service supplied by the operator adapter."""
    from cadence_mcp_bridge.candidate_execution import (
        PmosDefaultChangeRequest,
        PmosDefaultChangeResult,
    )

    request = PmosDefaultChangeRequest.model_validate_json(read_candidate_document(path))
    returned = service.apply(request)
    result = PmosDefaultChangeResult.model_validate_json(returned.model_dump_json(warnings="error"))
    if (result.operation_id, result.plan_sha256, result.scope_sha256) != (
        request.operation_id,
        request.expected_plan_sha256,
        request.expected_scope_sha256,
    ):
        raise OperationRejected("pmos_default_change_identity_mismatch")
    return result


def _output(path: Path, reserved: set[Path]) -> Path:
    path = _local_path(path)
    if path in reserved or path.exists() or not path.parent.is_dir():
        raise OperationRejected("candidate_new_unreserved_output_required")
    return path


def _export(path: Path, raw: bytes) -> str:
    if len(raw) > DOCUMENT_LIMIT:
        raise OperationRejected("candidate_output_capacity")
    path = _output(path, set())
    descriptor, name = tempfile.mkstemp(
        prefix=".cadence-candidates-", suffix=".pending", dir=path.parent
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    # Complete-file publication is exclusive; retain interrupted candidates as evidence.
    _publish_report(Path(name), path)
    return hashlib.sha256(raw).hexdigest()


def _reserved(settings: Path, contexts: tuple[ExecutionContext, ...]) -> set[Path]:
    paths = {_local_path(settings)}
    for context in contexts:
        paths.add(_local_path(context.lock_path))
        for name in type(context.binding).model_fields:
            value = getattr(context.binding, name)
            if isinstance(value, Path):
                paths.add(_local_path(value))
        for path in (context.binding.analysis_journal, context.binding.sweep_journal):
            path = _local_path(path)
            paths.update(
                path.with_name(path.name + suffix) for suffix in ("-wal", "-shm", "-journal")
            )
    return paths


def _load_plan(path: Path, expected: str) -> CandidateBatchPlan:
    plan = CandidateBatchPlan.model_validate_json(read_candidate_document(path))
    if plan.plan_sha256 != expected:
        raise OperationRejected("candidate_plan_digest_mismatch")
    return plan


def _compose(arguments: argparse.Namespace) -> dict[str, Any]:
    from cadence_mcp_bridge.candidate_execution import CandidateAnalysisManifest

    if len(arguments.batch) > 3:
        raise OperationRejected("candidate_analysis_batch_limit")
    inputs = [(Path(path), expected) for path, expected in arguments.batch]
    output = _output(arguments.output, {_local_path(path) for path, _ in inputs})
    manifest = CandidateAnalysisManifest(
        batches=tuple(_load_plan(path, expected) for path, expected in inputs),
    )
    return {
        "status": "CANDIDATE_ANALYSIS_MANIFEST_EXPORTED",
        "manifest_sha256": manifest.manifest_sha256,
        "file_sha256": _export(output, manifest.model_dump_json().encode("utf-8")),
        "expected_executions": manifest.expected_executions,
        "planned_result_reservation_bytes": manifest.result_reservation_bytes,
    }


def _collect(arguments: argparse.Namespace) -> dict[str, Any]:
    from cadence_mcp_bridge.candidate_execution import (
        CandidateAnalysisManifest,
        CandidateRevisionResult,
        collect_candidate_analyses,
    )

    captures = {batch_id: Path(path) for batch_id, path in arguments.capture}
    if len(captures) != len(arguments.capture) or len(captures) > 3:
        raise OperationRejected("candidate_analysis_capture_ids_invalid")
    output = _output(
        arguments.output,
        {_local_path(path) for path in (arguments.manifest, *captures.values())},
    )
    manifest = CandidateAnalysisManifest.model_validate_json(
        read_candidate_document(arguments.manifest)
    )
    results = collect_candidate_analyses(
        manifest,
        arguments.expected_manifest_sha256,
        {
            key: OBSERVATIONS.validate_json(read_candidate_document(path))
            for key, path in captures.items()
        },
    )
    raw = TypeAdapter(tuple[CandidateRevisionResult, ...]).dump_json(results)
    return {
        "status": "CANDIDATE_ANALYSIS_RESULTS_EXPORTED",
        "manifest_sha256": manifest.manifest_sha256,
        "file_sha256": _export(output, raw),
        "candidate_count": len(results),
    }


def _amplifier_select(arguments: argparse.Namespace) -> dict[str, Any]:
    from cadence_mcp_bridge.amplifier_candidate_selection import (
        AmplifierCandidateSelectionRequest,
        select_retained_amplifier_candidates,
    )
    from cadence_mcp_bridge.amplifier_specifications import (
        AmplifierEvaluationQuery,
        AmplifierSpecificationEvaluation,
    )
    from cadence_mcp_bridge.amplifier_sweeps import (
        AmplifierPrepared,
        AmplifierQuery,
        AmplifierSubmission,
        AmplifierSweepResult,
        make_amplifier_plan,
    )

    inputs = {name: getattr(arguments, name.replace("-", "_")) for name in AMPLIFIER_EVIDENCE}
    output = _output(
        arguments.output,
        {_local_path(Path(path)) for path, _ in inputs.values()} | {_local_path(arguments.request)},
    )
    documents = {
        name: json.loads(read_candidate_document(Path(path), expected_sha256=digest))
        for name, (path, digest) in inputs.items()
    }
    request = AmplifierCandidateSelectionRequest.model_validate_json(
        read_candidate_document(arguments.request)
    )
    sources = {}
    evaluations = {}
    for mode in ("dc", "ac"):
        capture = documents[f"{mode}-result"]
        intent = documents[f"{mode}-intent"]
        check = documents["specification"]["outputs"][mode]
        source = AmplifierSweepResult.model_validate_json(json.dumps(capture["result"]))
        query = AmplifierQuery.model_validate_json(json.dumps(capture["query"]))
        submission = AmplifierSubmission.model_validate_json(json.dumps(intent["submission"]))
        prepared = AmplifierPrepared.model_validate_json(json.dumps(intent["prepared"]))
        spec_query = AmplifierEvaluationQuery.model_validate_json(json.dumps(check["request"]))
        evaluation = AmplifierSpecificationEvaluation.model_validate_json(
            json.dumps(check["evaluation"])
        )
        if (
            query.sweep_id != source.engine.sweep_id
            or submission.experiment_key != source.engine.experiment_key
            or prepared.engine_plan != make_amplifier_plan(submission.request)
            or submission.expected_plan_hash != prepared.engine_plan.plan_hash
            or submission.expected_plan_hash != source.engine.plan_hash
            or prepared.definition != source.definition
            or prepared.definition_sha256 != source.definition_sha256
            or spec_query.sweep_id != query.sweep_id
            or spec_query.expected_sweep_result_sha256 != evaluation.source_result_sha256
            or spec_query.expected_specification_registry_sha256
            != evaluation.specification_registry_sha256
            or evaluation.source != source
        ):
            raise OperationRejected("amplifier_candidate_retained_identity_mismatch")
        sources[mode] = source
        evaluations[mode] = evaluation
    selection = select_retained_amplifier_candidates(
        sources["dc"],
        sources["ac"],
        expected_dc_sha256=evaluations["dc"].source_result_sha256,
        expected_ac_sha256=evaluations["ac"].source_result_sha256,
        request=request,
    )
    if selection.dc != evaluations["dc"] or selection.ac != evaluations["ac"]:
        raise OperationRejected("amplifier_candidate_retained_evaluation_mismatch")
    return {
        "status": "AMPLIFIER_CANDIDATE_SELECTION_EXPORTED",
        "selection_status": selection.status,
        "selected_candidate_id": selection.selected_candidate_id,
        "file_sha256": _export(output, selection.model_dump_json().encode("utf-8")),
        "new_simulations": selection.new_simulations,
        "new_extractions": selection.new_extractions,
        "new_reservations": selection.new_reservations,
    }


def _verify_change_readback(arguments: argparse.Namespace) -> dict[str, Any]:
    from cadence_mcp_bridge.parameter_changes import (
        ChangePlan,
        ChangeReadback,
        Readback,
        verify_change_readback,
    )

    inputs = {
        stage: (Path(pair[0]), pair[1])
        for stage in CHANGE_READBACK_STAGES
        if (pair := getattr(arguments, stage)) is not None
    }
    output = _output(
        arguments.output,
        {_local_path(arguments.plan)} | {_local_path(path) for path, _ in inputs.values()},
    )
    plan = ChangePlan.model_validate_json(read_candidate_document(arguments.plan))
    if plan.plan_sha256 != arguments.expected_plan_sha256:
        raise OperationRejected("change_plan_digest_mismatch")
    stages = {
        stage: Readback.model_validate_json(read_candidate_document(path, expected_sha256=digest))
        for stage, (path, digest) in inputs.items()
    }
    result = verify_change_readback(
        plan,
        baseline=stages.get("baseline"),
        reopened=stages.get("reopened"),
        netlist=stages.get("netlist"),
    )
    file_sha256 = _export(output, result.model_dump_json().encode("utf-8"))
    saved = ChangeReadback.model_validate_json(
        read_candidate_document(output, expected_sha256=file_sha256)
    )
    if saved != result:
        raise OperationRejected("change_readback_output_mismatch")
    return {
        "status": "CHANGE_READBACK_EXPORTED",
        "readback_status": saved.status,
        "reason": saved.reason,
        "plan_sha256": saved.plan_sha256,
        "file_sha256": file_sha256,
        "provenance": saved.provenance,
        "execution_authorized": saved.execution_authorized,
        "new_simulations": 0,
        "new_extractions": 0,
        "new_reservations": 0,
    }


def _comparison_document(source: _PinnedComparisonFile) -> bytes:
    return read_candidate_document(source.path, expected_sha256=source.sha256)


def _comparison_bytes(source: _PinnedComparisonFile) -> bytes:
    return _read_candidate_bytes(source.path, expected_sha256=source.sha256)


def _retained_analysis_operation(side: _RetainedAnalysisOperation) -> PmosDcOperation:
    from cadence_mcp_bridge.analysis_store import MAX_BYTES, AnalysisStore
    from cadence_mcp_bridge.candidate_execution import PmosDcOperation
    from cadence_mcp_bridge.native_service import NativeOperationQuery
    from cadence_mcp_bridge.operator_operations import OperationPlan

    query = NativeOperationQuery(
        operation_id=side.operation_id,
        expected_plan_sha256=side.plan_sha256,
    )
    record = None
    if side.journal is not None:
        path, digest = side.journal.path, side.journal.sha256
        _read_candidate_bytes(path, expected_sha256=digest, limit=MAX_BYTES)
        with AnalysisStore(path).connection(create=False, read_only=True) as connection:
            record = AnalysisStore._read_operation(connection, query.operation_id)
        _read_candidate_bytes(path, expected_sha256=digest, limit=MAX_BYTES)
        plan = record.plan
    else:
        if not isinstance(side, _AmplifierWidthChild) or side.execution_plan is None:
            raise OperationRejected("candidate_retained_plan_required")
        plan = OperationPlan.model_validate_json(_comparison_document(side.execution_plan))
    report = side.report
    return PmosDcOperation(
        query=query,
        plan=plan,
        record=record,
        report=None if report is None else _comparison_document(report),
        expected_report_sha256=None if report is None else report.sha256,
        expected_terminal_sha256=side.terminal_sha256,
        runtime_manifest=_comparison_document(side.runtime_manifest),
        runtime_registration=_comparison_document(side.runtime_registration),
        design_registry=_comparison_document(side.design_registry),
    )


def _retained_analysis_paths(side: _RetainedAnalysisOperation) -> set[Path]:
    paths = {
        _local_path(source.path)
        for source in (
            side.journal,
            side.runtime_manifest,
            side.runtime_registration,
            side.design_registry,
            side.report,
        )
        if source is not None
    }
    if side.journal is not None:
        journal = _local_path(side.journal.path)
        paths.update(journal.with_name(journal.name + s) for s in ("-wal", "-shm", "-journal"))
    return paths


def _pmos_dc_compare(arguments: argparse.Namespace) -> dict[str, Any]:
    from cadence_mcp_bridge.candidate_execution import associate_pmos_dc_pair
    from cadence_mcp_bridge.parameter_changes import ChangePlan, ChangeReadback

    request_path, request_sha256 = arguments.request
    request_path = _local_path(Path(request_path))
    request = _PmosDcComparisonRequest.model_validate_json(
        read_candidate_document(request_path, expected_sha256=request_sha256)
    )
    common = (
        request.change_plan,
        request.readback,
        request.baseline_input,
        request.candidate_input,
        request.copy_receipt,
    )
    reserved = {request_path} | {_local_path(source.path) for source in common}
    reserved.update(_retained_analysis_paths(request.baseline))
    reserved.update(_retained_analysis_paths(request.candidate))
    output = _output(arguments.output, reserved)
    pair = associate_pmos_dc_pair(
        ChangePlan.model_validate_json(_comparison_document(request.change_plan)),
        ChangeReadback.model_validate_json(_comparison_document(request.readback)),
        expected_plan_sha256=request.change_plan_sha256,
        baseline_input=_comparison_bytes(request.baseline_input),
        candidate_input=_comparison_bytes(request.candidate_input),
        copy_receipt=_comparison_document(request.copy_receipt),
        expected_copy_receipt_sha256=request.copy_receipt.sha256,
        expected_copy_scope_sha256=request.copy_scope_sha256,
        expected_copy_id=request.copy_id,
        expected_reopen_receipt_sha256=request.reopen_receipt_sha256,
        baseline=_retained_analysis_operation(request.baseline),
        candidate=_retained_analysis_operation(request.candidate),
    )
    deltas = []
    for metric in pair.metrics:
        baseline_value = None if metric.baseline is None else metric.baseline.value
        candidate_value = None if metric.candidate is None else metric.candidate.value
        absolute, relative, reason = candidate_metric_delta(
            candidate_value,
            baseline_value,
            baseline_present=metric.baseline is not None,
        )
        deltas.append(
            {
                "signal_id": metric.signal_id,
                "absolute_delta": absolute,
                "relative_delta": relative,
                "reason": reason,
            }
        )
    raw = json.dumps(
        {
            "association": pair.model_dump(mode="json"),
            "request_sha256": request_sha256,
            "baseline_report_sha256": request.baseline.report.sha256,
            "candidate_report_sha256": request.candidate.report.sha256,
            "deltas": deltas,
            "selected_candidate_id": None,
        },
        sort_keys=True,
        allow_nan=False,
    ).encode()
    file_sha256 = _export(output, raw)
    read_candidate_document(output, expected_sha256=file_sha256)
    return {
        "status": "PMOS_DC_COMPARISON_EXPORTED",
        "file_sha256": file_sha256,
        "goals": pair.goals,
        "selected_candidate_id": None,
        "execution_authorized": False,
        "new_simulations": 0,
        "new_extractions": 0,
        "new_reservations": 0,
    }


def _amplifier_width_compare(arguments: argparse.Namespace) -> dict[str, Any]:
    from cadence_mcp_bridge.amplifier_sweeps import AmplifierQuery, AmplifierSweepResult
    from cadence_mcp_bridge.candidate_execution import (
        AmplifierWidthAnalysis,
        AmplifierWidthPair,
        associate_amplifier_width_pair,
    )
    from cadence_mcp_bridge.parameter_changes import ChangePlan, ChangeReadback

    request_path, request_sha256 = arguments.request
    request_path = _local_path(Path(request_path))
    request = _AmplifierWidthComparisonRequest.model_validate_json(
        read_candidate_document(request_path, expected_sha256=request_sha256)
    )
    common = (
        request.change_plan,
        request.readback,
        request.baseline_input,
        request.candidate_input,
        request.registration_evidence,
    )
    reserved = {request_path} | {_local_path(source.path) for source in common}
    for side in (request.dc, request.ac):
        reserved.update(
            _local_path(source.path)
            for source in (
                side.baseline_result,
                side.baseline_input,
            )
        )
        if side.child is not None:
            reserved.update(_retained_analysis_paths(side.child))
            reserved.add(_local_path(side.child.effective_input.path))
            if side.child.execution_plan is not None:
                reserved.add(_local_path(side.child.execution_plan.path))
    output = _output(arguments.output, reserved)

    def analysis(side: _AmplifierWidthSide) -> AmplifierWidthAnalysis:
        capture = json.loads(_comparison_document(side.baseline_result))
        source = AmplifierSweepResult.model_validate_json(json.dumps(capture["result"]))
        query = AmplifierQuery.model_validate_json(json.dumps(capture["query"]))
        if query.sweep_id != source.engine.sweep_id:
            raise OperationRejected("amplifier_candidate_retained_identity_mismatch")
        child = side.child
        return AmplifierWidthAnalysis(
            baseline=source,
            expected_baseline_sha256=side.baseline_result_sha256,
            baseline_input=_comparison_bytes(side.baseline_input),
            child=None if child is None else _retained_analysis_operation(child),
            child_input=None if child is None else _comparison_bytes(child.effective_input),
        )

    plan = ChangePlan.model_validate_json(_comparison_document(request.change_plan))
    pair = associate_amplifier_width_pair(
        plan,
        ChangeReadback.model_validate_json(_comparison_document(request.readback)),
        expected_plan_sha256=request.change_plan_sha256,
        baseline_input=_comparison_bytes(request.baseline_input),
        candidate_input=_comparison_bytes(request.candidate_input),
        registration_evidence=_comparison_document(request.registration_evidence),
        expected_registration_sha256=request.registration_evidence.sha256,
        dc=analysis(request.dc),
        ac=analysis(request.ac),
    )
    deltas = {}
    for row in (pair.dc, pair.ac):
        absolute, _, reason = candidate_metric_delta(
            row.child_value,
            row.baseline_value,
            baseline_present=True,
        )
        deltas[row.analysis] = {
            "absolute_delta": absolute,
            "reason": "available" if absolute is not None else row.reason or reason,
        }
    raw = json.dumps(
        {
            "association": pair.model_dump(mode="json"),
            "requested_width": plan.requested.model_dump(mode="json"),
            "request_sha256": request_sha256,
            "deltas": deltas,
            "selected_candidate_id": None,
        },
        sort_keys=True,
        allow_nan=False,
    ).encode()
    file_sha256 = _export(output, raw)
    saved = json.loads(read_candidate_document(output, expected_sha256=file_sha256))
    if AmplifierWidthPair.model_validate_json(json.dumps(saved["association"])) != pair:
        raise OperationRejected("amplifier_width_comparison_output_mismatch")
    return {
        "status": "AMPLIFIER_WIDTH_COMPARISON_EXPORTED",
        "file_sha256": file_sha256,
        "goals": pair.goals,
        "selected_candidate_id": None,
        "execution_authorized": pair.execution_authorized,
        "new_simulations": 0,
        "new_extractions": 0,
        "new_reservations": 0,
    }


def _observe_amplifier_pm0(arguments: argparse.Namespace) -> dict[str, Any]:
    from cadence_mcp_bridge.parameter_changes import (
        AmplifierPm0InputObservation,
        observe_amplifier_pm0_input,
    )

    path, digest = arguments.request
    request_path = _local_path(Path(path))
    request = _AmplifierPm0ObservationRequest.model_validate_json(
        read_candidate_document(request_path, expected_sha256=digest)
    )
    baseline_input = _local_path(request.baseline_input)
    child_input = _local_path(request.child_input)
    output = _output(arguments.output, {request_path, baseline_input, child_input})
    observation = observe_amplifier_pm0_input(
        _read_candidate_bytes(baseline_input, expected_sha256=request.baseline.netlist_sha256),
        _read_candidate_bytes(child_input, expected_sha256=request.child.netlist_sha256),
        baseline=request.baseline,
        child=request.child,
        diagnostic_receipt_sha256=request.diagnostic_receipt_sha256,
        footprint_receipt_sha256=request.footprint_receipt_sha256,
        dfm_evidence_sha256=request.dfm_evidence_sha256,
        baseline_effective_dfm=request.baseline_effective_dfm,
        child_effective_dfm=request.child_effective_dfm,
    )
    file_sha256 = _export(output, observation.model_dump_json().encode("utf-8"))
    saved = AmplifierPm0InputObservation.model_validate_json(
        read_candidate_document(output, expected_sha256=file_sha256)
    )
    if saved != observation:
        raise OperationRejected("amplifier_pm0_observation_output_mismatch")
    return {
        "status": saved.status,
        "scope": saved.scope,
        "oa_footprint": saved.oa_footprint,
        "oa_change_status": saved.oa_change_status,
        "receipt_authentication": saved.receipt_authentication,
        "execution_authorized": saved.execution_authorized,
        "admission_authorized": saved.admission_authorized,
        "selection_authorized": saved.selection_authorized,
        "file_sha256": file_sha256,
    }


def candidates_cli(arguments: argparse.Namespace) -> int:
    remote_contact: bool | None = False
    action = arguments.candidates_action
    try:
        if action == "schema":
            result: dict[str, Any] = {
                "request_schema": CandidateBatchRequest.model_json_schema(),
                "observations_schema": OBSERVATIONS.json_schema(),
                "supported_dimensions": ["qualified_owned_copy_V", "qualified_owned_copy_A"],
                "wl": "UNSUPPORTED",
                "waveforms": "UNSUPPORTED_RETAINED_SCALARS_ONLY",
            }
            if arguments.schema_action == "select":
                from cadence_mcp_bridge.candidate_selection import CandidateSelectionRequest

                result = {"request_schema": CandidateSelectionRequest.model_json_schema()}
            elif arguments.schema_action == "amplifier-select":
                from cadence_mcp_bridge.amplifier_candidate_selection import (
                    AmplifierCandidateSelectionRequest,
                )

                result = {"request_schema": AmplifierCandidateSelectionRequest.model_json_schema()}
            elif arguments.schema_action == "amplifier-width-compare":
                result = {"request_schema": _AmplifierWidthComparisonRequest.model_json_schema()}
            elif arguments.schema_action == "observe-amplifier-pm0":
                result = {"request_schema": _AmplifierPm0ObservationRequest.model_json_schema()}
        elif action in ("compare", "csv"):
            inputs = {
                _local_path(getattr(arguments, name))
                for name in (("plan", "observations") if action == "compare" else ("comparison",))
            }
            output = _output(arguments.output, inputs)
            if action == "compare":
                plan = _load_plan(arguments.plan, arguments.expected_plan_sha256)
                observations = OBSERVATIONS.validate_json(
                    read_candidate_document(arguments.observations)
                )
                comparison = compare_candidate_reports(
                    plan, arguments.expected_plan_sha256, observations
                )
                raw = comparison.model_dump_json().encode("utf-8")
            else:
                comparison = CandidateComparison.model_validate_json(
                    read_candidate_document(arguments.comparison)
                )
                raw = render_candidate_csv(comparison)
            result = {
                "status": "CANDIDATE_COMPARISON_EXPORTED"
                if action == "compare"
                else "CANDIDATE_CSV_EXPORTED",
                "file_sha256": _export(output, raw),
                "candidate_count": len(comparison.rows),
                "verification_at_read": comparison.verification_at_read,
                "new_simulations": 0,
                "new_extractions": 0,
                "new_reservations": 0,
            }
            if action == "compare":
                result["comparison_sha256"] = canonical_digest(comparison)
        elif action == "select":
            from cadence_mcp_bridge.candidate_selection import (
                CandidateSelectionRequest,
                select_candidates,
            )

            output = _output(
                arguments.output,
                {_local_path(arguments.comparison), _local_path(arguments.request)},
            )
            comparison = CandidateComparison.model_validate_json(
                read_candidate_document(arguments.comparison)
            )
            selection_request = CandidateSelectionRequest.model_validate_json(
                read_candidate_document(arguments.request)
            )
            selection = select_candidates(
                comparison,
                arguments.expected_comparison_sha256,
                selection_request,
            )
            result = {
                "status": "CANDIDATE_SELECTION_EXPORTED",
                "selection_status": selection.status,
                "selected_candidate_id": selection.selected_candidate_id,
                "file_sha256": _export(output, selection.model_dump_json().encode("utf-8")),
                "new_simulations": 0,
                "new_extractions": 0,
                "new_reservations": 0,
            }
        elif action in ("compose", "collect"):
            result = _compose(arguments) if action == "compose" else _collect(arguments)
            result.update(new_simulations=0, new_extractions=0, new_reservations=0)
        elif action == "amplifier-select":
            result = _amplifier_select(arguments)
        elif action == "verify-change-readback":
            result = _verify_change_readback(arguments)
        elif action == "pmos-dc-compare":
            result = _pmos_dc_compare(arguments)
        elif action == "amplifier-width-compare":
            result = _amplifier_width_compare(arguments)
        elif action == "observe-amplifier-pm0":
            result = _observe_amplifier_pm0(arguments)
        else:
            contexts = load_runtime(_local_path(arguments.settings))
            context = next((c for c in contexts if c.binding.context_id == arguments.context), None)
            if context is None:
                raise OperationRejected("candidate_context_required")
            if action == "apply-pmos-default":
                from cadence_mcp_bridge.pmos_default_service import registered_pmos_default_change

                service = registered_pmos_default_change(context)
                remote_contact = None  # A failure after entering the adapter may follow dispatch.
                receipt = dispatch_pmos_default_change(arguments.request, service)
                remote_contact = receipt.dispatched_this_call
                result = receipt.model_dump(mode="json")
            elif action == "plan":
                output = _output(
                    arguments.output,
                    _reserved(arguments.settings, contexts)
                    | {
                        _local_path(arguments.request),
                    },
                )
                binding = context.binding
                if binding.operator_grant is None or binding.operator_grant_sha256 is None:
                    raise OperationRejected("candidate_existing_grant_required")
                grant, digest = load_grant(binding.operator_grant, binding.operator_grant_sha256)
                request = CandidateBatchRequest.model_validate_json(
                    read_candidate_document(arguments.request)
                )
                plan = prepare_candidate_plan(context, grant, digest, request, int(time.time()))
                result = {
                    "status": "LOCAL_CANDIDATE_PLAN_PREPARED_NOT_ADMITTED",
                    "plan_sha256": plan.plan_sha256,
                    "plan": plan.model_dump(mode="json"),
                    "file_sha256": _export(output, plan.model_dump_json().encode("utf-8")),
                    "new_simulations": 0,
                    "new_reservations": 0,
                    "admission_created": False,
                }
            else:
                from cadence_mcp_bridge.candidate_batches import (
                    CandidateBatchQuery,
                    CandidateBatchSubmission,
                    CandidateBatchSupervisor,
                )
                from cadence_mcp_bridge.native_service import NativeOperationService

                plan = _load_plan(arguments.plan, arguments.expected_plan_sha256)
                if action in ("submit", "advance") and not getattr(
                    arguments, "experimental_candidates", False
                ):
                    raise OperationRejected("candidate_explicit_opt_in_required")
                supervisor = CandidateBatchSupervisor(NativeOperationService(context))
                query = CandidateBatchQuery(
                    batch_id=plan.request.batch_id, expected_plan_sha256=plan.plan_sha256
                )
                if action == "capture":
                    output = _output(
                        arguments.output,
                        _reserved(arguments.settings, contexts)
                        | {
                            _local_path(arguments.plan),
                        },
                    )

                async def observe() -> dict[str, Any]:
                    if action == "capture":
                        # Status is reconciliation only. The saved manifest and every
                        # retained durable identity are checked before any result read.
                        await supervisor.status(query)
                        if supervisor.store.read(query) != plan:
                            raise OperationRejected("candidate_capture_manifest_changed")
                        observations = []
                        for candidate, point in zip(
                            plan.request.candidates, plan.plans, strict=True
                        ):
                            record = None
                            report = None
                            unavailable: Literal["retained_report_read_failed"] | None = None
                            if supervisor.store.admitted(candidate.operation_id):
                                record = supervisor.native.lifecycle.store.operation(
                                    candidate.operation_id
                                )
                                if (
                                    record.operation_id != candidate.operation_id
                                    or record.plan != point
                                ):
                                    raise OperationRejected("candidate_capture_identity_mismatch")
                                if record.progress.phase == "SUCCEEDED":
                                    try:
                                        report = await capture_report(
                                            supervisor.native,
                                            candidate.operation_id,
                                            point.plan_sha256,
                                        )
                                    except (OSError, ValueError, BridgeError, KeyError, TypeError):
                                        unavailable = "retained_report_read_failed"
                            observations.append(
                                CandidateObservation(
                                    candidate_id=candidate.candidate_id,
                                    record=record,
                                    report=report,
                                    unavailable_reason=unavailable,
                                )
                            )
                        raw = OBSERVATIONS.dump_json(tuple(observations))
                        return {
                            "status": "CANDIDATE_OBSERVATIONS_CAPTURED",
                            "file_sha256": _export(output, raw),
                            "candidate_count": len(observations),
                            "unavailable_reports": sum(
                                o.unavailable_reason is not None for o in observations
                            ),
                            "verification_scope": (
                                "REGISTERED_PROVIDER_READ_AT_CAPTURE_IMPORT_IS_CONTENT_ONLY"
                            ),
                            "new_simulations": 0,
                            "new_extractions": 0,
                            "new_reservations": 0,
                        }
                    observation: Any
                    if action == "submit":
                        observation = await supervisor.submit(
                            CandidateBatchSubmission(
                                **query.model_dump(),
                                request=plan.request,
                            )
                        )
                    elif action == "advance":
                        observation = await supervisor.advance(query)
                    elif action == "status":
                        observation = await supervisor.status(query)
                    else:
                        observation = await supervisor.result(query)
                    projected: dict[str, Any] = observation.model_dump(mode="json")
                    return projected

                remote_contact = None  # A failed transport can have an unknown outcome.
                result = asyncio.run(observe())
                result["experimental_candidates"] = True
        result.update(remote_contact=remote_contact, budget_reset_or_refund=False)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, BridgeError, sqlite3.Error, KeyError, TypeError, RecursionError):
        if action == "apply-pmos-default":
            guidance = (
                "Check the registered PMOS change, context and exact request. "
                "Review retained evidence before retrying."
            )
        elif action in (
            "compose",
            "collect",
            "select",
            "amplifier-select",
            "verify-change-readback",
            "pmos-dc-compare",
            "amplifier-width-compare",
            "observe-amplifier-pm0",
        ):
            guidance = "Check pinned local documents and use a new output file."
        else:
            guidance = (
                "Check complete registered V/A inputs, fixed evidence, IDs and grant. "
                "Reconcile unknown or running work before advancing; W/L is unsupported."
            )
        print(
            json.dumps(
                {
                    "status": "CANDIDATE_WORKFLOW_REJECTED",
                    "remote_contact": remote_contact,
                    "guidance": guidance,
                    "budget_reset_or_refund": False,
                }
            )
        )
        return 2
