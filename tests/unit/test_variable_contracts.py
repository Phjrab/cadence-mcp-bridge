from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import Client
from pydantic import ValidationError

import cadence_mcp_bridge.__main__ as cli
from cadence_mcp_bridge.designs import (
    DesignContractRegistry,
    DesignRegistry,
    DesignRejected,
    load_design_registry,
    reference_contract_registry,
    reference_registry,
    register_designs,
)
from cadence_mcp_bridge.profiles import FIXTURE_PROFILE
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.variable_contracts import (
    VariableContract,
    VariableValuesRequest,
    canonical_digest,
    number_text,
)


def fixture_contract() -> dict[str, Any]:
    # Reuse reviewed RC fixture bounds, never fabricate amplifier safety limits.
    bounds = FIXTURE_PROFILE.variables[0]
    assert bounds.name == "resistance_ohm"
    return {
        "logical_id": "resistance",
        "cadence_binding": "PrivateResistance",
        "unit": "ohm",
        "value_type": "real",
        "default": str(bounds.default),
        "mutation_policy": "owned_copy_only",
        "range_status": "qualified",
        "minimum": str(bounds.minimum),
        "maximum": str(bounds.maximum),
        "step_policy": "continuous",
        "step": None,
        "fixed_value": None,
        "review_id": "review-fixture",
    }


def reviewed_payload() -> dict[str, Any]:
    value = reference_registry().model_dump(mode="json")
    profile = value["designs"][0]
    profile.update(design_id="fixture-contract", allowed_variables=["resistance"])
    profile["binding"] = {
        "library": "PrivateLibrary",
        "cell": "PrivateCell",
        "view": "schematic",
        "ade": {"kind": "ade_l", "state": "PrivateState"},
    }
    design = DesignRegistry.model_validate_json(json.dumps(value)).designs[0]
    variable = VariableContract.model_validate(fixture_contract())
    digest = canonical_digest(design)
    return {
        "schema_version": 2,
        "designs": value["designs"],
        "variable_sets": [
            {
                "design_id": design.design_id,
                "design_profile_sha256": digest,
                "variables": [variable.model_dump(mode="json")],
            }
        ],
        "range_reviews": [
            {
                "review_id": "review-fixture",
                "design_id": design.design_id,
                "design_profile_sha256": digest,
                "variable_contract_sha256": canonical_digest(variable),
                "evidence_id": "registered-rc-fixture",
                "evidence_sha256": canonical_digest(FIXTURE_PROFILE),
                "scope": "operator_reviewed_project_numeric_contract",
            }
        ],
    }


def registry(payload: dict[str, Any] | None = None) -> DesignContractRegistry:
    return DesignContractRegistry.model_validate_json(json.dumps(payload or reviewed_payload()))


def request(value: str, unit: str = "ohm", logical_id: str = "resistance") -> VariableValuesRequest:
    return VariableValuesRequest.model_validate_json(
        json.dumps(
            {
                "design_id": "fixture-contract",
                "values": {logical_id: {"value": value, "unit": unit}},
            }
        )
    )


@pytest.mark.parametrize(
    "value",
    [
        True,
        1,
        1.0,
        None,
        "NaN",
        "Inf",
        "1 ",
        " 1",
        "١",
        "1;id",
        "1e41",
        "1e31",
        "1e-31",
        "0" * 49,
        "1e9999999",
    ],
)
def test_decimal_values_are_closed_and_bounded(value: Any) -> None:
    with pytest.raises((ValueError, ValidationError)):
        number_text(value)


@pytest.mark.parametrize(
    "value,canonical", [("1e-3", "0.001"), ("+1.00", "1"), ("-0", "0"), (".0010", "0.001")]
)
def test_decimal_canonicalization_is_exact(value: str, canonical: str) -> None:
    assert number_text(value) == canonical


@pytest.mark.parametrize(
    "value,admissible,reason",
    [
        ("100", True, "numeric_contract_matched"),
        ("10000", True, "numeric_contract_matched"),
        ("99.999999999999999999999999999", False, "outside_reviewed_range"),
        ("10000.000000000000000000000001", False, "outside_reviewed_range"),
    ],
)
def test_exact_range_endpoints(value: str, admissible: bool, reason: str) -> None:
    result = registry().check_variables(request(value))
    assert result.locally_admissible is admissible
    assert result.values[0].reason == reason
    assert result.execution_authorized is False and result.spec_evaluation == "not_evaluated"


@pytest.mark.parametrize(
    "step,value,reason",
    [
        ("0.1", "100.3", None),
        ("0.1", "100.3000000000000000000001", "off_grid"),
        ("0.000000000000000000000000000001", "100.000000000000000000000000000001", None),
    ],
)
def test_decimal_grid_uses_lower_bound_and_exact_remainder(
    step: str,
    value: str,
    reason: str | None,
) -> None:
    payload = fixture_contract()
    payload.update(step_policy="grid", step=step, default=None)
    assert VariableContract.model_validate(payload).check_number(value) == reason


