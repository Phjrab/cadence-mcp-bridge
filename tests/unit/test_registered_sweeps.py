"""Scientific denials, exact decimal planning and absence of execution/admission."""

from __future__ import annotations

import json
from decimal import localcontext
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from mcp import Client
from pydantic import ValidationError
from test_variable_contracts import reviewed_payload

from cadence_mcp_bridge.analyses import AnalysisContract
from cadence_mcp_bridge.designs import (
    DesignContractRegistry,
    DesignMeasurementRegistry,
    RegistryBase,
    reference_measurement_registry,
)
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.registered_measurements import RegisteredMeasurement
from cadence_mcp_bridge.registered_sweeps import (
    DesignSweepRequest,
    DesignSweepSelection,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.variable_contracts import canonical_digest

REFERENCE = "reference-differential-amplifier-tb2"


def fixture_registry(grid: bool = False) -> DesignMeasurementRegistry:
    """Reuse established RC numeric bounds; never qualify a physical reader/adapter."""
    payload = reviewed_payload()
    if grid:
        payload["variable_sets"][0]["variables"][0].update(step_policy="grid", step="100")
        from cadence_mcp_bridge.variable_contracts import VariableContract

        variable = VariableContract.model_validate_json(
            json.dumps(payload["variable_sets"][0]["variables"][0])
        )
        payload["range_reviews"][0]["variable_contract_sha256"] = canonical_digest(variable)
    base = DesignContractRegistry.model_validate_json(json.dumps(payload))
    analysis = AnalysisContract(
        design_id="fixture-contract",
        analysis_id="example-dc",
        analysis="dc",
        design_profile_sha256=canonical_digest(base.designs[0]),
        variable_set_sha256=canonical_digest(base.variable_sets[0]),
        adapter_kind="unqualified",
        adapter_contract_sha256=None,
        input_policy="unqualified",
    )
    measurement = RegisteredMeasurement(
        design_id="fixture-contract",
        measurement_id="dc-scalars",
        analysis_id="example-dc",
        analysis_contract_sha256=canonical_digest(analysis),
        reader="unqualified",
        output_id=None,
        definition_sha256=None,
    )
    return DesignMeasurementRegistry(
        **{**base.model_dump(), "schema_version": 4},
        analysis_contracts=(analysis,),
        measurement_contracts=(measurement,),
    )


def service(tmp_path: Path, registry: RegistryBase | None = None) -> CadenceService:
    return CadenceService(
        cast(CadenceBackend, MagicMock()),
        designs=registry,
        analysis_journal=tmp_path / "admissions.sqlite3",
        sweep_journal=tmp_path / "sweep.sqlite3",
    )


def selection(fixture: bool = False) -> DesignSweepSelection:
    return DesignSweepSelection(
        design_id="fixture-contract" if fixture else REFERENCE,
        analysis_id="example-dc" if fixture else "native-dc",
        variable_id="resistance" if fixture else "vbiasn",
        measurement_ids=("dc-scalars",),
    )


async def request(svc: CadenceService, fixture: bool = False, **changes: Any) -> DesignSweepRequest:
    selected = selection(fixture)
    described = await svc.describe_design_sweep(selected)
    payload = {
        **selected.model_dump(mode="json"),
        "expected_contract_sha256": described.contract_sha256,
        "unit": "ohm" if fixture else "V",
        "values": ["1000", "2000"] if fixture else ["0.32", "0.31"],
        "fixed": {}
        if fixture
        else {
            "vbiasp": {"value": "0.702", "unit": "V"},
            "vdd": {"value": "1", "unit": "V"},
        },
        **changes,
    }
    return DesignSweepRequest.model_validate_json(json.dumps(payload))


@pytest.mark.asyncio
async def test_reference_candidate_values_never_qualify_a_range_or_run(tmp_path: Path) -> None:
    svc = service(tmp_path)
    journal = (tmp_path / "sweep.sqlite3").read_bytes()
    plan = await svc.plan_design_sweep(await request(svc))
    assert not plan.locally_admissible and not plan.execution_authorized
    assert "axis_range_unqualified" in plan.contract.blocking_reasons
    assert "parameterized_adapter_unqualified" in plan.contract.blocking_reasons
    assert all(
        p.state == "NOT_RUN" and p.axis_check.reason == "unqualified_range" for p in plan.points
    )
    assert {c.logical_id: c.reason for c in plan.fixed_checks} == {
        "vbiasp": "unqualified_range",
        "vdd": "fixed_constraint_matched",
    }
    assert plan.reservation_state == "not_reserved" and plan.durable_admission == "not_created"
    assert plan.spec_evaluation == "not_evaluated"
    assert not (tmp_path / "admissions.sqlite3").exists()
    assert (tmp_path / "sweep.sqlite3").read_bytes() == journal
    assert not cast(MagicMock, svc._backend).mock_calls
    assert "MyDesignLib" not in plan.model_dump_json()


@pytest.mark.asyncio
async def test_numeric_fixture_plan_is_still_not_execution_authority(tmp_path: Path) -> None:
    svc = service(tmp_path, fixture_registry())
    plan = await svc.plan_design_sweep(await request(svc, True))
    assert plan.locally_admissible and all(p.locally_admissible for p in plan.points)
    assert not plan.execution_authorized
    assert "parameterized_adapter_unqualified" in plan.contract.blocking_reasons
    assert "analysis_unqualified" in plan.contract.blocking_reasons
    assert "measurement_unqualified" in plan.contract.blocking_reasons
    resumed = await service(tmp_path, fixture_registry()).plan_design_sweep(
        await request(svc, True)
    )
    assert resumed == plan
    assert not cast(MagicMock, svc._backend).mock_calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "linear,expected",
    [
        ({"start": "1000", "stop": "2000", "step": "500"}, ("1000", "1500", "2000")),
        ({"start": "2000", "stop": "1000", "step": "-500"}, ("2000", "1500", "1000")),
        ({"start": "1000", "stop": "1000", "step": "1"}, ("1000",)),
    ],
)
async def test_linear_and_explicit_plans_equal_under_small_decimal_context(
    tmp_path: Path,
    linear: dict[str, str],
    expected: tuple[str, ...],
) -> None:
    svc = service(tmp_path, fixture_registry())
    with localcontext() as context:
        context.prec = 2
        a = await svc.plan_design_sweep(await request(svc, True, values=None, linear=linear))
        b = await svc.plan_design_sweep(await request(svc, True, values=expected))
    assert a == b and a.canonical_values == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "linear",
    [
        {"start": "1000", "stop": "2000", "step": "0"},
        {"start": "1000", "stop": "2000", "step": "-1"},
        {"start": "1000", "stop": "2000", "step": "300"},
        {"start": "1000", "stop": "2000", "step": "1e-30"},
    ],
)
async def test_unbounded_or_inexact_linear_denied(tmp_path: Path, linear: dict[str, str]) -> None:
    svc = service(tmp_path, fixture_registry())
    with pytest.raises(InvalidInputError):
        await svc.plan_design_sweep(await request(svc, True, values=None, linear=linear))


