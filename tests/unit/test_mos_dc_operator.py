"""Resolve sealed W/L result selection before the existing native report read."""

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import pytest
from test_generic_measurements import operator as measurement_operator  # noqa: F401
from test_generic_measurements import reader_for
from test_mos_dc_evaluation import _point, _terminal
from test_operator_operations import operator as operator_base  # noqa: F401

from cadence_mcp_bridge import mos_dc_operator as operator
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.authenticated_provider import NativeResultPayload, verify_native_result
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.operator_operations import OperationRejected
from cadence_mcp_bridge.registered_mos_sizing import (
    RegisteredMosSizingResult,
    RetainedMosSizingEvidence,
)
from cadence_mcp_bridge.registered_mos_sizing_transport import MosSizingLookup


@pytest.mark.asyncio
async def test_selected_evaluation_enrollment_reads_only_admitted_original(
    measurement_operator,  # noqa: F811
    tmp_path,
    monkeypatch,
):
    point = _point(reader_for(measurement_operator), "250", 0)
    evidence, _, _ = point
    route = evidence.route
    assert route is not None and evidence.confirmed_input is not None
    context, native = route.context, route.operation
    result = RegisteredMosSizingResult.model_validate_json(evidence.edit_result)
    sizing_pin = "f" * 64

    def artifact(name, raw):
        path = tmp_path / name
        path.write_bytes(raw)
        return {"path": path, "sha256": sha256(raw).hexdigest()}

    roster = operator._Enrollment.model_validate(
        {
            "schema_version": 1,
            "owner": "C0",
            "context_id": context.binding.context_id,
            "resource_domain_sha256": context.resource_domain_sha256,
            "sizing_enrollment_sha256": sizing_pin,
            "candidates": (
                {
                    "edit": result.identity,
                    "analysis": {
                        "query": native.query,
                        "plan": native.plan,
                        "runtime_manifest": artifact("runtime.json", native.runtime_manifest),
                        "runtime_registration": artifact(
                            "registration.json", native.runtime_registration
                        ),
                    },
                    "source_export": artifact("export.json", route.export),
                },
            ),
        }
    )
    enrollment = tmp_path / "evaluation.json"
    contents = roster.model_dump_json().encode()
    enrollment.write_bytes(contents)
    context = replace(
        context,
        binding=context.binding.model_copy(
            update={
                "mos_dc_evaluation_binding": enrollment,
                "mos_dc_evaluation_sha256": sha256(contents).hexdigest(),
            }
        ),
    )
    sizing = SimpleNamespace(
        enrollment_sha256=sizing_pin,
        inspect=lambda: SimpleNamespace(operation_ids=(result.identity.operation_id,)),
    )

    def retained(identity):
        assert identity == result.identity
        return (
            MosSizingLookup(identity=identity, outcome="VERIFIED", result=result),
            RetainedMosSizingEvidence(
                evidence.sizing_plan,
                evidence.edit_binding,
                evidence.baseline_input,
                evidence.confirmed_input,
            ),
        )

    sizing.lookup_evidence = retained
    store = AnalysisStore(context.binding.analysis_journal)
    calls = []
    failure = None

    async def report_result(identity, plan):
        calls.append((identity, plan))
        if failure is not None:
            raise OperationRejected(failure)
        return verify_native_result(
            context,
            plan,
            identity,
            native_result,
            include_report_conditions=True,
        )

    def native_service(selected):
        assert selected == context
        return SimpleNamespace(
            context=selected,
            current=lambda: None,
            lifecycle=SimpleNamespace(store=store),
            provider=SimpleNamespace(report_result=report_result),
        )

    monkeypatch.setattr(operator, "NativeOperationService", native_service)
    request = operator.MosDcCompareRequest(edits=(result.identity,))
    pending = (await operator.compare_registered_mos_dc(context, sizing, request)).rows[0]
    assert pending.edit_outcome == "VERIFIED" and pending.analysis_status == "NOT_RUN"
    assert pending.reason == "operation_not_admitted"
    assert pending.evaluation.analysis_operation_id == native.query.operation_id
    assert not calls and not store.path.exists()

    terminal = _terminal(point, "SUCCEEDED", "0.8")
    native_result = NativeResultPayload.model_validate_json(terminal)
    journal = store.path.read_bytes()
    read = (await operator.compare_registered_mos_dc(context, sizing, request)).rows[0]
    assert read.analysis_status == "SUCCEEDED"
    assert read.evaluation.report.operation_id == native.query.operation_id
    assert read.evaluation.edit.candidate_revision == result.candidate_revision
    assert read.evaluation.comparison_status == "BASELINE_UNAVAILABLE"

    failure = "native_provider_transport_unknown"
    retained_status = (await operator.compare_registered_mos_dc(context, sizing, request)).rows[0]
    assert retained_status.analysis_status == "SUCCEEDED"
    assert retained_status.reason == "original_result_unavailable"
    assert retained_status.evaluation.report is None

    failure = "native_provider_result_binding_mismatch"
    with pytest.raises(OperationRejected) as rejected:
        await operator.compare_registered_mos_dc(context, sizing, request)
    assert rejected.value.reason == failure

    foreign = result.identity.model_copy(update={"expected_scope_sha256": "0" * 64})
    with pytest.raises(ValueError, match="enrolled evaluation"):
        await operator.compare_registered_mos_dc(
            context,
            sizing,
            operator.MosDcCompareRequest(edits=(foreign,)),
        )
    enrollment.write_bytes(contents + b"\n")
    with pytest.raises(ConfigurationError):
        await operator.compare_registered_mos_dc(context, sizing, request)
    assert calls == [(native.query.operation_id, native.plan)] * 3
    assert store.path.read_bytes() == journal
