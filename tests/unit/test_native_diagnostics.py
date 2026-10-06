"""Native MCP identity, provenance, measurement and replay boundaries."""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from mcp import Client
from pydantic import ValidationError

from cadence_mcp_bridge.actual_diagnostics import COPY_SHA256, NETLIST_SHA256, SOURCE_SHA256
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import InvalidInputError, OperationTimeoutError, RemoteFailureError
from cadence_mcp_bridge.native_diagnostics import (
    MODEL_SHA256,
    OPERATING_POINT,
    REVISION,
    STATE_SHA256,
    NativeDiagnosticRequest,
    NativeDiagnosticResult,
    NativeDiagnosticStatus,
    NativeSettings,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

ROOT = Path(__file__).resolve().parents[2]


def remote_module(version: str = "native-mcp-v1", file: str = "helper.py") -> Any:
    def load_source(name: str, path: str) -> Any:
        parts = path.split("/phase-campaign/")[1].split("/")
        return remote_module(parts[0], parts[1])

    module = ModuleType(version)
    module.__dict__["imp"] = SimpleNamespace(load_source=load_source)
    source = (ROOT / "remote/phase-campaign" / version / file).read_text(encoding="utf-8")
    exec(
        compile(
            source.replace("import imp", "# injected imp").replace(
                "import pwd", "# Unix identity mocked"
            ),
            file,
            "exec",
        ),
        module.__dict__,
    )
    return module


def native_payload(analysis: str = "dc") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": str(uuid4()),
        "analysis": analysis,
        "state": "succeeded",
        "simulator": "succeeded",
        "extraction": "succeeded",
        "quality": "valid",
        "spec_evaluation": "not_evaluated",
        "execution_mode": "native_ade_owned_candidate_state",
        "settings": NativeSettings().model_dump(mode="json"),
        "source_sha256": SOURCE_SHA256,
        "copy_sha256": COPY_SHA256,
        "state_sha256": STATE_SHA256,
        "model_sha256": MODEL_SHA256,
        "circuit_sha256": NETLIST_SHA256,
        "input_sha256": "a" * 64,
        "owned_variables_sha256": "b" * 64,
        "psf_sha256": "c" * 64,
        "measurement_frame_sha256": "d" * 64,
        "result_selector": "dcOp" if analysis == "dc" else analysis,
        "protected_unchanged": True,
        "source_copy_signature_equal": True,
        "state_loaded": True,
        "netlist_valid": True,
        "warnings": 2,
        "notices": 0,
    }
    if analysis == "dc":
        payload["scalars"] = [
            {"logical_id": key, "value": value, "unit": "V"}
            for key, value in zip(
                ("vop", "vom", "vdd", "vp", "vm", "output_common_mode", "output_differential"),
                (0.6, 0.4, 1.0, 0.5, 0.5, 0.5, 0.2),
                strict=True,
            )
        ]
    elif analysis == "ac":
        payload["spectrum"] = [
            {
                "frequency_hz": 10 ** (1 + index / 10),
                "gain_v_per_v": 4,
                "gain_db": 20 * math.log10(4),
                "phase_deg": 0,
            }
            for index in range(71)
        ]
    else:
        payload["transient"] = {
            "point_count": 401,
            "start_s": 0,
            "stop_s": 0.004,
            "max_observed_step_s": 1e-5,
            "output_differential_min_v": -0.2,
            "output_differential_max_v": 0.2,
            "output_common_mode_min_v": 0.4,
            "output_common_mode_max_v": 0.5,
            "input_vcm_v": 0.5,
            "input_differential_peak_v": 0.1,
            "input_tone_hz": 1000,
            "vdd_v": 1.0,
            "sampling": "adaptive_native_no_fft",
            "stimulus_verified": True,
        }
    return payload


@pytest.mark.parametrize("analysis", ["dc", "ac", "tran"])
def test_native_projection_contract(analysis: str) -> None:
    assert NativeDiagnosticResult.model_validate(native_payload(analysis)).analysis == analysis


@pytest.mark.parametrize(
    "change",
    [
        {"analysis": "noise"},
        {"revision_id": "snapshot"},
        {"operating_point_id": "baseline"},
        {"operation_id": "../x"},
        {"operation_id": str(uuid4()).upper()},
        {"operation_id": "00000000-0000-1000-8000-000000000000"},
        {"voltage": 0.33},
        {"path": "/tmp/circuit"},
        {"script": "exit()"},
    ],
)
def test_closed_native_request(change: dict[str, Any]) -> None:
    valid = {
        "operation_id": str(uuid4()),
        "revision_id": REVISION,
        "operating_point_id": OPERATING_POINT,
        "analysis": "dc",
    }
    with pytest.raises(ValidationError):
        NativeDiagnosticRequest.model_validate({**valid, **change})


