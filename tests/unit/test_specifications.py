"""Fictional goals exercise comparisons; no target is assigned to the reference design."""

import asyncio
import json
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from mcp import Client
from pydantic import ValidationError
from test_analog_measurements import SpectrumBackend, admitted
from test_analyses import DESIGN, NativeBackend

from cadence_mcp_bridge import __main__ as cli
from cadence_mcp_bridge.analog_measurements import definition
from cadence_mcp_bridge.analog_registry import reference_analog_registry
from cadence_mcp_bridge.analyses import AnalysisSelection
from cadence_mcp_bridge.designs import load_design_registry
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import NativeSettings
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.specification_registry import (
    DesignSpecificationRegistry,
    reference_specification_registry,
)
from cadence_mcp_bridge.specifications import (
    SpecificationContract,
    SpecificationQuery,
    evaluate,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest

ROOT = Path(__file__).resolve().parents[2]


async def configured(
    path: Path,
    metric: str = "gain",
    target: str | None = "40",
    comparison: str = ">=",
    upper: str | None = None,
    conditions: dict[str, Any] | None = None,
) -> tuple[CadenceService, SpectrumBackend, SpecificationQuery]:
    backend = SpectrumBackend([40.0] + [36.0] * 70)
    base = reference_specification_registry()
    probe = CadenceService(cast(CadenceBackend, backend), designs=base, analysis_journal=path)
    plan = await probe.plan_analysis(AnalysisSelection(design_id=DESIGN, analysis_id="native-ac"))
    analog = next(a for a in base.analog_contracts if a.metric == metric)
    c = SpecificationContract.model_validate_json(
        json.dumps(
            {
                "spec_id": "test-only-goal",
                "design_id": DESIGN,
                "measurement_id": analog.measurement_id,
                "measurement_contract_sha256": canonical_digest(analog),
                "definition_sha256": analog.definition_sha256,
                "unit": definition(cast(Any, metric)).unit,
                "comparison": comparison,
                "target": target,
                "upper_target": upper,
                "goal_id": "fictional-unit-test-goal" if target is not None else None,
                "conditions": {
                    "analysis_id": "native-ac",
                    "analysis_plan_hash": plan.plan_hash,
                    "revision_id": "wp14-native-ade-v1",
                    "operating_point_id": "candidate-320-702mv-v1",
                    "corner": "NN",
                    "temperature_c": "27",
                    "vdd_v": "1",
                    "applied_bias_values_v": ["0.32", "0.702"],
                    "effective_settings_sha256": canonical_digest(NativeSettings()),
                    **(conditions or {}),
                },
            }
        )
    )
    registry = DesignSpecificationRegistry.model_validate(
        {**base.model_dump(), "specification_contracts": (c,)}
    )
    svc = CadenceService(cast(CadenceBackend, backend), designs=registry, analysis_journal=path)
    return (
        svc,
        backend,
        SpecificationQuery(
            design_id=DESIGN,
            spec_id=c.spec_id,
            expected_contract_sha256=canonical_digest(c),
            operation_id=str(uuid4()),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "comparison,target,upper,expected",
    [
        (">=", "40", None, "PASS"),
        (">", "40", None, "FAIL"),
        ("<=", "40", None, "PASS"),
        ("<", "40", None, "FAIL"),
        (">=", "40.0000000000000001", None, "FAIL"),
        (">", "39.9999999999999999", None, "PASS"),
        ("<=", "39", None, "FAIL"),
        ("<", "41", None, "PASS"),
        ("range", "40", "40", "PASS"),
        ("range", "39", "40", "PASS"),
        ("range", "40", "41", "PASS"),
        ("range", "41", "42", "FAIL"),
    ],
)
async def test_fictional_comparators_and_no_rounding(
    tmp_path: Path, comparison: str, target: str, upper: str | None, expected: str
) -> None:
    svc, backend, query = await configured(
        tmp_path / "db", comparison=comparison, target=target, upper=upper
    )
    assert query.operation_id is not None
    await admitted(svc, tmp_path / "db", query.operation_id)
    before = (tmp_path / "db").read_bytes()
    result = await svc.evaluate_specification(query)
    assert result.status == expected and result.measurement is not None
    assert result.measurement.value == 40 and result.measurement.provenance is not None
    assert result.measurement_result_sha256 == canonical_digest(result.measurement)
    assert result.measurement.spec_evaluation == "not_evaluated"
    assert result.scope == "one_operation_exact_registered_conditions"
    restarted = CadenceService(
        cast(CadenceBackend, backend), designs=svc._designs, analysis_journal=tmp_path / "db"
    )
    repeats = await asyncio.gather(*(restarted.evaluate_specification(query) for _ in range(3)))
    assert all(r == result for r in repeats)
    assert before == (tmp_path / "db").read_bytes() and backend.submissions == []
    assert len(result.model_dump_json()) < 12000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("corner", "FF"),
        ("temperature_c", "28"),
        ("vdd_v", "1.1"),
        ("applied_bias_values_v", ["0.3", "0.65"]),
        ("revision_id", "other-revision"),
        ("operating_point_id", "other-op"),
        ("analysis_plan_hash", "0" * 64),
        ("effective_settings_sha256", "0" * 64),
    ],
)
async def test_conditions_never_expand_to_other_pvt(tmp_path: Path, field: str, value: Any) -> None:
    svc, _, query = await configured(tmp_path / "db", conditions={field: value})
    assert query.operation_id is not None
    await admitted(svc, tmp_path / "db", query.operation_id)
    result = await svc.evaluate_specification(query)
    assert result.status == "CONDITION_MISMATCH" and result.measurement is not None
    assert result.measurement.provenance is not None
    assert result.measurement.provenance.settings.corner == "NN"