@pytest.mark.asyncio
async def test_canonical_duplicates_and_contract_tampering_fail(tmp_path: Path) -> None:
    svc = service(tmp_path, fixture_registry())
    for changes in (
        {"values": ["1000", "1e3"]},
        {"expected_contract_sha256": "0" * 64},
        {"unit": "V"},
        {"fixed": {"resistance": {"unit": "ohm", "value": "1000"}}},
    ):
        with pytest.raises(InvalidInputError):
            await svc.plan_design_sweep(await request(svc, True, **changes))


@pytest.mark.asyncio
async def test_constraints_ranges_units_and_grid_are_checked(tmp_path: Path) -> None:
    svc = service(tmp_path)
    for value, unit, reason in (("0.9", "V", "fixed_value_mismatch"), ("1", "A", "wrong_unit")):
        plan = await svc.plan_design_sweep(
            await request(
                svc,
                fixed={
                    "vbiasp": {"value": "0.702", "unit": "V"},
                    "vdd": {"value": value, "unit": unit},
                },
            )
        )
        assert next(c for c in plan.fixed_checks if c.logical_id == "vdd").reason == reason
    for grid, value, reason in ((False, "0", "outside_reviewed_range"), (True, "1050", "off_grid")):
        numeric = service(tmp_path, fixture_registry(grid))
        plan = await numeric.plan_design_sweep(await request(numeric, True, values=[value]))
        assert not plan.locally_admissible and plan.points[0].axis_check.reason == reason


