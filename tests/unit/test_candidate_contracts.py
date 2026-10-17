"""Synthetic local V/A contracts; these fixtures are not PDK/native qualification."""

from __future__ import annotations

import copy
import hashlib
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_operator_operations import operator

from cadence_mcp_bridge.candidate_contracts import (
    CandidateBatchPlan,
    CandidateBatchRequest,
    SuppliedValue,
    prepare_candidate_plan,
)
from cadence_mcp_bridge.operator_operations import GRANT_DOCUMENT, OperationRejected
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.variable_contracts import DesignVariables, canonical_digest

__all__ = ["candidate_operator", "operator"]


@pytest.fixture
def candidate_operator(operator):
    context, grant, _, settings = operator
    document = json.loads(context.binding.design_registry.read_bytes())
    variable_set = document["variable_sets"][0]
    for index, variable in enumerate(variable_set["variables"]):
        variable.update(
            mutation_policy="owned_copy_only",
            fixed_value=None,
            default=None,
            range_status="qualified",
            step_policy="grid",
            review_id=f"synthetic-region-{index}",
            unit="V" if index == 0 else "A",
            minimum="0.8" if index == 0 else "0.000001",
            maximum="1.2" if index == 0 else "0.000003",
            step="0.1" if index == 0 else "0.000001",
        )
    variables = DesignVariables.model_validate_json(json.dumps(variable_set))
    document["range_reviews"] = [
        dict(
            review_id=variable.review_id,
            design_id=variables.design_id,
            design_profile_sha256=variables.design_profile_sha256,
            variable_contract_sha256=canonical_digest(variable),
            evidence_id="synthetic-fixture-only",
            evidence_sha256="e" * 64,
            scope="operator_reviewed_project_numeric_contract",
        )
        for variable in variables.variables
    ]
    for analysis in document["analysis_contracts"]:
        analysis["variable_set_sha256"] = canonical_digest(variables)
    context.binding.design_registry.write_bytes(
        type(context.contracts.designs)
        .model_validate_json(json.dumps(document))
        .model_dump_json()
        .encode(),
    )
    digest = hashlib.sha256(context.binding.design_registry.read_bytes()).hexdigest()
    runtime = json.loads(settings.read_bytes())
    runtime["contexts"][0]["design_sha256"] = digest
    settings.write_text(json.dumps(runtime), encoding="utf-8")
    context = load_runtime(settings)[0]
    regions = [
        dict(
            design_id=variables.design_id,
            logical_id=variable.logical_id,
            unit=variable.unit,
            minimum=variable.minimum,
            maximum=variable.maximum,
        )
        for variable in variables.variables
    ]
    grant_doc = grant.model_dump(mode="json")
    grant_doc.update(design_sha256=digest, numeric_regions=regions)
    grant = GRANT_DOCUMENT.validate_json(json.dumps(grant_doc))
    registry = context.contracts.designs
    profile = registry.profile(variables.design_id)
    contract = next(c for c in registry.analyses_for(variables.design_id) if c.analysis == "dc")
    payload = dict(
        schema_version=1,
        batch_id=str(uuid4()),
        baseline_candidate_id="baseline",
        declared_difference_ids=[v.logical_id for v in variables.variables],
        candidates=[
            dict(
                candidate_id=identity,
                label=label,
                operation_id=str(uuid4()),
                design_id=variables.design_id,
                analysis_id=contract.analysis_id,
                values=[
                    dict(logical_id=v.logical_id, unit=v.unit, value=value)
                    for v, value in zip(variables.variables, values, strict=True)
                ],
                result_reservation_bytes=134217728,
            )
            for identity, label, values in (
                ("baseline", "기준 회로", ("1.00", ".000002")),
                ("voltage", "전압 후보", ("1.1", "0.000002")),
                ("mixed", "혼합 후보", ("0.9", "3e-6")),
            )
        ],
        fixed_evidence=dict(
            source_revision_sha256="4" * 64,
            testbench_revision_sha256="5" * 64,
            source_baseline_sha256="6" * 64,
            design_profile_sha256=canonical_digest(profile),
            analysis_contract_sha256=canonical_digest(contract),
            measurement_id=profile.allowed_measurements[0],
            reader_registration_sha256="c" * 64,
            conditions=dict(
                analysis_inputs=dict(
                    analysis="dc", mode="saved_operating_point", statement_sha256="0" * 64
                ),
                source_tree_sha256="1" * 64,
                ade_state_tree_sha256="2" * 64,
                static_statements_sha256="3" * 64,
                model_file_sha256=["f" * 64],
                transfer=None,
            ),
            variable_bindings=[
                dict(
                    logical_id=v.logical_id,
                    cadence_binding=v.cadence_binding,
                    binding_evidence_sha256="e" * 64,
                    targets=[
                        dict(
                            instance_path=f"I0/SOURCE{index}",
                            master_library="synthetic",
                            master_cell="vdc" if v.unit == "V" else "idc",
                            master_view="symbol",
                            property_name="dc",
                        )
                    ],
                )
                for index, v in enumerate(variables.variables)
            ],
        ),
    )
    return context, grant, CandidateBatchRequest.model_validate_json(json.dumps(payload)), settings


