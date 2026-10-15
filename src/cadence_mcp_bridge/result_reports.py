"""Find admitted jobs and report existing results; no simulation or extraction dispatch."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import json
import math
import os
import stat
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, TypeAdapter, model_validator

from cadence_mcp_bridge.analysis_store import MAX_RECORDS, AnalysisStore
from cadence_mcp_bridge.domain_provisioning import _closed_document
from cadence_mcp_bridge.errors import BridgeError
from cadence_mcp_bridge.generic_ade import AnalysisInputs
from cadence_mcp_bridge.generic_measurements import TransferSignal
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import NativeOperationService
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_operations import (
    DurableOperation,
    OperationPlan,
    OperationRejected,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext, load_runtime
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel

REPORT_LIMIT = 262144
PAGE_SIZE = 32
MetricKind = Literal[
    "node_voltage", "delivered_power", "voltage_gain", "voltage_gain_db", "voltage_phase",
    "minimum", "maximum", "first", "last", "time_weighted_mean",
]
DEFINITIONS: dict[str, str] = {
    "node_voltage": "Registered node voltage relative to ground at the DC operating point.",
    "delivered_power": "Negative terminal voltage times signed source current; positive delivered.",
    "voltage_gain": "Magnitude of complex output voltage divided by measured input voltage.",
    "voltage_gain_db": "20 log10 of voltage_gain; null for zero transfer.",
    "voltage_phase": "Principal phase of complex output/input in degrees; null for zero transfer.",
    "minimum": "Minimum of all saved real transient samples.",
    "maximum": "Maximum of all saved real transient samples.",
    "first": "First saved real transient sample.",
    "last": "Last saved real transient sample.",
    "time_weighted_mean": "Trapezoidal integral of saved voltage samples divided by duration.",
}


def conditions_digest(report: ResultReport) -> str:
    return hashlib.sha256(json.dumps(
        report.conditions(), sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


class ReportMetric(VariableModel):
    kind: MetricKind
    signal_id: LogicalId | None = None
    value: float | None
    unit: Literal["V", "W", "V/V", "dB", "deg"]
    frequency_hz: float | None = None
    start_s: float | None = None
    stop_s: float | None = None
    sample_count: Annotated[int, Field(ge=2, le=256)] | None = None
    source_role: Literal["supply", "bias", "stimulus"] | None = None

    @model_validator(mode="after")
    def finite(self) -> Self:
        expected_unit = {
            "delivered_power": "W", "voltage_gain": "V/V", "voltage_gain_db": "dB",
            "voltage_phase": "deg",
        }.get(self.kind, "V")
        if self.unit != expected_unit:
            raise ValueError("metric unit differs from its definition")
        if (self.kind == "delivered_power") != (self.source_role is not None):
            raise ValueError("delivered power requires a source role")
        if self.value is None and self.kind not in ("voltage_gain_db", "voltage_phase"):
            raise ValueError("this metric requires a value")
        if any(
            value is not None and not math.isfinite(value)
            for value in (self.value, self.frequency_hz, self.start_s, self.stop_s)
        ):
            raise ValueError("finite metrics required")
        return self


class ReportConditions(VariableModel):
    analysis_inputs: AnalysisInputs
    source_tree_sha256: Digest
    ade_state_tree_sha256: Digest
    static_statements_sha256: Digest
    model_file_sha256: Annotated[tuple[Digest, ...], Field(max_length=16)]
    transfer: TransferSignal | None


class ResultReport(VariableModel):
    schema_version: Literal[1] = 1
    operation_id: OperationId
    plan: OperationPlan
    captured_at_utc: datetime
    execution_timestamp: Literal[None] = None
    date_semantics: Literal["capture_date_not_simulation_date"] = "capture_date_not_simulation_date"
    measurement_id: LogicalId
    reader_registration_sha256: Digest
    execution_input_sha256: Digest
    extraction_receipt_sha256: Digest
    frame_sha256: Digest
    source_provenance: Literal["FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED"]
    analysis_conditions: ReportConditions
    metrics: Annotated[tuple[ReportMetric, ...], Field(min_length=1, max_length=256)]

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.analysis_conditions.analysis_inputs.analysis != self.plan.analysis or (
            (self.plan.analysis == "ac") != (self.analysis_conditions.transfer is not None)
        ):
            raise ValueError("analysis definition mismatch")
        offset = self.captured_at_utc.utcoffset()
        if offset is None or offset.total_seconds():
            raise ValueError("UTC capture time required")
        identities = [
            (m.kind, m.signal_id, m.frequency_hz, m.start_s, m.stop_s, m.sample_count)
            for m in self.metrics
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate metric")
        for metric in self.metrics:
            if self.plan.analysis == "dc" and (
                metric.kind not in ("node_voltage", "delivered_power")
                or metric.signal_id is None or metric.frequency_hz is not None
                or metric.start_s is not None or metric.stop_s is not None
            ):
                raise ValueError("DC metric scope invalid")
            if self.plan.analysis == "ac" and (
                metric.kind not in ("voltage_gain", "voltage_gain_db", "voltage_phase")
                or metric.frequency_hz is None or metric.frequency_hz <= 0
                or metric.start_s is not None or metric.stop_s is not None
            ):
                raise ValueError("AC metric scope invalid")
            if self.plan.analysis == "tran" and (
                metric.kind not in ("minimum", "maximum", "first", "last", "time_weighted_mean")
                or metric.signal_id is None or metric.start_s is None or metric.stop_s is None
                or metric.sample_count is None or metric.frequency_hz is not None
                or metric.start_s < 0 or metric.stop_s <= metric.start_s
            ):
                raise ValueError("transient metric scope invalid")
        return self

    def conditions(self) -> dict[str, Any]:
        plan = self.plan
        return {
            "design_id": plan.request.design_id, "analysis_id": plan.request.analysis_id,
            "analysis": plan.analysis, "environment_sha256": plan.environment_sha256,
            "design_sha256": plan.design_sha256, "pdk_sha256": plan.pdk_sha256,
            "runner_sha256": plan.runner_sha256,
            "values": [v.model_dump(mode="json") for v in plan.request.values],
            "measurement_id": self.measurement_id,
            "reader_registration_sha256": self.reader_registration_sha256,
            "execution_input_sha256": self.execution_input_sha256,
            "analysis_conditions": self.analysis_conditions.model_dump(mode="json"),
            "metric_conditions": [
                m.model_dump(mode="json", exclude={"value"}) for m in self.metrics
            ],
        }


def job_page(context: ExecutionContext, offset: int = 0) -> dict[str, Any]:
    if type(offset) is not int or not 0 <= offset <= MAX_RECORDS:
        raise OperationRejected("result_page_invalid")
    jobs: list[dict[str, Any]] = []
    path = context.binding.analysis_journal
    exists = path.exists()
    if path.is_symlink() or path.is_junction():
        raise OperationRejected("result_journal_invalid")
    if exists:
        store = AnalysisStore(path)
        with store.connection(create=False, read_only=True) as connection:
            present = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='operator_plans_v1' AND type='table'",
            ).fetchone()
            if present:
                ids = connection.execute(
                    "SELECT operation_id FROM operator_plans_v1 "
                    "ORDER BY operation_id LIMIT ? OFFSET ?",
                    (PAGE_SIZE + 1, offset),
                ).fetchall()
                for (operation_id,) in ids[:PAGE_SIZE]:
                    record = store._read_operation(connection, operation_id)
                    if (record.plan.resource_domain_sha256, record.plan.ledger_ref) != (
                        context.resource_domain_sha256, context.binding.ledger_ref,
                    ):
                        raise OperationRejected("result_journal_domain_mismatch")
                    jobs.append({
                        "operation_id": record.operation_id,
                        "plan_sha256": record.plan.plan_sha256,
                        "design_id": record.plan.request.design_id,
                        "analysis_id": record.plan.request.analysis_id,
                        "analysis": record.plan.analysis,
                        "values": [v.model_dump(mode="json") for v in record.plan.request.values],
                        "phase": record.progress.phase,
                        "execution_timestamp": None,
                        "observation": "LOCAL_RETAINED_JOURNAL_NOT_REMOTE_RECONCILIATION",
                    })
                next_offset = offset + PAGE_SIZE if len(ids) > PAGE_SIZE else None
            else:
                next_offset = None
    else:
        next_offset = None
    return {
        "schema_version": 1, "jobs": jobs, "next_offset": next_offset,
        "journal_initialized": exists, "remote_contact": False,
        "new_simulations": 0, "new_reservations": 0,
    }


def _metrics(result: dict[str, Any]) -> tuple[ReportMetric, ...]:
    metrics: list[ReportMetric] = []
    if result["analysis"] == "dc":
        for node in result["nodes"]:
            if node.get("unit") != "V":
                raise OperationRejected("report_metric_unit_invalid")
            metrics.append(ReportMetric(
                kind="node_voltage", signal_id=node["logical_id"], value=float(node["value"]),
                unit="V",
            ))
        for source in result.get("sources", []):
            metrics.append(ReportMetric(
                kind="delivered_power", signal_id=source["source_id"],
                value=float(source["delivered_w"]), unit="W",
                source_role=source["role"],
            ))
    elif result["analysis"] == "ac":
        for sample in result["transfer"]:
            for kind, key, unit in (
                ("voltage_gain", "gain_v_per_v", "V/V"),
                ("voltage_gain_db", "gain_db", "dB"),
                ("voltage_phase", "phase_deg", "deg"),
            ):
                metrics.append(ReportMetric.model_validate_json(json.dumps({
                    "kind": kind, "value": sample[key], "unit": unit,
                    "frequency_hz": sample["frequency_hz"],
                })))
    else:
        for sample in result["transient"]:
            if sample.get("unit") != "V":
                raise OperationRejected("report_metric_unit_invalid")
            for kind in ("minimum", "maximum", "first", "last", "time_weighted_mean"):
                metrics.append(ReportMetric.model_validate_json(json.dumps({
                    "kind": kind, "value": sample[kind], "unit": "V",
                    "signal_id": sample["logical_id"], "start_s": sample["start_s"],
                    "stop_s": sample["stop_s"], "sample_count": sample["sample_count"],
                })))
    return tuple(metrics)


def make_report(record: DurableOperation, result: dict[str, Any]) -> ResultReport:
    if (
        record.progress.phase != "SUCCEEDED"
        or result.get("status") != "NATIVE_RESULT_RETRIEVED"
        or (result.get("operation_id"), result.get("plan_sha256"), result.get("design_id"),
            result.get("analysis"))
        != (record.operation_id, record.plan.plan_sha256, record.plan.request.design_id,
            record.plan.analysis)
    ):
        raise OperationRejected("report_source_identity_invalid")
    return ResultReport(
        operation_id=record.operation_id, plan=record.plan,
        captured_at_utc=datetime.now(UTC),
        measurement_id=result["measurement_id"],
        reader_registration_sha256=result["reader_registration_sha256"],
        execution_input_sha256=result["execution_input_sha256"],
        extraction_receipt_sha256=result["extraction_receipt_sha256"],
        frame_sha256=result["frame_sha256"], source_provenance=result["native_provenance"],
        analysis_conditions=ReportConditions.model_validate_json(
            json.dumps(result["report_conditions"]),
        ),
        metrics=_metrics(result),
    )


async def capture(native: NativeOperationService, operation_id: str, digest: str) -> ResultReport:
    TypeAdapter(OperationId).validate_python(operation_id)
    TypeAdapter(Digest).validate_python(digest)
    native.current()
    store = native.lifecycle.store
    with store.connection(create=False, read_only=True) as connection:
        record = store._read_operation(connection, operation_id)
    if (
        record.operation_id != operation_id or record.plan.plan_sha256 != digest
        or record.plan.resource_domain_sha256 != native.context.resource_domain_sha256
        or record.plan.ledger_ref != native.context.binding.ledger_ref
        or record.progress.phase != "SUCCEEDED"
    ):
        raise OperationRejected("report_requires_retained_succeeded_identity")
    observed, result = await native.provider.report_result(operation_id, record.plan)
    observed.check(record)
    if observed.progress != record.progress:
        raise OperationRejected("report_terminal_identity_mismatch")
    return make_report(record, result)


def report_view(report: ResultReport) -> dict[str, Any]:
    return {
        "report": report.model_dump(mode="json"),
        "definitions": {m.kind: DEFINITIONS[m.kind] for m in report.metrics},
        "conditions_sha256": conditions_digest(report),
        "verification_at_read": "LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION",
        "new_simulations": 0, "new_reservations": 0,
    }


def compare(reports: list[ResultReport]) -> dict[str, Any]:
    if not 2 <= len(reports) <= 16 or len({r.operation_id for r in reports}) != len(reports):
        raise OperationRejected("report_comparison_identity_invalid")
    conditions = [conditions_digest(r) for r in reports]
    if len(set(conditions)) != 1:
        raise OperationRejected("report_conditions_mismatch")
    return {
        "conditions_sha256": conditions[0],
        "operation_ids": [r.operation_id for r in reports],
        "reports": [report_view(r) for r in reports],
        "new_simulations": 0, "new_reservations": 0,
    }


def read_report(path: Path) -> ResultReport:
    path = _local_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > REPORT_LIMIT:
        raise OperationRejected("report_file_invalid")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (
            opened.st_dev, opened.st_ino,
        ):
            raise OperationRejected("report_file_changed")
        raw = stream.read(REPORT_LIMIT + 1)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
    ) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino) or (
        len(raw) > REPORT_LIMIT
    ):
        raise OperationRejected("report_file_changed")
    _closed_document(raw, max_bytes=REPORT_LIMIT)
    return ResultReport.model_validate_json(raw)


def _publish_report(candidate: Path, destination: Path) -> None:
    """Atomically move a complete file without replacing any existing entry."""
    if os.name == "nt":
        # Windows rename is atomic and rejects an existing destination. POSIX
        # rename replaces one, so it must never be used as the Linux fallback.
        os.rename(candidate, destination)
    elif sys.platform == "linux":
        try:
            rename = ctypes.CDLL(None, use_errno=True).renameat2
        except AttributeError:
            raise OperationRejected("report_atomic_publication_unsupported") from None
        rename.argtypes = [
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint,
        ]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(candidate), -100, os.fsencode(destination), 1) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), destination)
        descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    else:
        raise OperationRejected("report_atomic_publication_unsupported")


def export_report(path: Path, report: ResultReport) -> str:
    raw = report.model_dump_json().encode("utf-8")
    if len(raw) > REPORT_LIMIT:
        raise OperationRejected("report_capacity_exceeded")
    path = _local_path(path)
    if not path.parent.is_dir():
        raise OperationRejected("report_parent_required")
    if path.exists():
        raise FileExistsError(path)
    # Interrupted/failed candidates remain evidence outside find's *.json
    # namespace. Only the fully written and fsynced record receives its final
    # name. A link/unlink publication is intentionally avoided: a crash between
    # them would leave a two-link report rejected by the existing read guard.
    descriptor, name = tempfile.mkstemp(
        prefix=".cadence-report-", suffix=".pending", dir=path.parent,
    )
    candidate = Path(name)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _publish_report(candidate, path)
    return hashlib.sha256(raw).hexdigest()


def add_results_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    command = subparsers.add_parser("operator-results", help="Find/report existing native results.")
    actions = command.add_subparsers(dest="results_action", required=True)
    for action in ("jobs", "capture"):
        sub = actions.add_parser(action)
        sub.add_argument("--settings", type=Path, required=True)
        sub.add_argument("--context", required=True)
        if action == "jobs":
            sub.add_argument("--offset", type=int, default=0)
        else:
            sub.add_argument("--operation-id", required=True)
            sub.add_argument("--expected-plan-sha256", required=True)
            sub.add_argument("--output", type=Path, required=True)
    find = actions.add_parser("find")
    find.add_argument("--directory", type=Path, required=True)
    find.add_argument("--design-id")
    find.add_argument("--captured-date", type=date.fromisoformat)
    find.add_argument("--conditions-sha256")
    comparison = actions.add_parser("compare")
    comparison.add_argument("--reports", type=Path, nargs="+", required=True)
    show = actions.add_parser("show")
    show.add_argument("--report", type=Path, required=True)


def results_cli(arguments: argparse.Namespace) -> int:

    remote_contact: bool | None = False
    try:
        action = arguments.results_action
        if action in ("jobs", "capture"):
            contexts = load_runtime(_local_path(arguments.settings))
            context = next((c for c in contexts if c.binding.context_id == arguments.context), None)
            if context is None:
                raise OperationRejected("result_context_required")
            if action == "jobs":
                result = job_page(context, arguments.offset)
            else:
                output = _local_path(arguments.output)
                reserved = {_local_path(arguments.settings)}
                for loaded in contexts:
                    reserved.add(loaded.lock_path)
                    for field in type(loaded.binding).model_fields:
                        value = getattr(loaded.binding, field)
                        if isinstance(value, Path):
                            reserved.add(_local_path(value))
                    for journal in (
                        loaded.binding.analysis_journal, loaded.binding.sweep_journal,
                    ):
                        journal = _local_path(journal)
                        reserved.update(
                            journal.with_name(journal.name + suffix).absolute()
                            for suffix in ("-wal", "-shm", "-journal")
                        )
                if output in reserved:
                    raise OperationRejected("report_output_reserved")
                if output.exists() or not output.parent.is_dir():
                    raise OperationRejected("report_new_output_required")
                native = NativeOperationService(context)
                remote_contact = None  # A failed capture cannot attest whether contact occurred.
                report = asyncio.run(capture(
                    native, arguments.operation_id, arguments.expected_plan_sha256,
                ))
                remote_contact = True
                result = {**report_view(report), "file_sha256": export_report(output, report)}
        elif action == "compare":
            if not 2 <= len(arguments.reports) <= 16:
                raise OperationRejected("report_comparison_identity_invalid")
            result = compare([read_report(p) for p in arguments.reports])
        elif action == "show":
            result = report_view(read_report(arguments.report))
        else:
            folder = _local_path(arguments.directory)
            if not folder.is_dir():
                raise OperationRejected("report_directory_required")
            reports = []
            for index, path in enumerate(sorted(folder.glob("*.json"))):
                if index >= 256:
                    raise OperationRejected("report_catalog_capacity")
                report = read_report(path)
                if arguments.design_id and arguments.design_id != report.plan.request.design_id:
                    continue
                if arguments.captured_date and (
                    arguments.captured_date != report.captured_at_utc.date()
                ):
                    continue
                digest = conditions_digest(report)
                if arguments.conditions_sha256 and arguments.conditions_sha256 != digest:
                    continue
                reports.append({
                    "operation_id": report.operation_id, "design_id": report.plan.request.design_id,
                    "captured_at_utc": report.captured_at_utc.isoformat(),
                    "execution_timestamp": None, "conditions_sha256": digest,
                })
            result = {"reports": reports, "date_semantics": "capture_date_not_simulation_date"}
        result.update(remote_contact=remote_contact, new_simulations=0, new_reservations=0)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, BridgeError, KeyError, TypeError):
        print(json.dumps({
            "status": "BLOCKED", "reason": "result_report_rejected",
            "guidance": "Check registered context, retained succeeded ID, matching conditions "
            "and exclusive report files. Reconcile with existing status if local state is stale.",
            "remote_contact": remote_contact, "new_simulations": 0, "new_reservations": 0,
        }))
        return 2