@pytest.mark.asyncio
async def test_stale_review_pdk_and_measurement_identity_change_hash(tmp_path: Path) -> None:
    svc = service(tmp_path, fixture_registry())
    old_request = await request(svc, True)
    payload = fixture_registry().model_dump(mode="json")
    payload["range_reviews"][0]["evidence_sha256"] = "0" * 64
    new = service(tmp_path, DesignMeasurementRegistry.model_validate_json(json.dumps(payload)))
    with pytest.raises(InvalidInputError, match="current registry"):
        await new.plan_design_sweep(old_request)
    ref = service(tmp_path)
    for changes in (
        {"measurement_ids": ("ac-spectrum",)},
        {"variable_id": "missing"},
        {"analysis_id": "missing"},
        {"measurement_ids": ("power",)},
    ):
        with pytest.raises(InvalidInputError):
            await ref.describe_design_sweep(selection().model_copy(update=changes))
    assert not cast(MagicMock, new._backend).mock_calls


@pytest.mark.asyncio
async def test_fixed_axis_cannot_be_swept_even_at_its_constraint(tmp_path: Path) -> None:
    svc = service(tmp_path)
    selected = selection().model_copy(update={"variable_id": "vdd"})
    described = await svc.describe_design_sweep(selected)
    assert "axis_not_mutable" in described.blocking_reasons
    query = DesignSweepRequest.model_validate_json(
        json.dumps(
            {
                **selected.model_dump(mode="json"),
                "expected_contract_sha256": described.contract_sha256,
                "unit": "V",
                "values": ["1"],
                "fixed": {
                    "vbiasn": {"value": "0.32", "unit": "V"},
                    "vbiasp": {"value": "0.702", "unit": "V"},
                },
            }
        )
    )
    assert not (await svc.plan_design_sweep(query)).locally_admissible


@pytest.mark.asyncio
async def test_mcp_closed_json_outputs_and_no_legacy_submission_bypass(tmp_path: Path) -> None:
    svc = service(tmp_path, fixture_registry())
    query = await request(svc, True)
    async with Client(create_server(svc)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert len(tools) == 53
        for name in ("cadence_describe_design_sweep", "cadence_plan_design_sweep"):
            assert tools[name].input_schema["additionalProperties"] is False
            assert tools[name].annotations and tools[name].annotations.read_only_hint
        result = await client.call_tool(
            "cadence_plan_design_sweep", {"request": query.model_dump(mode="json")}
        )
        assert not result.is_error and result.structured_content["execution_authorized"] is False
        assert result.structured_content["locally_admissible"] is True
        for field in (
            "path",
            "script",
            "netlist",
            "corner",
            "target",
            "execution_authorized",
            "experiment_key",
        ):
            bad = {**query.model_dump(mode="json"), field: "private"}
            assert (await client.call_tool("cadence_plan_design_sweep", {"request": bad})).is_error
            assert (
                await client.call_tool(
                    "cadence_plan_design_sweep",
                    {"request": query.model_dump(mode="json"), field: "private"},
                )
            ).is_error
        assert (
            await client.call_tool(
                "cadence_submit_sweep", {"submission": result.structured_content}
            )
        ).is_error
    assert not (tmp_path / "admissions.sqlite3").exists()
    assert not cast(MagicMock, svc._backend).mock_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("values", [[True], [1], ["NaN"], ["1;id"], [], ["1"] * 17])
async def test_bounded_strict_inputs(tmp_path: Path, values: list[Any]) -> None:
    svc = service(tmp_path)
    with pytest.raises(ValidationError):
        await request(svc, values=values)


def test_reference_contracts_and_schema_stay_unchanged() -> None:
    registry = reference_measurement_registry()
    assert all(v.range_status == "unqualified" for v in registry.variable_sets[0].variables)
    assert registry.variable_sets[0].variables[2].fixed_value == "1"
    for version in (1, 2, 3, 4):
        assert (
            Path(__file__).resolve().parents[2]
            / f"docs/schemas/design-registry-v{version}.schema.json"
        ).is_file()
