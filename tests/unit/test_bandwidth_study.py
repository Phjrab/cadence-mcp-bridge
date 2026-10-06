"""Independent science, preserved admission, immutable reads and bounded MCP outputs."""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mcp import Client
from pydantic import ValidationError
from test_analog_measurements import admitted, request, service
from test_analyses import NativeBackend
from test_native_diagnostics import native_payload

import cadence_mcp_bridge.bandwidth_service as binding
from cadence_mcp_bridge.bandwidth_study import (
    REFERENCE_INPUT,
    REFERENCE_OPERATION,
    REFERENCE_PSF,
    RefinementExtraction,
    StudyPoint,
    convergence,
    study_definition,
    summarize,
)
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import InvalidInputError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import NativeDiagnosticResult
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.variable_contracts import canonical_digest


def one_pole(density: int, decades: int = 5) -> tuple[StudyPoint, ...]:
    # Exact independent continuous transfer, gain=100/pole=100kHz. No private circuit data.
    return tuple(
        StudyPoint(frequency_hz=f, gain_db=40 - 10 * math.log10(1 + (f / 100000) ** 2))
        for f in (10 ** (1 + i / density) for i in range(decades * density + 1))
    )


def artifact() -> RefinementExtraction:
    return RefinementExtraction.model_validate(
        {
            "schema_version": 1,
            "grids": [
                {
                    "schema_version": 1,
                    "grid": grid,
                    "source_job_id": REFERENCE_OPERATION,
                    "source_input_sha256": REFERENCE_INPUT,
                    "source_psf_sha256": REFERENCE_PSF,
                    "input_sha256": "1" * 64,
                    "psf_sha256": "2" * 64,
                    "frame_sha256": "3" * 64,
                    "spectrum": [p.model_dump() for p in one_pole(grid)],
                    "protected_unchanged": True,
                    "warnings": 0,
                    "notices": 0,
                    "counter": {
                        "campaign_id": "AUTO-PHASE-01",
                        "count": 63 + i,
                        "result_reserved_bytes": 7114588160 + (i + 1) * 128 * 1024**2,
                    },
                }
                for i, grid in enumerate((50, 100))
            ],
        }
    )


def test_one_pole_distinguishes_three_db_from_half_power_and_grid_change() -> None:
    grids = tuple(summarize(one_pole(d), d) for d in (10, 50, 100))
    state, changes, agreement = convergence(grids)
    # Solve precisely the 3.0 dB crossing using the actual 10Hz reference.
    expected = 100000 * math.sqrt((1 + (10 / 100000) ** 2) * 10**0.3 - 1)
    assert expected != pytest.approx(100000, abs=0.1)  # Not the half-power pole.
    for g in grids:
        assert g.crossing_bracket_hz is not None and g.estimate_hz is not None
        assert g.crossing_bracket_hz[0] <= expected <= g.crossing_bracket_hz[1]
    errors = [abs(g.estimate_hz - expected) for g in grids]
    assert errors[2] < errors[1] < errors[0]
    assert state == "OBSERVED_WITHIN_0_1_PERCENT" and agreement == 0
    assert changes[1] < changes[0] and study_definition().absolute_error_bound is None


@pytest.mark.parametrize(
    "gains,expected,count",
    [
        ([20, 20, 20, 20, 20], "NO_CROSSING", 0),
        ([20, 20, 17, 19, 16], "MULTIPLE_DOWNWARD_CROSSINGS", 2),
        ([20, 20, 20, 17, 17], "FIRST_CROSSING", 1),
        ([20, 20, None, 16, 15], "INSUFFICIENT_DATA", 0),
        ([None, 20, 19, 16, 15], "INSUFFICIENT_DATA", 0),
    ],
)
def test_crossing_missing_multiple_exact_and_no_extrapolation(
    gains: list[float | None], expected: str, count: int
) -> None:
    points = tuple(
        StudyPoint(frequency_hz=f, gain_db=g)
        for f, g in zip((10, 100, 1000, 10000, 100000), gains, strict=True)
    )
    s = summarize(points, 10)
    assert s.crossing_status == expected and s.downward_crossing_count == count
    if expected in ("NO_CROSSING", "INSUFFICIENT_DATA"):
        assert s.estimate_hz is None and s.crossing_bracket_hz is None
    if gains[3] == 17:
        assert s.estimate_hz == 10000  # Exact sampled crossing stays exact.


