"""Boundary tests for the fixed work-copy reader and typed MCP result."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.actual_diagnostics import (
    COPY_SHA256,
    NETLIST_SHA256,
    SOURCE_SHA256,
    ActualDiagnosticRequest,
    ActualDiagnosticResult,
)


def remote_reader() -> ModuleType:
    source = (
        Path(__file__).resolve().parents[2] / "remote/phase-campaign/sim-mcp-v2/diagnostic.py"
    ).read_text(encoding="utf-8")
    module = ModuleType("sim_mcp_v2_reader")
    module.__dict__["__name__"] = "sim_mcp_v2_reader"
    # Python 2.6's imp module was removed on the host Python; the parser
    # functions under test do not call it.
    exec(
        compile(source.replace("import imp", "import importlib as imp"), "diagnostic.py", "exec"),
        module.__dict__,
    )
    return module


def result_payload() -> dict:
    return {
        "job_id": str(uuid4()),
        "state": "succeeded",
        "profile_id": "actual-wp14-dc-v1",
        "revision_id": "wp14-copied-netlist-v1",
        "operating_point_id": "candidate-320-702mv-v1",
        "simulator": "succeeded",
        "extraction": "succeeded",
        "quality": "valid",
        "spec_evaluation": "not_evaluated",
        "source_sha256": SOURCE_SHA256,
        "copy_sha256": COPY_SHA256,
        "netlist_sha256": NETLIST_SHA256,
        "wrapper_sha256": "a" * 64,
        "psf_sha256": "b" * 64,
        "vdd_v": 1.0,
        "input_vcm_v": 0.5,
        "applied_bias_values_v": [0.32, 0.702],
        "scalars": [
            {"logical_id": name, "unit": "V", "value": value}
            for name, value in zip(
                ("vop", "vom", "vdd", "vp", "vm", "output_common_mode", "output_differential"),
                (0.6, 0.4, 1.0, 0.5, 0.5, 0.5, 0.2),
                strict=True,
            )
        ],
        "spectrum": [],
        "artifact_names": ["profile.scs", "spectre.log", "psf", "scalars.txt"],
    }


def test_fixed_dc_reader_and_result_relationships() -> None:
    reader = remote_reader()
    frame = (
        "MCP_DC_SCALAR|Vop|0.6\nMCP_DC_SCALAR|Vom|0.4\n"
        "MCP_DC_SCALAR|VDD|1\nMCP_DC_SCALAR|Vp|0.5\n"
        "MCP_DC_SCALAR|Vm|0.5\nMCP_DC_SCALAR_COMPLETE|true\n"
    )
    assert len(reader.dc_result(frame)) == 7
    payload = result_payload()
    assert ActualDiagnosticResult.model_validate(payload).quality == "valid"
    payload["scalars"][5]["value"] = 0.8
    with pytest.raises(ValidationError):
        ActualDiagnosticResult.model_validate(payload)
    with pytest.raises(ValueError):
        reader.dc_result(frame.replace("MCP_DC_SCALAR|VDD|1", "MCP_DC_SCALAR|VDD|0.9"))


def test_fixed_ac_reader_bounds_and_order() -> None:
    reader = remote_reader()
    lines = ["MCP_AC_STAGE|file_open", "MCP_AC_STAGE|results_open", "MCP_AC_STAGE|ac_selected"]
    for signal, value in (("Vop", 2), ("Vom", -2), ("Vp", 0.5), ("Vm", -0.5)):
        lines.append(f"MCP_AC_VECTOR|{signal}|71|71")
        for index in range(71):
            frequency = 10 ** (1 + index / 10)
            lines.append(f"MCP_AC_POINT|{signal}|{index}|{frequency}|{value}|0")
    lines.append("MCP_AC_POINT_COMPLETE|true")
    points = reader.ac_result("\n".join(lines) + "\n")
    assert len(points) == 71
    assert all(abs(point["gain_v_per_v"] - 4) < 1e-12 for point in points)
    assert abs(points[-1]["frequency_hz"] - 1e8) < 1
    corrupt = list(lines)
    corrupt[4] = "MCP_AC_POINT|Vop|0|9|2|0"
    with pytest.raises(ValueError):
        reader.ac_result("\n".join(corrupt) + "\n")


def test_request_rejects_arbitrary_inputs() -> None:
    valid = {
        "revision_id": "wp14-copied-netlist-v1",
        "analysis": "dc",
        "operating_point_id": "candidate-320-702mv-v1",
        "output_id": "dc-node-scalars-v1",
    }
    assert ActualDiagnosticRequest.model_validate(valid).analysis == "dc"
    for changed in (
        {"analysis": "tran"},
        {"output_id": "ac-differential-spectrum-v1"},
        {"operating_point_id": "other"},
        {"revision_id": "other"},
        {"path": "/tmp/netlist"},
    ):
        with pytest.raises(ValidationError):
            ActualDiagnosticRequest.model_validate({**valid, **changed})


def test_remote_attempt_and_result_budget_replay(tmp_path: Path) -> None:
    reader = remote_reader()
    reader.os = SimpleNamespace(**vars(os))
    reader.os.rename = os.replace  # Linux target's os.rename replaces atomically.
    reader.JOBS = str(tmp_path)
    job = tmp_path / str(uuid4())
    job.mkdir()
    counter = tmp_path / "counter.json"
    counter.write_text(
        json.dumps({"campaign_id": "AUTO-PHASE-01", "count": 9, "result_reserved_bytes": 1048576}),
        encoding="ascii",
    )
    reader.reserve(str(job))
    assert json.loads(counter.read_text(encoding="ascii"))["count"] == 10
    with pytest.raises(ValueError, match="replay"):
        reader.reserve(str(job))
    counter.write_text(
        json.dumps(
            {"campaign_id": "AUTO-PHASE-01", "count": 10, "result_reserved_bytes": 5 * 1024**3}
        ),
        encoding="ascii",
    )
    other_job = tmp_path / str(uuid4())
    other_job.mkdir()
    with pytest.raises(ValueError, match="result budget"):
        reader.reserve(str(other_job))


def test_result_rejects_nonfinite_and_malformed_data() -> None:
    payload = result_payload()
    payload["scalars"][0]["value"] = math.nan
    with pytest.raises(ValidationError):
        ActualDiagnosticResult.model_validate(payload)
    payload = result_payload()
    del payload["applied_bias_values_v"]
    with pytest.raises(ValidationError):
        ActualDiagnosticResult.model_validate(payload)
    payload = result_payload()
    del payload["revision_id"]
    with pytest.raises(ValidationError):
        ActualDiagnosticResult.model_validate(payload)
    payload = result_payload()
    payload["quality"] = "valid"
    payload["extraction"] = "failed"
    with pytest.raises(ValidationError):
        ActualDiagnosticResult.model_validate(payload)


def test_prepare_accepts_only_submit_created_status_files(tmp_path: Path) -> None:
    reader = remote_reader()
    job = tmp_path / str(uuid4())
    job.mkdir()
    (job / "request.json").write_text(
        json.dumps(
            {
                "analysis": "dc",
                "revision_id": "wp14-copied-netlist-v1",
                "operating_point_id": "candidate-320-702mv-v1",
            }
        ),
        encoding="ascii",
    )
    for name in ("stage", "worker.stdout", "worker.stderr"):
        (job / name).write_text("", encoding="ascii")
    netlist = tmp_path / "fixed-netlist"
    netlist.write_text("fixed", encoding="ascii")
    reader.NETLIST = str(netlist)
    reader.snapshot = lambda: {"copy_sha256": COPY_SHA256}
    reader.prepare(str(job), "dc")
    assert (job / "before.json").is_file()
    assert (job / "profile.scs").is_file()
    other = tmp_path / str(uuid4())
    other.mkdir()
    (other / "unexpected").write_text("", encoding="ascii")
    with pytest.raises(ValueError, match="job path"):
        reader.prepare(str(other), "dc")
