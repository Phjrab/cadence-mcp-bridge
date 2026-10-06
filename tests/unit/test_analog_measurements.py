"""Scientific extraction, admission and registry boundaries for derived analog metrics."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from mcp import Client
from pydantic import ValidationError
from test_analyses import DESIGN, NativeBackend, selection
from test_native_diagnostics import native_payload

from cadence_mcp_bridge import __main__ as cli
from cadence_mcp_bridge.analog_measurements import AnalogQuery, AnalogSelection, definition
from cadence_mcp_bridge.analog_registry import DesignAnalogRegistry, reference_analog_registry
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.designs import load_design_registry, reference_measurement_registry
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import NativeDiagnosticResult
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.sweep_registry import DesignSweepRegistry, fixture_sweep_registry
from cadence_mcp_bridge.variable_contracts import canonical_digest

ROOT = Path(__file__).resolve().parents[2]


class SpectrumBackend(NativeBackend):
    def __init__(self, db: list[float | None]) -> None:
        super().__init__()
        self.db = db

    async def native_diagnostic_result(self, job_id: Any, analysis: str) -> NativeDiagnosticResult:
        self.results.append((job_id, analysis))
        payload = native_payload(analysis)
        payload["job_id"] = str(job_id)
        for p, db in zip(payload["spectrum"], self.db, strict=True):
            p["gain_db"] = db
            p["gain_v_per_v"] = 0 if db is None else 10 ** (db / 20)
        return NativeDiagnosticResult.model_validate(payload)


def service(backend: NativeBackend, path: Path, registry: Any = None) -> CadenceService:
    return CadenceService(
        cast(CadenceBackend, backend),
        designs=registry or reference_analog_registry(),
        analysis_journal=path,
    )


async def request(svc: CadenceService, metric: str, operation: str) -> AnalogQuery:
    description = await svc.describe_analog_measurement(
        AnalogSelection(design_id=DESIGN, measurement_id="analog-" + metric)
    )
    return AnalogQuery(
        design_id=DESIGN,
        measurement_id=description.measurement_id,
        expected_contract_sha256=description.contract_sha256,
        operation_id=operation,
    )


async def admitted(svc: CadenceService, path: Path, operation: str) -> None:
    plan = await svc.plan_analysis(selection("ac"))
    AnalysisStore(path).admit(operation, DESIGN, "native-ac", plan.plan_hash)


@pytest.mark.asyncio
async def test_one_pole_gain_bandwidth_provenance_and_restart(tmp_path: Path) -> None:
    # Independent known transfer: gain 100, pole 1 kHz. 3.0 dB differs from half-power.
    frequencies = [10 ** (1 + i / 10) for i in range(71)]
    db = [20 * math.log10(100 / math.sqrt(1 + (f / 1000) ** 2)) for f in frequencies]
    backend = SpectrumBackend(db)
    path = tmp_path / "admission.sqlite3"
    svc = service(backend, path)
    operation = str(uuid4())
    await admitted(svc, path, operation)
    before = path.read_bytes()
    gain = await svc.analog_measurement_result(await request(svc, "gain", operation))
    assert gain.status == "QUALIFIED" and gain.value == pytest.approx(db[0])
    query = await request(svc, "bandwidth", operation)
    bw = await svc.analog_measurement_result(query)
    exact = 1000 * math.sqrt(10 ** (3 / 10) * (1 + (10 / 1000) ** 2) - 1)
    assert bw.value == pytest.approx(exact, rel=0.006)
    assert bw.status == "PARTIALLY_QUALIFIED" and bw.crossing_bracket_hz == (frequencies[19], 1000)
    assert bw.provenance == gain.provenance and bw.source_result_sha256 == gain.source_result_sha256
    assert await service(backend, path).analog_measurement_result(query) == bw
    assert path.read_bytes() == before and backend.submissions == [] and backend.reads == []
    assert bw.spec_evaluation == "not_evaluated" and bw.provenance is not None
    assert bw.provenance.settings.corner == "NN" and bw.provenance.settings.vdd_v == 1
    assert len(bw.model_dump_json()) < 8192


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["flat", "zero", "null-bracket", "exact", "recross"])
async def test_crossing_semantics_no_extrapolation(tmp_path: Path, mode: str) -> None:
    db: list[float | None] = [20.0] * 71
    if mode == "zero":
        db[0] = None
    elif mode == "null-bracket":
        db[1] = None
    elif mode == "exact":
        db[1:] = [17.0] * 70
    elif mode == "recross":
        db[1:4] = [18.0, 16.0, 20.0]
    svc = service(SpectrumBackend(db), tmp_path / "db")
    op = str(uuid4())
    await admitted(svc, tmp_path / "db", op)
    result = await svc.analog_measurement_result(await request(svc, "bandwidth", op))
    if mode in ("exact", "recross"):
        assert result.status == "PARTIALLY_QUALIFIED"
        assert result.value is not None and result.value < 16
        if mode == "exact":
            assert result.value == 10**1.1
    else:
        assert result.status == "UNQUALIFIED" and result.value is None and result.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("metric", ["phase-margin", "power", "offset", "slew-rate"])
async def test_missing_science_returns_no_value_without_transport(
    tmp_path: Path, metric: str
) -> None:
    backend = NativeBackend()
    svc = service(backend, tmp_path / "db")
    result = await svc.analog_measurement_result(await request(svc, metric, str(uuid4())))
    assert result.status == "UNQUALIFIED" and result.value is None and result.provenance is None
    assert result.reason == definition(cast(Any, metric)).blocking_reason
    assert backend.results == backend.submissions == backend.reads == []
    assert not (tmp_path / "db").exists()


@pytest.mark.asyncio
async def test_unadmitted_stale_unknown_and_wrong_source_fail_closed(tmp_path: Path) -> None:
    backend = NativeBackend()
    svc = service(backend, tmp_path / "db")
    op = str(uuid4())
    query = await request(svc, "gain", op)
    with pytest.raises(InvalidInputError):
        await svc.analog_measurement_result(query)
    with pytest.raises(InvalidInputError):
        await svc.analog_measurement_result(
            query.model_copy(update={"expected_contract_sha256": "0" * 64})
        )
    for design, measurement in (("unknown", "analog-gain"), (DESIGN, "unknown")):
        with pytest.raises(InvalidInputError):
            await svc.describe_analog_measurement(
                AnalogSelection(design_id=design, measurement_id=measurement)
            )
    assert backend.results == []
    await admitted(svc, tmp_path / "db", op)
    backend.wrong_identity = True
    with pytest.raises(RemoteFailureError):
        await svc.analog_measurement_result(query)


@pytest.mark.parametrize(
    "change",
    ["hash", "source", "definition", "duplicate", "design", "unqualified-reader", "collision"],
)
def test_registry_rejects_redirected_or_unreviewed_contracts(change: str) -> None:
    payload = reference_analog_registry().model_dump(mode="json")
    contract = payload["analog_contracts"][0]
    if change == "duplicate":
        payload["analog_contracts"].append(dict(contract))
    elif change == "unqualified-reader":
        payload["analog_contracts"][2].update(
            source_measurement_id=contract["source_measurement_id"],
            source_contract_sha256=contract["source_contract_sha256"],
        )
    else:
        field, value = {
            "hash": ("source_contract_sha256", "0" * 64),
            "source": ("source_measurement_id", "dc-scalars"),
            "definition": ("definition_sha256", "0" * 64),
            "design": ("design_id", "unknown"),
            "collision": ("measurement_id", "ac-spectrum"),
        }[change]
        contract[field] = value
    with pytest.raises((ValidationError, InvalidInputError)):
        DesignAnalogRegistry.model_validate_json(json.dumps(payload))


def test_v6_cli_registration_and_old_schema_bytes(tmp_path: Path, capsys: Any) -> None:
    assert cli.main(["design", "schema", "--schema-version", "6"]) == 0
    assert json.loads(capsys.readouterr().out) == DesignAnalogRegistry.model_json_schema()
    path = tmp_path / "registry.json"
    path.write_text(reference_analog_registry().model_dump_json(), encoding="utf-8")
    assert load_design_registry(path)[0] == reference_analog_registry()
    # Every old CLI schema must continue to match its published schema artifact.
    for version in range(1, 6):
        assert cli.main(["design", "schema", "--schema-version", str(version)]) == 0
        assert json.loads(capsys.readouterr().out) == json.loads(
            (ROOT / f"docs/schemas/design-registry-v{version}.schema.json").read_bytes()
        )
    old = reference_measurement_registry()
    new = reference_analog_registry()
    assert old.designs == new.designs and old.analysis_contracts == new.analysis_contracts
    assert old.measurement_contracts == new.measurement_contracts


@pytest.mark.asyncio
async def test_old_registries_do_not_gain_implicit_readers(tmp_path: Path) -> None:
    svc = service(NativeBackend(), tmp_path / "db", reference_measurement_registry())
    assert (await svc.list_analog_measurements(DESIGN)).measurements == ()
    with pytest.raises(InvalidInputError):
        await request(svc, "gain", str(uuid4()))


def test_v6_preserves_full_v5_sweep_identity_and_execution_drift_changes_hash() -> None:
    fixture = fixture_sweep_registry()
    native = reference_measurement_registry()
    payload = native.model_dump()
    payload["schema_version"] = 5
    for field in (
        "designs",
        "variable_sets",
        "range_reviews",
        "analysis_contracts",
        "measurement_contracts",
    ):
        payload[field] += getattr(fixture, field)
    old = DesignSweepRegistry.model_validate(payload)
    derived = reference_analog_registry().analog_contracts
    current = DesignAnalogRegistry.model_validate(
        {**payload, "schema_version": 6, "analog_contracts": derived}
    )
    assert old.sweep_identity_digest() == current.sweep_identity_digest()
    assert canonical_digest(old) == current.sweep_identity_digest()
    reduced = DesignAnalogRegistry.model_validate(
        {**payload, "schema_version": 6, "analog_contracts": ()}
    )
    assert reduced.sweep_identity_digest() == current.sweep_identity_digest()
    # Removing an entire admitted execution route must still change durable identity.
    smaller = reference_analog_registry()
    assert smaller.sweep_identity_digest() != current.sweep_identity_digest()


@pytest.mark.asyncio
async def test_mcp_closed_readonly_schema_and_qualified_read(tmp_path: Path) -> None:
    svc = service(NativeBackend(), tmp_path / "db")
    op = str(uuid4())
    await admitted(svc, tmp_path / "db", op)
    query = await request(svc, "gain", op)
    async with Client(create_server(svc)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert len(tools) == 72
        for name in (
            "cadence_list_analog_measurements",
            "cadence_describe_analog_measurement",
            "cadence_analog_measurement_result",
        ):
            assert tools[name].input_schema["additionalProperties"] is False
            assert tools[name].annotations is not None and tools[name].annotations.read_only_hint
        listing = await client.call_tool("cadence_list_analog_measurements", {"design_id": DESIGN})
        assert not listing.is_error and len(listing.structured_content["measurements"]) == 6
        for extra in ("path", "formula", "frequency_hz", "script", "target"):
            bad = await client.call_tool(
                "cadence_analog_measurement_result",
                {"request": {**query.model_dump(mode="json"), extra: "private"}},
            )
            assert bad.is_error
        for opid in (str(uuid4()).upper(), "../secret", "00000000-0000-1000-8000-000000000000"):
            bad = await client.call_tool(
                "cadence_analog_measurement_result",
                {"request": {**query.model_dump(mode="json"), "operation_id": opid}},
            )
            assert bad.is_error
        good = await client.call_tool(
            "cadence_analog_measurement_result", {"request": query.model_dump(mode="json")}
        )
        assert not good.is_error and good.structured_content["status"] == "QUALIFIED"
        assert good.structured_content["value"] == pytest.approx(20 * math.log10(4))