@pytest.mark.parametrize(
    "field",
    [
        "source_sha256",
        "copy_sha256",
        "state_sha256",
        "model_sha256",
        "circuit_sha256",
        "protected_unchanged",
        "state_loaded",
        "netlist_valid",
        "source_copy_signature_equal",
        "result_selector",
        "spec_evaluation",
        "quality",
        "notices",
        "warnings",
    ],
)
def test_result_rejects_false_provenance(field: str) -> None:
    payload = native_payload()
    payload[field] = (
        "e" * 64
        if field.endswith("sha256")
        else False
        if isinstance(payload[field], bool)
        else 3
        if isinstance(payload[field], int)
        else "unqualified"
    )
    with pytest.raises(ValidationError):
        NativeDiagnosticResult.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("vdd_v", 0.9),
        ("input_vcm_v", 0.55),
        ("saved_bias_values_v", [0.32, 0.702]),
        ("applied_bias_values_v", [0.3, 0.65]),
        ("tran_method", "default"),
        ("tran_stop_s", 0.005),
        ("tran_maxstep_s", 2e-5),
        ("corner", "FF"),
    ],
)
def test_settings_do_not_promote_candidate_or_expand_range(field: str, value: Any) -> None:
    payload = native_payload()
    payload["settings"][field] = value
    with pytest.raises(ValidationError):
        NativeDiagnosticResult.model_validate(payload)


def test_measurement_arithmetic_and_shape_are_enforced() -> None:
    payload = native_payload()
    payload["scalars"][5]["value"] = 0.8
    with pytest.raises(ValidationError):
        NativeDiagnosticResult.model_validate(payload)
    payload = native_payload("ac")
    payload["spectrum"][2]["gain_db"] += 1
    with pytest.raises(ValidationError):
        NativeDiagnosticResult.model_validate(payload)
    payload = native_payload("tran")
    payload["transient"]["output_differential_min_v"] = 1
    with pytest.raises(ValidationError):
        NativeDiagnosticResult.model_validate(payload)
    payload["transient"]["output_differential_min_v"] = math.nan
    with pytest.raises(ValidationError):
        NativeDiagnosticResult.model_validate(payload)


def test_remote_projection_drops_raw_and_checks_saved_applied() -> None:
    helper = remote_module()
    payload = native_payload()
    raw = {
        **payload,
        "simulation": "succeeded",
        "source_saved_state": {
            "variables_v": helper.CAND.SAVED,
            "enabled_analyses": ["dc"],
            "model_section": "NN",
            "temperature_c": 27,
        },
        "effective": {
            "variables_v": helper.CAND.CANDIDATE,
            "enabled_analyses": ["dc"],
            "model_section": "NN",
            "temperature_c": 27,
        },
        "job_analysis_override": {},
        "vdd_v": 1.0,
        "applied_bias_values_v": [0.32, 0.702],
        "private_netlist": "private",
        "counter": {"count": 21},
    }
    projected = helper.project(raw, payload["job_id"], "dc", "d" * 64)
    assert "private_netlist" not in projected and "counter" not in projected
    assert NativeDiagnosticResult.model_validate(projected).quality == "valid"
    raw["source_saved_state"]["variables_v"] = helper.CAND.CANDIDATE
    with pytest.raises(ValueError, match="provenance"):
        helper.project(raw, payload["job_id"], "dc", "d" * 64)


def test_native_routing_request_identity_and_symlink(tmp_path: Path) -> None:
    helper = remote_module()
    helper.JOBS = tmp_path.as_posix()
    helper.os = SimpleNamespace(**vars(os))
    paths = dict(vars(os.path))
    paths["realpath"] = lambda path: Path(path).resolve().as_posix()
    helper.os.path = SimpleNamespace(**paths)
    job_id = str(uuid4())
    helper.configure(job_id, "tran")
    assert (tmp_path / job_id / "work").as_posix() == helper.BASE.JOB
    assert helper.CAND.NATIVE.VERSION == helper.VERSION
    record = tmp_path / job_id
    record.mkdir()
    (record / "request.json").write_text(
        json.dumps(
            {"analysis": "tran", "revision_id": REVISION, "operating_point_id": OPERATING_POINT}
        )
    )
    helper.request()
    helper.ANALYSIS = "ac"
    with pytest.raises(ValueError, match="identity"):
        helper.request()
    with pytest.raises(ValueError, match="identity"):
        helper.configure("../x", "dc")


