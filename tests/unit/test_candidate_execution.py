"""Synthetic retained candidate analysis links with no VM or provider calls."""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest
from test_candidate_contracts import candidate_operator, operator
from test_candidate_reports import succeeded

from cadence_mcp_bridge.candidate_contracts import CandidateBatchRequest, prepare_candidate_plan
from cadence_mcp_bridge.candidate_execution import (
    CandidateAnalysisManifest,
    collect_candidate_analyses,
    validate_cross_analysis_conditions,
)
from cadence_mcp_bridge.candidate_reports import CandidateObservation
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration
from cadence_mcp_bridge.native_runtime import KIND
from cadence_mcp_bridge.operator_operations import OperationProgress, OperationRejected
from cadence_mcp_bridge.result_reports import make_report
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["candidate_operator", "operator"]


def analysis_batch(candidate_operator, analysis, change=None):
    context, grant, request, _ = candidate_operator
    document = request.model_dump(mode="json")
    contract = next(
        c
        for c in context.contracts.designs.analyses_for(request.candidates[0].design_id)
        if c.analysis == analysis
    )
    document["batch_id"] = str(uuid4())
    for candidate in document["candidates"]:
        candidate.update(analysis_id=contract.analysis_id, operation_id=str(uuid4()))
    evidence = document["fixed_evidence"]
    evidence["analysis_contract_sha256"] = canonical_digest(contract)
    if analysis == "ac":
        evidence["conditions"].update(
            analysis_inputs=dict(
                analysis="ac", start_hz="100", stop_hz="10000", points_per_decade=1
            ),
            transfer=dict(
                positive_input="input",
                negative_input=None,
                positive_output="output",
                negative_output=None,
                gain_frequencies_hz=["1000"],
            ),
        )
    if analysis == "tran":
        evidence["conditions"]["analysis_inputs"] = dict(
            analysis="tran",
            stop_s="0.004",
            maxstep_s="0.002",
            method="trap",
        )
    if change is not None:
        change(document)
    return prepare_candidate_plan(
        context,
        grant,
        canonical_digest(grant),
        CandidateBatchRequest.model_validate_json(json.dumps(document)),
        100,
    )


def test_join_dc_and_ac_by_exact_candidate_with_all_outcomes(candidate_operator):
    dc = analysis_batch(candidate_operator, "dc")
    ac = analysis_batch(candidate_operator, "ac")
    manifest = CandidateAnalysisManifest(batches=(dc, ac))
    assert manifest.expected_executions == 6
    assert manifest.result_reservation_bytes == 6 * 134217728
    dc_observed = list(succeeded(dc))
    failed = dc_observed[1].record.model_copy(
        update={
            "progress": OperationProgress(
                phase="EXTRACTION_FAILED", remote_revision=5, provider_receipt_sha256="a" * 64
            ),
        }
    )
    dc_observed[1] = CandidateObservation(candidate_id="voltage", record=failed)
    dc_observed[2] = CandidateObservation(candidate_id="mixed")

    dc_report = dc_observed[0].report
    ac_record = dc_observed[0].record.model_copy(
        update={
            "operation_id": ac.request.candidates[0].operation_id,
            "plan": ac.plans[0],
        }
    )
    ac_report = make_report(
        ac_record,
        dict(
            status="NATIVE_RESULT_RETRIEVED",
            operation_id=ac_record.operation_id,
            plan_sha256=ac_record.plan.plan_sha256,
            design_id=ac_record.plan.request.design_id,
            analysis="ac",
            measurement_id=ac.request.fixed_evidence.measurement_id,
            reader_registration_sha256=ac.request.fixed_evidence.reader_registration_sha256,
            execution_input_sha256="d" * 64,
            extraction_receipt_sha256="e" * 64,
            frame_sha256="f" * 64,
            native_provenance="FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
            report_conditions=ac.request.fixed_evidence.conditions.model_dump(mode="json"),
            transfer=[
                dict(
                    frequency_hz=1000.0,
                    gain_v_per_v=2.0,
                    gain_db=6.020599913279624,
                    phase_deg=-90.0,
                )
            ],
        ),
    )
    observations = {
        dc.request.batch_id: tuple(dc_observed),
        ac.request.batch_id: (
            CandidateObservation(candidate_id="baseline", record=ac_record, report=ac_report),
        ),
    }
    results = collect_candidate_analyses(manifest, manifest.manifest_sha256, observations)
    assert [item.candidate_id for item in results] == ["baseline", "voltage", "mixed"]
    assert len({item.revision_sha256 for item in results}) == 3
    assert [tuple(a.status for a in item.analyses) for item in results] == [
        ("SUCCEEDED", "SUCCEEDED"),
        ("EXTRACTION_FAILED", "NOT_OBSERVED"),
        ("NOT_RUN", "NOT_OBSERVED"),
    ]
    assert results[0].revision.values == dc.plans[0].request.values == ac.plans[0].request.values
    assert results[0].analyses[0].row.source_report == dc_report
    assert results[0].analyses[1].row.source_report == ac_report
    assert results[0].analyses[1].row.effective_values is None
    assert results[1].analyses[0].row.source_report is None
    assert results[2].analyses[1].operation_id == ac.request.candidates[2].operation_id
    assert results[2].analyses[1].reason == "retained_observation_not_supplied"
    replay = CandidateAnalysisManifest.model_validate_json(manifest.model_dump_json())
    assert collect_candidate_analyses(replay, manifest.manifest_sha256, observations) == results
    assert not candidate_operator[0].binding.analysis_journal.exists()