@pytest.mark.asyncio
async def test_precedence_missing_target_missing_measurement_partial_and_unqualified(
    tmp_path: Path,
) -> None:
    for metric in ("gain", "bandwidth", "phase-margin", "power", "offset", "slew-rate"):
        path = tmp_path / metric
        svc, backend, query = await configured(path, metric=metric, target=None)
        assert (await svc.evaluate_specification(query)).status == "NOT_EVALUATED"
        assert backend.results == [] and not path.exists()
        svc, backend, query = await configured(path, metric=metric)
        no_op = query.model_copy(update={"operation_id": None})
        result = await svc.evaluate_specification(no_op)
        assert result.status == (
            "MISSING_MEASUREMENT" if metric in ("gain", "bandwidth") else "UNQUALIFIED"
        )
        if metric == "bandwidth":
            assert query.operation_id is not None
            await admitted(svc, path, query.operation_id)
            result = await svc.evaluate_specification(query)
            assert result.status == "UNQUALIFIED" and result.measurement is not None
            assert result.measurement.status == "PARTIALLY_QUALIFIED"


@pytest.mark.asyncio
async def test_unknown_stale_unadmitted_failed_source_are_errors(tmp_path: Path) -> None:
    svc, backend, query = await configured(tmp_path / "db")
    for update in (
        {"spec_id": "unknown"},
        {"design_id": "unknown"},
        {"expected_contract_sha256": "0" * 64},
        {},
    ):
        with pytest.raises(InvalidInputError):
            await svc.evaluate_specification(query.model_copy(update=update))
    assert backend.results == []
    assert query.operation_id is not None
    await admitted(svc, tmp_path / "db", query.operation_id)
    invalid_backend = NativeBackend()
    invalid_backend.wrong_identity = True
    svc = CadenceService(
        cast(CadenceBackend, invalid_backend),
        designs=svc._designs,
        analysis_journal=tmp_path / "db",
    )
    with pytest.raises(RemoteFailureError):
        await svc.evaluate_specification(query)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("target", 40),
        ("target", "NaN"),
        ("target", "1e9999"),
        ("target", "1;rm"),
        ("target", True),
        ("upper_target", "2"),
        ("goal_id", None),
        ("contract_version", True),
        ("unit", "mW"),
        ("comparison", "eval"),
        ("measurement_id", "unknown"),
        ("design_id", "unknown"),
        ("measurement_contract_sha256", "0" * 64),
        ("definition_sha256", "0" * 64),
        ("formula", "x"),
        ("path", "../secret"),
    ],
)
async def test_operator_registry_rejects_coercion_redirect_and_extra_fields(
    tmp_path: Path, field: str, value: Any
) -> None:
    svc, _, _ = await configured(tmp_path / "db")
    payload = svc._designs.model_dump(mode="json")
    payload["specification_contracts"][0][field] = value
    with pytest.raises((ValidationError, InvalidInputError)):
        DesignSpecificationRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.asyncio
async def test_range_and_identity_and_limit_rejection(tmp_path: Path) -> None:
    for target, upper in (("41", "40"), ("40", None)):
        with pytest.raises(ValidationError):
            await configured(tmp_path / "db", target=target, comparison="range", upper=upper)
    svc, _, _ = await configured(tmp_path / "db")
    payload = svc._designs.model_dump(mode="json")
    original = payload["specification_contracts"][0]
    for change in ("duplicate", "wrong-analysis", "unknown-analysis", "too-many"):
        current = json.loads(json.dumps(payload))
        if change == "duplicate":
            current["specification_contracts"].append(dict(original))
        elif change == "too-many":
            current["specification_contracts"] = [
                {**original, "spec_id": "test-" + str(i)} for i in range(33)
            ]
        else:
            current["specification_contracts"][0]["conditions"]["analysis_id"] = (
                "native-dc" if change == "wrong-analysis" else "unknown"
            )
        with pytest.raises(ValidationError):
            DesignSpecificationRegistry.model_validate_json(json.dumps(current))


