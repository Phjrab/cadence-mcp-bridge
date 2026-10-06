"""Synthetic goals only; exact production power admission and reader gates reused."""

import asyncio
import json
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from mcp import Client
from pydantic import ValidationError
from test_analyses import DESIGN, selection
from test_power_measurements import Backend, admit
from test_specifications import configured as legacy_configured

import cadence_mcp_bridge.power_service as power
from cadence_mcp_bridge import __main__ as cli
from cadence_mcp_bridge.designs import load_design_registry
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.measurement_bindings import (
    DesignPowerSpecificationRegistry,
    PowerSpecificationContract,
    SpecificationEvaluationV2,
    power_binding,
    reference_power_specification_registry,
)
from cadence_mcp_bridge.native_diagnostics import NativeSettings
from cadence_mcp_bridge.power_measurements import (
    REFERENCE_OPERATION,
    PowerDefinition,
    PowerSelection,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.specifications import SpecificationQuery
from cadence_mcp_bridge.variable_contracts import canonical_digest


async def configured(
    path: Path,
    target: str | None = "0.002",
    comparison: str = "<=",
    upper: str | None = None,
    conditions: dict[str, Any] | None = None,
) -> tuple[CadenceService, Backend, SpecificationQuery]:
    b = Backend()
    base = reference_power_specification_registry()
    svc = CadenceService(
        cast(CadenceBackend, b),
        designs=base,
        analysis_journal=path,
        sweep_journal=path.with_suffix(".sweep"),
    )
    plan = await svc.plan_analysis(selection("dc"))
    binding = await svc.describe_power_measurement(
        PowerSelection(design_id=DESIGN, measurement_id="analog-power")
    )
    c = PowerSpecificationContract.model_validate_json(
        json.dumps(
            {
                "contract_version": 2,
                "spec_id": "test-only-power",
                "design_id": DESIGN,
                "measurement_id": "analog-power",
                "measurement_contract_sha256": binding.contract_sha256,
                "definition_sha256": canonical_digest(PowerDefinition()),
                "unit": "W",
                "comparison": comparison,
                "target": target,
                "upper_target": upper,
                "goal_id": "fictional-test-goal" if target is not None else None,
                "conditions": {
                    "analysis_id": "native-dc",
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
    registry = DesignPowerSpecificationRegistry.model_validate(
        {
            **base.model_dump(),
            "power_specification_contracts": (c,),
        }
    )
    svc = CadenceService(
        cast(CadenceBackend, b),
        designs=registry,
        analysis_journal=path,
        sweep_journal=path.with_suffix(".sweep"),
    )
    return (
        svc,
        b,
        SpecificationQuery(
            design_id=DESIGN,
            spec_id=c.spec_id,
            expected_contract_sha256=canonical_digest(c),
            operation_id=REFERENCE_OPERATION,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "comparison,target,upper,expected",
    [
        ("<=", "0.002", None, "PASS"),
        ("<", "0.002", None, "FAIL"),
        (">=", "0.002", None, "PASS"),
        (">", "0.002", None, "FAIL"),
        ("<=", "0.0019999999999999999", None, "FAIL"),
        ("range", "0.002", "0.002", "PASS"),
        ("range", "0.001", "0.0019", "FAIL"),
    ],
)
async def test_admitted_signed_power_goals_shared_comparator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    comparison: str,
    target: str,
    upper: str | None,
    expected: str,
) -> None:
    path = tmp_path / "db"
    svc, b, q = await configured(path, target, comparison, upper)
    monkeypatch.setattr(power, "REFERENCE_EXTRACTION", canonical_digest(b.artifact))
    await admit(svc, path)
    before = path.read_bytes()
    values = await asyncio.gather(*(svc.evaluate_specification_v2(q) for _ in range(3)))
    assert all(v == values[0] for v in values)
    r = values[0]
    assert r.status == expected and r.contract_version == 2 and r.measurement
    assert r.measurement.value == 0.002 and r.measurement.definition == PowerDefinition()
    assert r.measurement_result_sha256 == canonical_digest(r.measurement)
    assert SpecificationEvaluationV2.model_validate_json(r.model_dump_json()) == r
    again, _, _ = await configured(path, target, comparison, upper)
    assert await again.evaluate_specification_v2(q) == r
    assert before == path.read_bytes() and not b.submissions
    catalog = await svc.measurement_catalog(DESIGN)
    assert len(catalog.analog) == 6 and len(catalog.signed_dc_power) == 1
    assert not next(a for a in catalog.analog if a.definition.metric == "power").read_eligible
    assert power_binding(svc._designs, DESIGN, "analog-power")[0] == (
        catalog.signed_dc_power[0].contract_sha256
    )
    assert len(catalog.model_dump_json()) < 20000 and "/home/" not in catalog.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "conditions",
    [
        {"corner": "FF"},
        {"temperature_c": "28"},
        {"vdd_v": "0.9"},
        {"analysis_plan_hash": "0" * 64},
        {"revision_id": "other-revision"},
        {"operating_point_id": "other-point"},
        {"applied_bias_values_v": ["0.3", "0.65"]},
        {"effective_settings_sha256": "a" * 64},
    ],
)
async def test_every_condition_mismatch_not_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    conditions: dict[str, Any],
) -> None:
    svc, b, q = await configured(tmp_path / "db", conditions=conditions)
    monkeypatch.setattr(power, "REFERENCE_EXTRACTION", canonical_digest(b.artifact))
    await admit(svc, tmp_path / "db")
    assert (await svc.evaluate_specification_v2(q)).status == "CONDITION_MISMATCH"


@pytest.mark.asyncio
async def test_targetless_missing_unknown_and_stale_do_not_read(tmp_path: Path) -> None:
    svc, b, q = await configured(tmp_path / "db", target=None)
    assert (await svc.evaluate_specification_v2(q)).status == "NOT_EVALUATED"
    assert (await svc.runtime_info_v2()).designs.schema_version == 8
    with pytest.raises(InvalidInputError, match="runtime_info_v2"):
        await svc.runtime_info()
    for changed in (
        {"spec_id": "unknown"},
        {"design_id": "unknown"},
        {"expected_contract_sha256": "0" * 64},
    ):
        with pytest.raises(InvalidInputError):
            await svc.evaluate_specification_v2(q.model_copy(update=changed))
    assert not b.power_reads and not b.results and not b.submissions
    svc, b, q = await configured(tmp_path / "other")
    assert (
        await svc.evaluate_specification_v2(q.model_copy(update={"operation_id": None}))
    ).status == ("MISSING_MEASUREMENT")
    with pytest.raises(InvalidInputError):
        await svc.evaluate_specification_v2(q)
    with pytest.raises(InvalidInputError):
        await svc.evaluate_specification_v2(q.model_copy(update={"operation_id": str(uuid4())}))
    assert not b.power_reads


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["receipt", "native-psf", "unqualified"])
async def test_failed_extraction_or_unqualified_never_spec_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    svc, b, q = await configured(tmp_path / "db")
    monkeypatch.setattr(power, "REFERENCE_EXTRACTION", canonical_digest(b.artifact))
    await admit(svc, tmp_path / "db")
    if case == "native-psf":
        b.native_changes["psf_sha256"] = "a" * 64
    else:
        d = b.artifact.model_dump()
        if case == "receipt":
            d["sources"][0]["current_a"] *= 2
        else:
            d.update(status="UNQUALIFIED", reason="signed_branch_current_unavailable")
            d["sources"][0]["current_a"] = None
        b.artifact = type(b.artifact).model_validate(d)
        if case == "unqualified":
            monkeypatch.setattr(power, "REFERENCE_EXTRACTION", canonical_digest(b.artifact))
    if case == "unqualified":
        assert (await svc.evaluate_specification_v2(q)).status == "UNQUALIFIED"
    else:
        with pytest.raises(RemoteFailureError):
            await svc.evaluate_specification_v2(q)


@pytest.mark.asyncio
async def test_legacy_v2_dispatch_exact_fact_and_targetless_reference(tmp_path: Path) -> None:
    svc, _, q = await legacy_configured(tmp_path / "db", target=None)
    old = await svc.evaluate_specification(q)
    new = await svc.evaluate_specification_v2(q)
    assert new.model_dump(exclude={"contract_version"}) == old.model_dump(
        exclude={"contract_version"}
    )
    assert not reference_power_specification_registry().power_specification_contracts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("measurement_contract_sha256", "0" * 64),
        ("definition_sha256", "a" * 64),
        ("measurement_id", "analog-gain"),
        ("unit", "mW"),
        ("contract_version", 1),
        ("contract_version", True),
    ],
)
async def test_registry_rejects_substituted_goals(tmp_path: Path, field: str, value: Any) -> None:
    svc, _, _ = await configured(tmp_path / "db")
    d = svc._designs.model_dump(mode="json")
    d["power_specification_contracts"][0][field] = value
    with pytest.raises(ValidationError):
        DesignPowerSpecificationRegistry.model_validate_json(json.dumps(d))