def planned(candidate_operator):
    context, grant, request, _ = candidate_operator
    return prepare_candidate_plan(context, grant, canonical_digest(grant), request, 100)


def test_full_mixed_plan_preserves_raw_values_bindings_and_no_state(candidate_operator):
    context, _, request, _ = candidate_operator
    before = {
        p.name: p.read_bytes()
        for p in context.binding.design_registry.parent.iterdir()
        if p.is_file()
    }
    plan = planned(candidate_operator)
    assert plan.expected_executions == 3
    assert plan.result_reservation_bytes == 3 * 134217728
    assert plan.request.candidates[0].values[0].value == "1.00"
    assert plan.plans[0].request.values[0].value == "1"
    assert plan.request.candidates[2].values[1].value == "3e-6"
    assert plan.plans[2].request.values[1].value == "0.000003"
    assert tuple(v.unit for v in plan.varied_variables) == ("V", "A")
    assert plan.request.fixed_evidence.variable_bindings[0].targets[0].instance_path == "I0/SOURCE0"
    assert plan.request.fixed_evidence.verification.endswith("NOT_INDEPENDENTLY_ATTESTED")
    assert not plan.execution_authorized and not plan.remote_contact and not plan.admission_created
    assert plan.new_reservations == 0
    assert not context.binding.analysis_journal.exists()
    assert not context.binding.sweep_journal.exists() and not context.lock_path.exists()
    assert before == {
        p.name: p.read_bytes()
        for p in context.binding.design_registry.parent.iterdir()
        if p.is_file()
    }
    assert CandidateBatchPlan.model_validate_json(plan.model_dump_json()) == plan
    assert request.fixed_evidence.source_revision_sha256 == "4" * 64


@pytest.mark.parametrize(
    "change",
    [
        "partial",
        "duplicate-id",
        "duplicate-operation",
        "duplicate-canonical",
        "undeclared",
        "overdeclared",
        "changed-unit",
        "other-analysis",
        "missing-binding",
        "binding-alias",
        "bad-target",
        "true-version",
    ],
)
def test_invalid_batch_identity_and_partial_overrides_reject(candidate_operator, change):
    _, _, request, _ = candidate_operator
    payload = json.loads(request.model_dump_json())
    if change == "partial":
        payload["candidates"][1]["values"].pop()
    elif change == "duplicate-id":
        payload["candidates"][1]["candidate_id"] = "baseline"
    elif change == "duplicate-operation":
        payload["candidates"][1]["operation_id"] = payload["candidates"][0]["operation_id"]
    elif change == "duplicate-canonical":
        payload["candidates"][1]["values"] = copy.deepcopy(payload["candidates"][0]["values"])
        payload["candidates"][1]["values"][0]["value"] = "1e0"
    elif change == "undeclared":
        payload["declared_difference_ids"].pop()
    elif change == "overdeclared":
        payload["declared_difference_ids"].append("supply")
    elif change == "changed-unit":
        payload["candidates"][1]["values"][0]["unit"] = "A"
    elif change == "other-analysis":
        payload["candidates"][1]["analysis_id"] = "example-ac"
    elif change == "missing-binding":
        payload["fixed_evidence"]["variable_bindings"].pop()
    elif change == "binding-alias":
        payload["fixed_evidence"]["variable_bindings"][1]["targets"] = copy.deepcopy(
            payload["fixed_evidence"]["variable_bindings"][0]["targets"],
        )
    elif change == "bad-target":
        payload["fixed_evidence"]["variable_bindings"][0]["targets"][0]["instance_path"] = "../V0"
    else:
        payload["schema_version"] = True
    with pytest.raises(ValidationError):
        CandidateBatchRequest.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("value", ["nan", "inf", "1u", "1 + 1", "1e99", "", 1.0, True])
def test_supplied_decimal_spelling_is_strict(value):
    with pytest.raises(ValidationError):
        SuppliedValue(logical_id="bias", value=value, unit="V")


@pytest.mark.parametrize(
    "field,value", [("attempt_limit", 2), ("result_reserved_bytes_limit", 402653183)]
)
def test_aggregate_cost_does_not_use_global_capacity_as_grant(candidate_operator, field, value):
    context, grant, request, _ = candidate_operator
    grant = grant.model_copy(update={field: value})
    with pytest.raises(OperationRejected) as error:
        prepare_candidate_plan(context, grant, canonical_digest(grant), request, 100)
    assert error.value.reason == "candidate_batch_exceeds_authority"


