"""Synthetic receipt/science/admission/transport and client-independent read checks."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mcp import Client
from pydantic import ValidationError
from test_analog_measurements import request, service
from test_analyses import DESIGN, NativeBackend, selection
from test_native_diagnostics import native_payload

import cadence_mcp_bridge.slew_service as binding
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import NativeDiagnosticResult
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.slew_study import (
    REFERENCE_INPUT,
    REFERENCE_OPERATION,
    REFERENCE_PSF,
    StepExtraction,
    direction_summary,
)
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import canonical_digest


def artifact() -> StepExtraction:
    # Independent synthetic linear ramps, not copied reference measurements.
    runs = []
    for index, (case, step, edge) in enumerate(
        (
            ("coarse", 1e-8, 1e-9),
            ("medium", 2e-10, 1e-9),
            ("fine", 1e-10, 1e-9),
            ("fast", 1e-10, 5e-10),
        )
    ):
        transitions = []
        for direction, start, end, base in (("rise", -1, 1, 2e-6), ("fall", 1, -1, 6e-6)):
            t0, t1 = base + 2e-7, base + 8e-7
            w0, w1 = start + 0.2 * (end - start), start + 0.8 * (end - start)
            transitions.append(
                {
                    "status": "DEFINED_TRANSITION",
                    "direction": direction,
                    "rate_v_per_s": (w1 - w0) / (t1 - t0),
                    "start_level_v": start,
                    "end_level_v": end,
                    "plateau_span_v": 0,
                    "window_v": [w0, w1],
                    "crossings_s": [t0, t1],
                    "brackets_s": [[t0 - 1e-9, t0 + 1e-9], [t1 - 1e-9, t1 + 1e-9]],
                    "window_sample_count": 32,
                    "overshoot_fraction": 0,
                    "subwindow_rate_ratio": 1,
                    "input_edge_overlap": False,
                }
            )
        runs.append(
            {
                "schema_version": 1,
                "source_job_id": REFERENCE_OPERATION,
                "source_input_sha256": REFERENCE_INPUT,
                "source_psf_sha256": REFERENCE_PSF,
                "input_sha256": "1" * 64,
                "psf_sha256": "2" * 64,
                "frame_sha256": "3" * 64,
                "summary": {
                    "case": case,
                    "maxstep_s": step,
                    "input_edge_s": edge,
                    "native_point_count": 1001,
                    "max_observed_step_s": step,
                    "output_differential_min_v": -1,
                    "output_differential_max_v": 1,
                    "transitions": transitions,
                },
                "counter": {
                    "campaign_id": "AUTO-PHASE-01",
                    "count": 65 + index,
                    "result_reserved_bytes": 7383023616 + (index + 1) * 128 * 1024**2,
                },
                "warnings": 0,
                "notices": 0,
                "protected_unchanged": True,
            }
        )
    return StepExtraction.model_validate({"schema_version": 1, "cases": runs})


@pytest.mark.parametrize(
    "case",
    [
        "source",
        "psf",
        "sequence",
        "case",
        "controls",
        "extra",
        "sign",
        "secant",
        "bracket",
        "samples",
        "invalid-rate",
    ],
)
def test_receipt_scientific_and_identity_rejection(case: str) -> None:
    data = artifact().model_dump(mode="json")
    r = data["cases"][0]
    t = r["summary"]["transitions"][0]
    if case == "source":
        r["source_input_sha256"] = "0" * 64
    elif case == "psf":
        r["source_psf_sha256"] = "0" * 64
    elif case == "sequence":
        r["counter"]["count"] = 66
    elif case == "case":
        r["summary"]["case"] = "fine"
    elif case == "controls":
        r["summary"]["maxstep_s"] = 1e-9
    elif case == "extra":
        r["path"] = "/private"
    elif case == "sign":
        t["direction"] = "fall"
    elif case == "secant":
        t["rate_v_per_s"] *= 2
    elif case == "bracket":
        t["brackets_s"][0] = [0, 1e-5]
    elif case == "samples":
        t["window_sample_count"] = 2
    elif case == "invalid-rate":
        t["status"] = "UNSETTLED"
    with pytest.raises(ValidationError):
        StepExtraction.model_validate(data)


def test_agreement_does_not_qualify_generic_slew_and_missing_rate_not_zero() -> None:
    x = artifact()
    d = direction_summary(x, "rise")
    assert d.fine_signed_rate_v_per_s == pytest.approx(2e6)
    assert d.fine_magnitude_v_per_us == pytest.approx(2)
    assert d.status == "PARTIALLY_QUALIFIED"
    assert d.resolution_agreement == "OBSERVED_WITHIN_1_PERCENT"
    data = x.model_dump(mode="json")
    data["cases"][2]["summary"]["transitions"][0].update(
        status="INSUFFICIENT_WINDOW_SAMPLES",
        rate_v_per_s=None,
        subwindow_rate_ratio=3,
    )
    d = direction_summary(StepExtraction.model_validate(data), "rise")
    assert d.fine_signed_rate_v_per_s is None and d.status == "UNQUALIFIED"
    assert d.resolution_agreement == "NOT_ASSESSED" and d.constant_slope == "NONLINEAR"


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

    async def slew_step_result(self, operation_id: str) -> StepExtraction:
        self.study_reads.append(operation_id)
        return self.study


async def admission(svc: Any, path: Path) -> None:
    plan = await svc.plan_analysis(selection("tran"))
    AnalysisStore(path).admit(REFERENCE_OPERATION, DESIGN, "native-tran", plan.plan_hash)


@pytest.mark.asyncio
async def test_mcp_admission_restart_concurrent_read_and_old_definition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    b = Backend()
    monkeypatch.setattr(binding, "REFERENCE_EXTRACTION", canonical_digest(b.study))
    path = tmp_path / "db"
    svc = service(b, path)
    await admission(svc, path)
    q = await request(svc, "slew-rate", REFERENCE_OPERATION)
    original = await svc.analog_measurement_result(q)
    before = path.read_bytes()
    results = await asyncio.gather(*(svc.slew_study_result(q) for _ in range(3)))
    assert all(r == results[0] for r in results)
    r = results[0]
    assert r.reference_result == original and original.value is None
    assert r.conventional_slew_qualification == "UNQUALIFIED"
    assert r.spec_evaluation == "not_evaluated"
    assert await service(b, path).slew_study_result(q) == r
    assert path.read_bytes() == before and not b.submissions
    async with Client(create_server(svc)) as client:
        tools = (await client.list_tools()).tools
        tool = next(t for t in tools if t.name == "cadence_slew_study_result")
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
    q = await request(svc, "slew-rate", REFERENCE_OPERATION)
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
        await svc.slew_study_result(q)
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
        assert await b.slew_step_result(REFERENCE_OPERATION) == artifact()
        assert calls == [
            ("/home/buet/cds_work/.cadence_mcp/phase-campaign/slew-read-v2/run.sh", "result")
        ]
    else:
        with pytest.raises((InvalidInputError, RemoteFailureError)) as exc:
            await b.slew_step_result(str(uuid4()) if case == "operation" else REFERENCE_OPERATION)
        assert "/private" not in str(exc.value)
        assert len(calls) == (0 if case in ("root", "operation") else 1)