@pytest.mark.asyncio
async def test_registry_execution_projection_loader_and_cli(tmp_path: Path, capsys: Any) -> None:
    svc, _, _ = await configured(tmp_path / "db")
    r = svc._designs
    assert (
        r.sweep_identity_digest()
        == reference_power_specification_registry().sweep_identity_digest()
    )
    p = tmp_path / "registry.json"
    p.write_text(r.model_dump_json(), encoding="utf-8")
    loaded, _ = load_design_registry(p)
    assert loaded == r
    assert cli.main(["design", "schema", "--schema-version", "8"]) == 0
    assert (
        json.loads(capsys.readouterr().out) == DesignPowerSpecificationRegistry.model_json_schema()
    )
    d = r.model_dump(mode="json")
    d["power_specification_contracts"][0]["conditions"]["analysis_id"] = "native-ac"
    with pytest.raises(ValidationError):
        DesignPowerSpecificationRegistry.model_validate_json(json.dumps(d))
    d = r.model_dump(mode="json")
    d["power_specification_contracts"] *= 2
    with pytest.raises(ValidationError):
        DesignPowerSpecificationRegistry.model_validate_json(json.dumps(d))


@pytest.mark.asyncio
async def test_mcp_catalog_evaluation_closed_schemas(tmp_path: Path) -> None:
    svc, b, q = await configured(tmp_path / "db", target=None)
    async with Client(create_server(svc)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        for n in (
            "cadence_measurement_catalog",
            "cadence_evaluate_specification_v2",
            "cadence_runtime_info_v2",
        ):
            t = tools[n]
            assert t.input_schema["additionalProperties"] is False and t.output_schema
            assert (
                t.annotations
                and t.annotations.read_only_hint
                and not t.annotations.destructive_hint
            )
        r = await client.call_tool("cadence_measurement_catalog", {"design_id": DESIGN})
        assert not r.is_error and r.structured_content["signed_dc_power"][0]["read_eligible"]
        r = await client.call_tool("cadence_evaluate_specification_v2", {"request": q.model_dump()})
        assert not r.is_error and r.structured_content["status"] == "NOT_EVALUATED"
        for fields in ({"path": "../private"}, {"script": "pv(...)"}, {"target": "1"}):
            assert (
                await client.call_tool(
                    "cadence_evaluate_specification_v2", {"request": {**q.model_dump(), **fields}}
                )
            ).is_error
        assert (
            await client.call_tool(
                "cadence_measurement_catalog", {"design_id": DESIGN, "path": "/private"}
            )
        ).is_error
        assert (await client.call_tool("cadence_runtime_info_v2", {"path": "/private"})).is_error
    assert not b.power_reads and not b.submissions
