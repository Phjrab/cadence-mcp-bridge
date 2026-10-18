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
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter

from cadence_mcp_bridge.candidate_contracts import (
    CandidateBatchPlan,
    CandidateBatchRequest,
    prepare_candidate_plan,
)
from cadence_mcp_bridge.candidate_reports import (
    CandidateComparison,
    CandidateObservation,
    compare_candidate_reports,
    render_candidate_csv,
)
from cadence_mcp_bridge.domain_provisioning import _closed_document
from cadence_mcp_bridge.errors import BridgeError
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import OperationRejected, load_grant
from cadence_mcp_bridge.result_reports import _publish_report
from cadence_mcp_bridge.result_reports import capture as capture_report
from cadence_mcp_bridge.runtime_context import ExecutionContext, load_runtime

DOCUMENT_LIMIT = 1048576
OBSERVATIONS: TypeAdapter[tuple[CandidateObservation, ...]] = TypeAdapter(
    Annotated[tuple[CandidateObservation, ...], Field(max_length=16)]
)


def add_candidates_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    parser = subparsers.add_parser(
        "operator-candidates",
        help="Experimental registered V/A candidates and retained reports.",
    )
    actions = parser.add_subparsers(dest="candidates_action", required=True)
    actions.add_parser("schema")
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


def read_candidate_document(path: Path) -> bytes:
    """Bound a regular local content record, without claiming remote authenticity."""
    path = _local_path(path)
    before = path.stat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or (before.st_size > DOCUMENT_LIMIT)
    ):
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
        raw = stream.read(DOCUMENT_LIMIT + 1)
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
    _closed_document(raw, max_bytes=DOCUMENT_LIMIT)
    return raw


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
        else:
            contexts = load_runtime(_local_path(arguments.settings))
            context = next((c for c in contexts if c.binding.context_id == arguments.context), None)
            if context is None:
                raise OperationRejected("candidate_context_required")
            if action == "plan":
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
        print(
            json.dumps(
                {
                    "status": "CANDIDATE_WORKFLOW_REJECTED",
                    "remote_contact": remote_contact,
                    "guidance": (
                        "Check complete registered V/A inputs, fixed evidence, IDs and grant. "
                        "Reconcile unknown or running work before advancing; W/L is unsupported."
                    ),
                    "budget_reset_or_refund": False,
                }
            )
        )
        return 2