@pytest.mark.parametrize(
    "count,reserved", [(100, 1611661312), (20, 1611661312), (21, 5 * 1024**3), (True, 1611661312)]
)
def test_native_budget_fail_closed(count: int, reserved: int) -> None:
    helper = remote_module()
    helper.BASE.environment_preflight = lambda: None
    helper.BASE.snapshot = lambda: {}
    helper.references = lambda: None
    helper.BASE.state_facts = lambda: {"variables_v": helper.CAND.SAVED}
    helper.BASE.read = lambda *_: json.dumps(
        {"campaign_id": "AUTO-PHASE-01", "count": count, "result_reserved_bytes": reserved}
    )
    with pytest.raises(ValueError, match="budget"):
        helper.preflight()


class Backend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.timeout = False
        self.mismatch = False

    async def submit_native_diagnostic(
        self, request: NativeDiagnosticRequest
    ) -> NativeDiagnosticStatus:
        self.calls.append((request.operation_id, request.analysis))
        if self.timeout:
            raise OperationTimeoutError("uncertain submit")
        return await self.native_diagnostic_status(UUID(request.operation_id), request.analysis)

    async def native_diagnostic_status(self, job_id: UUID, analysis: str) -> NativeDiagnosticStatus:
        return NativeDiagnosticStatus.model_validate(
            {
                "job_id": uuid4() if self.mismatch else job_id,
                "analysis": analysis,
                "state": "queued",
                "stage": "queued",
                "simulator": "not_started",
                "extraction": "not_started",
                "updated_at": datetime.now(UTC),
            }
        )


@pytest.mark.asyncio
async def test_service_recovers_same_id_and_rejects_identity_drift() -> None:
    backend = Backend()
    service = CadenceService(cast(CadenceBackend, backend))
    request = NativeDiagnosticRequest(
        operation_id=str(uuid4()),
        revision_id=REVISION,
        operating_point_id=OPERATING_POINT,
        analysis="dc",
    )
    backend.timeout = True
    result = await service.submit_native_diagnostic(request)
    assert str(result.job_id) == request.operation_id
    assert backend.calls == [(request.operation_id, "dc")]
    backend.mismatch = True
    with pytest.raises(RemoteFailureError, match="identity"):
        await service.submit_native_diagnostic(request)
    with pytest.raises(InvalidInputError):
        await service.native_diagnostic_status(str(uuid4()), "dc;exit")


@pytest.mark.asyncio
async def test_mcp_native_schema_and_validation() -> None:
    backend = Backend()
    async with Client(create_server(CadenceService(cast(CadenceBackend, backend)))) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert len(tools) == 75
        assert tools["cadence_submit_native_diagnostic"].annotations.idempotent_hint  # type: ignore[union-attr]
        profiles = await client.call_tool("cadence_list_native_diagnostics")
        assert profiles.structured_content["analyses"] == ["dc", "ac", "tran"]
        assert profiles.structured_content["contract_version"] == 2
        assert profiles.structured_content["campaign_max_spectre_attempts"] == 500
        assert profiles.structured_content["campaign_max_result_bytes"] == 5 * 1024**3
        submitted = await client.call_tool(
            "cadence_submit_native_diagnostic",
            {
                "request": {
                    "operation_id": str(uuid4()),
                    "revision_id": REVISION,
                    "operating_point_id": OPERATING_POINT,
                    "analysis": "dc",
                }
            },
        )
        assert not submitted.is_error
        invalid = await client.call_tool(
            "cadence_submit_native_diagnostic",
            {
                "request": {
                    "operation_id": "../x",
                    "revision_id": REVISION,
                    "operating_point_id": OPERATING_POINT,
                    "analysis": "dc",
                }
            },
        )
        assert invalid.is_error


@pytest.mark.asyncio
async def test_backend_narrow_native_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = OpenSshBackend(BridgeConfig())
    calls: list[tuple[str, ...]] = []

    def invoke(*args: str) -> str:
        calls.append(args)
        return "{}"

    monkeypatch.setattr(backend, "_invoke_at_path", invoke)
    job_id = uuid4()
    await backend._invoke_native_json("status", job_id, "tran")
    assert calls == [
        (
            "/home/buet/cds_work/.cadence_mcp/phase-campaign/native-mcp-v3/run.sh",
            "status",
            str(job_id),
            "tran",
        )
    ]
    for action, analysis in (("worker", "dc"), ("submit", "noise"), ("result;exit", "tran")):
        with pytest.raises(InvalidInputError):
            await backend._invoke_native_json(action, job_id, analysis)
    assert len(calls) == 1


def test_shell_lock_and_replay_contract() -> None:
    source = (ROOT / "remote/phase-campaign/native-mcp-v1/run.sh").read_text(encoding="ascii")
    assert source.index('if [ -e "$RECORD" ]') < source.index("flock -n 8")
    assert '9>"$ROOT/run.lock"' in source and "flock -n 9" in source
    assert "nohup" in source and "8>&-" in source
    assert source.index('"$HELPER" reserve') < source.index('timeout 120 "$SPECTRE"')
    assert "counter.json" not in source  # Ledger writes occur only through qualified reservation.