@pytest.mark.parametrize("case", ["duplicate", "unordered", "wrong-reference", "oversize", "short"])
def test_invalid_spectrum_denied(case: str) -> None:
    p = list(one_pole(10))
    if case == "duplicate":
        p[1] = p[0]
    if case == "unordered":
        p[2], p[3] = p[3], p[2]
    if case == "wrong-reference":
        p = p[1:]
    if case == "oversize":
        p = list(one_pole(100, 7))
    if case == "short":
        p = p[:2]
    with pytest.raises(ValueError):
        summarize(tuple(p), 10)


@pytest.mark.parametrize(
    "case", ["peaking", "nonflat", "multiple", "nocross", "reference-mismatch", "not-narrower"]
)
def test_empirical_convergence_never_infers_scientific_qualification(case: str) -> None:
    grids = [summarize(one_pole(d), d) for d in (10, 50, 100)]
    changes: dict[str, object] = {
        "peaking": {"peaking_above_reference_db": 2},
        "nonflat": {"sampled_gain_span_db": 1},
        "multiple": {"crossing_status": "MULTIPLE_DOWNWARD_CROSSINGS"},
        "nocross": {"crossing_status": "NO_CROSSING", "estimate_hz": None},
        "reference-mismatch": {"reference_gain_db": 50},
        "not-narrower": {"crossing_bracket_relative_width": 1},
    }[case]
    grids[-1] = grids[-1].model_copy(update=changes)
    state, _, _ = convergence(tuple(grids))
    assert state in ("NOT_CONVERGED", "NOT_ASSESSED")


@pytest.mark.parametrize(
    "case",
    [
        "source",
        "input",
        "psf",
        "density",
        "count",
        "frequency",
        "gain",
        "reversed",
        "counter",
        "extra",
        "nan",
    ],
)
def test_refinement_schema_rejects_substitution_and_unbounded_input(case: str) -> None:
    data = artifact().model_dump(mode="json")
    g = data["grids"][0]
    if case == "source":
        g["source_job_id"] = str(uuid4())
    if case == "input":
        g["source_input_sha256"] = "0" * 64
    if case == "psf":
        g["source_psf_sha256"] = "0" * 64
    if case == "density":
        g["grid"] = 999
    if case == "count":
        g["spectrum"].pop()
    if case == "frequency":
        g["spectrum"][1]["frequency_hz"] = 10
    if case == "gain":
        g["spectrum"][1]["gain_db"] = None
    if case == "reversed":
        data["grids"].reverse()
    if case == "counter":
        data["grids"][1]["counter"]["count"] += 1
    if case == "extra":
        g["path"] = "/private"
    if case == "nan":
        g["spectrum"][1]["gain_db"] = float("nan")
    with pytest.raises(ValidationError):
        RefinementExtraction.model_validate(data)