@pytest.mark.asyncio
async def test_source_substitution_and_partial_never_pass(tmp_path: Path) -> None:
    svc, _, query = await configured(tmp_path / "db")
    assert query.operation_id is not None
    await admitted(svc, tmp_path / "db", query.operation_id)
    result = await svc.evaluate_specification(query)
    assert result.measurement is not None
    c = result.specification.contract
    for update in (
        {"design_id": "other"},
        {"measurement_id": "other"},
        {"contract_sha256": "0" * 64},
        {"definition": definition("power")},
    ):
        with pytest.raises(ValueError):
            evaluate(c, result.measurement.model_copy(update=update))
    assert (
        evaluate(c, result.measurement.model_copy(update={"status": "PARTIALLY_QUALIFIED"}))
        == "UNQUALIFIED"
    )


@pytest.mark.asyncio
async def test_v7_schema_registration_reference_no_goal_and_sweep_projection(
    tmp_path: Path,
    capsys: Any,
) -> None:
    registry = reference_specification_registry()
    assert registry.specification_contracts == ()
    assert registry.sweep_identity_digest() == reference_analog_registry().sweep_identity_digest()
    path = tmp_path / "registry.json"
    path.write_text(registry.model_dump_json(), encoding="utf-8")
    assert load_design_registry(path)[0] == registry
    for version in range(1, 8):
        assert cli.main(["design", "schema", "--schema-version", str(version)]) == 0
        assert json.loads(capsys.readouterr().out) == json.loads(
            (ROOT / f"docs/schemas/design-registry-v{version}.schema.json").read_bytes()
        )
    svc, _, _ = await configured(tmp_path / "db")
    assert svc._designs.sweep_identity_digest() == registry.sweep_identity_digest()
    for reg in (registry, reference_analog_registry()):
        empty = CadenceService(cast(CadenceBackend, NativeBackend()), designs=reg)
        listing = await empty.list_specifications(DESIGN)
        assert listing.specifications == () and listing.target_status == "not_selected"
        assert listing.spec_evaluation == "not_evaluated"


@pytest.mark.asyncio
async def test_mcp_closed_readonly_contract_and_concurrent_calls(tmp_path: Path) -> None:
    svc, backend, query = await configured(tmp_path / "db")
    assert query.operation_id is not None
    await admitted(svc, tmp_path / "db", query.operation_id)
    async with Client(create_server(svc)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert len(tools) == 69
        for name in (
            "cadence_list_specifications",
            "cadence_describe_specification",
            "cadence_evaluate_specification",
        ):
            assert tools[name].input_schema["additionalProperties"] is False
            assert tools[name].annotations is not None and tools[name].annotations.read_only_hint
        for bad in (
            {"design_id": DESIGN, "target": 40},
            {"design_id": 1},
            {"design_id": "../secret"},
            {},
        ):
            assert (await client.call_tool("cadence_list_specifications", bad)).is_error
        listing = await client.call_tool("cadence_list_specifications", {"design_id": DESIGN})
        assert not listing.is_error and len(listing.structured_content["specifications"]) == 1
        desc = await client.call_tool(
            "cadence_describe_specification",
            {
                "request": {
                    "design_id": DESIGN,
                    "spec_id": query.spec_id,
                }
            },
        )
        assert not desc.is_error
        for extra in ("target", "measurement", "path", "script", "formula", "unit"):
            bad = await client.call_tool(
                "cadence_evaluate_specification",
                {
                    "request": {**query.model_dump(), extra: "private"},
                },
            )
            assert bad.is_error
        for op in ("../secret", "00000000-0000-1000-8000-000000000000", True):
            bad = await client.call_tool(
                "cadence_evaluate_specification",
                {
                    "request": {**query.model_dump(), "operation_id": op},
                },
            )
            assert bad.is_error
        results = await asyncio.gather(
            *(
                client.call_tool(
                    "cadence_evaluate_specification",
                    {
                        "request": query.model_dump(),
                    },
                )
                for _ in range(3)
            )
        )
        assert all(not r.is_error and r.structured_content["status"] == "PASS" for r in results)
    assert backend.submissions == []
