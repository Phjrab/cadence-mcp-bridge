"""Pure local logical checks; fixture parameters establish no production CDF facts."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.schematic_plan import (
    DeviceRegistry,
    DisplayPoint,
    DisplayWire,
    RevisionBinding,
    SchematicPlan,
    dry_run_plan,
    semantic_diff,
    synthetic_inverter_fixture,
)


def binding(**updates: Any) -> RevisionBinding:
    return RevisionBinding.model_validate(
        {
            "workspace_id": "local-workspace",
            "design_id": "inverter",
            "revision_id": "rev-one",
            "source_baseline_sha256": "a" * 64,
            **updates,
        }
    )


def fixture() -> tuple[DeviceRegistry, SchematicPlan]:
    return synthetic_inverter_fixture(binding())


def parse(raw: dict[str, Any]) -> SchematicPlan:
    return SchematicPlan.model_validate_json(json.dumps(raw))


def test_fixture_dry_run_never_creates_electrical_or_execution_signoff() -> None:
    registry, plan = fixture()
    result = dry_run_plan(plan, registry, binding())
    assert result.status == "LOCAL_SYNTHETIC_PLAN_VALID"
    assert result.plan_sha256 == plan.plan_sha256
    assert result.semantic_sha256 == plan.semantic_sha256
    assert result.execution_authorized is False
    assert result.oa_created is False
    assert result.erc_status == result.lvs_status == "NOT_RUN"
    assert result.electrical_validation == "bounded_inverter_rules_only"
    assert all(change.change == "added" for change in result.semantic_diff)
    assert dry_run_plan(parse(json.loads(plan.model_dump_json())), registry, binding()) == result


@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_id", "another-workspace"),
        ("design_id", "another-design"),
        ("revision_id", "rev-two"),
        ("source_baseline_sha256", "b" * 64),
    ],
)
def test_independently_resolved_target_binding_rejects_mismatch(field: str, value: str) -> None:
    registry, plan = fixture()
    with pytest.raises(ValueError, match="binding mismatch"):
        dry_run_plan(plan, registry, binding(**{field: value}))


def test_parent_digest_mismatch_and_missing_pair_reject() -> None:
    registry, original = fixture()
    parent = binding(
        revision_id="rev-two", parent_revision_id="rev-one", parent_revision_sha256="b" * 64
    )
    plan = original.model_copy(update={"binding": parent})
    with pytest.raises(ValueError, match="binding mismatch"):
        dry_run_plan(plan, registry, parent.model_copy(update={"parent_revision_sha256": "c" * 64}))
    with pytest.raises(ValueError, match="together"):
        binding(parent_revision_id="rev-zero")
    with pytest.raises(ValueError, match="parent itself"):
        binding(parent_revision_id="rev-one", parent_revision_sha256="b" * 64)


def test_parent_plan_preserves_external_source_and_diff_is_revision_independent() -> None:
    registry, parent = fixture()
    child_binding = binding(
        revision_id="rev-two", parent_revision_id="rev-one", parent_revision_sha256="b" * 64
    )
    child = parent.model_copy(update={"binding": child_binding})
    result = dry_run_plan(child, registry, child_binding, parent)
    assert result.semantic_diff == ()
    assert child.semantic_sha256 == parent.semantic_sha256
    assert child.plan_sha256 != parent.plan_sha256
    assert result.binding.source_baseline_sha256 == parent.binding.source_baseline_sha256


def test_child_cannot_omit_bound_parent_diff_input() -> None:
    registry, parent = fixture()
    child_binding = binding(
        revision_id="rev-two", parent_revision_id="rev-one", parent_revision_sha256="b" * 64
    )
    child = parent.model_copy(update={"binding": child_binding})
    with pytest.raises(ValueError, match="requires the bound parent plan"):
        dry_run_plan(child, registry, child_binding)


@pytest.mark.parametrize(
    "updates",
    [
        {"revision_id": "wrong-parent"},
        {"design_id": "another"},
        {"workspace_id": "another"},
        {"source_baseline_sha256": "d" * 64},
    ],
)
def test_unrelated_parent_plan_rejects(updates: dict[str, Any]) -> None:
    registry, parent = fixture()
    child_binding = binding(
        revision_id="rev-two", parent_revision_id="rev-one", parent_revision_sha256="b" * 64
    )
    child = parent.model_copy(update={"binding": child_binding})
    wrong = parent.model_copy(update={"binding": binding(**updates)})
    with pytest.raises(ValueError, match="parent plan or source"):
        dry_run_plan(child, registry, child_binding, wrong)


def test_order_and_decimal_spelling_are_semantically_irrelevant() -> None:
    registry, plan = fixture()
    raw = json.loads(plan.model_dump_json())
    for name in ("dut", "testbench"):
        for key in ("instances", "pins", "nets"):
            raw[name][key].reverse()
        for instance in raw[name]["instances"]:
            instance["connections"].reverse()
            instance["parameters"].reverse()
            for parameter in instance["parameters"]:
                if parameter["value"] == "1":
                    parameter["value"] = "+1.000e0"
    raw["testbench"]["dut_reference"]["connections"].reverse()
    reordered = parse(raw)
    assert reordered.plan_sha256 == plan.plan_sha256
    assert reordered.semantic_sha256 == plan.semantic_sha256
    assert dry_run_plan(reordered, registry, binding()) == dry_run_plan(plan, registry, binding())
    registry_raw = json.loads(registry.model_dump_json())
    registry_raw["devices"].reverse()
    for device in registry_raw["devices"]:
        device["parameters"].reverse()
        device["terminals"].reverse()
    assert DeviceRegistry.model_validate_json(json.dumps(registry_raw)).semantic_sha256 == (
        registry.semantic_sha256
    )


def test_display_geometry_cannot_connect_or_change_electrical_semantics() -> None:
    registry, plan = fixture()
    display = (
        DisplayWire(
            wire_id="line",
            circuit_id=plan.dut.circuit_id,
            net_id="output",
            points=(DisplayPoint(x=0, y=0), DisplayPoint(x=1, y=1)),
        ),
    )
    illustrated = plan.model_copy(update={"display": display})
    result = dry_run_plan(illustrated, registry, binding())
    assert result.semantic_sha256 == plan.semantic_sha256
    assert result.plan_sha256 != plan.plan_sha256
    assert semantic_diff(plan, illustrated) == ()
    raw = json.loads(illustrated.model_dump_json())
    raw["dut"]["instances"][0]["connections"][0]["net_id"] = "input"
    with pytest.raises(ValueError, match="wiring rule"):
        dry_run_plan(parse(raw), registry, binding())


def test_diff_records_exact_parameter_change_with_stable_hashes() -> None:
    registry, parent = fixture()
    raw = json.loads(parent.model_dump_json())
    raw["binding"] = binding(
        revision_id="rev-two", parent_revision_id="rev-one", parent_revision_sha256="b" * 64
    ).model_dump(mode="json")
    raw["dut"]["instances"][0]["parameters"][0]["value"] = "2"
    child = parse(raw)
    diff = dry_run_plan(child, registry, child.binding, parent).semantic_diff
    assert len(diff) == 1
    assert (diff[0].kind, diff[0].entity_id, diff[0].change) == ("instance", "nmos", "changed")
    assert diff[0].before_sha256 != diff[0].after_sha256
    assert semantic_diff(parent, child) == diff


@pytest.mark.parametrize(
    "change",
    [
        "unknown-device",
        "unknown-terminal",
        "missing-terminal",
        "duplicate-terminal",
        "unknown-parameter",
        "missing-parameter",
        "duplicate-parameter",
        "wrong-unit",
        "out-of-range",
        "nonintegral",
        "unknown-net",
        "wrong-wiring",
    ],
)
def test_invalid_instance_contracts_reject(change: str) -> None:
    registry, plan = fixture()
    raw = json.loads(plan.model_dump_json())
    instance = raw["dut"]["instances"][0]
    if change == "unknown-device":
        instance["device_id"] = "unknown"
    elif change == "unknown-terminal":
        instance["connections"][0]["terminal_id"] = "x"
    elif change == "missing-terminal":
        instance["connections"].pop()
    elif change == "duplicate-terminal":
        instance["connections"][0]["terminal_id"] = "g"
    elif change == "unknown-parameter":
        instance["parameters"][0]["parameter_id"] = "unknown"
    elif change == "missing-parameter":
        instance["parameters"].pop()
    elif change == "duplicate-parameter":
        instance["parameters"][0]["parameter_id"] = "l"
    elif change == "wrong-unit":
        instance["parameters"][0]["unit"] = "m"
    elif change == "out-of-range":
        instance["parameters"][0]["value"] = "11"
    elif change == "nonintegral":
        instance["parameters"][2]["value"] = "1.5"
    elif change == "unknown-net":
        instance["connections"][0]["net_id"] = "missing"
    else:
        instance["connections"][0]["net_id"] = "input"
    with pytest.raises(ValueError):
        dry_run_plan(parse(raw), registry, binding())


@pytest.mark.parametrize(
    "value", [True, 1, 1.0, "NaN", "Infinity", "1e100", "1um", "w*2", "1;system", "", " " * 49]
)
def test_numbers_do_not_accept_coercion_expressions_or_nonfinite_values(value: Any) -> None:
    _, plan = fixture()
    raw = json.loads(plan.model_dump_json())
    raw["dut"]["instances"][0]["parameters"][0]["value"] = value
    with pytest.raises(ValueError):
        parse(raw)


@pytest.mark.parametrize(
    "change",
    [
        "instance-id",
        "net-id",
        "pin-id",
        "pin-conflict",
        "pin-role",
        "supply-short",
        "wrong-dut",
        "dut-port",
        "extra-net",
        "display-net",
        "extra-code",
        "wrong-role",
    ],
)
def test_topology_and_pin_conflicts_reject(change: str) -> None:
    registry, plan = fixture()
    raw = json.loads(plan.model_dump_json())
    if change == "instance-id":
        raw["dut"]["instances"][1]["instance_id"] = "nmos"
    elif change == "net-id":
        raw["dut"]["nets"][1]["net_id"] = "vdd"
    elif change == "pin-id":
        raw["dut"]["pins"][1]["pin_id"] = "vdd"
    elif change == "pin-conflict":
        raw["dut"]["pins"][1]["net_id"] = "vdd"
    elif change == "pin-role":
        raw["dut"]["pins"][0]["role"] = "input"
    elif change == "supply-short":
        raw["testbench"]["instances"][0]["connections"][0]["net_id"] = "vss"
    elif change == "wrong-dut":
        raw["testbench"]["dut_reference"]["dut_circuit_id"] = "unrelated"
    elif change == "dut-port":
        raw["testbench"]["dut_reference"]["connections"][0]["net_id"] = "input"
    elif change == "extra-net":
        raw["dut"]["nets"].append({"net_id": "unused", "role": "internal"})
    elif change == "display-net":
        raw["display"] = [
            {
                "wire_id": "wire",
                "circuit_id": "inverter-dut",
                "net_id": "missing",
                "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}],
            }
        ]
    elif change == "extra-code":
        raw["skill"] = "arbitrary code"
    else:
        raw["dut"]["role"] = "testbench"
    with pytest.raises(ValueError):
        dry_run_plan(parse(raw), registry, binding())


def test_unverified_production_registry_cannot_inherit_fixture_parameter_semantics() -> None:
    registry, plan = fixture()
    raw = json.loads(registry.model_dump_json())
    raw["provenance"] = "production_cdf_unverified"
    with pytest.raises(ValueError, match="synthetic parameter bounds"):
        DeviceRegistry.model_validate_json(json.dumps(raw))
    for device in raw["devices"]:
        device["parameters"] = []
    production = DeviceRegistry.model_validate_json(json.dumps(raw))
    planned = json.loads(plan.model_dump_json())
    planned["registry_sha256"] = production.semantic_sha256
    for circuit in (planned["dut"], planned["testbench"]):
        for instance in circuit["instances"]:
            instance["parameters"] = []
    result = dry_run_plan(parse(planned), production, binding())
    assert result.status == "BLOCKED_PRODUCTION_CDF_UNVERIFIED"
    assert result.execution_authorized is False


def test_registry_mutation_or_duplicate_registration_rejects() -> None:
    registry, plan = fixture()
    raw = json.loads(registry.model_dump_json())
    raw["devices"][0]["parameters"][0]["maximum"] = "20"
    changed = DeviceRegistry.model_validate_json(json.dumps(raw))
    with pytest.raises(ValueError, match="registry digest"):
        dry_run_plan(plan, changed, binding())
    raw["devices"].append(copy.deepcopy(raw["devices"][0]))
    with pytest.raises(ValueError, match="duplicate device"):
        DeviceRegistry.model_validate_json(json.dumps(raw))


def test_model_copy_validation_bypass_is_rechecked_at_dry_run_boundary() -> None:
    registry, plan = fixture()
    invalid = plan.model_copy(update={"dut": plan.dut.model_copy(update={"pins": ()})})
    with pytest.raises(ValidationError):
        dry_run_plan(invalid, registry, binding())


@pytest.mark.parametrize("identifier", ["../escape", "C:/path", "a;cmd", "a b", "a\n", "$exec"])
def test_ids_cannot_accept_paths_or_code(identifier: str) -> None:
    with pytest.raises(ValueError):
        binding(revision_id=identifier)


@pytest.mark.parametrize("value", ["0.1", "10"])
def test_registered_range_is_inclusive(value: str) -> None:
    registry, plan = fixture()
    raw = json.loads(plan.model_dump_json())
    raw["dut"]["instances"][0]["parameters"][0]["value"] = value
    assert dry_run_plan(parse(raw), registry, binding()).status == "LOCAL_SYNTHETIC_PLAN_VALID"
