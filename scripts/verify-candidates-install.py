"""Installed candidate CLI and retained capture; synthetic files, never EDA or SSH."""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import cadence_mcp_bridge
from cadence_mcp_bridge import candidate_cli
from cadence_mcp_bridge.__main__ import main as cli_main
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.authenticated_provider import NativeProviderBinding
from cadence_mcp_bridge.candidate_batches import CandidateBatchQuery, CandidateBatchStore
from cadence_mcp_bridge.candidate_contracts import CandidateBatchPlan
from cadence_mcp_bridge.candidate_reports import CandidateComparison
from cadence_mcp_bridge.designs import DesignAnalysisRegistry, DesignProfile
from cadence_mcp_bridge.native_service import NativeOperationService
from cadence_mcp_bridge.operator_lifecycle import OperatorLifecycle, ProviderObservation
from cadence_mcp_bridge.operator_operations import OperationProgress, OperationRejected
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.variable_contracts import DesignVariables, canonical_digest


def verify(workspace: Path, examples: Path) -> dict[str, object]:
    # The checker is outside the package and Python runs in isolated mode. Neither
    # test modules nor the source tree may supply product imports.
    for module in (cadence_mcp_bridge, candidate_cli):
        if not Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
            raise ValueError("installed wheel origin required")
    workspace.mkdir(mode=0o700, parents=False, exist_ok=False)
    environment = json.loads((examples / "environment.json").read_bytes())
    environment["limits"].update(spectre_attempts=6, result_reserved_bytes=805306368)
    registry = json.loads((examples / "designs.json").read_bytes())
    profile = registry["designs"][0]
    profile["work_copy_policy"] = "owned_copy_only"
    profile_hash = canonical_digest(DesignProfile.model_validate_json(json.dumps(profile)))
    variables = registry["variable_sets"][0]
    variables["design_profile_sha256"] = profile_hash
    for index, variable in enumerate(variables["variables"]):
        variable.update(
            mutation_policy="owned_copy_only", default=None, fixed_value=None,
            range_status="qualified", step_policy="grid",
            review_id=f"synthetic-region-{index}", unit="V" if index == 0 else "A",
            minimum="0.8" if index == 0 else "0.000001",
            maximum="1.2" if index == 0 else "0.000003",
            step="0.1" if index == 0 else "0.000001",
        )
    variable_set = DesignVariables.model_validate_json(json.dumps(variables))
    registry["range_reviews"] = [
        dict(
            review_id=v.review_id, design_id=variable_set.design_id,
            design_profile_sha256=profile_hash, variable_contract_sha256=canonical_digest(v),
            evidence_id="synthetic-fixture-only", evidence_sha256="e" * 64,
            scope="operator_reviewed_project_numeric_contract",
        )
        for v in variable_set.variables
    ]
    for contract in registry["analysis_contracts"]:
        contract.update(
            design_profile_sha256=profile_hash,
            variable_set_sha256=canonical_digest(variable_set),
        )
    registry_model = DesignAnalysisRegistry.model_validate_json(json.dumps(registry))
    paths = [workspace / (name + ".json") for name in ("environment", "design", "pdk")]
    for path, payload in zip(
        paths, (environment, registry, json.loads((examples / "pdks.json").read_bytes())),
        strict=True,
    ):
        path.write_text(json.dumps(payload), encoding="utf-8")
    binding = dict(
        context_id="installed-candidates-synthetic", environment_profile=str(paths[0]),
        environment_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),
        design_registry=str(paths[1]),
        design_sha256=hashlib.sha256(paths[1].read_bytes()).hexdigest(),
        pdk_registry=str(paths[2]), pdk_sha256=hashlib.sha256(paths[2].read_bytes()).hexdigest(),
        runner_sha256="b" * 64, authority_ref="synthetic-no-execution",
        ledger_ref="synthetic-ledger", analysis_journal=str(workspace / "analysis.sqlite3"),
        sweep_journal=str(workspace / "sweep.sqlite3"),
    )
    settings = workspace / "runtime.json"
    configured = dict(schema_version=1, resource_state_root=str(workspace), contexts=[binding])
    settings.write_text(json.dumps(configured), encoding="utf-8")
    context = load_runtime(settings)[0]
    # This fictional record is local test input; it cannot authorize any real VM.
    grant = workspace / "synthetic-authority.json"
    grant.write_text(json.dumps(dict(
        schema_version=1, grant_id="synthetic-no-execution",
        authorization_source="explicit_operator_record",
        resource_domain_sha256=context.resource_domain_sha256,
        runner_sha256=binding["runner_sha256"], ledger_ref=binding["ledger_ref"],
        environment_sha256=binding["environment_sha256"],
        design_sha256=binding["design_sha256"], pdk_sha256=binding["pdk_sha256"],
        design_ids=[variable_set.design_id], analyses=["dc"], actions=["submit"],
        numeric_regions=[
            dict(design_id=variable_set.design_id, logical_id=v.logical_id, unit=v.unit,
                 minimum=v.minimum, maximum=v.maximum)
            for v in variable_set.variables
        ],
        attempt_limit=6, result_reserved_bytes_limit=805306368,
        valid_from_unix=1, valid_until_unix=int(time.time()) + 3600, status="active",
    )), encoding="utf-8")
    provider_binding = workspace / "synthetic-provider.json"
    provider_binding.write_text(NativeProviderBinding(
        schema_version=1, identity_manifest_sha256="a" * 64,
        runtime_manifest_sha256=binding["runner_sha256"],
    ).model_dump_json(), encoding="utf-8")
    binding.update(
        native_provider_binding=str(provider_binding),
        native_provider_sha256=hashlib.sha256(provider_binding.read_bytes()).hexdigest(),
        operator_grant=str(grant),
        operator_grant_sha256=hashlib.sha256(grant.read_bytes()).hexdigest(),
    )
    settings.write_text(json.dumps(configured), encoding="utf-8")
    context = load_runtime(settings)[0]
    contract = registry_model.analyses_for(variable_set.design_id)[0]
    request = dict(
        schema_version=1, batch_id=str(uuid4()), baseline_candidate_id="baseline",
        declared_difference_ids=[v.logical_id for v in variable_set.variables],
        candidates=[
            dict(candidate_id=identity, label=label, operation_id=str(uuid4()),
                 design_id=variable_set.design_id, analysis_id=contract.analysis_id,
                 values=[dict(logical_id=v.logical_id, unit=v.unit, value=value)
                         for v, value in zip(variable_set.variables, values, strict=True)],
                 result_reservation_bytes=134217728)
            for identity, label, values in (
                ("baseline", "기준 회로", ("1.00", ".000002")),
                ("voltage", "전압 후보", ("1.1", "0.000002")),
                ("mixed", "  =SUM(1,2)", ("0.9", "3e-6")),
            )
        ],
        fixed_evidence=dict(
            source_revision_sha256="4" * 64, testbench_revision_sha256="5" * 64,
            source_baseline_sha256="6" * 64, design_profile_sha256=profile_hash,
            analysis_contract_sha256=canonical_digest(contract),
            measurement_id=profile["allowed_measurements"][0],
            reader_registration_sha256="c" * 64,
            conditions=dict(
                analysis_inputs=dict(analysis="dc", mode="saved_operating_point",
                                     statement_sha256="0" * 64),
                source_tree_sha256="1" * 64, ade_state_tree_sha256="2" * 64,
                static_statements_sha256="3" * 64, model_file_sha256=["f" * 64],
                transfer=None,
            ),
            variable_bindings=[
                dict(logical_id=v.logical_id, cadence_binding=v.cadence_binding,
                     binding_evidence_sha256="e" * 64,
                     targets=[dict(instance_path=f"I0/SOURCE{index}",
                                   master_library="synthetic",
                                   master_cell="vdc" if v.unit == "V" else "idc",
                                   master_view="symbol", property_name="dc")])
                for index, v in enumerate(variable_set.variables)
            ],
        ),
    )
    source, plan_path = workspace / "request.json", workspace / "plan.json"
    source.write_text(json.dumps(request), encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("CADENCE_MCP_")
           and k.upper() not in ("PYTHONPATH", "PYTHONHOME")}

    def run(*args: str, expected: int = 0) -> dict[str, object]:
        reply = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-m", "cadence_mcp_bridge",
             "operator-candidates", *args], cwd=workspace, env=env,
            capture_output=True, timeout=30,
        )
        assert reply.returncode == expected and not reply.stderr, reply.stderr.decode("utf-8")
        return json.loads(reply.stdout)

    assert run("schema")["wl"] == "UNSUPPORTED"
    shared = ["--settings", str(settings), "--context", binding["context_id"]]
    planned = run("plan", *shared, "--request", str(source), "--output", str(plan_path))
    plan = CandidateBatchPlan.model_validate_json(plan_path.read_bytes())
    assert planned["plan_sha256"] == plan.plan_sha256 and plan.expected_executions == 3
    assert plan.request.candidates[0].values[0].value == "1.00"
    assert plan.plans[0].request.values[0].value == "1"
    assert not context.binding.analysis_journal.exists() and not context.lock_path.exists()
    before_plan = plan_path.read_bytes()
    assert run("plan", *shared, "--request", str(source), "--output", str(plan_path),
               expected=2)["status"] == "CANDIDATE_WORKFLOW_REJECTED"
    assert plan_path.read_bytes() == before_plan

    # Seed two terminal synthetic records without submit/advance/provider admission.
    # Only the service-construction seam is replaced; installed capture, journal,
    # terminal identity checking and make_report are the real installed functions.
    store = AnalysisStore(context.binding.analysis_journal)
    query = CandidateBatchQuery(batch_id=plan.request.batch_id,
                                expected_plan_sha256=plan.plan_sha256)
    CandidateBatchStore(store).admit(query, plan)
    for candidate, child in zip(plan.request.candidates[:2], plan.plans[:2], strict=True):
        store.admit_operation(candidate.operation_id, child, dispatch_intent=True,
                              candidate_batch_id=query.batch_id)
        record = store.operation(candidate.operation_id)
        store.advance_operation(candidate.operation_id, record.progress,
                                OperationProgress(phase="SUCCEEDED", remote_revision=5,
                                                  provider_receipt_sha256="a" * 64))

    class RetainedProvider:
        def __init__(self) -> None:
            self.reads: list[str] = []
            self.fail = False

        async def report_result(self, operation_id, child):
            self.reads.append(operation_id)
            if self.fail:
                raise OperationRejected("synthetic_retained_read_failure")
            record = store.operation(operation_id)
            return ProviderObservation(
                operation_id=operation_id, plan_sha256=child.plan_sha256,
                resource_domain_sha256=context.resource_domain_sha256,
                ledger_ref=context.binding.ledger_ref, progress=record.progress,
            ), dict(
                status="NATIVE_RESULT_RETRIEVED", operation_id=operation_id,
                plan_sha256=child.plan_sha256, design_id=child.request.design_id,
                analysis=child.analysis,
                measurement_id=plan.request.fixed_evidence.measurement_id,
                reader_registration_sha256=plan.request.fixed_evidence.reader_registration_sha256,
                execution_input_sha256=hashlib.sha256(operation_id.encode()).hexdigest(),
                extraction_receipt_sha256="e" * 64, frame_sha256="f" * 64,
                native_provenance="FIXED_RUNTIME_TERMINAL_RECEIPT_AND_CONTENT_VERIFIED",
                nodes=[dict(logical_id="output", unit="V",
                            value=1.0 if operation_id == plan.request.candidates[0].operation_id
                            else 2.0)],
                report_conditions=plan.request.fixed_evidence.conditions.model_dump(mode="json"),
            )

    provider = RetainedProvider()
    native = object.__new__(NativeOperationService)
    native.context = context
    native.current = lambda: None
    native.provider = provider
    native.lifecycle = OperatorLifecycle(context, store, provider)
    observations = workspace / "observations.json"
    operational = [*shared, "--plan", str(plan_path), "--expected-plan-sha256", plan.plan_sha256]
    journal_before = store.path.read_bytes()

    def capture(path: Path) -> dict[str, object]:
        stdout = io.StringIO()
        with (
            patch("cadence_mcp_bridge.native_service.NativeOperationService", return_value=native),
            contextlib.redirect_stdout(stdout),
        ):
            code = cli_main(["operator-candidates", "capture", *operational,
                             "--output", str(path)])
        assert code == 0
        result = json.loads(stdout.getvalue())
        assert result["new_simulations"] == result["new_extractions"] == 0
        assert store.path.read_bytes() == journal_before
        return result

    assert capture(observations)["unavailable_reports"] == 0
    assert provider.reads == [c.operation_id for c in plan.request.candidates[:2]]
    comparison, csv_path = workspace / "comparison.json", workspace / "comparison.csv"
    run("compare", "--plan", str(plan_path), "--expected-plan-sha256", plan.plan_sha256,
        "--observations", str(observations), "--output", str(comparison))
    report = CandidateComparison.model_validate_json(comparison.read_bytes())
    assert [r.status for r in report.rows] == ["SUCCEEDED", "SUCCEEDED", "NOT_RUN"]
    assert report.rows[1].metrics[0].relative_change == 1.0
    assert all(row.effective_values is None for row in report.rows)
    assert report.native_candidate_qualification == "NOT_ESTABLISHED_BY_LOCAL_COMPARISON"
    assert run("csv", "--comparison", str(comparison), "--output", str(csv_path))[
        "remote_contact"] is False
    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8-sig"))))
    assert any(row["label"] == "기준 회로" for row in rows)
    assert any(row["label"].startswith("'") and "=SUM(1,2)" in row["label"] for row in rows)

    provider.fail = True
    unavailable = workspace / "unavailable-observations.json"
    assert capture(unavailable)["unavailable_reports"] == 2
    failed_comparison = workspace / "unavailable-comparison.json"
    run("compare", "--plan", str(plan_path), "--expected-plan-sha256", plan.plan_sha256,
        "--observations", str(unavailable), "--output", str(failed_comparison))
    failed = CandidateComparison.model_validate_json(failed_comparison.read_bytes())
    assert [row.status for row in failed.rows] == [
        "RESULT_UNAVAILABLE", "RESULT_UNAVAILABLE", "NOT_RUN",
    ]
    assert all(row.reason == "retained_report_read_failed" for row in failed.rows[:2])
    assert not any(row.metrics for row in failed.rows)
    assert not context.binding.sweep_journal.exists() and store.path.read_bytes() == journal_before
    return dict(
        status="PASS", scope="INSTALLED_CANDIDATE_CLI_SYNTHETIC_NOT_CADENCE",
        installed_origin=True, subprocess_plan_compare_csv=True,
        capture="INSTALLED_RETAINED_PATH_WITH_SYNTHETIC_PROVIDER_CONSTRUCTION",
        capture_read_failure_preserved=True, output_overwrite_rejected=True,
        effective_values="UNAVAILABLE_NOT_INFERRED_FROM_REQUEST",
        new_simulations=0, new_extractions=0, new_reservations=0, remote_contact=False,
        native_candidate_qualification=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--examples", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.workspace.resolve(), args.examples.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
