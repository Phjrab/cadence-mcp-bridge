"""Synthetic receipt/science/admission/transport and client-independent read checks."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mcp import Client
from test_analog_measurements import request, service
from test_analyses import DESIGN, NativeBackend, selection
from test_native_diagnostics import native_payload

import cadence_mcp_bridge.offset_service as binding
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import NativeDiagnosticResult
from cadence_mcp_bridge.offset_study import (
    REFERENCE_INPUT,
    REFERENCE_OPERATION,
    REFERENCE_PSF,
    OffsetExtraction,
    study_diagnostics,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import canonical_digest


def artifact() -> OffsetExtraction:
    # Synthetic local linear response; never reference qualification evidence.
    rows = []
    for i, (case, dx) in enumerate(
        zip(
            ("zero", "minus1", "plus1", "minus05", "plus05"),
            (0, -1e-6, 1e-6, -0.5e-6, 0.5e-6),
            strict=True,
        )
    ):
        rows.append(
            {
                "schema_version": 1,
                "case": case,
                "source_job_id": REFERENCE_OPERATION,
                "source_input_sha256": REFERENCE_INPUT,
                "source_psf_sha256": REFERENCE_PSF,
                "input_sha256": REFERENCE_INPUT if i == 0 else "1" * 64,
                "psf_sha256": REFERENCE_PSF if i == 0 else "2" * 64,
                "frame_sha256": "3" * 64,
                "scalars": {
                    "Vp": 0.5 + dx / 2,
                    "Vm": 0.5 - dx / 2,
                    "VDD": 1,
                    "Vop": 0.227 + dx * 4000,
                    "Vom": 0.227 - dx * 4000,
                },
                "counter": {
                    "campaign_id": "AUTO-PHASE-01",
                    "count": 68 + i,
                    "result_reserved_bytes": 7919894528 + i * 128 * 1024**2,
                },
                "new_simulation": i != 0,
                "warnings": 0,
                "notices": 0,
                "protected_unchanged": True,
            }
        )
    return OffsetExtraction.model_validate({"schema_version": 1, "cases": rows})


@pytest.mark.parametrize("case", ["source", "psf", "sequence", "case", "extra", "missing", "nan"])
def test_identity_science_and_shape_rejection(case: str) -> None:
    data = artifact().model_dump(mode="json")
    r = data["cases"][2]
    if case == "source":
        r["source_input_sha256"] = "0" * 64
    elif case == "psf":
        r["source_psf_sha256"] = "0" * 64
    elif case == "sequence":
        r["counter"]["count"] = 72
    elif case == "case":
        r["case"] = "minus1"
    elif case == "extra":
        r["path"] = "/private"
    elif case == "missing":
        data["cases"].pop()
    elif case == "nan":
        r["scalars"]["Vop"] = float("nan")
    with pytest.raises(ValueError):
        study_diagnostics(OffsetExtraction.model_validate(data))


@pytest.mark.parametrize("case", ["rail", "common-mode", "large-output", "nonmonotonic"])
def test_bad_effective_input_or_local_response_not_qualified(case: str) -> None:
    data = artifact().model_dump(mode="json")
    r = data["cases"][2]["scalars"]
    if case == "rail":
        r["VDD"] = 0.9
    elif case == "common-mode":
        r["Vp"] += 0.01
        r["Vm"] += 0.01
    elif case == "large-output":
        r["Vop"] = 0.99
    else:
        r["Vop"] = 0.22
    d = study_diagnostics(OffsetExtraction.model_validate(data))
    assert d.status == "UNQUALIFIED" and d.value_v is None


class Backend(NativeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.study = artifact()
        self.study_reads: list[str] = []
        self.native_changes: dict[str, Any] = {}

    async def native_diagnostic_result(self, job_id: Any, analysis: str) -> NativeDiagnosticResult:
        self.results.append((job_id, analysis))
        data = native_payload(analysis)
        data.update(job_id=str(job_id), input_sha256=REFERENCE_INPUT, psf_sha256=REFERENCE_PSF)
        data.update(self.native_changes)
        return NativeDiagnosticResult.model_validate(data)

    async def offset_study_result(self, operation_id: str) -> OffsetExtraction:
        self.study_reads.append(operation_id)
        return self.study


async def admission(svc: Any, path: Path) -> None:
    plan = await svc.plan_analysis(selection("dc"))
    AnalysisStore(path).admit(REFERENCE_OPERATION, DESIGN, "native-dc", plan.plan_hash)


@pytest.mark.asyncio
async def test_mcp_admission_restart_concurrent_read_and_old_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    b = Backend()
    monkeypatch.setattr(binding, "REFERENCE_EXTRACTION", canonical_digest(b.study))
    path = tmp_path / "db"
    svc = service(b, path)
    await admission(svc, path)
    q = await request(svc, "offset", REFERENCE_OPERATION)
    original = await svc.analog_measurement_result(q)
    before = path.read_bytes()
    results = await asyncio.gather(*(svc.offset_study_result(q) for _ in range(3)))
    assert all(r == results[0] for r in results)
    r = results[0]
    assert r.reference_result == original and original.value is None
    assert r.generic_offset_qualification == "UNQUALIFIED"
    assert r.spec_evaluation == "not_evaluated"
    assert r.diagnostics.status == "PARTIALLY_QUALIFIED"
    assert r.absolute_error_bound_v is None
    assert await service(b, path).offset_study_result(q) == r
    assert path.read_bytes() == before and not b.submissions
    async with Client(create_server(svc)) as client:
        tools = (await client.list_tools()).tools
        tool = next(t for t in tools if t.name == "cadence_offset_study_result")
        assert tool.annotations.read_only_hint and tool.annotations.idempotent_hint
        assert not tool.annotations.destructive_hint and not tool.annotations.open_world_hint
        out = await client.call_tool(tool.name, {"request": q.model_dump(mode="json")})
        assert not out.is_error and len(json.dumps(out.structured_content)) < 16384
        assert '"vectors":' not in json.dumps(out.structured_content)
        bad = q.model_dump(mode="json") | {"path": "/private", "stimulus": "arbitrary"}
        assert (await client.call_tool(tool.name, {"request": bad})).is_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "unadmitted",
        "unknown-design",
        "wrong-metric",
        "other-operation",
        "stale-contract",
        "source-drift",
        "receipt-drift",
    ],
)
async def test_fail_closed_before_receipt_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    b = Backend()
    monkeypatch.setattr(binding, "REFERENCE_EXTRACTION", canonical_digest(b.study))
    path = tmp_path / "db"
    svc = service(b, path)
    if case != "unadmitted":
        await admission(svc, path)
    q = await request(svc, "offset", REFERENCE_OPERATION)
    if case == "unknown-design":
        q = q.model_copy(update={"design_id": "unknown"})
    elif case == "wrong-metric":
        q = await request(svc, "gain", REFERENCE_OPERATION)
    elif case == "other-operation":
        q = q.model_copy(update={"operation_id": str(uuid4())})
    elif case == "stale-contract":
        q = q.model_copy(update={"expected_contract_sha256": "0" * 64})
    elif case == "source-drift":
        b.native_changes["input_sha256"] = "0" * 64
    elif case == "receipt-drift":
        monkeypatch.setattr(binding, "REFERENCE_EXTRACTION", "0" * 64)
    with pytest.raises((InvalidInputError, RemoteFailureError)):
        await svc.offset_study_result(q)
    assert len(b.study_reads) == (1 if case == "receipt-drift" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["valid", "operation", "root", "private-error", "schema"])
async def test_fixed_result_transport_privacy(monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    b = OpenSshBackend(BridgeConfig())
    calls = []

    def invoke(*args: Any) -> str:
        calls.append(args)
        if case == "private-error":
            raise RemoteFailureError("/private/vendor/license")
        return "{}" if case == "schema" else artifact().model_dump_json()

    monkeypatch.setattr(b, "_invoke_at_path", invoke)
    if case == "root":
        b._config = BridgeConfig(remote_root="/wrong", runner_path="/wrong/bin/cadence-runner")
    if case == "valid":
        assert await b.offset_study_result(REFERENCE_OPERATION) == artifact()
        assert calls == [
            ("/home/buet/cds_work/.cadence_mcp/phase-campaign/offset-read-v1/run.sh", "result")
        ]
    else:
        with pytest.raises((InvalidInputError, RemoteFailureError)) as exc:
            await b.offset_study_result(
                str(uuid4()) if case == "operation" else REFERENCE_OPERATION
            )
        assert "/private" not in str(exc.value)
        assert len(calls) == (0 if case in ("root", "operation") else 1)
