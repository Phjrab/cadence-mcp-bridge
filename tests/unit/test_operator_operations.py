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
                    dict(logical_id=name, unit="V", minimum="1", maximum="1")
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
    first = prepare_plan(context, grant, "c" * 64, request, int(time.time()))
    second = prepare_plan(
        context,
        grant,
        "c" * 64,
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
        prepare_plan(context, grant, "c" * 64, request.model_copy(update=change), int(time.time()))
    assert error.value.reason == reason


def test_registered_numbers_and_grant_region_are_independent(operator):
    context, grant, request, _ = operator
    wrong_value = request.values[0].model_copy(update={"value": "2"})
    with pytest.raises(OperationRejected) as error:
        prepare_plan(
            context,
            grant,
            "c" * 64,
            request.model_copy(update={"values": (wrong_value, request.values[1])}),
            int(time.time()),
        )
    assert error.value.reason == "registered_numeric_contract_denied"
    region = grant.numeric_regions[0].model_copy(update={"minimum": "2", "maximum": "3"})
    with pytest.raises(OperationRejected) as error:
        prepare_plan(
            context,
            grant.model_copy(update={"numeric_regions": (region, grant.numeric_regions[1])}),
            "c" * 64,
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
    assert load_grant(path, digest)[0] == grant
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
