"""Supply sign, complete inventory, admission, provenance and bounded MCP reads."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from mcp import Client
from pydantic import ValidationError
from test_analyses import DESIGN, NativeBackend, selection
from test_native_diagnostics import native_payload

import cadence_mcp_bridge.power_service as power
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import NativeDiagnosticResult
from cadence_mcp_bridge.power_measurements import (
    REFERENCE_FRAME,
    REFERENCE_INPUT,
    REFERENCE_OPERATION,
    REFERENCE_PSF,
    SOURCE_SET,
    PowerExtraction,
    PowerQuery,
    PowerResult,
    PowerSelection,
    SignedSource,
    delivered_power,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.specification_registry import reference_specification_registry
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import canonical_digest


def artifact() -> dict[str, Any]:
    # Synthetic sources, including an absorbing bias source. No private result values.
    return {
        "schema_version": 1,
        "job_id": REFERENCE_OPERATION,
        "analysis": "dc",
        "input_sha256": REFERENCE_INPUT,
        "psf_sha256": REFERENCE_PSF,
        "frame_sha256": REFERENCE_FRAME,
        "status": "EXTRACTED",
        "reason": None,
        "sources": [
            {"source_id": identity, "role": role, "voltage_v": voltage, "current_a": current}
            for (identity, role, voltage), current in zip(
                SOURCE_SET, (-0.002, 0.002, 0.001, -0.001, 0, 0), strict=True
            )
        ],
        "protected_unchanged": True,
        "new_spectre_attempts": 0,
        "new_reservation_bytes": 0,
        "counter": {
            "campaign_id": "AUTO-PHASE-01",
            "count": 62,
            "result_reserved_bytes": 7114588160,
        },
    }


class Backend(NativeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.artifact = PowerExtraction.model_validate(artifact())
        self.power_reads: list[str] = []
        self.native_changes: dict[str, Any] = {}

    async def native_diagnostic_result(self, job_id: Any, analysis: str) -> NativeDiagnosticResult:
        self.results.append((job_id, analysis))
        payload = native_payload(analysis)
        payload.update(job_id=str(job_id), input_sha256=REFERENCE_INPUT, psf_sha256=REFERENCE_PSF)
        payload.update(self.native_changes)
        return NativeDiagnosticResult.model_validate(payload)

    async def power_extraction_result(self, operation_id: str) -> PowerExtraction:
        self.power_reads.append(operation_id)
        return self.artifact


def service(backend: Backend, path: Path) -> CadenceService:
    return CadenceService(
        cast(CadenceBackend, backend),
        designs=reference_specification_registry(),
        analysis_journal=path,
        sweep_journal=path.with_suffix(".sweep"),
    )


def choose() -> PowerSelection:
    return PowerSelection(design_id=DESIGN, measurement_id="analog-power")


async def query(svc: CadenceService) -> PowerQuery:
    d = await svc.describe_power_measurement(choose())
    return PowerQuery(
        **choose().model_dump(),
        expected_contract_sha256=d.contract_sha256,
        operation_id=REFERENCE_OPERATION,
    )


async def admit(svc: CadenceService, path: Path) -> None:
    plan = await svc.plan_analysis(selection("dc"))
    AnalysisStore(path).admit(REFERENCE_OPERATION, DESIGN, "native-dc", plan.plan_hash)


def test_signed_power_absorption_zero_rail_and_separate_contributions() -> None:
    extracted = PowerExtraction.model_validate(artifact())
    values = delivered_power(extracted.sources)
    # A 2 mA load on 1 V delivers 2 mW. Bias-n absorbs .32 mW;
    # bias-p delivers .702 mW. Taking absolute currents would give a different answer.
    assert values == pytest.approx((0.002, 0.000382, 0, 0.002382))
    assert values[0] != sum(abs(s.current_a or 0) for s in extracted.sources)
    changed = [s.model_dump() for s in extracted.sources]
    changed[0]["current_a"] = 0.002
    assert delivered_power(tuple(SignedSource.model_validate(s) for s in changed))[0] == -0.002


@pytest.mark.parametrize(
    "case",
    [
        "missing-current",
        "missing-zero-rail",
        "duplicate",
        "role",
        "voltage",
        "infinite",
        "extra",
        "analysis",
        "unknown",
    ],
)
def test_incomplete_or_invalid_sources_cannot_qualify(case: str) -> None:
    d = artifact()
    if case == "missing-current":
        d["sources"][0]["current_a"] = None
    if case == "missing-zero-rail":
        d["sources"][1]["current_a"] = None
    if case == "duplicate":
        d["sources"][1]["source_id"] = "vdd"
    if case == "role":
        d["sources"][2]["role"] = "supply"
    if case == "voltage":
        d["sources"][0]["voltage_v"] = 0.9
    if case == "infinite":
        d["sources"][0]["current_a"] = float("inf")
    if case == "extra":
        d["path"] = "/private"
    if case == "analysis":
        d["analysis"] = "ac"
    if case == "unknown":
        d["sources"][0]["source_id"] = "private"
    with pytest.raises(ValidationError):
        PowerExtraction.model_validate(d)


def test_unqualified_missing_is_not_zero() -> None:
    d = artifact()
    d.update(status="UNQUALIFIED", reason="signed_branch_current_unavailable")
    d["sources"][1]["current_a"] = None
    result = PowerExtraction.model_validate(d)
    with pytest.raises(ValueError):
        delivered_power(result.sources)


@pytest.mark.asyncio
async def test_admitted_power_result_restart_concurrency_and_no_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    b = Backend()
    path = tmp_path / "admission.sqlite3"
    svc = service(b, path)
    # Sealing a synthetic fixture is confined to this test, production receipt stays pinned.
    monkeypatch.setattr(power, "REFERENCE_EXTRACTION", canonical_digest(b.artifact))
    await admit(svc, path)
    before = path.read_bytes()
    q = await query(svc)
    results = await asyncio.gather(*(svc.power_measurement_result(q) for _ in range(4)))
    assert all(r == results[0] for r in results)
    r = results[0]
    assert r.status == "QUALIFIED" and r.value == 0.002 and r.spec_evaluation == "not_evaluated"
    assert r.all_sources_delivered_power_w == pytest.approx(0.002382)
    assert r.provenance.settings.corner == "NN" and r.provenance.settings.temperature_c == 27
    assert r.provenance.settings.applied_bias_values_v == (0.32, 0.702)
    assert r.provenance.input_sha256 == REFERENCE_INPUT and r.power_frame_sha256 == REFERENCE_FRAME
    assert len(r.model_dump_json()) < 8192 and "/home/" not in r.model_dump_json()
    assert await service(b, path).power_measurement_result(q) == r
    assert path.read_bytes() == before and not b.submissions
    # Historical v1 analog-power definition still has no qualified source.
    assert not (await svc.describe_analog_measurement(choose())).read_eligible
    invalid = r.model_dump()
    invalid["value"] = 99
    with pytest.raises(ValidationError):
        PowerResult.model_validate(invalid)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["hash", "operation", "unadmitted", "native-psf", "receipt"])
async def test_wrong_bindings_fail_before_or_at_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    b = Backend()
    path = tmp_path / "db"
    svc = service(b, path)
    monkeypatch.setattr(power, "REFERENCE_EXTRACTION", canonical_digest(b.artifact))
    q = await query(svc)
    if case != "unadmitted":
        await admit(svc, path)
    if case == "hash":
        q = q.model_copy(update={"expected_contract_sha256": "0" * 64})
    if case == "operation":
        q = q.model_copy(update={"operation_id": str(uuid4())})
    if case == "native-psf":
        b.native_changes["psf_sha256"] = "a" * 64
    if case == "receipt":
        d = b.artifact.model_dump()
        d["sources"][0]["current_a"] *= 2
        b.artifact = PowerExtraction.model_validate(d)
    with pytest.raises((InvalidInputError, RemoteFailureError)):
        await svc.power_measurement_result(q)
    if case in ("hash", "operation", "unadmitted"):
        assert not b.power_reads
    assert not b.submissions


@pytest.mark.asyncio
async def test_unknown_design_or_wrong_metric_no_backend(tmp_path: Path) -> None:
    b = Backend()
    svc = service(b, tmp_path / "db")
    for d, m in [("unknown", "analog-power"), (DESIGN, "analog-gain"), (DESIGN, "unknown")]:
        with pytest.raises(InvalidInputError):
            await svc.describe_power_measurement(PowerSelection(design_id=d, measurement_id=m))
    assert not b.power_reads and not b.results


@pytest.mark.asyncio
async def test_mcp_strict_schema_no_paths_scripts_or_numeric_request(tmp_path: Path) -> None:
    svc = service(Backend(), tmp_path / "db")
    async with Client(create_server(svc)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        for name in ("cadence_describe_power_measurement", "cadence_power_measurement_result"):
            t = tools[name]
            assert t.input_schema["additionalProperties"] is False
            assert (
                t.annotations
                and t.annotations.read_only_hint
                and not t.annotations.destructive_hint
            )
            assert t.output_schema
        valid = {"request": choose().model_dump()}
        r = await client.call_tool("cadence_describe_power_measurement", valid)
        assert not r.is_error and r.structured_content["read_eligible"]
        for fields in ({"path": "../private"}, {"current_a": 0.002}, {"script": "pv(...)"}):
            bad = copy.deepcopy(valid)
            bad["request"].update(fields)
            assert (await client.call_tool("cadence_describe_power_measurement", bad)).is_error
        assert (
            await client.call_tool(
                "cadence_describe_power_measurement", {**valid, "path": "/private"}
            )
        ).is_error


@pytest.mark.asyncio
async def test_backend_has_only_fixed_result_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    b = OpenSshBackend(BridgeConfig())
    calls = []

    def invoke(runner: str, action: str, *args: str) -> str:
        calls.append((runner, action, args))
        return json.dumps(artifact())

    monkeypatch.setattr(b, "_invoke_at_path", invoke)
    assert (await b.power_extraction_result(REFERENCE_OPERATION)).job_id == REFERENCE_OPERATION
    assert calls == [
        ("/home/buet/cds_work/.cadence_mcp/phase-campaign/analog-power-v2/run.sh", "result", ())
    ]
    for operation in ("../private", str(uuid4()), "read", ""):
        with pytest.raises(InvalidInputError):
            await b.power_extraction_result(operation)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_backend_errors_do_not_expose_private_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    b = OpenSshBackend(BridgeConfig())

    def failed(*args: Any) -> str:
        raise RemoteFailureError("/home/private/result.json", details={"stderr": "/private/path"})

    monkeypatch.setattr(b, "_invoke_at_path", failed)
    with pytest.raises(RemoteFailureError) as error:
        await b.power_extraction_result(REFERENCE_OPERATION)
    assert not error.value.details and "/" not in error.value.safe_message


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["{}", '{"path":"/private"}', "not-json"])
async def test_backend_rejects_malformed_output(
    monkeypatch: pytest.MonkeyPatch, value: str,
) -> None:
    b = OpenSshBackend(BridgeConfig())
    monkeypatch.setattr(b, "_invoke_at_path", lambda *args: value)
    with pytest.raises(RemoteFailureError):
        await b.power_extraction_result(REFERENCE_OPERATION)