class Backend(NativeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.study = artifact()
        self.study_reads: list[str] = []
        self.native_changes: dict[str, Any] = {}

    async def native_diagnostic_result(self, job_id: Any, analysis: str) -> NativeDiagnosticResult:
        self.results.append((job_id, analysis))
        data = native_payload("ac")
        data.update(job_id=str(job_id), input_sha256=REFERENCE_INPUT, psf_sha256=REFERENCE_PSF)
        for p, g in zip(data["spectrum"], one_pole(10, 7), strict=True):
            p.update(gain_db=g.gain_db, gain_v_per_v=10 ** (g.gain_db / 20), phase_deg=0)
        data.update(self.native_changes)
        return NativeDiagnosticResult.model_validate(data)

    async def bandwidth_refinement_result(self, operation_id: str) -> RefinementExtraction:
        self.study_reads.append(operation_id)
        return self.study


@pytest.mark.asyncio
async def test_admission_restart_concurrent_read_and_mcp_bounded_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    b = Backend()
    monkeypatch.setattr(binding, "REFERENCE_EXTRACTION", canonical_digest(b.study))
    path = tmp_path / "admission.sqlite"
    svc = service(b, path)
    await admitted(svc, path, REFERENCE_OPERATION)
    q = await request(svc, "bandwidth", REFERENCE_OPERATION)
    old = await svc.analog_measurement_result(q)
    before = path.read_bytes()
    results = await asyncio.gather(svc.bandwidth_study_result(q), svc.bandwidth_study_result(q))
    assert results[0] == results[1]
    assert results[0].reference_result == old and old.status == "PARTIALLY_QUALIFIED"
    assert results[0].status == "PARTIALLY_QUALIFIED" and results[0].absolute_error_bound_hz is None
    assert not results[0].execution_authorized and not results[0].raw_vectors_included
    assert path.read_bytes() == before
    restarted = service(b, path)
    assert await restarted.bandwidth_study_result(q) == results[0]
    async with Client(create_server(restarted)) as client:
        tools = (await client.list_tools()).tools
        t = next(t for t in tools if t.name == "cadence_bandwidth_study_result")
        assert t.annotations.read_only_hint and t.annotations.idempotent_hint
        assert not t.annotations.destructive_hint and not t.annotations.open_world_hint
        result = await client.call_tool(t.name, {"request": q.model_dump(mode="json")})
        assert not result.is_error and len(json.dumps(result.structured_content)) < 12000
        assert '"spectrum":' not in json.dumps(result.structured_content)
        bad = q.model_dump(mode="json") | {"path": "/private", "grid": 999}
        assert (await client.call_tool(t.name, {"request": bad})).is_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "unadmitted",
        "unknown-design",
        "unknown-metric",
        "wrong-metric",
        "other-operation",
        "stale-contract",
        "source-drift",
        "receipt-drift",
    ],
)
async def test_fail_closed_before_private_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    b = Backend()
    monkeypatch.setattr(binding, "REFERENCE_EXTRACTION", canonical_digest(b.study))
    path = tmp_path / "admission.sqlite"
    svc = service(b, path)
    if case != "unadmitted":
        await admitted(svc, path, REFERENCE_OPERATION)
    q = await request(svc, "bandwidth", REFERENCE_OPERATION)
    if case == "unknown-design":
        q = q.model_copy(update={"design_id": "unknown"})
    if case == "unknown-metric":
        q = q.model_copy(update={"measurement_id": "unknown"})
    if case == "wrong-metric":
        q = await request(svc, "gain", REFERENCE_OPERATION)
    if case == "other-operation":
        q = q.model_copy(update={"operation_id": str(uuid4())})
    if case == "stale-contract":
        q = q.model_copy(update={"expected_contract_sha256": "0" * 64})
    if case == "source-drift":
        b.native_changes["input_sha256"] = "0" * 64
    if case == "receipt-drift":
        monkeypatch.setattr(binding, "REFERENCE_EXTRACTION", "0" * 64)
    with pytest.raises((InvalidInputError, RemoteFailureError)):
        await svc.bandwidth_study_result(q)
    assert len(b.study_reads) == (1 if case == "receipt-drift" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["wrong-operation", "wrong-root", "private-error", "invalid-schema", "valid"]
)
async def test_fixed_transport_and_error_privacy(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    backend = OpenSshBackend(
        BridgeConfig(
            remote_root="/wrong" if case == "wrong-root" else "/home/buet/cds_work/.cadence_mcp",
            runner_path="/wrong/bin/cadence-runner"
            if case == "wrong-root"
            else "/home/buet/cds_work/.cadence_mcp/bin/cadence-runner",
        )
    )
    calls = []

    def invoke(*args: Any) -> str:
        calls.append(args)
        if case == "private-error":
            raise RemoteFailureError("/private/vendor/license")
        return "{}" if case == "invalid-schema" else artifact().model_dump_json()

    monkeypatch.setattr(backend, "_invoke_at_path", invoke)
    if case == "valid":
        assert await backend.bandwidth_refinement_result(REFERENCE_OPERATION) == artifact()
        assert calls == [
            ("/home/buet/cds_work/.cadence_mcp/phase-campaign/bandwidth-qual-v1/run.sh", "result")
        ]
    else:
        with pytest.raises((InvalidInputError, RemoteFailureError)) as exc:
            await backend.bandwidth_refinement_result(
                str(uuid4()) if case == "wrong-operation" else REFERENCE_OPERATION
            )
        assert "/private" not in str(exc.value)
        if case in ("wrong-operation", "wrong-root"):
            assert calls == []
