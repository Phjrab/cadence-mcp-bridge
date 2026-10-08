"""Two fictional designs and hostile effective inputs; no native simulation."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_operator_operations import operator as operator_fixture

from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.designs import DesignAnalysisRegistry, DesignProfile
from cadence_mcp_bridge.generic_ade import (
    AcInputs,
    AdeExecutionRegistration,
    TranInputs,
    render_netlist,
    static_fingerprint,
    template_sha256,
    verify_effective_input,
)
from cadence_mcp_bridge.operator_operations import OperationRejected, prepare_plan
from cadence_mcp_bridge.variable_contracts import canonical_digest

operator = operator_fixture

RC = "R0 (in out) resistor r=1000\nC0 (out 0) capacitor c=0.000001"
MOS = "M0 (out gate 0 0) nch w=0.000002 l=0.0000001\nV0 (gate 0) vsource dc=1"


def setup(operator, analysis="ac", static=RC):
    context, grant, request, _ = operator
    request = request.model_copy(update={"analysis_id": "example-" + analysis})
    plan = prepare_plan(context, grant, "c" * 64, request, int(time.time()))
    profile = context.contracts.designs.profile(request.design_id)
    variables = context.contracts.designs.variable_set(request.design_id)
    inputs = (
        {
            "analysis": "dc",
            "mode": "saved_operating_point",
            "statement_sha256": hashlib.sha256(b"dc save=all").hexdigest(),
        }
        if analysis == "dc"
        else {"analysis": "ac", "start_hz": "10", "stop_hz": "1000000", "points_per_decade": 10}
        if analysis == "ac"
        else {"analysis": "tran", "stop_s": "0.004", "maxstep_s": "0.00001", "method": "trap"}
    )
    registration = AdeExecutionRegistration.model_validate_json(
        json.dumps(
            {
                "schema_version": 1,
                "design_id": request.design_id,
                "analysis_id": request.analysis_id,
                "design_profile_sha256": canonical_digest(profile),
                "variable_set_sha256": canonical_digest(variables),
                "source_tree_sha256": "1" * 64,
                "ade_state_tree_sha256": "2" * 64,
                "static_statements_sha256": static_fingerprint(static.splitlines()),
                "model_includes": [],
                "inputs": inputs,
            }
        )
    )
    analysis_line = {
        "dc": "dc save=all",
        "ac": "ac start=10 stop=1000000 dec=10",
        "tran": "tran stop=0.004 maxstep=0.00001 method=trap",
    }[analysis]
    data = (
        "simulator lang=spectre\nparameters ExampleBiasN=1 ExampleBiasP=1\n"
        + static
        + "\nanalysis0 "
        + analysis_line
        + "\n"
    ).encode("ascii")
    return context, plan, registration, data


@pytest.mark.parametrize("analysis", ["dc", "ac", "tran"])
def test_compile_and_match_all_modes_without_native_authority(operator, analysis):
    context, plan, registration, data = setup(operator, analysis)
    operation_id = str(uuid4())
    script = render_netlist(context, plan, registration, operation_id)
    assert b"ExampleLib" not in script and b"ExampleAmplifier" not in script
    assert b"MCP_GREL_Work" in script and operation_id.encode() in script
    assert plan.plan_sha256.encode() in script
    assert script.count(b"asiSetDesignVarList(session") == 1
    assert b'list("ExampleBiasN" "1") list("ExampleBiasP" "1")' in script
    assert b"dbSave" not in script and b"asiSaveState" not in script and b"run()" not in script
    report = verify_effective_input(context, plan, registration, operation_id, data)
    assert report["analysis"] == analysis and report["template_sha256"] == template_sha256()
    assert report["input_sha256"] == hashlib.sha256(data).hexdigest()
    assert not report["execution_authorized"] and not report["native_source_copy_attested"]
    assert not report["native_model_bytes_attested"] and not report["remote_contact"]
    assert not context.binding.analysis_journal.exists() and not context.lock_path.exists()


def test_same_template_two_distinct_registered_circuits(operator):
    context, plan, registration, data = setup(operator)
    first = verify_effective_input(context, plan, registration, str(uuid4()), data)
    registry = json.loads(context.contracts.designs.model_dump_json())
    profile = registry["designs"][0]
    profile.update(design_id="new-small-mos")
    profile["binding"]["library"] = "NewMosLib"
    profile["binding"]["cell"] = "NewSmallMos"
    digest = canonical_digest(DesignProfile.model_validate_json(json.dumps(profile)))
    registry["variable_sets"][0].update(
        design_id=profile["design_id"], design_profile_sha256=digest
    )
    from cadence_mcp_bridge.variable_contracts import DesignVariables

    variable_digest = canonical_digest(
        DesignVariables.model_validate_json(json.dumps(registry["variable_sets"][0]))
    )
    for contract in registry["analysis_contracts"]:
        contract.update(
            design_id=profile["design_id"],
            design_profile_sha256=digest,
            variable_set_sha256=variable_digest,
        )
    second_registry = DesignAnalysisRegistry.model_validate_json(json.dumps(registry))
    second_catalog_digest = hashlib.sha256(second_registry.model_dump_json().encode()).hexdigest()
    second_context = replace(
        context,
        binding=context.binding.model_copy(update={"design_sha256": second_catalog_digest}),
        contracts=replace(
            context.contracts, designs=second_registry, design_sha256=second_catalog_digest
        ),
    )
    second_plan = plan.model_copy(
        update={
            "design_sha256": second_catalog_digest,
            "request": plan.request.model_copy(update={"design_id": profile["design_id"]}),
        }
    )
    second_registration = registration.model_copy(
        update={
            "design_id": profile["design_id"],
            "design_profile_sha256": digest,
            "variable_set_sha256": variable_digest,
            "static_statements_sha256": static_fingerprint(MOS.splitlines()),
        }
    )
    second_data = data.replace(RC.encode(), MOS.encode())
    second = verify_effective_input(
        second_context, second_plan, second_registration, str(uuid4()), second_data
    )
    assert first["template_sha256"] == second["template_sha256"]
    assert first["input_sha256"] != second["input_sha256"]
    assert first["plan_sha256"] != second["plan_sha256"]
    with pytest.raises(OperationRejected):
        verify_effective_input(context, plan, registration, str(uuid4()), second_data)


@pytest.mark.parametrize(
    "old,new,reason",
    [
        (b"ExampleBiasN=1", b"ExampleBiasN=2", "spectre_explicit_parameters_mismatch"),
        (b"ExampleBiasN=1", b"ExampleBiasN=(1+0)", "spectre_scalar_expression_denied"),
        (b"ExampleBiasN=1", b"ExampleBiasN=1 ExampleBiasN=1", "spectre_parameters_invalid"),
        (b"ExampleBiasN=1", b"ExtraHidden=1", "spectre_explicit_parameters_mismatch"),
        (b"r=1000", b"r=2000", "spectre_static_inputs_mismatch"),
        (b"c=0.000001", b"c=0.000002", "spectre_static_inputs_mismatch"),
        (b"dec=10", b"dec=20", "spectre_analysis_binding_mismatch"),
        (b"dec=10", b"dec=10 start=10", "spectre_analysis_binding_mismatch"),
        (b"dec=10", b"dec=10\nextra tran stop=1", "spectre_analysis_binding_mismatch"),
        (
            b"dec=10",
            b'dec=10\ninclude "/models/other.scs" section=NN',
            "spectre_model_binding_mismatch",
        ),
        (b"dec=10", b"dec=10 // changed", "spectre_dialect_unsupported"),
        (b"dec=10", b"dec=10\n+ continuation", "spectre_dialect_unsupported"),
        (b"r=1000", b'r="1000"', "spectre_dialect_unsupported"),
        (b"lang=spectre", b"lang=spice", "spectre_dialect_unsupported"),
    ],
)
def test_effective_inputs_reject_hidden_inheritance_and_substitution(operator, old, new, reason):
    context, plan, registration, data = setup(operator)
    with pytest.raises(OperationRejected) as error:
        verify_effective_input(context, plan, registration, str(uuid4()), data.replace(old, new))
    assert error.value.reason == reason
    assert str(error.value) == "Operator operation rejected"


@pytest.mark.parametrize(
    "analysis,old,new",
    [
        ("dc", b"save=all", b"save=none"),
        ("tran", b"stop=0.004", b"stop=0.008"),
        ("tran", b"method=trap", b"method=gear2only"),
    ],
)
def test_complete_analysis_conditions(operator, analysis, old, new):
    context, plan, registration, data = setup(operator, analysis)
    with pytest.raises(OperationRejected) as error:
        verify_effective_input(context, plan, registration, str(uuid4()), data.replace(old, new))
    assert error.value.reason == "spectre_analysis_binding_mismatch"


def test_whitespace_numeric_forms_and_comments_do_not_change_semantics(operator):
    context, plan, registration, data = setup(operator)
    changed = (
        data.replace(b"ExampleBiasN=1", b"ExampleBiasN=1.0")
        .replace(b"start=10", b"start=1e1")
        .replace(b"r=1000", b"r=1000  ")
    )
    changed = b"// synthetic comment\n" + changed
    report = verify_effective_input(context, plan, registration, str(uuid4()), changed)
    assert report["input_sha256"] != hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize(
    "field,value",
    [
        ("design_profile_sha256", "a" * 64),
        ("variable_set_sha256", "a" * 64),
        ("analysis_id", "another-analysis"),
        ("design_id", "another-design"),
    ],
)
def test_registration_identity_mismatch(operator, field, value):
    context, plan, registration, _ = setup(operator)
    with pytest.raises(OperationRejected) as error:
        render_netlist(context, plan, registration.model_copy(update={field: value}), str(uuid4()))
    assert error.value.reason == "ade_registration_binding_mismatch"


@pytest.mark.parametrize(
    "field,value",
    [
        ("ledger_ref", "different-ledger"),
        ("resource_domain_sha256", "f" * 64),
        ("environment_sha256", "f" * 64),
        ("design_sha256", "f" * 64),
        ("pdk_sha256", "f" * 64),
        ("runner_sha256", "f" * 64),
    ],
)
def test_plan_context_binding(operator, field, value):
    context, plan, registration, _ = setup(operator)
    with pytest.raises(OperationRejected) as error:
        render_netlist(context, plan.model_copy(update={field: value}), registration, str(uuid4()))
    assert error.value.reason == "ade_context_binding_mismatch"


@pytest.mark.parametrize("value", ['evil" exit(0)', "with space", "bad\nname", "../escape"])
def test_operator_strings_cannot_inject_skill(operator, value):
    context, _, _, _ = operator
    raw = json.loads(context.contracts.designs.designs[0].model_dump_json())
    raw["binding"]["ade"]["state"] = value
    with pytest.raises(ValidationError):
        DesignProfile.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "inputs",
    [
        {"analysis": "ac", "start_hz": "10", "stop_hz": "10", "points_per_decade": 10},
        {"analysis": "ac", "start_hz": "1e-6", "stop_hz": "1e12", "points_per_decade": 1000},
        {"analysis": "ac", "start_hz": "1", "stop_hz": "1e6", "points_per_decade": True},
        {"analysis": "tran", "stop_s": "1", "maxstep_s": "1e-12", "method": "trap"},
        {"analysis": "tran", "stop_s": "1", "maxstep_s": "2", "method": "trap"},
        {"analysis": "tran", "stop_s": "1", "maxstep_s": "0.01", "method": "custom()"},
    ],
)
def test_bounds_reject_expressions_and_excessive_work(inputs):
    model = AcInputs if inputs["analysis"] == "ac" else TranInputs
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(inputs))


def cli_args(operator, tmp_path, analysis="ac"):
    context, grant, request, settings = operator
    _, plan, registration, data = setup(operator, analysis)
    request = request.model_copy(update={"analysis_id": "example-" + analysis})
    grant_path, request_path, reg_path = [
        tmp_path / (s + ".json") for s in ("grant", "request", "reg")
    ]
    grant_path.write_text(grant.model_dump_json(), encoding="utf-8")
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    # Recompute plan for the real byte digest of the local grant file.
    grant_digest = hashlib.sha256(grant_path.read_bytes()).hexdigest()
    plan = prepare_plan(context, grant, grant_digest, request, int(time.time()))
    reg_path.write_text(registration.model_dump_json(), encoding="utf-8")
    return [
        "--settings",
        str(settings),
        "--context",
        "operator",
        "--grant",
        str(grant_path),
        "--expected-grant-sha256",
        grant_digest,
        "--request",
        str(request_path),
        "--registration",
        str(reg_path),
        "--expected-registration-sha256",
        hashlib.sha256(reg_path.read_bytes()).hexdigest(),
        "--operation-id",
        str(uuid4()),
        "--expected-plan-sha256",
        plan.plan_sha256,
    ], data


def test_cli_exclusive_compile_verify_receipts_no_public_bindings(operator, tmp_path, capsys):
    args, data = cli_args(operator, tmp_path)
    output = tmp_path / "prepared"
    assert main(["ade-input", "compile", *args, "--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "LOCAL_ADE_INPUTS_PREPARED_NATIVE_UNQUALIFIED"
    assert not report["execution_authorized"] and not report["remote_contact"]
    assert set(p.name for p in output.iterdir()) == {
        "manifest.json",
        "registration.json",
        "netlist.ocn",
    }
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    assert main(["ade-input", "compile", *args, "--output", str(output)]) == 1
    denied = capsys.readouterr().out
    assert "ExampleLib" not in denied and str(tmp_path) not in denied
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    netlist = tmp_path / "synthetic.scs"
    netlist.write_bytes(data)
    assert main(["ade-input", "verify-input", *args, "--native-input", str(netlist)]) == 0
    result = capsys.readouterr().out
    assert json.loads(result)["status"] == "LOCAL_EFFECTIVE_INPUT_MATCHED"
    assert "ExampleBias" not in result and "R0" not in result and str(tmp_path) not in result


def test_cli_stale_registration_and_plan_rejected_before_output(operator, tmp_path, capsys):
    args, _ = cli_args(operator, tmp_path)
    for flag in ("--expected-registration-sha256", "--expected-plan-sha256"):
        changed = args.copy()
        changed[changed.index(flag) + 1] = "f" * 64
        output = tmp_path / flag[2:]
        assert main(["ade-input", "compile", *changed, "--output", str(output)]) == 1
        assert not output.exists()
        assert str(tmp_path) not in capsys.readouterr().out


def test_bounded_native_file_and_hardlink_denied(operator, tmp_path, capsys):
    import os

    args, _ = cli_args(operator, tmp_path)
    netlist = tmp_path / "synthetic.scs"
    netlist.write_bytes(b"x" * 262145)
    assert main(["ade-input", "verify-input", *args, "--native-input", str(netlist)]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "ade_input_size_exceeded"
    alias = tmp_path / "alias.scs"
    os.link(netlist, alias)
    assert main(["ade-input", "verify-input", *args, "--native-input", str(alias)]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "ade_input_file_invalid"


def test_model_sections_and_reference_protection(operator):
    from cadence_mcp_bridge.generic_ade import ModelInclude

    context, plan, registration, data = setup(operator)
    root = context.contracts.environment.paths.protected_roots[0]
    model = ModelInclude(path=root + "/synthetic-model.scs", section="NN", file_sha256="3" * 64)
    registration = registration.model_copy(update={"model_includes": (model,)})
    data += ('include "' + model.path + '" section=NN\n').encode()
    report = verify_effective_input(context, plan, registration, str(uuid4()), data)
    assert report["model_count"] == 1 and not report["native_model_bytes_attested"]
    for changed in (
        data.replace(b"section=NN", b"section=FF"),
        data + data.splitlines()[-1] + b"\n",
    ):
        with pytest.raises(OperationRejected) as error:
            verify_effective_input(context, plan, registration, str(uuid4()), changed)
        assert error.value.reason == "spectre_model_binding_mismatch"
    outside = registration.model_copy(
        update={"model_includes": (model.model_copy(update={"path": "/unprotected/model.scs"}),)}
    )
    with pytest.raises(OperationRejected) as error:
        render_netlist(context, plan, outside, str(uuid4()))
    assert error.value.reason == "model_reference_outside_protected_roots"


@pytest.mark.parametrize("kind", ["ade_xl", "explorer", "assembler"])
def test_unsupported_ade_subtypes_do_not_fallback(operator, kind):
    context, plan, registration, _ = setup(operator)
    registry = context.contracts.designs
    old = registry.designs[0]
    profile = old.model_copy(
        update={
            "binding": old.binding.model_copy(
                update={"ade": old.binding.ade.model_copy(update={"kind": kind})}
            )
        }
    )
    # Deliberately constructed synthetic context to exercise the adapter gate.
    changed = replace(
        context,
        contracts=replace(
            context.contracts, designs=registry.model_copy(update={"designs": (profile,)})
        ),
    )
    registration = registration.model_copy(
        update={"design_profile_sha256": canonical_digest(profile)}
    )
    with pytest.raises(OperationRejected) as error:
        render_netlist(changed, plan, registration, str(uuid4()))
    assert error.value.reason == "ade_subtype_or_copy_policy_unsupported"


def test_zero_variable_inputs_do_not_inherit_parameters(operator):
    context, plan, registration, data = setup(operator)
    registry = context.contracts.designs
    profile = registry.designs[0].model_copy(update={"allowed_variables": ()})
    changed = replace(
        context,
        contracts=replace(
            context.contracts,
            designs=registry.model_copy(update={"designs": (profile,), "variable_sets": ()}),
        ),
    )
    plan = plan.model_copy(update={"request": plan.request.model_copy(update={"values": ()})})
    registration = registration.model_copy(
        update={"design_profile_sha256": canonical_digest(profile), "variable_set_sha256": None}
    )
    script = render_netlist(changed, plan, registration, str(uuid4()))
    assert b"asiSetDesignVarList(session" not in script
    with pytest.raises(OperationRejected) as error:
        verify_effective_input(changed, plan, registration, str(uuid4()), data)
    assert error.value.reason == "spectre_explicit_parameters_mismatch"
    data = data.replace(b"parameters ExampleBiasN=1 ExampleBiasP=1\n", b"")
    assert (
        verify_effective_input(changed, plan, registration, str(uuid4()), data)["parameter_count"]
        == 0
    )
