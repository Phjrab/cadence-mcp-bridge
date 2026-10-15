"""Synthetic retained reports; lookup/report must never resimulate or re-extract."""

import copy
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from mcp import Client
from test_native_public_service import configured, operator, operator_base
from test_runtime_context import make_settings

from cadence_mcp_bridge import result_reports
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.operator_lifecycle import ProviderObservation
from cadence_mcp_bridge.operator_operations import (
    OperationProgress,
    OperationRejected,
    prepare_plan,
)
from cadence_mcp_bridge.result_reports import (
    ResultReport,
    capture,
    compare,
    conditions_digest,
    export_report,
    job_page,
    make_report,
    read_report,
    report_view,
)
from cadence_mcp_bridge.runtime_context import load_runtime

__all__ = ["configured", "operator", "operator_base"]


def inventory(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir() if p.is_file()}


def seed(configured):
    _, service, request, _, _ = configured
    native = service.native_operations
    plan = prepare_plan(
        native.context, native.grant, native.grant_sha256, request, int(time.time()),
    )
    identity = str(uuid4())
    store = native.lifecycle.store
    store.admit_operation(identity, plan, dispatch_intent=True)
    record = store.advance_operation(
        identity, OperationProgress(phase="UNKNOWN_OUTCOME"),
        OperationProgress(phase="SUCCEEDED", remote_revision=5, provider_receipt_sha256="a" * 64),
    )
    result = {
        "status": "NATIVE_RESULT_RETRIEVED", "operation_id": identity,
        "plan_sha256": plan.plan_sha256, "design_id": request.design_id,
        "analysis": plan.analysis, "measurement_id": "dc-output",
        "reader_registration_sha256": "c" * 64, "execution_input_sha256": "d" * 64,
        "extraction_receipt_sha256": "e" * 64, "frame_sha256": "f" * 64,
        "native_provenance": "FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
        "nodes": [{"logical_id": "output", "value": 1.0, "unit": "V"}],
        "report_conditions": {
            "analysis_inputs": {"analysis": "dc", "mode": "saved_operating_point",
                                "statement_sha256": "0" * 64},
            "source_tree_sha256": "1" * 64, "ade_state_tree_sha256": "2" * 64,
            "static_statements_sha256": "3" * 64, "model_file_sha256": [], "transfer": None,
        },
    }
    observation = ProviderObservation(
        operation_id=identity, plan_sha256=plan.plan_sha256,
        resource_domain_sha256=plan.resource_domain_sha256, ledger_ref=plan.ledger_ref,
        progress=record.progress,
    )
    native.provider.report_result = AsyncMock(return_value=(observation, result))
    for action in ("lookup", "accept", "authorize", "cancel_pending"):
        setattr(native.provider, action, AsyncMock(
            side_effect=AssertionError("dispatch forbidden"),
        ))
    return native, record, result


