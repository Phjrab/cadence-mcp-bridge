"""Synthetic retained candidate analysis links with no VM or provider calls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_amplifier_specifications import source as amplifier_source
from test_candidate_contracts import candidate_operator, operator
from test_candidate_reports import succeeded
from test_generic_measurements import operator as measurement_operator
from test_generic_measurements import reader_for
from test_operator_operations import operator as operator_base
from test_parameter_changes import _NETLIST, BASELINE, CHILD, _mos, _row

from cadence_mcp_bridge._native_rendering import partition_input, static_fingerprint
from cadence_mcp_bridge.candidate_contracts import CandidateBatchRequest, prepare_candidate_plan
from cadence_mcp_bridge.candidate_execution import (
    AmplifierWidthAnalysis,
    AmplifierWidthAnalysisBinding,
    AmplifierWidthBinding,
    CandidateAnalysisManifest,
    FreshAmplifierOperation,
    FreshAmplifierOperationBinding,
    FreshAmplifierRevisionBinding,
    FreshAmplifierWidthAnalysis,
    FreshAmplifierWidthBinding,
    PmosDcOperation,
    PmosDefaultChangeRequest,
    PmosDefaultChangeResult,
    associate_amplifier_width_pair,
    associate_fresh_amplifier_width_pair,
    associate_pmos_dc_pair,
    associate_saved_width_bias_analysis,
    collect_candidate_analyses,
    validate_cross_analysis_conditions,
)
from cadence_mcp_bridge.candidate_reports import CandidateObservation
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration, ModelInclude
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration, NodeSignal
from cadence_mcp_bridge.native_runtime import KIND
from cadence_mcp_bridge.native_service import NativeOperationQuery
from cadence_mcp_bridge.operator_operations import (
    DurableOperation,
    ExplicitValue,
    OperationProgress,
    OperationRejected,
)
from cadence_mcp_bridge.parameter_changes import (
    ChangeValue,
    DerivedChange,
    DerivedValue,
    plan_mos_width_change,
    verify_change_readback,
)
from cadence_mcp_bridge.result_reports import ReportConditions, make_report
from cadence_mcp_bridge.variable_contracts import canonical_digest

__all__ = ["candidate_operator", "measurement_operator", "operator", "operator_base"]


@pytest.mark.parametrize(
    "drift", [None, "bias", "fixed-bias", "model", "pm0", "source", "input-pin", "alias"]
)
def test_saved_width_bias_reuses_center_across_runtime_and_design_ids(
    measurement_operator, monkeypatch, drift
):
    from cadence_mcp_bridge import candidate_execution

    _, plan, ade, reader, _, _ = reader_for(measurement_operator)
    routes = {}
    monkeypatch.setattr(
        candidate_execution,
        "_width_route",
        lambda op, raw, mode, *, varied_id: routes[op.query.operation_id],
    )
    monkeypatch.setattr(candidate_execution, "_fresh_amplifier_reader", lambda *args: None)

    def point(bias, design, runner, *, candidate=False):
        pm0 = b"130n" if candidate and drift == "pm0" else b"120n"
        input_bias = b"0.322" if candidate and drift == "bias" else bias.encode()
        fixed_bias = b"0.703" if candidate and drift == "fixed-bias" else b"0.702"
        raw = (
            b"simulator lang=spectre\nparameters VBIASN=" + input_bias
            + b" VBIASP=" + fixed_bias + b"\n"
            + b"PM0 (d g s b) gpdk090_pmos1v w=" + pm0 + b" l=1u\n"
            + b"analysis0 dc save=all\n"
        )
        request = plan.request.model_copy(update={
            "design_id": design,
            "values": (ExplicitValue(logical_id="vbiasn", value=bias, unit="V"),),
        })
        child = plan.model_copy(update={"request": request, "runner_sha256": runner})
        query = NativeOperationQuery(
            operation_id=str(uuid4()), expected_plan_sha256=child.plan_sha256
        )
        record = DurableOperation(
            operation_id=query.operation_id,
            plan=child,
            event_count=4,
            progress=OperationProgress(
                phase="FAILED", remote_revision=5, provider_receipt_sha256="b" * 64
            ),
        )
        source = "2" * 64 if candidate and drift == "source" else "3" * 64
        conditions = ReportConditions(
            analysis_inputs=ade.inputs,
            source_tree_sha256=source,
            ade_state_tree_sha256="4" * 64,
            static_statements_sha256="5" * 64,
            model_file_sha256=("6" * 64,),
            transfer=None,
        )
        variable = dict(
            logical_id="vbiasn", cadence_binding="VBIASN", unit="V", value_type="real",
            default=bias, mutation_policy="fixed", range_status="unqualified",
            minimum=None, maximum=None, step_policy="fixed", step=None, fixed_value=bias,
            review_id=None,
        )
        routes[query.operation_id] = (
            dict(variables=[variable], source_cell="/same/cell", libraries=[],
                 ade=ade.model_dump(mode="json")),
            conditions,
            reader,
            ("model-drift",) if candidate and drift == "model" else (),
        )
        return FreshAmplifierOperation(PmosDcOperation(query, child, b"", b"", b"", record), raw)

    center = point("0.32", "saved-width", "7" * 64)
    candidate = point("0.321", "saved-width-bias321", "8" * 64, candidate=True)
    center_sha = hashlib.sha256(center.effective_input).hexdigest()
    candidate_sha = hashlib.sha256(candidate.effective_input).hexdigest()
    saved_width = FreshAmplifierRevisionBinding(
        revision_sha256="9" * 64,
        testbench_revision_sha256="a" * 64,
        source_tree_sha256="3" * 64,
        ade_state_sha256="4" * 64,
        dc=FreshAmplifierOperationBinding(
            operation_id=center.operation.query.operation_id,
            plan_sha256=center.operation.query.expected_plan_sha256,
            input_sha256=center_sha,
        ),
    )
    kwargs = dict(
        saved_width=saved_width,
        baseline_input_sha256=center_sha,
        candidate_input_sha256="0" * 64 if drift == "input-pin" else candidate_sha,
        candidate_query=(
            candidate.operation.query.model_copy(update={"expected_plan_sha256": "1" * 64})
            if drift == "alias" else candidate.operation.query
        ),
        requested_bias=ChangeValue(value="0.321", unit="V"),
    )
    if drift:
        with pytest.raises(OperationRejected) as rejected:
            associate_saved_width_bias_analysis("dc", center, candidate, **kwargs)
        assert rejected.value.reason == "candidate_saved_width_bias_evidence_mismatch"
    else:
        result = associate_saved_width_bias_analysis("dc", center, candidate, **kwargs)
        assert (result.baseline.status, result.candidate.status) == ("FAILED", "FAILED")
        assert result.baseline.value is result.candidate.value is None
        assert result.candidate.operation == candidate.operation.query


@pytest.mark.parametrize(
    "drift",
    [None, "missing", "alias", "section", "graph", "current-only", "input", "root", "extra"],
)
def test_amplifier_requires_pinned_historical_include_equivalence(monkeypatch, drift):
    from cadence_mcp_bridge import candidate_execution
    from cadence_mcp_bridge.generic_ade import ModelInclude

    archived = "/fixture/old/../models/root.scs"
    canonical = ModelInclude(path="/fixture/models/root.scs", section="NN", file_sha256="a" * 64)
    archived_pin = hashlib.sha256(archived.encode("ascii")).hexdigest()
    monkeypatch.setattr(candidate_execution, "_AMP_ARCHIVED_INCLUDE_PATH_SHA256", archived_pin)
    monkeypatch.setattr(
        candidate_execution,
        "_AMP_CANONICAL_INCLUDE_PATH_SHA256",
        hashlib.sha256(canonical.path.encode("ascii")).hexdigest(),
    )
    input_pin, closure = "b" * 64, "c" * 64
    evidence = candidate_execution.AmplifierBaselineIncludeAlias(
        baseline_input_sha256=input_pin,
        archived_path_sha256=archived_pin,
        canonical_include=canonical,
        historical_model_closure_sha256=closure,
        historical_equivalence_receipt_sha256="d" * 64,
    )
    binding = AmplifierWidthAnalysisBinding.model_construct(
        model_includes=(canonical,),
        model_closure_sha256=closure,
        baseline_include_alias=evidence,
    )
    includes = [(archived, "NN")]
    if drift == "missing":
        binding = binding.model_copy(update={"baseline_include_alias": None})
        assert (
            candidate_execution._amp_model_comparison(includes, binding, input_pin)
            == "NOT_EVALUATED"
        )
        assert (
            candidate_execution._amp_model_comparison(
                [(canonical.path, canonical.section)],
                binding,
                input_pin,
            )
            == "MATCHED"
        )
        return
    if drift is None:
        assert candidate_execution._amp_model_comparison(includes, binding, input_pin) == "MATCHED"
        return
    if drift == "alias":
        includes = [(archived.replace("/old/", "/other/"), "NN")]
    elif drift == "section":
        includes = [(archived, "SS")]
    elif drift == "extra":
        includes.append((canonical.path, "NN"))
    elif drift == "graph":
        binding = binding.model_copy(update={"model_closure_sha256": "e" * 64})
    elif drift == "root":
        binding = binding.model_copy(
            update={"model_includes": (canonical.model_copy(update={"file_sha256": "e" * 64}),)}
        )
    elif drift == "current-only":
        binding = binding.model_copy(
            update={
                "baseline_include_alias": evidence.model_copy(
                    update={"historical_equivalence_receipt_sha256": closure}
                )
            }
        )
    else:
        input_pin = "e" * 64
    with pytest.raises(ValueError):
        candidate_execution._amp_model_comparison(includes, binding, input_pin)


@pytest.mark.parametrize(
    "drift",
    [
        None,
        "not-run",
        "failed",
        "duplicate",
        "closure",
        "orientation",
        "ac-control",
        "ac-roundoff",
        "ac-missing",
        "dc-duplicate",
        "dc-missing",
    ],
)
def test_fresh_amplifier_associates_only_bound_native_reports(
    monkeypatch, measurement_operator, drift
):
    from cadence_mcp_bridge import candidate_execution, parameter_changes

    def digest(raw):
        return hashlib.sha256(raw).hexdigest()

    model = ModelInclude(path="/synthetic/amp.scs", section="NN", file_sha256="1" * 64)
    models = [dict(path=model.path, file_sha256=model.file_sha256)]
    pm0 = (
        b"PM0 (net33 Vbiasp VDD VDD) gpdk090_pmos1v w=(20u) l=1u "
        b"as=5.6p ad=5.6p ps=40.56u pd=40.56u m=(1)*(1) simM=(1)*(1)"
    )
    body = (
        b"simulator lang=spectre\nparameters VBIASN=0.320 VBIASP=0.702\n"
        b'include "/synthetic/amp.scs" section=NN\n'
        b"V0 (VDD 0) vsource dc=1\nV5 (VSS 0) vsource dc=0\n" + pm0 + b"\n"
    )
    center = body + b"analysis0 dc save=all\n"
    changed = center.replace(b"w=(20u)", b"w=(120n)")
    monkeypatch.setattr(parameter_changes, "_AMP_CENTER_SHA256", digest(center))
    monkeypatch.setattr(parameter_changes, "_AMP_PM0_STATEMENT_SHA256", digest(pm0))
    original = BASELINE.revision.model_copy(
        update={
            "design_id": "reference-differential-amplifier-tb2",
            "revision_id": "reference-amplifier-bias-grid-v1",
        }
    )
    candidate = CHILD.model_copy(
        update={
            "design_id": original.design_id,
            "parent_revision_id": original.revision_id,
        }
    )
    qualification = _mos()
    qualification = qualification.model_copy(
        update={
            "baseline": BASELINE.model_copy(
                update={"revision": original, "netlist_sha256": digest(center)}
            ),
            "target": qualification.target.model_copy(
                update={
                    "instance": qualification.target.instance.model_copy(
                        update={"instance_path": "PM0"}
                    )
                }
            ),
            "old": ChangeValue(value="20", unit="um"),
            "derived": (
                DerivedChange(
                    before=DerivedValue(property_name="fw", value="20u"),
                    after=DerivedValue(property_name="fw", value="120n"),
                ),
            ),
        }
    )
    plan = plan_mos_width_change(qualification, "amp-child", candidate, qualification.expected)
    old = _row(plan, "baseline").model_copy(update={"revision": original})
    reopened = _row(plan, "reopened").model_copy(update={"revision": candidate})
    netlist = _row(plan, "netlist").model_copy(
        update={"revision": candidate, "artifact_sha256": digest(changed)}
    )
    readback = verify_change_readback(plan, baseline=old, reopened=reopened, netlist=netlist)
    routes = {}
    monkeypatch.setattr(
        candidate_execution, "_width_route", lambda op, raw, mode: routes[op.query.operation_id]
    )

    def side(is_baseline):
        side_tree, ade_tree = ("2" * 64, "3" * 64) if is_baseline else ("4" * 64, "5" * 64)
        circuit = center if is_baseline else changed
        row = old if is_baseline else reopened
        pins, ops = {}, {}
        for mode in ("dc", "ac"):
            if not is_baseline and mode == "ac" and drift == "not-run":
                continue
            raw = (
                circuit
                if mode == "dc"
                else circuit.replace(b"dc save=all", b"ac start=10 stop=100000000 dec=10")
            )
            if not is_baseline and mode == "ac" and drift == "ac-control":
                raw = raw.replace(b"dec=10", b"dec=11")
            _, ap, ade, reader, _, _ = reader_for(measurement_operator, mode)
            ap = ap.model_copy(update={"runner_sha256": side_tree})
            ade = ade.model_copy(update={"model_includes": (model,)})
            if mode == "ac":
                ade = ade.model_copy(
                    update={
                        "inputs": ade.inputs.model_copy(
                            update={
                                "start_hz": "10",
                                "stop_hz": "100000000",
                                "points_per_decade": 10,
                            }
                        )
                    }
                )
            definition = reader.model_dump(mode="json")
            if mode == "dc":
                definition["nodes"] = [
                    dict(logical_id=n.lower(), selector="/" + n) for n in ("VDD", "VSS")
                ]
                template = definition["sources"][0]
                definition["sources"] = [
                    {
                        **template,
                        "source_id": "vdd",
                        "role": "supply",
                        "positive_node": "vdd",
                        "negative_node": None,
                        "current_selector": "/V0/PLUS",
                    },
                    {
                        **template,
                        "source_id": "vss",
                        "role": "supply",
                        "positive_node": "vss",
                        "negative_node": None,
                        "current_selector": "/V5/PLUS",
                    },
                ]
                if not is_baseline and drift == "orientation":
                    definition["sources"][0]["negative_node"] = "vss"
            else:
                definition["nodes"] = [
                    dict(logical_id=n.lower(), selector="/" + n) for n in ("Vp", "Vm", "Vop", "Vom")
                ]
                definition["transfer"] = dict(
                    positive_input="vp",
                    negative_input="vm",
                    positive_output="vop",
                    negative_output="vom",
                    gain_frequencies_hz=["10"],
                )
            reader = GenericReaderRegistration.model_validate_json(json.dumps(definition))
            conditions = ReportConditions(
                analysis_inputs=ade.inputs,
                source_tree_sha256=side_tree,
                ade_state_tree_sha256=ade_tree,
                static_statements_sha256=ade.static_statements_sha256,
                model_file_sha256=(model.file_sha256,),
                transfer=reader.transfer,
            )
            identity = (
                str(uuid4()) if drift != "duplicate" else "b130b66e-7f23-47c0-87ef-df1029ce5720"
            )
            query = NativeOperationQuery(operation_id=identity, expected_plan_sha256=ap.plan_sha256)
            phase = (
                "FAILED" if not is_baseline and mode == "ac" and drift == "failed" else "SUCCEEDED"
            )
            record = DurableOperation(
                operation_id=identity,
                plan=ap,
                event_count=4,
                progress=OperationProgress(
                    phase=phase, remote_revision=5, provider_receipt_sha256="b" * 64
                ),
            )
            report_raw = None
            if phase == "SUCCEEDED":
                report_raw = (
                    make_report(
                        record,
                        dict(
                            status="NATIVE_RESULT_RETRIEVED",
                            operation_id=identity,
                            plan_sha256=ap.plan_sha256,
                            design_id=ade.design_id,
                            analysis=mode,
                            measurement_id=reader.measurement_id,
                            reader_registration_sha256=canonical_digest(reader),
                            execution_input_sha256=digest(raw),
                            extraction_receipt_sha256="d" * 64,
                            frame_sha256="e" * 64,
                            native_provenance="FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
                            report_conditions=conditions.model_dump(mode="json"),
                            nodes=[],
                            sources=[
                                dict(source_id="vdd", role="supply", delivered_w=0.003),
                                dict(source_id="vss", role="supply", delivered_w=0.0),
                            ],
                            transfer=[
                                dict(
                                    frequency_hz=10.0,
                                    gain_v_per_v=10000.0,
                                    gain_db=80.0,
                                    phase_deg=0.0,
                                )
                            ],
                        ),
                    )
                    .model_dump_json()
                    .encode()
                )
            if not is_baseline and report_raw is not None:
                saved = json.loads(report_raw)
                if mode == "ac" and drift in ("ac-roundoff", "ac-missing"):
                    for metric in saved["metrics"]:
                        metric["frequency_hz"] = 10.000000000005 if drift == "ac-roundoff" else 10.1
                if mode == "dc" and drift == "dc-duplicate":
                    saved["metrics"].append({**saved["metrics"][0], "sample_count": 2})
                if mode == "dc" and drift == "dc-missing":
                    saved["metrics"].pop()
                report_raw = json.dumps(saved).encode()
            route_models = [] if not is_baseline and drift == "closure" else models
            routes[identity] = (
                dict(ade=ade.model_dump(mode="json"), model_files=route_models),
                conditions,
                reader,
                (),
            )
            op = PmosDcOperation(
                query,
                ap,
                b"",
                b"",
                b"",
                record,
                report_raw,
                None if report_raw is None else digest(report_raw),
                "b" * 64,
            )
            ops[mode] = FreshAmplifierOperation(op, raw)
            pins[mode] = FreshAmplifierOperationBinding(
                operation_id=identity, plan_sha256=ap.plan_sha256, input_sha256=digest(raw)
            )
        return ops, FreshAmplifierRevisionBinding(
            revision_sha256=row.revision_sha256,
            testbench_revision_sha256=row.testbench_revision_sha256,
            source_tree_sha256=side_tree,
            ade_state_sha256=ade_tree,
            **pins,
        )

    baseline_ops, baseline_binding = side(True)
    candidate_ops, candidate_binding = side(False)
    binding = FreshAmplifierWidthBinding(
        change_plan_sha256=plan.plan_sha256,
        readback_sha256=canonical_digest(readback),
        canonical_model_include=model,
        diagnostic_model_closure_sha256=digest(_canonical(models)),
        diagnostic_model_receipt_sha256="6" * 64,
        baseline=baseline_binding,
        candidate=candidate_binding,
    )
    raw = binding.model_dump_json().encode()

    def compare_pair():
        return associate_fresh_amplifier_width_pair(
            plan,
            readback,
            expected_plan_sha256=plan.plan_sha256,
            baseline_input=center,
            candidate_input=changed,
            registration_evidence=raw,
            expected_registration_sha256=digest(raw),
            dc=FreshAmplifierWidthAnalysis(baseline_ops["dc"], candidate_ops["dc"]),
            ac=FreshAmplifierWidthAnalysis(baseline_ops["ac"], candidate_ops.get("ac")),
        )

    if drift in ("duplicate", "closure", "orientation", "ac-control", "dc-duplicate"):
        with pytest.raises(OperationRejected) as rejected:
            compare_pair()
        assert rejected.value.reason == "candidate_fresh_amplifier_width_evidence_mismatch"
        return
    result = compare_pair()
    assert result.dc.baseline.value == 0.003
    assert result.dc.candidate.value == (None if drift == "dc-missing" else 0.003)
    assert result.ac.baseline.value == 80.0
    assert result.ac.candidate.status == {"not-run": "NOT_RUN", "failed": "FAILED"}.get(
        drift, "SUCCEEDED"
    )
    assert result.ac.candidate.value == (
        None if drift in ("not-run", "failed", "ac-missing") else 80.0
    )
    assert result.goals == "GOALS_NOT_PROVIDED" and result.selected_candidate_id is None
    assert not result.execution_authorized


@pytest.fixture
async def amplifier_width_evidence(tmp_path, monkeypatch, measurement_operator):
    from cadence_mcp_bridge import candidate_execution, parameter_changes

    def digest(raw):
        return hashlib.sha256(raw).hexdigest()

    pm0 = (
        b"PM0 (net33 Vbiasp VDD VDD) gpdk090_pmos1v w=(20u) l=1u "
        b"as=5.6p ad=5.6p ps=40.56u pd=40.56u m=(1)*(1) simM=(1)*(1)"
    )
    common = b"simulator lang=spectre\nparameters VBIASN=320m VBIASP=702m\n" + pm0 + b"\n"
    directive = b"dcOpInfo info what=oppoint where=rawfile"
    monkeypatch.setattr(candidate_execution, "_AMP_DC_OUTPUT_DIRECTIVE_SHA256", digest(directive))
    dc_raw = common + b"analysis0 dc save=all\n" + directive + b"\n"
    ac_raw = common + b"analysis0 ac start=10 stop=100000000 dec=10\n"
    child_raw = dc_raw.replace(b"w=(20u)", b"w=(19u)")
    monkeypatch.setattr(parameter_changes, "_AMP_CENTER_SHA256", digest(dc_raw))
    monkeypatch.setattr(parameter_changes, "_AMP_PM0_STATEMENT_SHA256", digest(pm0))
    baseline = BASELINE.model_copy(
        update={
            "netlist_sha256": digest(dc_raw),
            "revision": BASELINE.revision.model_copy(
                update={
                    "design_id": "reference-differential-amplifier-tb2",
                    "revision_id": "reference-amplifier-bias-grid-v1",
                }
            ),
        }
    )
    candidate = CHILD.model_copy(
        update={
            "design_id": baseline.revision.design_id,
            "parent_revision_id": baseline.revision.revision_id,
        }
    )
    original = _mos()
    qualification = original.model_copy(
        update={
            "baseline": baseline,
            "target": original.target.model_copy(
                update={
                    "instance": original.target.instance.model_copy(update={"instance_path": "PM0"})
                }
            ),
            "old": ChangeValue(value="20", unit="um"),
            "expected": ChangeValue(value="19", unit="um"),
            "derived": (
                DerivedChange(
                    before=DerivedValue(property_name="fw", value="20u"),
                    after=DerivedValue(property_name="fw", value="19u"),
                ),
            ),
        }
    )
    plan = plan_mos_width_change(qualification, "amp-child", candidate, qualification.expected)
    old = _row(plan, "baseline").model_copy(update={"revision": baseline.revision})
    reopened = _row(plan, "reopened").model_copy(update={"revision": candidate})
    netlist = _row(plan, "netlist").model_copy(
        update={"revision": candidate, "artifact_sha256": digest(child_raw)}
    )
    readback = verify_change_readback(plan, baseline=old, reopened=reopened, netlist=netlist)

    async def analysis(mode, raw):
        root = tmp_path / mode
        root.mkdir()
        _, _, sweep = await amplifier_source(root, mode)
        center = sweep.measurements[1].model_copy(update={"input_sha256": digest(raw)})
        sweep = sweep.model_copy(
            update={"measurements": (sweep.measurements[0], center, sweep.measurements[2])}
        )
        _, _, _, reader, _, _ = reader_for(measurement_operator, mode)
        binding = AmplifierWidthAnalysisBinding(
            baseline_operation_id=str(center.job_id),
            baseline_plan_sha256=sweep.engine.plan_hash,
            baseline_reader=reader,
            model_includes=(),
            model_closure_sha256=digest(_canonical([])),
        )
        return AmplifierWidthAnalysis(sweep, canonical_digest(sweep), raw), binding

    dc, dc_binding = await analysis("dc", dc_raw)
    ac, ac_binding = await analysis("ac", ac_raw)
    binding = AmplifierWidthBinding(
        change_plan_sha256=plan.plan_sha256,
        readback_sha256=canonical_digest(readback),
        baseline_revision_sha256=old.revision_sha256,
        baseline_testbench_revision_sha256=old.testbench_revision_sha256,
        child_revision_sha256=reopened.revision_sha256,
        child_testbench_revision_sha256=reopened.testbench_revision_sha256,
        child_source_tree_sha256="8" * 64,
        child_ade_state_sha256="9" * 64,
        dc=dc_binding,
        ac=ac_binding,
    )
    return plan, readback, binding, dc, ac, child_raw


def run_amplifier_pair(evidence, *, drift=None, child_fixture=None):
    plan, readback, binding, dc, ac, child_raw = evidence
    if drift == "baseline-input":
        ac = replace(ac, baseline_input=ac.baseline_input.replace(b"320m", b"321m"))
    if drift == "wrong-original-id":
        binding = binding.model_copy(
            update={
                "dc": binding.dc.model_copy(
                    update={"baseline_operation_id": binding.ac.baseline_operation_id}
                )
            }
        )
    if drift == "wrong-child-revision":
        binding = binding.model_copy(update={"child_revision_sha256": "0" * 64})
    if drift == "reused-baseline-testbench":
        baseline_tb = readback.baseline.testbench_revision_sha256
        reopened = readback.reopened.model_copy(update={"testbench_revision_sha256": baseline_tb})
        netlist = readback.netlist.model_copy(update={"testbench_revision_sha256": baseline_tb})
        readback = verify_change_readback(
            plan, baseline=readback.baseline, reopened=reopened, netlist=netlist
        )
        assert readback.status == "MATCHED"
        binding = binding.model_copy(
            update={
                "child_testbench_revision_sha256": baseline_tb,
                "readback_sha256": canonical_digest(readback),
            }
        )
    if drift == "unauthorized-geometry":
        child_raw = child_raw.replace(b"as=5.6p", b"as=5.7p")
    if drift == "ac-circuit":
        raw = ac.baseline_input + b"CL (Vop 0) capacitor c=1p\n"
        center = ac.baseline.measurements[1].model_copy(
            update={"input_sha256": hashlib.sha256(raw).hexdigest()}
        )
        sweep = ac.baseline.model_copy(
            update={
                "measurements": (ac.baseline.measurements[0], center, ac.baseline.measurements[2])
            }
        )
        ac = replace(
            ac, baseline=sweep, expected_baseline_sha256=canonical_digest(sweep), baseline_input=raw
        )
    if child_fixture is not None:
        dc, dc_binding = child_fixture(dc, binding.dc, "dc")
        ac, ac_binding = child_fixture(ac, binding.ac, "ac")
        binding = binding.model_copy(update={"dc": dc_binding, "ac": ac_binding})
    if drift == "ac-grid":
        ac = replace(ac, child_input=ac.child_input.replace(b"dec=10", b"dec=11"))
        binding = binding.model_copy(
            update={
                "ac": binding.ac.model_copy(
                    update={"child_input_sha256": hashlib.sha256(ac.child_input).hexdigest()}
                )
            }
        )
    if drift == "unobserved-ac":
        ac = replace(
            ac,
            child=replace(
                ac.child,
                record=None,
                report=None,
                expected_report_sha256=None,
                expected_terminal_sha256=None,
            ),
        )
    registration = binding.model_dump_json().encode()
    return associate_amplifier_width_pair(
        plan,
        readback,
        expected_plan_sha256=plan.plan_sha256,
        baseline_input=dc.baseline_input,
        candidate_input=child_raw,
        registration_evidence=registration,
        expected_registration_sha256=hashlib.sha256(registration).hexdigest(),
        dc=dc,
        ac=ac,
    )


def test_amplifier_width_pair_preserves_original_dc_ac_and_unrun_child(amplifier_width_evidence):
    pair = run_amplifier_pair(amplifier_width_evidence)
    _, _, binding, _, _, _ = amplifier_width_evidence
    assert str(pair.dc.baseline.job_id) == binding.dc.baseline_operation_id
    assert str(pair.ac.baseline.job_id) == binding.ac.baseline_operation_id
    assert (pair.dc.baseline_value, pair.ac.baseline_value) == (0.002, 60.0)
    assert (pair.dc.child_status, pair.ac.child_status) == ("NOT_RUN", "NOT_RUN")
    assert pair.dc.child_value is pair.ac.child_value is None
    assert pair.dc.dc_output_reason == "baseline_output_scalars_not_retained"
    assert pair.goals == "GOALS_NOT_PROVIDED" and not pair.execution_authorized


def test_amplifier_cross_analysis_body_omits_only_the_pinned_dc_directive(monkeypatch):
    from cadence_mcp_bridge import candidate_execution

    directive = "dcOpInfo info what=oppoint where=rawfile"
    other_info = "other info what=oppoint where=rawfile"
    monkeypatch.setattr(
        candidate_execution,
        "_AMP_DC_OUTPUT_DIRECTIVE_SHA256",
        hashlib.sha256(directive.encode("ascii")).hexdigest(),
    )
    assert candidate_execution._amplifier_cross_analysis_body(
        ["circuit statement", directive, other_info]
    ) == ["circuit statement", other_info]
    with pytest.raises(ValueError):
        candidate_execution._amplifier_cross_analysis_body([directive, directive])


@pytest.fixture
def amplifier_child_fixture(monkeypatch, measurement_operator):
    from cadence_mcp_bridge import candidate_execution

    routes = {}
    # The P120 fixtures exercise the common compiled-route validator end to end.
    monkeypatch.setattr(candidate_execution, "_width_route", lambda op, _raw, mode: routes[mode])

    def child(evidence, binding, mode):
        raw = evidence.baseline_input.replace(b"w=(20u)", b"w=(19u)")
        _, plan, ade, reader, _, _ = reader_for(measurement_operator, mode)
        reader_doc = reader.model_dump(mode="json")
        if mode == "dc":
            reader_doc["nodes"] = [
                dict(logical_id=n.lower(), selector="/" + n) for n in ("VDD", "VSS")
            ]
            reader_doc["sources"][0].update(
                source_id="vdd",
                current_selector="/VDD/PLUS",
                positive_node="vdd",
                negative_node=None,
            )
            reader_doc["sources"].append(
                {
                    **reader_doc["sources"][0],
                    "source_id": "vss",
                    "current_selector": "/VSS/PLUS",
                    "positive_node": "vss",
                }
            )
        else:
            reader_doc["nodes"] = [
                dict(logical_id=n.lower(), selector="/" + n) for n in ("Vp", "Vm", "Vop", "Vom")
            ]
            reader_doc["transfer"] = dict(
                positive_input="vp",
                negative_input="vm",
                positive_output="vop",
                negative_output="vom",
                gain_frequencies_hz=["10"],
            )
        reader = GenericReaderRegistration.model_validate_json(json.dumps(reader_doc))
        conditions = dict(
            analysis_inputs=ade.inputs.model_dump(mode="json"),
            source_tree_sha256="8" * 64,
            ade_state_tree_sha256="9" * 64,
            static_statements_sha256=ade.static_statements_sha256,
            model_file_sha256=[],
            transfer=reader_doc["transfer"],
        )
        query = NativeOperationQuery(
            operation_id=str(uuid4()), expected_plan_sha256=plan.plan_sha256
        )
        record = DurableOperation(
            operation_id=query.operation_id,
            plan=plan,
            event_count=4,
            progress=OperationProgress(
                phase="SUCCEEDED", remote_revision=5, provider_receipt_sha256="b" * 64
            ),
        )
        report = make_report(
            record,
            dict(
                status="NATIVE_RESULT_RETRIEVED",
                operation_id=query.operation_id,
                plan_sha256=plan.plan_sha256,
                design_id=ade.design_id,
                analysis=mode,
                measurement_id=reader.measurement_id,
                reader_registration_sha256=canonical_digest(reader),
                execution_input_sha256=hashlib.sha256(raw).hexdigest(),
                extraction_receipt_sha256="d" * 64,
                frame_sha256="e" * 64,
                native_provenance="FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
                report_conditions=conditions,
                nodes=[],
                sources=[
                    dict(source_id="vdd", role="supply", delivered_w=0.003),
                    dict(source_id="vss", role="supply", delivered_w=0.0),
                ],
                transfer=[
                    dict(frequency_hz=10.0, gain_v_per_v=10000.0, gain_db=80.0, phase_deg=0.0)
                ],
            ),
        )
        routes[mode] = (
            dict(ade=ade.model_dump(mode="json"), model_files=[]),
            report.analysis_conditions,
            reader,
            (),
        )
        report_raw = report.model_dump_json().encode()
        operation = PmosDcOperation(
            query,
            plan,
            b"",
            b"",
            b"",
            record,
            report_raw,
            hashlib.sha256(report_raw).hexdigest(),
            "b" * 64,
        )
        return replace(evidence, child=operation, child_input=raw), binding.model_copy(
            update={
                "baseline_reader": reader,
                "child_operation_id": query.operation_id,
                "child_plan_sha256": plan.plan_sha256,
                "child_input_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )

    return child


def test_amplifier_width_pair_binds_succeeded_child_analyses(
    amplifier_width_evidence,
    amplifier_child_fixture,
):
    pair = run_amplifier_pair(amplifier_width_evidence, child_fixture=amplifier_child_fixture)
    assert (pair.dc.child_status, pair.ac.child_status) == ("SUCCEEDED", "SUCCEEDED")
    assert pair.dc.child_operation.operation_id == pair.dc.child_report.operation_id
    assert pair.ac.child_operation.operation_id == pair.ac.child_report.operation_id
    assert (pair.dc.child_value, pair.ac.child_value) == (0.003, 80.0)


def test_amplifier_width_pair_preserves_unobserved_child_operation(
    amplifier_width_evidence,
    amplifier_child_fixture,
):
    pair = run_amplifier_pair(
        amplifier_width_evidence, drift="unobserved-ac", child_fixture=amplifier_child_fixture
    )
    assert pair.dc.child_status == "SUCCEEDED"
    assert pair.ac.child_status == "NOT_OBSERVED"
    assert pair.ac.child_operation is not None
    assert pair.ac.child_report is pair.ac.child_value is None


@pytest.mark.parametrize("drift", ["ac-grid", "ac-circuit"])
def test_amplifier_width_pair_rejects_ac_drift(
    amplifier_width_evidence,
    amplifier_child_fixture,
    drift,
):
    with pytest.raises(OperationRejected) as rejected:
        run_amplifier_pair(
            amplifier_width_evidence, drift=drift, child_fixture=amplifier_child_fixture
        )
    assert rejected.value.reason == "candidate_amplifier_width_evidence_mismatch"


@pytest.mark.parametrize(
    "drift",
    [
        "baseline-input",
        "wrong-original-id",
        "wrong-child-revision",
        "unauthorized-geometry",
        "reused-baseline-testbench",
    ],
)
def test_amplifier_width_pair_rejects_changed_evidence(amplifier_width_evidence, drift):
    with pytest.raises(OperationRejected) as rejected:
        run_amplifier_pair(amplifier_width_evidence, drift=drift)
    assert rejected.value.reason == "candidate_amplifier_width_evidence_mismatch"


@pytest.fixture
def registered_pmos_change():
    qualification = _mos()
    plan = plan_mos_width_change(qualification, "candidate", CHILD, qualification.expected)
    request = PmosDefaultChangeRequest(
        operation_id=str(uuid4()),
        expected_plan_sha256=plan.plan_sha256,
        expected_scope_sha256="a" * 64,
    )
    result = {
        "operation_id": request.operation_id,
        "plan_sha256": plan.plan_sha256,
        "scope_sha256": "a" * 64,
        "outcome": "VERIFIED",
        "replayed": False,
        "dispatched_this_call": True,
        "candidate_revision": plan.candidate_revision,
        "observed_revision_sha256": "b" * 64,
        "observed_testbench_revision_sha256": "c" * 64,
        "source_preservation_sha256": "d" * 64,
        "reopen_receipt_sha256": "e" * 64,
        "netlist_receipt_sha256": "f" * 64,
        "netlist_sha256": "0" * 64,
    }
    return plan, request, result


def test_registered_pmos_change_request_is_closed(registered_pmos_change):
    _, request, _ = registered_pmos_change
    payload = request.model_dump()
    assert PmosDefaultChangeRequest.model_validate(payload) == request
    with pytest.raises(ValidationError):
        PmosDefaultChangeRequest.model_validate({**payload, "requires_netlist": True})
    with pytest.raises(ValidationError):
        PmosDefaultChangeRequest.model_validate({**payload, "operation_id": "invalid"})


@pytest.mark.parametrize(
    "override",
    [
        {"source_preservation_sha256": None},
        {"observed_testbench_revision_sha256": None},
        {"reopen_receipt_sha256": None},
        {"replayed": True},
        {"dispatched_this_call": None},
        {"netlist_sha256": None},
        {"netlist_receipt_sha256": None, "netlist_sha256": None},
        {"new_simulations": 1},
        {"new_reservations": 1},
    ],
)
def test_registered_pmos_change_rejects_inconsistent_result(registered_pmos_change, override):
    _, _, fields = registered_pmos_change
    with pytest.raises(ValidationError):
        PmosDefaultChangeResult.model_validate({**fields, **override})


def test_registered_pmos_change_checks_exact_scope_and_required_receipt(registered_pmos_change):
    plan, request, fields = registered_pmos_change

    result = PmosDefaultChangeResult.model_validate(fields)
    result.check_registered_scope(request, registered_plan=plan, registered_scope_sha256="a" * 64)
    with pytest.raises(OperationRejected) as rejected:
        result.check_registered_scope(
            request, registered_plan=plan, registered_scope_sha256="0" * 64
        )
    assert rejected.value.reason == "pmos_default_change_identity_mismatch"


def test_registered_pmos_change_preserves_replayed_partial_evidence(registered_pmos_change):
    plan, request, fields = registered_pmos_change
    result = PmosDefaultChangeResult.model_validate(
        {
            **fields,
            "outcome": "OUTCOME_UNKNOWN",
            "replayed": True,
            "dispatched_this_call": False,
            "netlist_receipt_sha256": None,
            "netlist_sha256": None,
            "reason": "netlist_receipt_unavailable",
        }
    )
    result.check_registered_scope(
        request,
        registered_plan=plan,
        registered_scope_sha256="a" * 64,
    )
    assert result.reopen_receipt_sha256 == "e" * 64
    assert result.netlist_receipt_sha256 is None
    assert result.new_simulations == result.new_reservations == 0


@pytest.fixture
def pmos_pair(measurement_operator):
    context, plan, original_ade, original_reader, _, _ = reader_for(measurement_operator)
    original_reader = original_reader.model_copy(
        update={
            "nodes": (
                NodeSignal(logical_id="cmos-vin", selector="/in"),
                NodeSignal(logical_id="cmos-vout", selector="/out"),
                NodeSignal(logical_id="cmos-vdd", selector="/vdd"),
            ),
            "sources": (
                original_reader.sources[0].model_copy(
                    update={
                        "source_id": "supply-rail",
                        "positive_node": "cmos-vdd",
                        "negative_node": None,
                    }
                ),
            ),
        }
    )
    registry = context.binding.design_registry.read_bytes()
    raw = (
        _NETLIST.replace(b"m2_vin=0", b"ExampleBiasN=1 ExampleBiasP=1").replace(
            b"dc=m2_vin", b"dc=ExampleBiasN"
        )
        + b"analysis0 dc save=all\n"
    )
    changed = raw.replace(b"(350n)", b"(120n)")
    baseline = BASELINE.model_copy(update={"netlist_sha256": hashlib.sha256(raw).hexdigest()})
    qualification = _mos().model_copy(update={"baseline": baseline})
    change = plan_mos_width_change(qualification, "candidate", CHILD, qualification.expected)
    reopened = _row(change, "reopened")
    netlist = _row(change, "netlist").model_copy(
        update={"artifact_sha256": hashlib.sha256(changed).hexdigest()}
    )
    readback = verify_change_readback(
        change,
        baseline=_row(change, "baseline"),
        reopened=reopened,
        netlist=netlist,
    )
    receipt = dict(
        status="OWNED_INPUT_COPY_VERIFIED",
        scope_sha256="d" * 64,
        copy_id=str(uuid4()),
        source_revision_sha256=reopened.revision_sha256,
        reopen_receipt_sha256="a" * 64,
        source_ade_sha256=original_ade.ade_state_tree_sha256,
        source_cell="/synthetic/child/"
        + context.contracts.designs.profile(plan.request.design_id).binding.cell,
        source_state="/synthetic/child/ade",
        source_cell_sha256="6" * 64,
        source_state_sha256="7" * 64,
        library_path="/synthetic/child",
        dependency_tree_sha256="8" * 64,
    )

    def operation(child, drift=None):
        profile = context.contracts.designs.profile(plan.request.design_id)
        variables = context.contracts.designs.variable_set(plan.request.design_id).variables
        ade = original_ade.model_copy(
            update={
                "source_tree_sha256": receipt["source_cell_sha256"] if child else "1" * 64,
                "ade_state_tree_sha256": receipt["source_state_sha256"] if child else "2" * 64,
                "static_statements_sha256": static_fingerprint(
                    partition_input(changed if child else raw)[3]
                ),
            }
        )
        reader = original_reader.model_copy(
            update={"ade_registration_sha256": canonical_digest(ade)}
        )
        if drift == "reader":
            reader = reader.model_copy(update={"maximum_samples": reader.maximum_samples + 1})
        route = dict(
            analysis="dc",
            design_id=plan.request.design_id,
            analysis_id=plan.request.analysis_id,
            source_cell=receipt["source_cell"]
            if child
            else "/synthetic/parent/" + profile.binding.cell,
            source_state=receipt["source_state"] if child else "/synthetic/parent/ade",
            libraries=[
                dict(
                    name=profile.binding.library,
                    path=receipt["library_path"] if child else "/synthetic/parent",
                    tree_sha256=receipt["dependency_tree_sha256"],
                )
            ],
            model_files=[dict(path="/synthetic/other.scs", file_sha256="a" * 64)]
            if drift == "model"
            else [],
            profile=profile.model_dump(mode="json"),
            variables=[variable.model_dump(mode="json") for variable in variables],
            ade=ade.model_dump(mode="json"),
            reader=reader.model_dump(mode="json"),
        )
        registration = _canonical(
            dict(
                schema_version=1,
                environment_sha256=plan.environment_sha256,
                design_sha256=plan.design_sha256,
                pdk_sha256=plan.pdk_sha256,
                routes=[route],
            )
        )
        digest = hashlib.sha256(registration).hexdigest()
        runtime = _canonical(
            dict(
                schema_version=3,
                kind=KIND,
                profile_sha256=plan.environment_sha256,
                registration_sha256=digest,
                files={"registration.json": dict(sha256=digest, bytes=len(registration))},
            )
        )
        bound = plan.model_copy(update={"runner_sha256": hashlib.sha256(runtime).hexdigest()})
        identity = str(uuid4())
        query = NativeOperationQuery(operation_id=identity, expected_plan_sha256=bound.plan_sha256)
        record = DurableOperation(
            operation_id=identity,
            plan=bound,
            event_count=3,
            progress=OperationProgress(
                phase="SUCCEEDED", remote_revision=5, provider_receipt_sha256="b" * 64
            ),
        )
        nodes = [
            dict(logical_id="cmos-vin", value=0.0, unit="V"),
            dict(logical_id="cmos-vout", value=0.8 if child else 1.0, unit="V"),
            dict(logical_id="cmos-vdd", value=0.95 if drift == "rail" else 1.0, unit="V"),
        ]
        if child:
            nodes.reverse()
        if drift == "vin-missing":
            nodes.pop()
        report = (
            make_report(
                record,
                dict(
                    status="NATIVE_RESULT_RETRIEVED",
                    operation_id=identity,
                    plan_sha256=bound.plan_sha256,
                    design_id=plan.request.design_id,
                    analysis="dc",
                    measurement_id=reader.measurement_id,
                    reader_registration_sha256=canonical_digest(reader),
                    execution_input_sha256="c" * 64,
                    extraction_receipt_sha256="d" * 64,
                    frame_sha256="e" * 64,
                    native_provenance="FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
                    report_conditions=dict(
                        analysis_inputs=ade.inputs.model_dump(mode="json"),
                        source_tree_sha256=ade.source_tree_sha256,
                        ade_state_tree_sha256=ade.ade_state_tree_sha256,
                        static_statements_sha256=ade.static_statements_sha256,
                        model_file_sha256=[],
                        transfer=None,
                    ),
                    nodes=nodes,
                    sources=[]
                    if drift == "power-missing"
                    else [
                        dict(
                            source_id="supply-rail",
                            role="bias" if drift == "power-role" else "supply",
                            delivered_w=1e-7,
                        )
                    ],
                ),
            )
            .model_dump_json()
            .encode()
        )
        return PmosDcOperation(
            query,
            bound,
            runtime,
            registration,
            registry,
            record,
            report,
            hashlib.sha256(report).hexdigest(),
            "b" * 64,
        )

    return change, readback, raw, changed, receipt, operation


def pmos_association(pmos_pair, drift=None):
    change, readback, raw, changed, receipt, operation = pmos_pair
    baseline, child = operation(False), operation(True, drift)
    if drift == "copy":
        receipt["dependency_tree_sha256"] = "9" * 64
    if drift == "analysis":
        changed_plan = child.plan.model_copy(update={"analysis": "tran"})
        child = replace(
            child,
            plan=changed_plan,
            query=child.query.model_copy(
                update={
                    "expected_plan_sha256": changed_plan.plan_sha256,
                }
            ),
        )
    if drift == "report":
        child = replace(child, expected_report_sha256="0" * 64)
    if drift == "pending":
        child = replace(child, record=None, report=None, expected_terminal_sha256=None)
    if drift == "capture-missing":
        child = replace(child, report=None)
    if drift == "unknown":
        child = replace(
            child,
            report=None,
            record=child.record.model_copy(
                update={
                    "progress": child.record.progress.model_copy(
                        update={"phase": "UNKNOWN_OUTCOME"}
                    ),
                }
            ),
        )
    copy = _canonical(receipt)
    return associate_pmos_dc_pair(
        change,
        readback,
        expected_plan_sha256=change.plan_sha256,
        baseline_input=raw,
        candidate_input=changed,
        copy_receipt=copy,
        expected_copy_receipt_sha256=hashlib.sha256(copy).hexdigest(),
        expected_copy_scope_sha256="d" * 64,
        expected_copy_id=receipt["copy_id"],
        expected_reopen_receipt_sha256="a" * 64,
        baseline=baseline,
        candidate=child,
    )


def test_pmos_pair_preserves_separate_reports_and_unobserved_child(pmos_pair):
    result = pmos_association(pmos_pair)
    base, child = result.rows
    assert (base.status, child.status) == ("SUCCEEDED", "SUCCEEDED")
    assert base.revision_sha256 != child.revision_sha256
    assert base.report.operation_id == base.operation.operation_id
    assert child.report.operation_id == child.operation.operation_id
    assert child.effective_width.value == "120"
    vout, power = result.metrics
    assert (vout.baseline.value, vout.candidate.value) == (1.0, 0.8)
    assert (power.baseline.value, power.candidate.value) == (1e-7, 1e-7)
    assert result.goals == "GOALS_NOT_PROVIDED" and not result.execution_authorized
    pending = pmos_association(pmos_pair, "pending").rows[1]
    assert pending.status == "NOT_OBSERVED" and pending.report is None
    assert pending.reason == "retained_operation_not_supplied"
    unknown = pmos_association(pmos_pair, "unknown").rows[1]
    assert unknown.status == "UNKNOWN_OUTCOME" and unknown.report is None
    assert unknown.reason == "retained_operation_not_succeeded"
    assert unknown.terminal_receipt_sha256 == "b" * 64
    capture_missing = pmos_association(pmos_pair, "capture-missing").rows[1]
    assert capture_missing.status == "SUCCEEDED" and capture_missing.report is None
    assert capture_missing.reason == "retained_result_unavailable"


def test_pmos_pair_preserves_vout_when_power_is_missing(pmos_pair):
    vout, power = pmos_association(pmos_pair, "power-missing").metrics
    assert vout.candidate.value == 0.8
    assert power.baseline.value == 1e-7 and power.candidate is None


@pytest.mark.parametrize(
    "drift", ["analysis", "model", "reader", "copy", "report", "rail", "vin-missing", "power-role"]
)
def test_pmos_pair_rejects_unbound_or_incomparable_evidence(pmos_pair, drift):
    with pytest.raises(OperationRejected) as rejected:
        pmos_association(pmos_pair, drift)
    assert rejected.value.reason == "candidate_pmos_dc_evidence_mismatch"


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