@pytest.mark.parametrize("drift", ["source", "testbench", "order", "baseline", "values", "id"])
def test_cross_analysis_drift_is_rejected(candidate_operator, drift):
    dc = analysis_batch(candidate_operator, "dc")

    def mutate(document):
        if drift in ("source", "testbench"):
            document["fixed_evidence"][f"{drift}_revision_sha256"] = "0" * 64
        elif drift == "order":
            document["candidates"].reverse()
        elif drift == "baseline":
            document["baseline_candidate_id"] = "voltage"
        elif drift == "values":
            document["candidates"][1]["values"][0]["value"] = "1.2"
        else:
            document["candidates"][1]["operation_id"] = dc.request.candidates[0].operation_id

    ac = analysis_batch(candidate_operator, "ac", mutate)
    with pytest.raises(ValueError, match="differ|distinct analyses and operation identities"):
        CandidateAnalysisManifest(batches=(dc, ac))


def test_missing_batch_is_unobserved_and_foreign_capture_rejects(candidate_operator):
    dc = analysis_batch(candidate_operator, "dc")
    tran = analysis_batch(candidate_operator, "tran")
    manifest = CandidateAnalysisManifest(batches=(dc, tran))
    observed = succeeded(dc)[0]
    unknown = observed.record.model_copy(
        update={
            "progress": OperationProgress(phase="UNKNOWN_OUTCOME"),
        }
    )
    rows = collect_candidate_analyses(
        manifest,
        manifest.manifest_sha256,
        {
            dc.request.batch_id: (CandidateObservation(candidate_id="baseline", record=unknown),),
        },
    )
    assert rows[0].analyses[0].status == "UNKNOWN_OUTCOME"
    assert rows[0].analyses[1].status == "NOT_OBSERVED"
    assert rows[0].analyses[1].planned_evidence.conditions.analysis_inputs.analysis == "tran"
    with pytest.raises(OperationRejected) as foreign:
        collect_candidate_analyses(
            manifest,
            manifest.manifest_sha256,
            {
                tran.request.batch_id: (observed,),
            },
        )
    assert foreign.value.reason == "candidate_retained_operation_mismatch"
    with pytest.raises(OperationRejected) as digest:
        collect_candidate_analyses(manifest, "0" * 64, {})
    assert digest.value.reason == "candidate_analysis_manifest_digest_mismatch"


def test_mismatched_conditions_keep_source_without_comparable_metrics(candidate_operator):
    dc = analysis_batch(candidate_operator, "dc")
    manifest = CandidateAnalysisManifest(batches=(dc,))
    observation = succeeded(dc)[0]
    report = observation.report
    conditions = report.analysis_conditions.model_copy(
        update={"static_statements_sha256": "0" * 64}
    )
    changed = observation.model_copy(
        update={
            "report": report.model_copy(update={"analysis_conditions": conditions}),
        }
    )
    results = collect_candidate_analyses(
        manifest,
        manifest.manifest_sha256,
        {dc.request.batch_id: (changed,)},
    )
    analysis = results[0].analyses[0]
    assert analysis.status == "CONDITION_MISMATCH"
    assert analysis.reason == "fixed_or_common_conditions_differ"
    assert analysis.row.metrics == ()
    assert analysis.row.source_report == changed.report