def test_empty_catalog_never_initializes_state(tmp_path, capsys):
    settings = make_settings(tmp_path)
    context = load_runtime(settings)[0]
    before = inventory(tmp_path)
    assert job_page(context)["jobs"] == []
    assert main([
        "operator-results", "jobs", "--settings", str(settings), "--context", "context-1",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["journal_initialized"] is False
    assert inventory(tmp_path) == before


def test_wal_snapshot_is_rejected_without_creating_sidecars(configured):
    native, _, _ = seed(configured)
    path = native.context.binding.analysis_journal
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connection.close()
    before = inventory(path.parent)
    assert not path.with_name(path.name + "-shm").exists()
    with pytest.raises(ConfigurationError):
        job_page(native.context)
    assert inventory(path.parent) == before


@pytest.mark.asyncio
async def test_capture_and_restart_repeat_keep_all_journal_bytes(configured):
    native, record, _ = seed(configured)
    folder = native.context.binding.analysis_journal.parent
    before = inventory(folder)
    first = await capture(native, record.operation_id, record.plan.plan_sha256)
    second = await capture(native, record.operation_id, record.plan.plan_sha256)
    assert first.metrics == second.metrics
    assert first.operation_id == record.operation_id
    assert first.execution_timestamp is None
    assert report_view(first)["verification_at_read"] == (
        "LOCAL_RECORD_CONTENT_ONLY_NOT_REMOTE_REATTESTATION"
    )
    assert inventory(folder) == before
    assert native.provider.report_result.await_count == 2
    assert job_page(native.context)["jobs"][0]["phase"] == "SUCCEEDED"
    assert inventory(folder) == before
    with (
        pytest.raises(ConfigurationError),
        AnalysisStore(native.context.binding.analysis_journal).connection(
            create=False, read_only=True,
        ) as connection,
    ):
        connection.execute("DELETE FROM admissions")
    assert inventory(folder) == before


@pytest.mark.asyncio
async def test_resource_catalog_and_report_preserve_96_tool_contracts(configured):
    server, _, _, _, _ = configured
    native, record, _ = seed(configured)
    before = inventory(native.context.binding.analysis_journal.parent)
    async with Client(server) as client:
        catalog = json.loads((await client.read_resource("cadence://operations")).contents[0].text)
        assert catalog["jobs"][0]["operation_id"] == record.operation_id
        uri = f"cadence://operation/{record.operation_id}/{record.plan.plan_sha256}/report"
        report = json.loads((await client.read_resource(uri)).contents[0].text)
        assert report["report"]["operation_id"] == record.operation_id
        assert report["remote_contact"] is True and report["new_simulations"] == 0
        assert len((await client.list_tools()).tools) == 96
    assert inventory(native.context.binding.analysis_journal.parent) == before


@pytest.mark.parametrize("difference", ["values", "pdk", "reader", "metric_conditions"])
def test_compare_requires_identical_scientific_conditions(configured, difference):
    _, record, source = seed(configured)
    first = make_report(record, source)
    document = json.loads(first.model_dump_json())
    document["operation_id"] = str(uuid4())
    if difference == "values":
        document["plan"]["request"]["values"][0]["value"] = "2"
    elif difference == "pdk":
        document["plan"]["pdk_sha256"] = "0" * 64
    elif difference == "reader":
        document["reader_registration_sha256"] = "0" * 64
    else:
        document["metrics"][0]["signal_id"] = "different-output"
    second = ResultReport.model_validate_json(json.dumps(document))
    with pytest.raises(OperationRejected) as failure:
        compare([first, second])
    assert failure.value.reason == "report_conditions_mismatch"


def test_show_find_compare_exclusive_output_and_untrusted_import(configured, tmp_path, capsys):
    _, record, source = seed(configured)
    first = make_report(record, source)
    second = first.model_copy(update={"operation_id": str(uuid4())})
    reports = tmp_path / "reports"
    reports.mkdir()
    one, two = reports / "one.json", reports / "two.json"
    export_report(one, first)
    export_report(two, second)
    before = inventory(reports)
    assert read_report(one) == first
    with pytest.raises(FileExistsError):
        export_report(one, first)
    assert main(["operator-results", "show", "--report", str(one)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["report"]["metrics"][0]["unit"] == "V"
    assert "node_voltage" in shown["definitions"] and shown["new_simulations"] == 0
    assert main([
        "operator-results", "find", "--directory", str(reports),
        "--design-id", first.plan.request.design_id,
        "--captured-date", first.captured_at_utc.date().isoformat(),
        "--conditions-sha256", conditions_digest(first),
    ]) == 0
    found = json.loads(capsys.readouterr().out)
    assert len(found["reports"]) == 2
    assert found["date_semantics"] == "capture_date_not_simulation_date"
    assert main(["operator-results", "compare", "--reports", str(one), str(two)]) == 0
    assert json.loads(capsys.readouterr().out)["new_simulations"] == 0
    assert inventory(reports) == before
    assert main(["operator-results", "compare", "--reports", str(one), str(one)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


@pytest.mark.parametrize("change", ["id", "plan", "unattested", "nonfinite", "unit"])
def test_source_or_value_mismatch_cannot_form_report(configured, change):
    _, record, source = seed(configured)
    result = copy.deepcopy(source)
    if change == "id":
        result["operation_id"] = str(uuid4())
    elif change == "plan":
        result["plan_sha256"] = "0" * 64
    elif change == "unattested":
        result["native_provenance"] = "NOT_ATTESTED"
    elif change == "nonfinite":
        result["nodes"][0]["value"] = float("inf")
    else:
        result["nodes"][0]["unit"] = "W"
    with pytest.raises(ValueError):
        make_report(record, result)


@pytest.mark.parametrize("analysis", ["ac", "tran"])
def test_ac_and_transient_reports_preserve_defined_quantities(configured, analysis):
    _, record, source = seed(configured)
    plan = record.plan.model_copy(update={"analysis": analysis})
    record = record.model_copy(update={"plan": plan})
    source.update(analysis=analysis, plan_sha256=plan.plan_sha256)
    if analysis == "ac":
        source["report_conditions"].update(
            analysis_inputs={"analysis": "ac", "start_hz": "100", "stop_hz": "10000",
                             "points_per_decade": 1},
            transfer={"positive_input": "input", "negative_input": None,
                      "positive_output": "output", "negative_output": None,
                      "gain_frequencies_hz": ["1000"]},
        )
        source["transfer"] = [{
            "frequency_hz": 1000.0, "gain_v_per_v": 2.0,
            "gain_db": 6.020599913279624, "phase_deg": -90.0,
        }]
        expected = [2.0, 6.020599913279624, -90.0]
    else:
        source["report_conditions"]["analysis_inputs"] = {
            "analysis": "tran", "stop_s": "0.004", "maxstep_s": "0.002", "method": "trap",
        }
        source["transient"] = [{
            "logical_id": "output", "unit": "V", "minimum": 0.0, "maximum": 2.0,
            "first": 0.0, "last": 1.0, "time_weighted_mean": 1.25,
            "start_s": 0.0, "stop_s": 0.004, "sample_count": 3,
        }]
        expected = [0.0, 2.0, 0.0, 1.0, 1.25]
    report = make_report(record, source)
    assert [m.value for m in report.metrics] == expected
    assert report.analysis_conditions.analysis_inputs.analysis == analysis


def test_corrupted_event_chain_and_reserved_cross_context_output_are_rejected(
    configured, capsys,
):
    _, record, _ = seed(configured)
    _, service, _, settings, _ = configured
    context = service.context
    before = inventory(settings.parent)
    assert main([
        "operator-results", "capture", "--settings", str(settings),
        "--context", context.binding.context_id, "--operation-id", record.operation_id,
        "--expected-plan-sha256", record.plan.plan_sha256,
        "--output", str(context.binding.sweep_journal),
    ]) == 2
    assert json.loads(capsys.readouterr().out)["remote_contact"] is False
    assert inventory(settings.parent) == before
    store = AnalysisStore(context.binding.analysis_journal)
    with store.connection(create=False) as connection:
        connection.execute("UPDATE operator_events_v1 SET event_sha256=?", ("0" * 64,))
    with pytest.raises(ConfigurationError):
        job_page(context)


@pytest.mark.parametrize("context_number", [0, 1])
@pytest.mark.parametrize("journal_field", ["analysis_journal", "sweep_journal"])
@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_all_configured_sqlite_sidecars_reserved_before_capture(
    tmp_path, monkeypatch, capsys, context_number, journal_field, suffix,
):
    settings = make_settings(tmp_path)
    contexts = load_runtime(settings)
    journal = getattr(contexts[context_number].binding, journal_field)
    output = journal.with_name(journal.name + suffix)
    before = inventory(tmp_path)

    def reject_contact(*args):
        raise AssertionError("reserved output must reject before provider construction")

    monkeypatch.setattr(result_reports, "NativeOperationService", reject_contact)
    assert main([
        "operator-results", "capture", "--settings", str(settings), "--context", "context-1",
        "--operation-id", str(uuid4()), "--expected-plan-sha256", "a" * 64,
        "--output", str(output),
    ]) == 2
    assert json.loads(capsys.readouterr().out)["remote_contact"] is False
    assert inventory(tmp_path) == before
    assert job_page(contexts[0])["jobs"] == []
    assert job_page(contexts[1])["jobs"] == []
    assert inventory(tmp_path) == before


def test_normalized_other_context_journal_sidecar_is_reserved(tmp_path, monkeypatch, capsys):
    settings = make_settings(tmp_path)
    document = json.loads(settings.read_bytes())
    (tmp_path / "nested").mkdir()
    document["contexts"][1]["sweep_journal"] = str(tmp_path / "nested/../sweep-2.sqlite3")
    settings.write_text(json.dumps(document), encoding="utf-8")
    before = inventory(tmp_path)

    def reject_contact(*args):
        raise AssertionError("normalized reserved output must reject before provider construction")

    monkeypatch.setattr(result_reports, "NativeOperationService", reject_contact)
    assert main([
        "operator-results", "capture", "--settings", str(settings), "--context", "context-1",
        "--operation-id", str(uuid4()), "--expected-plan-sha256", "a" * 64,
        "--output", str(tmp_path / "sweep-2.sqlite3-wal"),
    ]) == 2
    assert json.loads(capsys.readouterr().out)["remote_contact"] is False
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("stage", ["write", "fsync"])
def test_incomplete_export_keeps_candidate_outside_catalog_and_retry_succeeds(
    configured, tmp_path, monkeypatch, capsys, stage,
):
    _, record, source = seed(configured)
    report = make_report(record, source)
    folder = tmp_path / "reports"
    folder.mkdir()
    final = folder / "result.json"
    expected = report.model_dump_json().encode()
    real_fdopen = os.fdopen

    class InterruptedWrite:
        def __init__(self, descriptor, mode):
            self.stream = real_fdopen(descriptor, mode)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, data):
            self.stream.write(data[:len(data) // 2])
            self.stream.flush()
            raise OSError("synthetic interrupted report write")

    def reject_fsync(_):
        raise OSError("synthetic report fsync failure")

    with monkeypatch.context() as fault:
        if stage == "write":
            fault.setattr(result_reports.os, "fdopen", InterruptedWrite)
        else:
            fault.setattr(result_reports.os, "fsync", reject_fsync)
        with pytest.raises(OSError):
            export_report(final, report)
    assert not final.exists()
    candidates = list(folder.glob(".cadence-report-*.pending"))
    assert len(candidates) == 1
    failure_bytes = candidates[0].read_bytes()
    assert failure_bytes == (expected[:len(expected) // 2] if stage == "write" else expected)
    assert main(["operator-results", "find", "--directory", str(folder)]) == 0
    assert json.loads(capsys.readouterr().out)["reports"] == []
    export_report(final, report)
    assert read_report(final) == report and final.stat().st_nlink == 1
    assert candidates[0].read_bytes() == failure_bytes
    assert main(["operator-results", "find", "--directory", str(folder)]) == 0
    assert len(json.loads(capsys.readouterr().out)["reports"]) == 1


def test_competing_destination_is_not_replaced_at_publication(configured, tmp_path, monkeypatch):
    _, record, source = seed(configured)
    report = make_report(record, source)
    final = tmp_path / "winner.json"
    original = b"unrelated concurrent writer"
    publish = result_reports._publish_report

    def racing_publish(candidate, destination):
        destination.write_bytes(original)
        publish(candidate, destination)

    monkeypatch.setattr(result_reports, "_publish_report", racing_publish)
    with pytest.raises(FileExistsError):
        export_report(final, report)
    assert final.read_bytes() == original
    candidates = list(tmp_path.glob(".cadence-report-*.pending"))
    assert len(candidates) == 1 and candidates[0].read_bytes() == report.model_dump_json().encode()


@pytest.mark.parametrize("stage", ["before", "after"])
def test_process_exit_at_publication_preserves_complete_catalog(
    configured, tmp_path, capsys, stage,
):
    _, record, source = seed(configured)
    report = make_report(record, source)
    folder = tmp_path / "reports"
    folder.mkdir()
    fixture = tmp_path / "report.fixture"
    fixture.write_bytes(report.model_dump_json().encode())
    final = folder / "after-crash.json"
    code = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from cadence_mcp_bridge import result_reports as reports
report = reports.ResultReport.model_validate_json(Path(sys.argv[2]).read_bytes())
publish = reports._publish_report
def crash(candidate, destination):
    if sys.argv[4] == "after":
        publish(candidate, destination)
    os._exit(23)
reports._publish_report = crash
reports.export_report(Path(sys.argv[3]), report)
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code,
         str(Path(result_reports.__file__).resolve().parents[1]), str(fixture), str(final), stage],
        capture_output=True, timeout=30, check=False,
    )
    assert completed.returncode == 23, completed.stderr
    candidates = list(folder.glob(".cadence-report-*.pending"))
    if stage == "before":
        assert not final.exists()
        assert len(candidates) == 1 and candidates[0].read_bytes() == fixture.read_bytes()
    else:
        assert not candidates and read_report(final) == report and final.stat().st_nlink == 1
    assert main(["operator-results", "find", "--directory", str(folder)]) == 0
    assert len(json.loads(capsys.readouterr().out)["reports"]) == (0 if stage == "before" else 1)
    if stage == "before":
        export_report(final, report)
    else:
        with pytest.raises(FileExistsError):
            export_report(final, report)
    assert read_report(final) == report


@pytest.mark.skipif(sys.platform != "linux", reason="real POSIX directory durability")
def test_directory_fsync_failure_retains_complete_published_report(
    configured, tmp_path, monkeypatch,
):
    _, record, source = seed(configured)
    report = make_report(record, source)
    final = tmp_path / "complete.json"
    fsync = os.fsync
    calls = 0

    def fail_directory_fsync(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic directory fsync failure")
        fsync(descriptor)

    with monkeypatch.context() as fault:
        fault.setattr(result_reports.os, "fsync", fail_directory_fsync)
        with pytest.raises(OSError, match="directory fsync"):
            export_report(final, report)
    assert read_report(final) == report and final.stat().st_nlink == 1
    with pytest.raises(FileExistsError):
        export_report(final, report)