@pytest.mark.parametrize("value", ["0.7", "1.05"])
def test_range_and_grid_still_use_existing_prepare_plan(candidate_operator, value):
    context, grant, request, _ = candidate_operator
    candidate = request.candidates[1]
    altered_value = candidate.values[0].model_copy(update={"value": value})
    altered = candidate.model_copy(update={"values": (altered_value, candidate.values[1])})
    request = request.model_copy(
        update={"candidates": (request.candidates[0], altered, request.candidates[2])}
    )
    with pytest.raises(OperationRejected) as error:
        prepare_candidate_plan(context, grant, canonical_digest(grant), request, 100)
    assert error.value.reason == "registered_numeric_contract_denied"


@pytest.mark.parametrize("change", ["profile", "contract", "ade-binding", "measurement"])
def test_evidence_labels_cannot_replace_registered_bindings(candidate_operator, change):
    context, grant, request, _ = candidate_operator
    evidence = json.loads(request.fixed_evidence.model_dump_json())
    if change == "profile":
        evidence["design_profile_sha256"] = "a" * 64
    elif change == "contract":
        evidence["analysis_contract_sha256"] = "a" * 64
    elif change == "ade-binding":
        evidence["variable_bindings"][0]["cadence_binding"] = "OtherBias"
    else:
        evidence["measurement_id"] = "unregistered"
    payload = json.loads(request.model_dump_json())
    payload["fixed_evidence"] = evidence
    altered = CandidateBatchRequest.model_validate_json(json.dumps(payload))
    with pytest.raises(OperationRejected) as error:
        prepare_candidate_plan(context, grant, canonical_digest(grant), altered, 100)
    assert error.value.reason == "candidate_fixed_registration_mismatch"


def test_loaded_v2_grant_and_exact_raw_grant_digest_are_preserved(candidate_operator, tmp_path):
    from cadence_mcp_bridge.operator_operations import load_grant

    context, grant, request, _ = candidate_operator
    payload = grant.model_dump(mode="json")
    payload.update(
        schema_version=2,
        analyses=["dc"],
        design_analyses=[dict(design_id=request.candidates[0].design_id, analysis="dc")],
    )
    source = tmp_path / "grant.json"
    raw = json.dumps(payload, indent=2).encode()
    source.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    loaded, _ = load_grant(source, digest)
    plan = prepare_candidate_plan(context, loaded, digest, request, 100)
    assert all(p.grant_sha256 == digest for p in plan.plans)
    broken = loaded.model_copy(update={"design_analyses": ()})
    with pytest.raises(ValidationError):
        prepare_candidate_plan(context, broken, canonical_digest(broken), request, 100)


def test_model_copy_bypass_is_revalidated_and_expired_authority_rejects(candidate_operator):
    context, grant, request, _ = candidate_operator
    altered = request.model_copy(update={"declared_difference_ids": ("unknown",)})
    with pytest.raises(ValidationError):
        prepare_candidate_plan(context, grant, canonical_digest(grant), altered, 100)
    with pytest.raises(OperationRejected) as error:
        prepare_candidate_plan(
            context, grant, canonical_digest(grant), request, grant.valid_until_unix
        )
    assert error.value.reason == "authority_inactive"
    plan = planned(candidate_operator)
    bad_child = plan.plans[1].model_copy(update={"runner_sha256": "f" * 64})
    with pytest.raises(ValidationError):
        CandidateBatchPlan.model_validate_json(
            plan.model_copy(
                update={
                    "plans": (plan.plans[0], bad_child, plan.plans[2]),
                }
            ).model_dump_json()
        )


def test_omitted_value_from_every_candidate_still_fails_registered_complete_inventory(
    candidate_operator,
):
    context, grant, request, _ = candidate_operator
    payload = json.loads(request.model_dump_json())
    payload["declared_difference_ids"] = ["bias-n"]
    for candidate in payload["candidates"]:
        candidate["values"] = candidate["values"][:1]
    payload["fixed_evidence"]["variable_bindings"] = payload["fixed_evidence"]["variable_bindings"][
        :1
    ]
    request = CandidateBatchRequest.model_validate_json(json.dumps(payload))
    with pytest.raises(OperationRejected) as error:
        prepare_candidate_plan(context, grant, canonical_digest(grant), request, 100)
    assert error.value.reason == "all_explicit_registered_values_required"


@pytest.mark.parametrize("policy", ["read_only", "unqualified", "length-unit"])
def test_unqualified_or_non_va_difference_contract_cannot_enter_a_plan(candidate_operator, policy):
    plan = planned(candidate_operator)
    payload = json.loads(plan.model_dump_json())
    variable = payload["varied_variables"][0]
    if policy == "read_only":
        variable["mutation_policy"] = "read_only"
    elif policy == "unqualified":
        variable.update(
            range_status="unqualified",
            minimum=None,
            maximum=None,
            step_policy="unqualified",
            step=None,
            review_id=None,
        )
    else:
        variable["unit"] = "m"
    with pytest.raises(ValidationError):
        CandidateBatchPlan.model_validate_json(json.dumps(payload))
