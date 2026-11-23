"""MCP projection of one host-pinned retained amplifier comparison."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, JsonValue

from cadence_mcp_bridge.candidate_cli import read_candidate_document
from cadence_mcp_bridge.candidate_execution import (
    FreshAmplifierMeasurement,
    FreshAmplifierWidthPair,
)
from cadence_mcp_bridge.candidate_reports import candidate_metric_delta
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.native_service import NativeOperationQuery
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel


class _RetainedReport(VariableModel):
    association: FreshAmplifierWidthPair
    requested_width: JsonValue
    request_sha256: Digest
    deltas: dict[str, JsonValue]
    selected_candidate_id: Literal[None]


class RetainedAmpComparisonQuery(VariableModel):
    expected_report_sha256: Digest


class _Measurement(VariableModel):
    operation: NativeOperationQuery
    value: Annotated[float, Field(allow_inf_nan=False)]


class _Comparison(VariableModel):
    unit: Literal["W", "dB"]
    baseline: _Measurement
    candidate: _Measurement
    absolute_delta: Annotated[float, Field(allow_inf_nan=False)]


class RetainedAmpComparison(VariableModel):
    report_sha256: Digest
    dc: _Comparison
    ac: _Comparison
    goals: Literal["GOALS_NOT_PROVIDED"] = "GOALS_NOT_PROVIDED"
    selected_candidate_id: Literal[None] = None
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False


def _measurement(record: FreshAmplifierMeasurement) -> _Measurement:
    if record.status != "SUCCEEDED" or record.operation is None or record.value is None:
        raise ValueError("retained comparison measurement unavailable")
    return _Measurement(operation=record.operation, value=record.value)


def load_retained_amp_comparison(path: Path, expected_sha256: str) -> RetainedAmpComparison:
    try:
        raw = read_candidate_document(path, expected_sha256=expected_sha256)
        report = _RetainedReport.model_validate_json(raw)
        metrics = {}
        for row in (report.association.dc, report.association.ac):
            baseline, candidate = _measurement(row.baseline), _measurement(row.candidate)
            delta, _, reason = candidate_metric_delta(
                candidate.value, baseline.value, baseline_present=True,
            )
            if delta is None or report.deltas.get(row.analysis) != {
                "absolute_delta": delta, "reason": reason,
            }:
                raise ValueError("retained comparison delta mismatch")
            metrics[row.analysis] = _Comparison(
                unit=row.unit, baseline=baseline, candidate=candidate, absolute_delta=delta,
            )
        if report.association.dc.unit != "W" or report.association.ac.unit != "dB":
            raise ValueError("retained comparison units differ")
        return RetainedAmpComparison(
            report_sha256=expected_sha256, dc=metrics["dc"], ac=metrics["ac"],
        )
    except (InvalidInputError, OSError, ValueError):
        raise ConfigurationError("Configured retained amplifier comparison is invalid") from None


def register_retained_amp_comparison(server: MCPServer, summary: RetainedAmpComparison) -> None:
    @server.tool(
        name="cadence_retained_amplifier_comparison",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
        structured_output=True,
        description="Read the host-pinned amplifier comparison by exact report digest.",
    )
    def retained_amplifier_comparison(request: RetainedAmpComparisonQuery) -> RetainedAmpComparison:
        if request.expected_report_sha256 != summary.report_sha256:
            raise ToolError("Retained amplifier comparison digest differs")
        return summary