@pytest.mark.parametrize(
    "updates",
    [
        {"range_status": "unqualified"},
        {"review_id": None},
        {"minimum": "10000"},
        {"maximum": "100"},
        {"default": "99"},
        {"step_policy": "unqualified"},
        {"step_policy": "grid", "step": "0"},
        {"step_policy": "grid", "step": "-1"},
        {"step_policy": "grid", "step": "3", "default": "101"},
        {"step": "1"},
        {"value_type": "integer", "minimum": "100.1"},
        {"mutation_policy": "fixed"},
        {"fixed_value": "1"},
        {"cadence_binding": "x;id"},
        {"cadence_binding": "/private"},
        {"unit": "mV"},
        {"path": "/private"},
        {"execution_authorized": True},
    ],
)
def test_incoherent_or_executable_contract_rejected(updates: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VariableContract.model_validate({**fixture_contract(), **updates})


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("design", "environment_id", "different-environment"),
        ("design", "pdk_adapter_id", "different-pdk"),
        ("design", "work_copy_policy", "read_only"),
        ("variable", "maximum", "20000"),
        ("variable", "cadence_binding", "OtherBinding"),
        ("variable", "unit", "V"),
        ("variable", "mutation_policy", "read_only"),
        ("review", "design_id", "other-design"),
        ("review", "design_profile_sha256", "0" * 64),
        ("review", "variable_contract_sha256", "0" * 64),
        ("review", "scope", "electrically_safe"),
    ],
)
def test_stale_or_substituted_review_rejected(target: str, field: str, value: Any) -> None:
    payload = reviewed_payload()
    obj = {
        "design": payload["designs"][0],
        "variable": payload["variable_sets"][0]["variables"][0],
        "review": payload["range_reviews"][0],
    }[target]
    obj[field] = value
    with pytest.raises(ValidationError):
        registry(payload)


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "orphan",
        "duplicate",
        "duplicate-set",
        "wrong-set",
        "missing-variable",
        "binding-alias",
    ],
)
def test_review_and_variable_identity_are_one_to_one(kind: str) -> None:
    payload = reviewed_payload()
    if kind == "missing":
        payload["range_reviews"] = []
    elif kind == "orphan":
        extra = {**payload["range_reviews"][0], "review_id": "orphan"}
        payload["range_reviews"].append(extra)
    elif kind == "duplicate":
        payload["range_reviews"] *= 2
    elif kind == "duplicate-set":
        payload["variable_sets"] *= 2
    elif kind == "wrong-set":
        payload["variable_sets"][0]["design_id"] = "unknown"
    elif kind == "missing-variable":
        payload["variable_sets"][0]["variables"] = []
    else:
        variables = payload["variable_sets"][0]["variables"]
        variables.append({**variables[0], "logical_id": "alias"})
    with pytest.raises(ValidationError):
        registry(payload)


def test_reference_does_not_qualify_biases_or_apply_candidate_defaults() -> None:
    reference = reference_contract_registry()
    design_id = reference.designs[0].design_id
    described = reference.variables(design_id)
    assert described.missing_contracts == ()
    for variable in described.variables[:2]:
        assert variable.range_status == "unqualified" and variable.default is None
        assert variable.minimum is None and variable.maximum is None
    inputs = VariableValuesRequest.model_validate_json(
        json.dumps(
            {
                "design_id": design_id,
                "values": {
                    "vbiasn": {"value": "0.320", "unit": "V"},
                    "vbiasp": {"value": "0.702", "unit": "V"},
                    "vdd": {"value": "1.0", "unit": "V"},
                },
            }
        )
    )
    result = reference.check_variables(inputs)
    assert [v.reason for v in result.values] == [
        "unqualified_range",
        "unqualified_range",
        "fixed_constraint_matched",
    ]
    vdd_only = inputs.model_copy(update={"values": {"vdd": inputs.values["vdd"]}})
    assert reference.check_variables(vdd_only).locally_admissible is True
    assert len(reference.check_variables(vdd_only).values) == 1  # never fill defaults
    wrong = json.loads(vdd_only.model_dump_json())
    wrong["values"]["vdd"]["value"] = "0.999999999999999999999999999999"
    assert (
        reference.check_variables(VariableValuesRequest.model_validate_json(json.dumps(wrong)))
        .values[0]
        .reason
        == "fixed_value_mismatch"
    )


