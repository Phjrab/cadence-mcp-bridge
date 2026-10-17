"""Synthetic operator CLI chains; no actual VM, grant or circuit qualification."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from test_candidate_batches import candidate_native
from test_candidate_contracts import candidate_operator, operator, planned
from test_candidate_reports import succeeded

from cadence_mcp_bridge import candidate_cli as cli
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.candidate_batches import CandidateBatchSupervisor
from cadence_mcp_bridge.candidate_contracts import CandidateBatchPlan
from cadence_mcp_bridge.candidate_reports import CandidateComparison
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["candidate_native", "candidate_operator", "operator"]


def output(capsys):
    return json.loads(capsys.readouterr().out)


def test_schema_and_missing_opt_in_never_load_context(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_runtime", lambda _: pytest.fail("unexpected context load"))
    assert main(["operator-candidates", "schema"]) == 0
    assert output(capsys)["wl"] == "UNSUPPORTED"
    with pytest.raises(SystemExit):
        main(
            [
                "operator-candidates",
                "advance",
                "--settings",
                "missing",
                "--context",
                "missing",
                "--plan",
                "missing",
                "--expected-plan-sha256",
                "0" * 64,
            ]
        )


def test_local_plan_exports_full_vector_without_journal(
    candidate_operator, tmp_path, monkeypatch, capsys
):
    context, grant, request, settings = candidate_operator
    grant_path = tmp_path / "cli-grant.json"
    grant_path.write_text(grant.model_dump_json(), encoding="utf-8")
    digest = canonical_digest(grant)
    context = replace(
        context,
        binding=context.binding.model_copy(
            update={
                "operator_grant": grant_path,
                "operator_grant_sha256": digest,
            }
        ),
    )
    monkeypatch.setattr(cli, "load_runtime", lambda _: (context,))
    monkeypatch.setattr(cli, "load_grant", lambda *args: (grant, digest))
    monkeypatch.setattr(cli.time, "time", lambda: 100)
    source, target = tmp_path / "request.json", tmp_path / "plan.json"
    source.write_text(request.model_dump_json(), encoding="utf-8")
    args = [
        "operator-candidates",
        "plan",
        "--settings",
        str(settings),
        "--context",
        context.binding.context_id,
        "--request",
        str(source),
        "--output",
        str(target),
    ]
    assert main(args) == 0
    receipt = output(capsys)
    plan = CandidateBatchPlan.model_validate_json(target.read_bytes())
    assert receipt["plan_sha256"] == plan.plan_sha256
    assert plan.request.candidates == request.candidates and plan.expected_executions == 3
    assert not context.binding.analysis_journal.exists() and not context.lock_path.exists()
    assert main(args) == 2
    assert output(capsys)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert CandidateBatchPlan.model_validate_json(target.read_bytes()) == plan
    args[-1] = str(context.binding.analysis_journal)
    assert main(args) == 2
    output(capsys)
    assert not context.binding.analysis_journal.exists()


def test_compare_csv_cli_chain_retains_all_rows(candidate_operator, tmp_path, capsys):
    plan = planned(candidate_operator)
    source, observations = tmp_path / "plan.json", tmp_path / "observations.json"
    comparison, csv = tmp_path / "comparison.json", tmp_path / "comparison.csv"
    source.write_text(plan.model_dump_json(), encoding="utf-8")
    observations.write_bytes(cli.OBSERVATIONS.dump_json(succeeded(plan)))
    args = [
        "operator-candidates",
        "compare",
        "--plan",
        str(source),
        "--expected-plan-sha256",
        plan.plan_sha256,
        "--observations",
        str(observations),
        "--output",
        str(comparison),
    ]
    assert main(args) == 0
    assert output(capsys)["new_simulations"] == 0
    report = CandidateComparison.model_validate_json(comparison.read_bytes())
    assert len(report.rows) == 3 and all(row.status == "SUCCEEDED" for row in report.rows)
    assert (
        main(["operator-candidates", "csv", "--comparison", str(comparison), "--output", str(csv)])
        == 0
    )
    assert output(capsys)["remote_contact"] is False
    assert csv.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "기준 회로" in csv.read_text(encoding="utf-8-sig")
    observations.write_bytes(b"[]")
    args[-1] = str(tmp_path / "not-run.json")
    assert main(args) == 0
    output(capsys)
    missing = CandidateComparison.model_validate_json((tmp_path / "not-run.json").read_bytes())
    assert all(row.status == "NOT_RUN" and not row.metrics for row in missing.rows)


def test_read_rejects_duplicate_keys_and_oversized_files(tmp_path):
    path = tmp_path / "input.json"
    path.write_bytes(b'{"x":1,"x":2}')
    with pytest.raises(ValueError):
        cli.read_candidate_document(path)
    path.write_bytes(b" " * (cli.DOCUMENT_LIMIT + 1))
    with pytest.raises(OperationRejected):
        cli.read_candidate_document(path)


def test_publication_failure_preserves_complete_pending_file(tmp_path, monkeypatch):
    target = tmp_path / "new.json"

    def fail(*_):
        raise OSError("synthetic interrupted publication")

    monkeypatch.setattr(cli, "_publish_report", fail)
    with pytest.raises(OSError):
        cli._export(target, b'{"synthetic":true}')
    assert not target.exists()
    pending = tuple(tmp_path.glob(".cadence-candidates-*.pending"))
    assert len(pending) == 1 and pending[0].read_bytes() == b'{"synthetic":true}'


@pytest.mark.parametrize("read_fails", [False, True])
def test_submit_advance_capture_compare_chain_without_retry(
    candidate_native,
    candidate_operator,
    tmp_path,
    monkeypatch,
    capsys,
    read_fails,
):
    make_native, provider, request = candidate_native
    context = make_native().context
    settings = candidate_operator[3]
    monkeypatch.setattr(cli, "load_runtime", lambda _: (context,))
    monkeypatch.setattr(cli.time, "time", lambda: 100)
    monkeypatch.setattr(
        "cadence_mcp_bridge.native_service.NativeOperationService", lambda _: make_native()
    )
    plan = asyncio.run(CandidateBatchSupervisor(make_native()).plan(request))
    source = tmp_path / "plan.json"
    source.write_text(plan.model_dump_json(), encoding="utf-8")
    shared = [
        "--settings",
        str(settings),
        "--context",
        context.binding.context_id,
        "--plan",
        str(source),
        "--expected-plan-sha256",
        plan.plan_sha256,
    ]
    assert main(["operator-candidates", "submit", *shared, "--experimental-candidates"]) == 0
    assert output(capsys)["state"] == "PLANNED" and provider.calls == []
    assert main(["operator-candidates", "advance", *shared, "--experimental-candidates"]) == 0
    assert output(capsys)["state"] == "PARTIAL" and len(provider.calls) == 1
    assert main(["operator-candidates", "submit", *shared, "--experimental-candidates"]) == 0
    output(capsys)
    assert len(provider.calls) == 1
    reports = {o.record.operation_id: o.report for o in succeeded(plan)}
    reads = []

    async def read(_native, operation_id, digest):
        reads.append(operation_id)
        assert digest == reports[operation_id].plan.plan_sha256
        if read_fails:
            raise OperationRejected("synthetic_report_read_failed")
        return reports[operation_id]

    monkeypatch.setattr(cli, "capture_report", read)
    observations = tmp_path / "observations.json"
    assert main(["operator-candidates", "capture", *shared, "--output", str(observations)]) == 0
    captured = output(capsys)
    assert captured["new_simulations"] == 0 and captured["unavailable_reports"] == int(read_fails)
    assert reads == [request.candidates[0].operation_id] and len(provider.calls) == 1
    comparison = tmp_path / "comparison.json"
    assert (
        main(
            [
                "operator-candidates",
                "compare",
                "--plan",
                str(source),
                "--expected-plan-sha256",
                plan.plan_sha256,
                "--observations",
                str(observations),
                "--output",
                str(comparison),
            ]
        )
        == 0
    )
    output(capsys)
    rows = CandidateComparison.model_validate_json(comparison.read_bytes()).rows
    assert [row.status for row in rows] == [
        "RESULT_UNAVAILABLE" if read_fails else "SUCCEEDED",
        "NOT_RUN",
        "NOT_RUN",
    ]
    assert rows[0].reason == ("retained_report_read_failed" if read_fails else None)
    assert len(provider.calls) == 1