def cross_analysis_bundle(candidate_operator, drift):
    batches = []
    routes = []
    for analysis in ("dc", "ac"):

        def conditions(document, analysis=analysis):
            if analysis == "ac":
                saved = document["fixed_evidence"]["conditions"]
                saved["ade_state_tree_sha256"] = "1" * 64
                if drift == "static":
                    saved["static_statements_sha256"] = "2" * 64

        batch = analysis_batch(candidate_operator, analysis, conditions)
        evidence = batch.request.fixed_evidence
        request = batch.plans[0].request
        saved = evidence.conditions
        path = "/synthetic/model.scs"
        ade = AdeExecutionRegistration.model_validate_json(
            _canonical(
                dict(
                    schema_version=1,
                    design_id=request.design_id,
                    analysis_id=request.analysis_id,
                    design_profile_sha256=evidence.design_profile_sha256,
                    variable_set_sha256=None,
                    source_tree_sha256=saved.source_tree_sha256,
                    ade_state_tree_sha256=saved.ade_state_tree_sha256,
                    static_statements_sha256=saved.static_statements_sha256,
                    model_includes=[
                        dict(
                            path=path,
                            section="FF" if analysis == "ac" and drift == "corner" else "NN",
                            file_sha256=saved.model_file_sha256[0],
                        )
                    ],
                    inputs=saved.analysis_inputs.model_dump(mode="json"),
                )
            )
        )
        reader = GenericReaderRegistration.model_validate_json(
            _canonical(
                dict(
                    schema_version=1,
                    design_id=request.design_id,
                    analysis_id=request.analysis_id,
                    measurement_id=evidence.measurement_id,
                    ade_registration_sha256=canonical_digest(ade),
                    measurement_contract_sha256="e" * 64,
                    nodes=[
                        dict(logical_id="input", selector="/vin"),
                        dict(logical_id="output", selector="/vout"),
                    ],
                    sources=[],
                    transfer=None
                    if saved.transfer is None
                    else saved.transfer.model_dump(mode="json"),
                    maximum_samples=8,
                )
            )
        )
        batches.append(
            batch.model_copy(
                update={
                    "request": batch.request.model_copy(
                        update={
                            "fixed_evidence": evidence.model_copy(
                                update={
                                    "reader_registration_sha256": (
                                        "0" * 64
                                        if analysis == "ac" and drift == "reader"
                                        else canonical_digest(reader)
                                    ),
                                }
                            ),
                        }
                    )
                }
            )
        )
        routes.append(
            dict(
                design_id=request.design_id,
                analysis_id=request.analysis_id,
                source_cell="/synthetic/cell",
                model_files=[
                    dict(path=path, file_sha256=saved.model_file_sha256[0]),
                    dict(
                        path="/synthetic/sub.scs",
                        file_sha256=("1" if analysis == "ac" and drift == "dependency" else "0")
                        * 64,
                    ),
                ],
                ade=ade.model_dump(mode="json"),
                reader=reader.model_dump(mode="json"),
            )
        )

    first = batches[0].plans[0]
    registration = _canonical(
        dict(
            schema_version=1,
            environment_sha256=first.environment_sha256,
            design_sha256=first.design_sha256,
            pdk_sha256=first.pdk_sha256,
            routes=routes,
        )
    )
    registration_sha = hashlib.sha256(registration).hexdigest()
    runtime = _canonical(
        dict(
            schema_version=3,
            kind=KIND,
            profile_sha256=first.environment_sha256,
            registration_sha256=registration_sha,
            files={"registration.json": dict(sha256=registration_sha, bytes=len(registration))},
        )
    )
    runner_sha = hashlib.sha256(runtime).hexdigest()
    manifest = CandidateAnalysisManifest(
        batches=tuple(
            batch.model_copy(
                update={
                    "plans": tuple(
                        plan.model_copy(update={"runner_sha256": runner_sha})
                        for plan in batch.plans
                    )
                }
            )
            for batch in batches
        )
    )
    return manifest, runtime, registration + (b" " if drift == "registration" else b"")


@pytest.mark.parametrize(
    ("drift", "reason"),
    [
        (None, None),
        ("static", "candidate_cross_analysis_static_conditions_mismatch"),
        ("corner", "candidate_cross_analysis_source_or_model_mismatch"),
        ("dependency", "candidate_cross_analysis_source_or_model_mismatch"),
        ("reader", "candidate_cross_analysis_route_binding_invalid"),
        ("registration", "candidate_cross_analysis_runtime_binding_invalid"),
    ],
)
def test_cross_analysis_requires_shared_verified_runtime_conditions(
    candidate_operator, drift, reason
):
    assets = cross_analysis_bundle(candidate_operator, drift)
    analyses = frozenset({"dc", "ac"})
    if reason is None:
        validate_cross_analysis_conditions(*assets, analyses=analyses)
    else:
        with pytest.raises(OperationRejected) as rejected:
            validate_cross_analysis_conditions(*assets, analyses=analyses)
        assert rejected.value.reason == reason