def test_readonly_unit_type_and_copy_denials_are_distinct() -> None:
    from cadence_mcp_bridge.variable_contracts import DesignVariables, check_values

    assert registry().check_variables(request("100", "V")).values[0].reason == "wrong_unit"
    assert (
        registry().check_variables(request("100", logical_id="other")).values[0].reason
        == "unregistered_variable"
    )
    variable = VariableContract.model_validate({**fixture_contract(), "value_type": "integer"})
    assert variable.check_number("100.5") == "nonintegral_value"
    contracts = DesignVariables(
        design_id="fixture-contract", design_profile_sha256="0" * 64, variables=(variable,)
    )
    assert (
        check_values(request("100"), contracts, "read_only").values[0].reason
        == "copy_policy_denied"
    )
    readonly = variable.model_copy(update={"mutation_policy": "read_only"})
    contracts = contracts.model_copy(update={"variables": (readonly,)})
    assert (
        check_values(request("100"), contracts, "owned_copy_only").values[0].reason
        == "read_only_variable"
    )


def test_v1_and_absent_v2_contracts_never_inherit_reference_bounds() -> None:
    v1 = reference_registry()
    assert v1.variables(v1.designs[0].design_id).variables == ()
    assert v1.variables(v1.designs[0].design_id).missing_contracts == ("vbiasn", "vbiasp", "vdd")
    v2 = DesignContractRegistry(
        schema_version=2, designs=v1.designs, variable_sets=(), range_reviews=()
    )
    assert v2.variables(v1.designs[0].design_id).variables == ()
    assert v2.listing() == v1.listing()
    assert v2.describe(v1.designs[0].design_id) == v1.describe(v1.designs[0].design_id)


def test_v2_load_register_schema_and_closed_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, output = tmp_path / "operator.json", tmp_path / "snapshot.json"
    source.write_text(json.dumps(reviewed_payload()), encoding="utf-8")
    loaded, _ = load_design_registry(source)
    assert isinstance(loaded, DesignContractRegistry)
    assert register_designs(source, output)["execution_authorized"] is False
    assert source.read_bytes() == output.read_bytes()
    assert cli.main(["design", "schema", "--schema-version", "2"]) == 0
    assert json.loads(capsys.readouterr().out) == DesignContractRegistry.model_json_schema()
    assert cli.main(["design", "validate", "--registry", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["execution_authorized"] is False
    payload = reviewed_payload()
    payload["range_reviews"] = []
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DesignRejected, match="^design_registry_invalid$"):
        load_design_registry(source)
    assert cli.main(["design", "validate", "--registry", str(source)]) == 1
    assert "Private" not in capsys.readouterr().out


class NoRemote:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Local variable checking contacted backend: {name}")


@pytest.mark.asyncio
async def test_mcp_local_validation_is_bounded_closed_and_private() -> None:
    service = CadenceService(cast(CadenceBackend, NoRemote()), registry())
    async with Client(create_server(service)) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert len(tools) == 66
        for name in ("cadence_list_design_variables", "cadence_check_variable_values"):
            assert tools[name].input_schema["additionalProperties"] is False
            assert tools[name].annotations is not None and tools[name].annotations.read_only_hint
        described = await client.call_tool(
            "cadence_list_design_variables", {"design_id": "fixture-contract"}
        )
        assert not described.is_error
        text = str(described.structured_content)
        for secret in ("Private", "cadence_binding", "review_id", "sha256", "evidence_id"):
            assert secret not in text
        valid = {"request": request("1e3").model_dump(mode="json")}
        checked = await client.call_tool("cadence_check_variable_values", valid)
        result = cast(dict[str, Any], checked.structured_content)
        assert not checked.is_error and result["locally_admissible"] is True
        assert result["execution_authorized"] is False
        bad = []
        for key in ("path", "script", "binding", "execution_authorized"):
            bad.append({**valid, key: True})
            nested = copy.deepcopy(valid)
            nested["request"][key] = True
            bad.append(nested)
        for value in (True, 1000, 1000.0, "NaN", "1;id"):
            nested = copy.deepcopy(valid)
            nested["request"]["values"]["resistance"]["value"] = value
            bad.append(nested)
        for entry in bad:
            assert (await client.call_tool("cadence_check_variable_values", entry)).is_error
        unknown = copy.deepcopy(valid)
        unknown["request"]["design_id"] = "unknown"
        assert (await client.call_tool("cadence_check_variable_values", unknown)).is_error
        assert (
            await client.call_tool(
                "cadence_list_design_variables",
                {"design_id": "fixture-contract", "path": "/private"},
            )
        ).is_error


def test_public_v2_schema_and_example() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (
        json.loads((root / "docs/schemas/design-registry-v2.schema.json").read_bytes())
        == DesignContractRegistry.model_json_schema()
    )
    loaded, _ = load_design_registry(root / "docs/examples/design-registry-v2.fictional.json")
    assert loaded.variables("example-amplifier").execution_authorized is False
