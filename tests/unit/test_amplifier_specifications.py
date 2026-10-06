"""Synthetic goals are never real project requirements or actual circuit PASS."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import Client
from pydantic import ValidationError
from test_amplifier_sweeps import Transport, setup, submission
from test_sweeps import finish

from cadence_mcp_bridge.amplifier_specifications import (
    AmplifierEvaluationQuery,
    AmplifierFactSettings,
    AmplifierSpecificationContract,
    AmplifierSpecificationRegistry,
    AmplifierSpecificationSupervisor,
    binding,
    conditions,
    evaluate_source,
    load_amplifier_specifications,
    provenance,
)
from cadence_mcp_bridge.amplifier_sweeps import DEFINITION_SHA, DESIGN, AmplifierQuery
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import NativeSettings
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.specifications import evaluate_fact
from cadence_mcp_bridge.sweeps import PointState
from cadence_mcp_bridge.variable_contracts import canonical_digest


async def source(tmp: Path, mode: str = "dc") -> tuple[Any, Any, Any]:
    t = Transport()
    svc = setup(tmp, t)
    first = await svc.submit(submission(mode))
    await finish(svc.engine, first.sweep_id)
    query = AmplifierQuery(design_id=DESIGN, sweep_id=first.sweep_id)
    return svc, query, await svc.result(query)


def goal(result: Any, **changes: Any) -> AmplifierSpecificationContract:
    m = result.measurements[0]
    p = provenance(m, result.engine.plan_hash)
    return AmplifierSpecificationContract.model_validate(
        {
            "spec_id": "synthetic-only-not-a-user-goal",
            "design_id": DESIGN,
            "measurement_id": m.measurement_id,
            "measurement_contract_sha256": canonical_digest(binding(m.measurement_id)),
            "definition_sha256": DEFINITION_SHA,
            "comparison": ">=",
            "target": "0.002",
            "unit": m.unit,
            "goal_id": "synthetic-fixture-only",
            "conditions": conditions(p),
            **changes,
        }
    )


def query(svc: Any, q: Any, result: Any) -> AmplifierEvaluationQuery:
    return AmplifierEvaluationQuery(
        **q.model_dump(),
        expected_sweep_result_sha256=canonical_digest(result),
        expected_specification_registry_sha256=canonical_digest(svc.registry),
    )


@pytest.mark.parametrize("mode", ["dc", "ac"])
async def test_absent_target_real_binding_retains_facts_and_conditions(
    tmp_path: Path, mode: str
) -> None:
    sweep, q, r = await source(tmp_path, mode)
    svc = AmplifierSpecificationSupervisor(sweep, AmplifierSpecificationRegistry())
    evaluation = await svc.result(query(svc, q, r))
    assert evaluation.source == r and evaluation.target_status == "not_registered"
    assert len(evaluation.provenance) == len(evaluation.evaluations) == 3
    assert all(e.status == "NOT_EVALUATED" and e.target is None for e in evaluation.evaluations)
    assert [p.settings.applied_bias_values_v[0] for p in evaluation.provenance] == [
        0.319,
        0.32,
        0.321,
    ]
    assert all(p.definition_sha256 == DEFINITION_SHA for p in evaluation.provenance)
    assert NativeSettings().applied_bias_values_v == (0.32, 0.702)
    assert len(evaluation.model_dump_json()) < 65536


@pytest.mark.parametrize(
    "comparison,target,upper,expected",
    [
        (">=", "0.002", None, "PASS"),
        (">", "0.002", None, "FAIL"),
        ("<=", "0.002", None, "PASS"),
        ("<", "0.002", None, "FAIL"),
        ("range", "0.001", "0.002", "PASS"),
        ("range", "0.0021", "0.003", "FAIL"),
    ],
)
async def test_reuses_exact_comparator_no_fitted_targets(
    tmp_path: Path,
    comparison: str,
    target: str,
    upper: str | None,
    expected: str,
) -> None:
    _, _, r = await source(tmp_path)
    c = goal(r, comparison=comparison, target=target, upper_target=upper)
    registry = AmplifierSpecificationRegistry(specifications=(c,))
    evaluated = evaluate_source(r, registry, c.measurement_id)
    assert evaluated.evaluations[0].status == expected
    assert all(e.status == "CONDITION_MISMATCH" for e in evaluated.evaluations[1:])
    assert registry.specifications[0] == c  # goals never changed to fit results


@pytest.mark.parametrize(
    "field,value",
    [
        ("corner", "FF"),
        ("temperature_c", "28"),
        ("vdd_v", "0.9"),
        ("revision_id", "other-revision"),
        ("operating_point_id", "other-point"),
        ("analysis_plan_hash", "f" * 64),
        ("effective_settings_sha256", "f" * 64),
        ("applied_bias_values_v", ["0.319", "0.703"]),
    ],
)
async def test_exact_conditions_do_not_widen_to_PVT(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    _, _, r = await source(tmp_path)
    data = goal(r).model_dump(mode="json")
    data["conditions"][field] = value
    c = AmplifierSpecificationContract.model_validate_json(json.dumps(data))
    e = evaluate_source(r, AmplifierSpecificationRegistry(specifications=(c,)), c.measurement_id)
    assert all(x.status == "CONDITION_MISMATCH" for x in e.evaluations)


@pytest.mark.parametrize(
    "change",
    [
        {"unit": "mW"},
        {"definition_sha256": "f" * 64},
        {"measurement_contract_sha256": "f" * 64},
        {"measurement_id": "analog-offset"},
        {"target": "nan"},
        {"target": "1e999999999"},
        {"target": 0.001},
        {"goal_id": None},
        {"design_id": "other"},
        {"contract_version": True},
    ],
)
async def test_operator_contract_rejects_ambiguous_or_stale_binding(
    tmp_path: Path,
    change: dict[str, Any],
) -> None:
    _, _, r = await source(tmp_path)
    with pytest.raises(ValidationError):
        goal(r, **change)


async def test_unqualified_and_no_target_do_not_yield_pass(tmp_path: Path) -> None:
    _, _, r = await source(tmp_path)
    c = goal(r)
    p = provenance(r.measurements[0], r.engine.plan_hash)
    for status in ("PARTIALLY_QUALIFIED", "UNQUALIFIED", "BLOCKED"):
        assert evaluate_fact(c, status, 0.002, p) == "UNQUALIFIED"
    assert evaluate_fact(c, "QUALIFIED", None, p) == "UNQUALIFIED"
    c = goal(r, target=None, goal_id=None)
    assert evaluate_fact(c, "QUALIFIED", 0.002, p) == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "state,expected",
    [
        ("FAILED", "SIMULATION_ERROR"),
        ("UNKNOWN", "SOURCE_UNAVAILABLE"),
        ("CANCELLED", "MISSING_MEASUREMENT"),
        ("NOT_RUN", "MISSING_MEASUREMENT"),
    ],
)
async def test_source_errors_are_distinct_from_design_fail(
    tmp_path: Path,
    state: str,
    expected: str,
) -> None:
    _, _, r = await source(tmp_path)
    c = goal(r)
    p = r.engine.points[0].model_copy(
        update={
            "state": PointState(state),
            "phase": "not_run",
            "measurement_value": False if state == "FAILED" else None,
            "quality": "invalid" if state == "FAILED" else "not_available",
            "error": "synthetic failure" if state == "FAILED" else None,
        }
    )
    modified = r.model_copy(
        update={
            "measurements": (),
            "engine": r.engine.model_copy(update={"points": (p,), "state": "FAILED"}),
        }
    )
    modified = type(r).model_validate_json(modified.model_dump_json())
    e = evaluate_source(
        modified, AmplifierSpecificationRegistry(specifications=(c,)), c.measurement_id
    )
    assert e.evaluations[0].status == expected
    assert e.evaluations[0].observed_value is None


async def test_catalog_and_source_hash_staleness_before_evaluation(tmp_path: Path) -> None:
    s, q, r = await source(tmp_path)
    svc = AmplifierSpecificationSupervisor(s, AmplifierSpecificationRegistry())
    selected = query(svc, q, r)
    for field in ("expected_sweep_result_sha256", "expected_specification_registry_sha256"):
        with pytest.raises(InvalidInputError):
            await svc.result(selected.model_copy(update={field: "f" * 64}))
    with pytest.raises(RemoteFailureError):
        evaluate_source(
            r.model_copy(update={"measurements": ()}), svc.registry, "dc-supply-power-grid-v2"
        )


def test_operator_loader_bounded_regular_duplicate_and_finite(tmp_path: Path) -> None:
    path = tmp_path / "targets.json"
    path.write_text('{"schema_version":1,"specifications":[]}', encoding="utf-8")
    assert load_amplifier_specifications(path).specifications == ()
    for text in (
        '{"schema_version":1,"schema_version":1,"specifications":[]}',
        '{"schema_version":true,"specifications":[]}',
        '{"schema_version":1,"specifications":[],"x":NaN}',
        " " * 65537,
    ):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(InvalidInputError):
            load_amplifier_specifications(path)
    with pytest.raises(InvalidInputError):
        load_amplifier_specifications(tmp_path)


async def test_goal_count_duplicates_and_fact_grid_bounds(tmp_path: Path) -> None:
    _, _, r = await source(tmp_path)
    c = goal(r)
    with pytest.raises(ValidationError):
        AmplifierSpecificationRegistry(specifications=(c, c))
    with pytest.raises(ValidationError):
        AmplifierSpecificationRegistry(specifications=(c,) * 17)
    data = provenance(r.measurements[0], r.engine.plan_hash).settings.model_dump(mode="json")
    data["applied_bias_values_v"][0] = 0.3195
    with pytest.raises(ValidationError):
        AmplifierFactSettings.model_validate(data)


async def test_MCP_no_caller_targets_values_paths_and_read_only(tmp_path: Path) -> None:
    sweep, q, r = await source(tmp_path)
    service = CadenceService(
        cast(CadenceBackend, sweep.transport),
        designs=sweep.registry,
        pdks=sweep.pdks,
        analysis_journal=tmp_path / "analyses.db",
        sweep_journal=tmp_path / "shared.db",
    )
    async with Client(create_server(service)) as client:
        catalog = await client.call_tool(
            "cadence_amplifier_specification_catalog", {"design_id": DESIGN}
        )
        assert not catalog.is_error and catalog.structured_content["specifications"] == []
        svc = service._amplifier_specifications
        selected = query(svc, q, r).model_dump(mode="json")
        evaluated = await client.call_tool(
            "cadence_evaluate_amplifier_specifications", {"request": selected}
        )
        assert not evaluated.is_error
        assert all(
            e["status"] == "NOT_EVALUATED" for e in evaluated.structured_content["evaluations"]
        )
        for change in ({"target": "0.001"}, {"value": 100}, {"path": "/tmp/x"}, {"script": "x"}):
            response = await client.call_tool(
                "cadence_evaluate_amplifier_specifications",
                {
                    "request": selected | change,
                },
            )
            assert response.is_error
        for t in (await client.list_tools()).tools:
            if t.name in (
                "cadence_amplifier_specification_catalog",
                "cadence_evaluate_amplifier_specifications",
            ):
                assert t.annotations.read_only_hint and not t.annotations.destructive_hint
                assert t.input_schema["additionalProperties"] is False


async def test_restart_and_catalog_input_guards(tmp_path: Path) -> None:
    sweep, q, r = await source(tmp_path)
    registry = AmplifierSpecificationRegistry()
    original = AmplifierSpecificationSupervisor(sweep, registry)
    restarted = AmplifierSpecificationSupervisor(setup(tmp_path, sweep.transport), registry)
    assert await original.result(query(original, q, r)) == await restarted.result(
        query(restarted, q, r)
    )
    service = CadenceService(
        cast(CadenceBackend, sweep.transport),
        designs=sweep.registry,
        pdks=sweep.pdks,
        sweep_journal=tmp_path / "shared.db",
    )
    async with Client(create_server(service)) as client:
        for args in (
            {},
            {"design_id": DESIGN, "path": "/tmp/x"},
            {"design_id": "unknown"},
            {"design_id": 1},
        ):
            result = await client.call_tool("cadence_amplifier_specification_catalog", args)
            assert result.is_error


async def test_maximum_targets_bounded_and_mode_substitution_denied(tmp_path: Path) -> None:
    _, _, r = await source(tmp_path)
    goals = tuple(goal(r, spec_id=f"synthetic-{i}") for i in range(16))
    registry = AmplifierSpecificationRegistry(specifications=goals)
    result = evaluate_source(r, registry, "dc-supply-power-grid-v2")
    assert len(result.evaluations) == 48
    assert len(result.model_dump_json().encode("utf-8")) <= 65536
    with pytest.raises(RemoteFailureError):
        evaluate_source(r, registry, "gain-10hz-grid-v1")
    with pytest.raises(InvalidInputError):
        evaluate_source(
            r.model_copy(update={"definition_sha256": "f" * 64}),
            registry,
            "dc-supply-power-grid-v2",
        )


def test_operator_loader_rejects_symbolic_link(tmp_path: Path) -> None:
    original = tmp_path / "original.json"
    original.write_text('{"schema_version":1,"specifications":[]}', encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(original)
    except OSError:
        pytest.skip("OS does not permit symlink creation")
    with pytest.raises(InvalidInputError):
        load_amplifier_specifications(link)
