"""Synthetic authority forms/plans; never remote qualification or grant issuance."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.designs import DesignProfile
from cadence_mcp_bridge.operator_operations import (
    OperationRejected,
    OperationRequest,
    OperatorGrant,
    load_grant,
    match_grant,
    prepare_plan,
)
from cadence_mcp_bridge.runtime_context import load_runtime
from cadence_mcp_bridge.variable_contracts import DesignVariables, canonical_digest

EXAMPLES = Path(__file__).resolve().parents[2] / "docs/examples/onboarding"


@pytest.fixture
def operator(tmp_path):
    environment = json.loads((EXAMPLES / "environment.json").read_bytes())
    environment["limits"].update(spectre_attempts=500, result_reserved_bytes=10737418240)
    registry = json.loads((EXAMPLES / "designs.json").read_bytes())
    profile = registry["designs"][0]
    profile["work_copy_policy"] = "owned_copy_only"
    profile_hash = canonical_digest(DesignProfile.model_validate_json(json.dumps(profile)))
    variables = registry["variable_sets"][0]
    variables["design_profile_sha256"] = profile_hash
    for variable in variables["variables"]:
        variable.update(mutation_policy="fixed", default="1", fixed_value="1", step_policy="fixed")
    variable_hash = canonical_digest(DesignVariables.model_validate_json(json.dumps(variables)))
    for contract in registry["analysis_contracts"]:
        contract.update(design_profile_sha256=profile_hash, variable_set_sha256=variable_hash)
    pdk = json.loads((EXAMPLES / "pdks.json").read_bytes())
    paths = [tmp_path / (name + ".json") for name in ("env", "design", "pdk")]
    for path, payload in zip(paths, (environment, registry, pdk), strict=True):
        path.write_text(json.dumps(payload), encoding="utf-8")
    binding = dict(
        context_id="operator",
        environment_profile=str(paths[0]),
        environment_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest(),
        design_registry=str(paths[1]),
        design_sha256=hashlib.sha256(paths[1].read_bytes()).hexdigest(),
        pdk_registry=str(paths[2]),
        pdk_sha256=hashlib.sha256(paths[2].read_bytes()).hexdigest(),
        runner_sha256="b" * 64,
        authority_ref="operator-record",
        ledger_ref="shared-ledger",
        analysis_journal=str(tmp_path / "analysis.sqlite3"),
        sweep_journal=str(tmp_path / "sweep.sqlite3"),
    )
    settings = tmp_path / "runtime.json"
    settings.write_text(
        json.dumps(dict(schema_version=1, resource_state_root=str(tmp_path), contexts=[binding])),
        encoding="utf-8",
    )
    context = load_runtime(settings)[0]
    grant = OperatorGrant.model_validate_json(
        json.dumps(
            dict(
                schema_version=1,
                grant_id="operator-record",
                authorization_source="explicit_operator_record",
                resource_domain_sha256=context.resource_domain_sha256,
                runner_sha256=binding["runner_sha256"],
                ledger_ref="shared-ledger",
                environment_sha256=binding["environment_sha256"],
                design_sha256=binding["design_sha256"],
                pdk_sha256=binding["pdk_sha256"],
                design_ids=["example-amplifier"],
                analyses=["dc", "ac", "tran"],
                actions=["submit", "cancel_pending"],
                numeric_regions=[
                    dict(
                        design_id="example-amplifier",
                        logical_id=name,
                        unit="V",
                        minimum="1",
                        maximum="1",
                    )
                    for name in ("bias-n", "bias-p")
                ],
                attempt_limit=6,
                result_reserved_bytes_limit=805306368,
                valid_from_unix=1,
                valid_until_unix=int(time.time()) + 3600,
                status="active",
            )
        )
    )
    request = OperationRequest.model_validate_json(
        json.dumps(
            dict(
                schema_version=1,
                design_id="example-amplifier",
                analysis_id="example-dc",
                values=[
                    dict(logical_id=name, unit="V", value="1") for name in ("bias-n", "bias-p")
                ],
                result_reservation_bytes=134217728,
            )
        )
    )
    return context, grant, request, settings


def test_plan_frozen_canonical_and_no_journal(operator):
    context, grant, request, _ = operator
    first = prepare_plan(context, grant, canonical_digest(grant), request, int(time.time()))
    second = prepare_plan(
        context,
        grant,
        canonical_digest(grant),
        request.model_copy(update={"values": tuple(reversed(request.values))}),
        int(time.time()),
    )
    assert first.plan_sha256 == second.plan_sha256
    with pytest.raises(ValidationError):
        first.request.values[0].value = "2"
    assert not context.binding.analysis_journal.exists()
    assert not context.binding.sweep_journal.exists()
    assert not context.lock_path.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("ledger_ref", "new-independent-ledger"),
        ("runner_sha256", "a" * 64),
        ("environment_sha256", "a" * 64),
        ("design_sha256", "a" * 64),
        ("pdk_sha256", "a" * 64),
        ("resource_domain_sha256", "a" * 64),
        ("grant_id", "different-grant"),
    ],
)
def test_authority_exact_install_domain_catalog_binding(operator, field, value):
    context, grant, _, _ = operator
    with pytest.raises(OperationRejected, match="Operator operation rejected") as error:
        match_grant(context, grant.model_copy(update={field: value}), int(time.time()))
    assert error.value.reason == "authority_binding_mismatch"


@pytest.mark.parametrize(
    "change",
    [
        {"status": "revoked"},
        {"valid_until_unix": 2},
        {"valid_from_unix": 9999999999},
        {"attempt_limit": 501},
        {"result_reserved_bytes_limit": 10737418241},
    ],
)
def test_lifetime_and_ceiling_no_budget_reset(operator, change):
    context, grant, _, _ = operator
    with pytest.raises(OperationRejected):
        match_grant(context, grant.model_copy(update=change), int(time.time()))


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"values": ()}, "all_explicit_registered_values_required"),
        ({"analysis_id": "not-registered"}, "analysis_scope_denied"),
        ({"result_reservation_bytes": 805306369}, "reservation_exceeds_authority"),
    ],
)
def test_request_denials(operator, change, reason):
    context, grant, request, _ = operator
    with pytest.raises(OperationRejected) as error:
        prepare_plan(
            context,
            grant,
            canonical_digest(grant),
            request.model_copy(update=change),
            int(time.time()),
        )
    assert error.value.reason == reason


def test_registered_numbers_and_grant_region_are_independent(operator):
    context, grant, request, _ = operator
    wrong_value = request.values[0].model_copy(update={"value": "2"})
    with pytest.raises(OperationRejected) as error:
        prepare_plan(
            context,
            grant,
            canonical_digest(grant),
            request.model_copy(update={"values": (wrong_value, request.values[1])}),
            int(time.time()),
        )
    assert error.value.reason == "registered_numeric_contract_denied"
    region = grant.numeric_regions[0].model_copy(update={"minimum": "2", "maximum": "3"})
    changed = grant.model_copy(update={"numeric_regions": (region, grant.numeric_regions[1])})
    with pytest.raises(OperationRejected) as error:
        prepare_plan(
            context,
            changed,
            canonical_digest(changed),
            request,
            int(time.time()),
        )
    assert error.value.reason == "authority_numeric_scope_denied"


def test_bounded_closed_grant_and_sha(operator, tmp_path):
    _, grant, _, _ = operator
    path = tmp_path / "grant.json"
    data = grant.model_dump_json().encode()
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    assert load_grant(path, digest)[0].model_dump() == grant.model_dump()
    with pytest.raises(OperationRejected):
        load_grant(path, "d" * 64)
    for raw in (b'{"schema_version":1,"schema_version":1}', b" " * 65537):
        path.write_bytes(raw)
        with pytest.raises(ValueError):
            load_grant(path, hashlib.sha256(raw).hexdigest())


def test_cli_local_plan_does_not_issue_authority(operator, tmp_path, capsys):
    context, grant, request, settings = operator
    grant_path = tmp_path / "grant.json"
    request_path = tmp_path / "request.json"
    grant_path.write_text(grant.model_dump_json(), encoding="utf-8")
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    digest = hashlib.sha256(grant_path.read_bytes()).hexdigest()
    common = [
        "--settings",
        str(settings),
        "--context",
        "operator",
        "--grant",
        str(grant_path),
        "--expected-grant-sha256",
        digest,
    ]
    assert main(["operation", "check-authority", *common]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["remaining_remote_attempts"] is None
    assert checked["operator_authenticity"] == "NOT_ATTESTED"
    assert main(["operation", "plan", *common, "--request", str(request_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert not result["dispatch_eligible"] and not result["execution_authorized"]
    assert not result["admission_created"] and not result["remote_contact"]
    assert str(tmp_path) not in json.dumps(result)
    assert not context.binding.analysis_journal.exists()
    request_path.write_text('{"script":"secret-private-content"}', encoding="utf-8")
    assert main(["operation", "plan", *common, "--request", str(request_path)]) == 1
    assert "secret-private-content" not in capsys.readouterr().out


@pytest.fixture
def multiple_designs(operator):
    from copy import deepcopy

    context, grant, request, settings = operator
    registry = json.loads(context.binding.design_registry.read_bytes())
    original = deepcopy(registry["designs"][0])
    for design_id, fixed in (("synthetic-rc", None), ("synthetic-other", "2")):
        profile = deepcopy(original)
        profile.update(design_id=design_id)
        profile["binding"]["cell"] = design_id.replace("-", "_")
        if fixed is None:
            profile["allowed_variables"] = []
        profile_hash = canonical_digest(DesignProfile.model_validate_json(json.dumps(profile)))
        registry["designs"].append(profile)
        variable_hash = None
        if fixed is not None:
            variables = deepcopy(registry["variable_sets"][0])
            variables.update(design_id=design_id, design_profile_sha256=profile_hash)
            for variable in variables["variables"]:
                variable.update(default=fixed, fixed_value=fixed)
            variable_hash = canonical_digest(
                DesignVariables.model_validate_json(json.dumps(variables))
            )
            registry["variable_sets"].append(variables)
        contract = deepcopy(registry["analysis_contracts"][0])
        contract.update(
            design_id=design_id,
            analysis_id=design_id + "-dc",
            design_profile_sha256=profile_hash,
            variable_set_sha256=variable_hash,
        )
        registry["analysis_contracts"].append(contract)
    context.binding.design_registry.write_text(json.dumps(registry), encoding="utf-8")
    binding = json.loads(settings.read_bytes())
    binding["contexts"][0]["design_sha256"] = hashlib.sha256(
        context.binding.design_registry.read_bytes()
    ).hexdigest()
    settings.write_text(json.dumps(binding), encoding="utf-8")
    context = load_runtime(settings)[0]
    payload = grant.model_dump(mode="json")
    payload.update(
        design_sha256=context.binding.design_sha256,
        design_ids=["example-amplifier", "synthetic-rc", "synthetic-other"],
    )
    payload["numeric_regions"] += [
        dict(design_id="synthetic-other", logical_id=name, unit="V", minimum="2", maximum="2")
        for name in ("bias-n", "bias-p")
    ]
    return context, OperatorGrant.model_validate_json(json.dumps(payload)), request


@pytest.mark.parametrize("design_id", ["example-amplifier", "synthetic-rc", "synthetic-other"])
def test_one_grant_plans_different_design_variable_sets(multiple_designs, design_id):
    context, grant, original = multiple_designs
    request = original.model_dump(mode="json")
    request["design_id"] = design_id
    if design_id != "example-amplifier":
        request["analysis_id"] = design_id + "-dc"
    if design_id == "synthetic-rc":
        request["values"] = []
    elif design_id == "synthetic-other":
        for value in request["values"]:
            value["value"] = "2"
    request = OperationRequest.model_validate_json(json.dumps(request))
    first = prepare_plan(context, grant, canonical_digest(grant), request, int(time.time()))
    assert first.request.design_id == design_id
    assert (
        first.plan_sha256
        == prepare_plan(
            context, grant, canonical_digest(grant), request, int(time.time())
        ).plan_sha256
    )
    assert not context.binding.analysis_journal.exists()
    assert not context.lock_path.exists()


def test_other_design_regions_cannot_satisfy_current_values(multiple_designs):
    context, grant, request = multiple_designs
    other_only = grant.model_copy(
        update={
            "numeric_regions": tuple(
                r for r in grant.numeric_regions if r.design_id == "synthetic-other"
            )
        }
    )
    with pytest.raises(OperationRejected) as error:
        prepare_plan(context, other_only, canonical_digest(other_only), request, int(time.time()))
    assert error.value.reason == "authority_numeric_scope_mismatch"


@pytest.mark.parametrize("fault", ["duplicate", "outside", "unscoped"])
def test_region_scope_is_closed_and_unique_within_design(operator, fault):
    _, grant, _, _ = operator
    payload = grant.model_dump(mode="json")
    if fault == "duplicate":
        payload["numeric_regions"].append(payload["numeric_regions"][0])
    elif fault == "outside":
        payload["numeric_regions"][0]["design_id"] = "not-authorized"
    else:
        del payload["numeric_regions"][0]["design_id"]
    expected = {
        "duplicate": "duplicate authority identifier",
        "outside": "numeric region design outside authority",
        "unscoped": "design_id",
    }
    with pytest.raises(ValidationError, match=expected[fault]):
        OperatorGrant.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "design_id,analysis,permitted",
    [
        ("example-amplifier", "dc", True),
        ("example-amplifier", "ac", False),
        ("synthetic-other", "dc", False),
        ("synthetic-other", "ac", True),
    ],
)
def test_v2_pairs_reject_cross_product(multiple_designs, design_id, analysis, permitted):
    from copy import deepcopy
    from dataclasses import replace

    from cadence_mcp_bridge.operator_operations import GRANT_DOCUMENT

    context, legacy, original = multiple_designs
    catalog = context.contracts.designs
    template = next(c for c in catalog.analysis_contracts if c.analysis == "ac")
    other_profile = catalog.profile("synthetic-other")
    other_variables = catalog.variable_set("synthetic-other")
    extra = template.model_copy(
        update={
            "design_id": "synthetic-other",
            "analysis_id": "synthetic-other-ac",
            "design_profile_sha256": canonical_digest(other_profile),
            "variable_set_sha256": canonical_digest(other_variables),
        }
    )
    # This fixture deliberately registers all four combinations; grant is the boundary.
    registry = catalog.model_copy(
        update={"analysis_contracts": (*catalog.analysis_contracts, extra)}
    )
    contracts = replace(context.contracts, designs=registry)
    context = replace(context, contracts=contracts)
    payload = deepcopy(legacy.model_dump(mode="json"))
    payload.update(
        schema_version=2,
        design_ids=["example-amplifier", "synthetic-other"],
        analyses=["dc", "ac"],
        design_analyses=[
            {"design_id": "example-amplifier", "analysis": "dc"},
            {"design_id": "synthetic-other", "analysis": "ac"},
        ],
    )
    grant = GRANT_DOCUMENT.validate_json(json.dumps(payload))
    request = original.model_dump(mode="json")
    request.update(
        design_id=design_id,
        analysis_id=("example-" + analysis)
        if design_id == "example-amplifier"
        else design_id + "-" + analysis,
    )
    if design_id == "synthetic-other":
        for v in request["values"]:
            v["value"] = "2"
    request = OperationRequest.model_validate_json(json.dumps(request))
    if permitted:
        assert (
            prepare_plan(
                context, grant, canonical_digest(grant), request, int(time.time())
            ).analysis
            == analysis
        )
    else:
        with pytest.raises(OperationRejected) as error:
            prepare_plan(context, grant, canonical_digest(grant), request, int(time.time()))
        assert error.value.reason == "analysis_scope_denied"
    assert not context.binding.analysis_journal.exists()


@pytest.mark.parametrize("fault", ["missing", "duplicate", "outside"])
def test_v2_requires_exact_unique_pairs(operator, fault):
    from cadence_mcp_bridge.operator_operations import GRANT_DOCUMENT

    _, grant, _, _ = operator
    payload = grant.model_dump(mode="json")
    payload.update(
        schema_version=2,
        design_analyses=[
            {"design_id": "example-amplifier", "analysis": a} for a in ("dc", "ac", "tran")
        ],
    )
    if fault == "missing":
        del payload["design_analyses"]
    elif fault == "duplicate":
        payload["design_analyses"].append(payload["design_analyses"][0])
    else:
        payload["design_analyses"][0]["design_id"] = "outside"
    with pytest.raises(ValidationError):
        GRANT_DOCUMENT.validate_json(json.dumps(payload))


def test_v1_bytes_and_explicit_scope_semantics_are_preserved(operator, tmp_path):
    _, grant, _, _ = operator
    raw = grant.model_dump_json().encode()
    p = tmp_path / "retained-v1.json"
    p.write_bytes(raw)
    restored, _ = load_grant(p, hashlib.sha256(raw).hexdigest())
    assert type(restored) is OperatorGrant
    assert restored.model_dump_json().encode() == raw
    assert "design_analyses" not in restored.model_dump()


@pytest.mark.parametrize("loaded", [False, True])
def test_grant_object_cannot_claim_unrelated_reviewed_hash(operator, tmp_path, loaded):
    context, grant, request, _ = operator
    if loaded:
        raw = grant.model_dump_json(indent=2).encode()
        path = tmp_path / "reviewed.json"
        path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        grant, _ = load_grant(path, digest)
    else:
        digest = canonical_digest(grant)
    assert prepare_plan(context, grant, digest, request, int(time.time())).grant_sha256 == digest
    broader = grant.model_copy(update={"attempt_limit": grant.attempt_limit + 1})
    with pytest.raises(OperationRejected) as error:
        prepare_plan(context, broader, digest, request, int(time.time()))
    assert error.value.reason == "grant_document_digest_mismatch"
    assert not context.binding.analysis_journal.exists()
