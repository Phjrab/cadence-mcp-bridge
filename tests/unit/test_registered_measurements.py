"""Registered readers fail closed before transport and preserve native provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from mcp import Client
from pydantic import ValidationError
from test_analyses import NativeBackend
from test_native_diagnostics import native_payload

from cadence_mcp_bridge import __main__ as cli
from cadence_mcp_bridge.analyses import AnalysisSelection
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.designs import (
    DesignMeasurementRegistry,
    RegistryBase,
    load_design_registry,
    reference_analysis_registry,
    reference_contract_registry,
    reference_measurement_registry,
    reference_registry,
    register_designs,
)
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import NativeDiagnosticResult
from cadence_mcp_bridge.pdk_adapters import PdkRegistry
from cadence_mcp_bridge.registered_measurements import MeasurementQuery, MeasurementSelection
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.variable_contracts import canonical_digest

ROOT = Path(__file__).resolve().parents[2]
DESIGN = reference_registry().designs[0].design_id
MODES = (("dc", "dc-scalars"), ("ac", "ac-spectrum"), ("tran", "tran-summary"))


def service(
    backend: NativeBackend,
    journal: Path,
    registry: RegistryBase | None = None,
    pdks: PdkRegistry | None = None,
) -> CadenceService:
    return CadenceService(
        cast(CadenceBackend, backend), designs=registry, analysis_journal=journal, pdks=pdks
    )


async def query(svc: CadenceService, measurement: str, operation: str) -> MeasurementQuery:
    description = await svc.describe_measurement(
        MeasurementSelection(design_id=DESIGN, measurement_id=measurement)
    )
    return MeasurementQuery(
        design_id=DESIGN,
        measurement_id=measurement,
        operation_id=operation,
        expected_contract_sha256=description.contract_sha256,
    )


async def admit(svc: CadenceService, path: Path, mode: str, operation: str) -> None:
    plan = await svc.plan_analysis(
        AnalysisSelection(design_id=DESIGN, analysis_id="native-" + mode)
    )
    AnalysisStore(path).admit(operation, DESIGN, "native-" + mode, plan.plan_hash)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,measurement", MODES)
async def test_read_reuses_native_evidence_without_submission_or_ledger_change(
    tmp_path: Path,
    mode: str,
    measurement: str,
) -> None:
    backend = NativeBackend()
    path = tmp_path / "admissions.sqlite3"
    svc = service(backend, path)
    operation = str(uuid4())
    await admit(svc, path, mode, operation)
    before = path.read_bytes()
    request = await query(svc, measurement, operation)
    first = await svc.measurement_result(request)
    resumed = await service(backend, path).measurement_result(request)
    payload = native_payload(mode)
    payload["job_id"] = operation
    native = NativeDiagnosticResult.model_validate(payload)
    assert first == resumed
    assert first.scalars == native.scalars and first.spectrum == native.spectrum
    assert first.transient == native.transient
    assert first.provenance.native_result_sha256 == canonical_digest(native)
    assert first.provenance.settings == native.settings
    assert first.provenance.measurement_frame_sha256 == native.measurement_frame_sha256
    assert first.spec_evaluation == "not_evaluated" and first.quality == "valid"
    assert first.provenance.warnings == native.warnings
    assert path.read_bytes() == before and backend.submissions == [] and backend.reads == []
    assert backend.results == [(UUID(operation), mode)] * 2
    assert len(first.model_dump_json()) < 32_768
    assert "MyDesignLib" not in first.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,measurement", MODES)
async def test_unadmitted_completed_uuid_cannot_bypass_registered_analysis(
    tmp_path: Path,
    mode: str,
    measurement: str,
) -> None:
    backend = NativeBackend()
    path = tmp_path / "missing.sqlite3"
    svc = service(backend, path)
    request = await query(svc, measurement, str(uuid4()))
    with pytest.raises(InvalidInputError, match="not admitted"):
        await svc.measurement_result(request)
    assert not path.exists() and not backend.results and not backend.submissions


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["stale-contract", "wrong-analysis-admission", "missing-pdk"])
async def test_identity_and_pdk_denials_precede_transport(tmp_path: Path, denial: str) -> None:
    backend = NativeBackend()
    path = tmp_path / "admission.sqlite3"
    svc = service(backend, path)
    operation = str(uuid4())
    await admit(svc, path, "ac" if denial == "wrong-analysis-admission" else "dc", operation)
    request = await query(svc, "dc-scalars", operation)
    if denial == "stale-contract":
        request = request.model_copy(update={"expected_contract_sha256": "0" * 64})
    elif denial == "missing-pdk":
        svc = service(backend, path, pdks=PdkRegistry(schema_version=2, adapters=()))
        desc = await svc.describe_measurement(request)
        assert desc.read_eligible is False and desc.blocking_reason == "analysis_unqualified"
    before = path.read_bytes()
    with pytest.raises(InvalidInputError):
        await svc.measurement_result(request)
    assert not backend.results and not backend.submissions and path.read_bytes() == before


@pytest.mark.asyncio
async def test_wrong_remote_identity_is_rejected(tmp_path: Path) -> None:
    backend = NativeBackend()
    path = tmp_path / "admission.sqlite3"
    svc = service(backend, path)
    operation = str(uuid4())
    await admit(svc, path, "dc", operation)
    backend.wrong_identity = True
    with pytest.raises(RemoteFailureError, match="identity mismatch"):
        await svc.measurement_result(await query(svc, "dc-scalars", operation))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"source_sha256": "0" * 64},
        {"quality": "invalid"},
        {"scalars": ()},
        {"protected_unchanged": False},
    ],
)
async def test_source_is_revalidated_before_claiming_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, Any],
) -> None:
    backend = NativeBackend()
    path = tmp_path / "admission.sqlite3"
    svc = service(backend, path)
    operation = str(uuid4())
    await admit(svc, path, "dc", operation)
    payload = native_payload()
    payload["job_id"] = operation
    malformed = NativeDiagnosticResult.model_validate(payload).model_copy(update=change)

    async def bad_result(job_id: UUID, analysis: str) -> NativeDiagnosticResult:
        return malformed

    monkeypatch.setattr(backend, "native_diagnostic_result", bad_result)
    with pytest.raises(RemoteFailureError, match="failed qualification"):
        await svc.measurement_result(await query(svc, "dc-scalars", operation))


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "unknown-design",
        "unknown-measurement",
        "stale-analysis",
        "wrong-mode",
        "raw-selector",
        "script",
        "modified-definition",
        "bool-version",
        "too-many",
    ],
)
def test_registration_cannot_redirect_reader_or_invent_definition(mutation: str) -> None:
    payload = reference_measurement_registry().model_dump(mode="json")
    contract = payload["measurement_contracts"][0]
    if mutation == "duplicate":
        payload["measurement_contracts"].append(dict(contract))
    elif mutation == "too-many":
        payload["measurement_contracts"] *= 172
    elif mutation == "wrong-mode":
        analysis = reference_analysis_registry().analysis_contracts[1]
        contract.update(
            analysis_id=analysis.analysis_id, analysis_contract_sha256=canonical_digest(analysis)
        )
    else:
        key, value = {
            "unknown-design": ("design_id", "unregistered"),
            "unknown-measurement": ("measurement_id", "power"),
            "stale-analysis": ("analysis_contract_sha256", "0" * 64),
            "raw-selector": ("output_id", 'getData("/private")'),
            "script": ("script", "run()"),
            "modified-definition": ("definition_sha256", "0" * 64),
            "bool-version": ("contract_version", True),
        }[mutation]
        contract[key] = value
    with pytest.raises(ValidationError):
        DesignMeasurementRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.asyncio
async def test_generic_and_legacy_registries_remain_unqualified(tmp_path: Path) -> None:
    backend = NativeBackend()
    for registry in (
        reference_registry(),
        reference_contract_registry(),
        reference_analysis_registry(),
    ):
        svc = service(backend, tmp_path / "no.sqlite3", registry)
        assert (await svc.list_measurements(DESIGN)).measurements == ()
        with pytest.raises(InvalidInputError):
            await svc.describe_measurement(
                MeasurementSelection(design_id=DESIGN, measurement_id="dc-scalars")
            )
    registry, _ = load_design_registry(ROOT / "docs/examples/design-registry-v4.fictional.json")
    svc = service(backend, tmp_path / "no.sqlite3", registry)
    listing = await svc.list_measurements("example-amplifier")
    assert len(listing.measurements) == 2
    for description in listing.measurements:
        assert not description.read_eligible and description.blocking_reason == "reader_unqualified"
        request = MeasurementQuery(
            design_id=description.design_id,
            measurement_id=description.measurement_id,
            operation_id=str(uuid4()),
            expected_contract_sha256=description.contract_sha256,
        )
        with pytest.raises(InvalidInputError, match="unqualified"):
            await svc.measurement_result(request)
    assert not (tmp_path / "no.sqlite3").exists() and backend.results == []


def test_old_plan_identities_and_v4_schema_registration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    backend = NativeBackend()
    old = service(backend, tmp_path / "old.sqlite3", reference_analysis_registry())
    new = service(backend, tmp_path / "new.sqlite3")
    for mode, _ in MODES:
        selection = AnalysisSelection(design_id=DESIGN, analysis_id="native-" + mode)
        assert old._analyses.plan(selection) == new._analyses.plan(selection)
    schema = json.loads((ROOT / "docs/schemas/design-registry-v4.schema.json").read_bytes())
    assert schema == DesignMeasurementRegistry.model_json_schema()
    assert cli.main(["design", "schema", "--schema-version", "4"]) == 0
    assert json.loads(capsys.readouterr().out) == schema
    proposed, registered = tmp_path / "proposed.json", tmp_path / "registered.json"
    proposed.write_text(reference_measurement_registry().model_dump_json(), encoding="utf-8")
    assert register_designs(proposed, registered)["execution_authorized"] is False
    assert proposed.read_bytes() == registered.read_bytes()
    assert load_design_registry(registered)[0] == reference_measurement_registry()
    with pytest.raises(FileExistsError):
        register_designs(proposed, registered)


@pytest.mark.asyncio
async def test_mcp_closed_schema_projection_and_useful_errors(tmp_path: Path) -> None:
    backend = NativeBackend()
    path = tmp_path / "admissions.sqlite3"
    svc = service(backend, path)
    operation = str(uuid4())
    await admit(svc, path, "ac", operation)
    request = await query(svc, "ac-spectrum", operation)
    async with Client(create_server(svc)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert len(tools) == 70
        for name in (
            "cadence_list_measurements",
            "cadence_describe_measurement",
            "cadence_measurement_result",
        ):
            assert tools[name].input_schema["additionalProperties"] is False
            assert tools[name].annotations and tools[name].annotations.read_only_hint
        listing = await client.call_tool("cadence_list_measurements", {"design_id": DESIGN})
        assert not listing.is_error and len(listing.structured_content["measurements"]) == 3
        data = {"request": request.model_dump(mode="json")}
        for extra in ("path", "script", "netlist", "signal", "formula", "target", "values"):
            assert (
                await client.call_tool("cadence_measurement_result", {**data, extra: "private"})
            ).is_error
            assert (
                await client.call_tool(
                    "cadence_measurement_result", {"request": {**data["request"], extra: "private"}}
                )
            ).is_error
        assert backend.results == []
        result = await client.call_tool("cadence_measurement_result", data)
        assert (
            not result.is_error and result.structured_content["spec_evaluation"] == "not_evaluated"
        )
        assert len(result.structured_content["spectrum"]) == 71
        denied = await client.call_tool(
            "cadence_describe_measurement",
            {"request": {"design_id": DESIGN, "measurement_id": "power"}},
        )
        assert denied.is_error and denied.structured_content["error"]["code"] == "invalid_input"
    assert backend.submissions == []


@pytest.mark.parametrize(
    "value", [True, "../../path", "A" * 36, "00000000-0000-1000-8000-000000000000"]
)
def test_query_requires_exact_uuid4(value: Any) -> None:
    with pytest.raises(ValidationError):
        MeasurementQuery(
            design_id=DESIGN,
            measurement_id="dc-scalars",
            operation_id=value,
            expected_contract_sha256="a" * 64,
        )
