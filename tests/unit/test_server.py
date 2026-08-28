from __future__ import annotations

import math
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

import pytest
from mcp import Client

from cadence_mcp_bridge.errors import AuthenticationError
from cadence_mcp_bridge.models import (
    CellList,
    CellViewInspection,
    HealthReport,
    JobLogTail,
    JobResult,
    JobState,
    JobStatus,
    JobSummary,
    LibraryList,
    LibraryMetadata,
    LicenseEnvironment,
    ProfileVariables,
    ToolAvailability,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.write_models import (
    DesignWritePlan,
    DesignWriteValidationResult,
    WriteConfirmation,
)


def write_plan() -> DesignWritePlan:
    return DesignWritePlan(
        policy_version=2,
        plan_id="mcp-cellview-property-v2",
        plan_sha256="a" * 64,
        source="MyDesignLib/Differential_Amplifier_TB2/schematic",
        target="MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic",
        backup="MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic",
        preserved_target="MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic",
        operation="set_cellview_property",
        property_name="mcpMutationTest",
        old_value=None,
        proposed_value="validated-v1",
        affected_objects=1,
        original_library_mutations=0,
        destructive=False,
        source_exists=True,
        source_artifact_present=False,
        target_exists=False,
        backup_exists=False,
        preserved_target_exists=True,
        ready=True,
        confirmation="APPROVE_MCP_WRITE_VALIDATED_V2",
    )


def write_result(validation_id: UUID) -> DesignWriteValidationResult:
    return DesignWriteValidationResult(
        validation_id=validation_id,
        plan_id="mcp-cellview-property-v2",
        plan_sha256="a" * 64,
        source="MyDesignLib/Differential_Amplifier_TB2/schematic",
        target="MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2/schematic",
        backup="MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP/schematic",
        preserved_target="MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic",
        operation="set_cellview_property",
        property_name="mcpMutationTest",
        old_value=None,
        proposed_value="validated-v1",
        affected_objects=1,
        original_library_mutations=0,
        destructive=False,
        copy_verified=True,
        dry_run_unchanged=True,
        backup_verified=True,
        apply_verified=True,
        rollback_verified=True,
        source_unchanged=True,
        preserved_target_unchanged=True,
        topology_unchanged=True,
        baseline_fingerprint="a" * 64,
        rollback_fingerprint="a" * 64,
        audit_recorded=True,
        sequence=(
            "source_verify",
            "copy",
            "baseline",
            "dry_run",
            "dry_run_unchanged",
            "backup",
            "apply",
            "verify_apply",
            "source_unchanged_before_rollback",
            "rollback",
            "verify_rollback",
            "source_unchanged",
            "complete",
        ),
    )


class FakeBackend:
    def __init__(self) -> None:
        self.failure: Exception | None = None

    async def health(self) -> HealthReport:
        if self.failure is not None:
            raise self.failure
        return HealthReport(
            ssh="ok",
            remote_host="cadence",
            remote_user="buet",
            remote_root_accessible=True,
            virtuoso=ToolAvailability(available=True, version="IC6.1.5.500.15"),
            spectre=ToolAvailability(available=True, version="12.1.0.347.isr3"),
            ocean=ToolAvailability(available=True),
            license_env=LicenseEnvironment(CDS_LIC_FILE="SET"),
            runner_version="test",
        )

    async def submit_smoke(self, job_id: UUID) -> JobStatus:
        return self._status(job_id)

    async def status(self, job_id: UUID) -> JobStatus:
        return self._status(job_id, JobState.RUNNING)

    async def log_tail(
        self, job_id: UUID, stream: Literal["stdout", "stderr"], lines: int = 100
    ) -> JobLogTail:
        return JobLogTail(
            job_id=job_id,
            stream=stream,
            lines_requested=lines,
            text="bounded log",
            original_bytes=11,
            returned_bytes=11,
        )

    async def result(self, job_id: UUID) -> JobResult:
        return JobResult(
            job_id=job_id,
            state=JobState.SUCCEEDED,
            exit_code=0,
            summary=JobSummary(text="complete", errors=0, warnings=0, notices=1),
        )

    async def cancel(self, job_id: UUID) -> JobStatus:
        return self._status(job_id, JobState.CANCELLING)

    async def list_libraries(self) -> LibraryList:
        return LibraryList(libraries=(LibraryMetadata(name="MyFirstDesign", allowed_cell_count=1),))

    async def list_cells(self, library: str) -> CellList:
        return CellList(library=library, cells=("NOT_gate",))

    async def inspect_cellview(self, library: str, cell: str, view: str) -> CellViewInspection:
        return CellViewInspection(library=library, cell=cell, view=view, exists=True)

    async def submit_profile(
        self,
        job_id: UUID,
        profile_id: str,
        corner: str,
        variables: ProfileVariables,
    ) -> JobStatus:
        return self._status(job_id).model_copy(update={"profile": profile_id})

    async def design_write_plan(self) -> DesignWritePlan:
        return write_plan()

    async def execute_design_write_validation(
        self, validation_id: UUID, confirmation: WriteConfirmation
    ) -> DesignWriteValidationResult:
        assert confirmation == "APPROVE_MCP_WRITE_VALIDATED_V2"
        return write_result(validation_id)

    @staticmethod
    def _status(job_id: UUID, state: JobState = JobState.QUEUED) -> JobStatus:
        now = datetime.now(UTC)
        return JobStatus(
            job_id=job_id,
            state=state,
            profile="spectre-smoke",
            submitted_at=now,
            updated_at=now,
        )


@pytest.mark.asyncio
async def test_in_memory_client_lists_exact_typed_tools() -> None:
    server = create_server(CadenceService(FakeBackend()))

    async with Client(server) as client:
        listing = await client.list_tools()

    tools = {tool.name: tool for tool in listing.tools}
    assert set(tools) == {
        "cadence_health",
        "cadence_submit_smoke",
        "cadence_job_status",
        "cadence_job_log_tail",
        "cadence_job_result",
        "cadence_cancel_job",
        "cadence_list_libraries",
        "cadence_list_cells",
        "cadence_inspect_cellview",
        "cadence_list_profiles",
        "cadence_get_profile",
        "cadence_submit_profile",
        "cadence_get_measurement_contract",
        "cadence_measure_dc_power",
        "cadence_measure_offset",
        "cadence_measure_settling",
        "cadence_measure_fft_metrics",
        "cadence_measure_linearity",
        "cadence_compare_corner_results",
        "cadence_summarize_monte_carlo",
        "cadence_design_write_plan",
        "cadence_execute_design_write_validation",
    }
    assert all(tool.output_schema is not None for tool in tools.values())
    assert tools["cadence_health"].input_schema["properties"] == {}
    assert tools["cadence_submit_smoke"].input_schema["properties"] == {}
    assert tools["cadence_list_libraries"].input_schema["properties"] == {}
    assert tools["cadence_list_profiles"].input_schema["properties"] == {}
    assert tools["cadence_design_write_plan"].input_schema["properties"] == {}
    confirmation_schema = tools["cadence_execute_design_write_validation"].input_schema[
        "properties"
    ]["confirmation"]
    assert "APPROVE_MCP_WRITE_VALIDATED_V2" in str(confirmation_schema)
    assert tools["cadence_get_profile"].input_schema["properties"]["profile_id"]["enum"] == [
        "fixture-rc-transient",
        "actual-differential-amplifier-tb2-transient",
    ]
    assert tools["cadence_submit_profile"].input_schema["properties"]["corner"]["enum"] == [
        "nominal",
        "NN",
    ]
    for name in ("cadence_job_status", "cadence_job_result", "cadence_cancel_job"):
        assert set(tools[name].input_schema["properties"]) == {"job_id"}
    assert set(tools["cadence_job_log_tail"].input_schema["properties"]) == {
        "job_id",
        "stream",
        "lines",
    }
    log_properties = tools["cadence_job_log_tail"].input_schema["properties"]
    assert log_properties["stream"]["enum"] == ["stdout", "stderr"]
    assert log_properties["lines"]["minimum"] == 1
    assert log_properties["lines"]["maximum"] == 200
    assert "pattern" in tools["cadence_job_status"].input_schema["properties"]["job_id"]
    assert set(tools["cadence_list_cells"].input_schema["properties"]) == {"library"}
    assert set(tools["cadence_inspect_cellview"].input_schema["properties"]) == {
        "library",
        "cell",
        "view",
    }
    read_only = {
        name
        for name, tool in tools.items()
        if tool.annotations is not None and tool.annotations.read_only_hint
    }
    assert read_only == {
        "cadence_health",
        "cadence_job_status",
        "cadence_job_log_tail",
        "cadence_job_result",
        "cadence_list_libraries",
        "cadence_list_cells",
        "cadence_inspect_cellview",
        "cadence_list_profiles",
        "cadence_get_profile",
        "cadence_get_measurement_contract",
        "cadence_measure_dc_power",
        "cadence_measure_offset",
        "cadence_measure_settling",
        "cadence_measure_fft_metrics",
        "cadence_measure_linearity",
        "cadence_compare_corner_results",
        "cadence_summarize_monte_carlo",
        "cadence_design_write_plan",
    }
    destructive = {
        name
        for name, tool in tools.items()
        if tool.annotations is not None and tool.annotations.destructive_hint
    }
    assert destructive == {
        "cadence_cancel_job",
        "cadence_execute_design_write_validation",
    }
    assert tools["cadence_health"].annotations is not None
    assert tools["cadence_health"].annotations.read_only_hint is True
    assert tools["cadence_submit_smoke"].annotations is not None
    assert tools["cadence_submit_smoke"].annotations.read_only_hint is False
    assert all(
        tool.annotations is not None and tool.annotations.open_world_hint is False
        for tool in tools.values()
    )


@pytest.mark.asyncio
async def test_submit_returns_without_polling_for_completion() -> None:
    server = create_server(CadenceService(FakeBackend()))

    async with Client(server) as client:
        response = await client.call_tool(
            "cadence_submit_smoke",
            read_timeout_seconds=0.5,
        )

    assert response.is_error is False
    assert cast(dict[str, Any], response.structured_content)["state"] == "queued"


@pytest.mark.asyncio
async def test_in_memory_client_calls_all_tools_successfully() -> None:
    server = create_server(CadenceService(FakeBackend()))

    async with Client(server) as client:
        health = await client.call_tool("cadence_health")
        submit = await client.call_tool("cadence_submit_smoke")
        submitted = cast(dict[str, Any], submit.structured_content)
        job_id = cast(str, submitted["job_id"])
        status = await client.call_tool("cadence_job_status", {"job_id": job_id})
        log_tail = await client.call_tool(
            "cadence_job_log_tail",
            {"job_id": job_id, "stream": "stdout", "lines": 20},
        )
        result = await client.call_tool("cadence_job_result", {"job_id": job_id})
        cancel = await client.call_tool("cadence_cancel_job", {"job_id": job_id})
        libraries = await client.call_tool("cadence_list_libraries")
        cells = await client.call_tool("cadence_list_cells", {"library": "MyFirstDesign"})
        cellview = await client.call_tool(
            "cadence_inspect_cellview",
            {"library": "MyFirstDesign", "cell": "NOT_gate", "view": "schematic"},
        )
        profiles = await client.call_tool("cadence_list_profiles")
        profile = await client.call_tool(
            "cadence_get_profile", {"profile_id": "fixture-rc-transient"}
        )
        profile_submit = await client.call_tool(
            "cadence_submit_profile",
            {
                "profile_id": "fixture-rc-transient",
                "corner": "nominal",
                "variables": {
                    "resistance_ohm": 1000.0,
                    "capacitance_f": 1e-12,
                    "stop_time_s": 1e-9,
                },
            },
        )
        actual_profile = await client.call_tool(
            "cadence_get_profile",
            {"profile_id": "actual-differential-amplifier-tb2-transient"},
        )
        actual_submit = await client.call_tool(
            "cadence_submit_profile",
            {
                "profile_id": "actual-differential-amplifier-tb2-transient",
                "corner": "NN",
                "variables": {},
            },
        )

    assert cast(dict[str, Any], health.structured_content)["ssh"] == "ok"
    assert cast(dict[str, Any], status.structured_content)["state"] == "running"
    assert cast(dict[str, Any], log_tail.structured_content)["text"] == "bounded log"
    assert cast(dict[str, Any], result.structured_content)["exit_code"] == 0
    assert cast(dict[str, Any], cancel.structured_content)["state"] == "cancelling"
    assert cast(dict[str, Any], libraries.structured_content)["allowlist_enforced"] is True
    assert cast(dict[str, Any], cells.structured_content)["cells"] == ["NOT_gate"]
    assert cast(dict[str, Any], cellview.structured_content)["exists"] is True
    assert cast(dict[str, Any], profiles.structured_content)["registry_version"] == 1
    assert cast(dict[str, Any], profile.structured_content)["classification"] == "fixture"
    assert cast(dict[str, Any], profile_submit.structured_content)["state"] == "queued"
    assert cast(dict[str, Any], actual_profile.structured_content)["classification"] == "actual"
    assert cast(dict[str, Any], actual_submit.structured_content)["state"] == "queued"
    assert all(
        not item.is_error
        for item in (
            health,
            submit,
            status,
            log_tail,
            result,
            cancel,
            libraries,
            cells,
            cellview,
            profiles,
            profile,
            profile_submit,
            actual_profile,
            actual_submit,
        )
    )


@pytest.mark.asyncio
async def test_in_memory_client_calls_all_measurement_tools_successfully() -> None:
    server = create_server(CadenceService(FakeBackend()))
    sample_count = 1024
    samples = [
        math.sin(2.0 * math.pi * 64 * index / sample_count)
        + 0.01 * math.sin(2.0 * math.pi * 128 * index / sample_count)
        + 0.001 * math.sin(2.0 * math.pi * 7 * index / sample_count)
        + 0.001 * math.sin(2.0 * math.pi * 11 * index / sample_count)
        for index in range(sample_count)
    ]

    async with Client(server) as client:
        contract = await client.call_tool(
            "cadence_get_measurement_contract", {"contract_id": "adc-synthetic-v1"}
        )
        power = await client.call_tool(
            "cadence_measure_dc_power",
            {
                "request": {
                    "contract_id": "adc-synthetic-v1",
                    "supply_voltage_v": [1.8, 1.8],
                    "supply_current_a": [0.001, 0.001],
                }
            },
        )
        offset = await client.call_tool(
            "cadence_measure_offset",
            {
                "request": {
                    "contract_id": "adc-synthetic-v1",
                    "observed_voltage_v": [0.01, -0.01],
                }
            },
        )
        settling = await client.call_tool(
            "cadence_measure_settling",
            {
                "request": {
                    "contract_id": "adc-synthetic-v1",
                    "time_s": [0.0, 1e-6, 2e-6],
                    "output_voltage_v": [0.0, 0.995, 1.0],
                }
            },
        )
        fft = await client.call_tool(
            "cadence_measure_fft_metrics",
            {"request": {"contract_id": "adc-synthetic-v1", "samples_v": samples}},
        )
        linearity = await client.call_tool(
            "cadence_measure_linearity",
            {
                "request": {
                    "contract_id": "adc-synthetic-v1",
                    "transition_voltage_v": [code / 8 for code in range(1, 8)],
                }
            },
        )
        corners = await client.call_tool(
            "cadence_compare_corner_results",
            {
                "request": {
                    "contract_id": "adc-synthetic-v1",
                    "values": {"NN": 1.0, "FF": 1.1, "SS": 0.9},
                    "unit": "V",
                }
            },
        )
        monte_carlo = await client.call_tool(
            "cadence_summarize_monte_carlo",
            {
                "request": {
                    "contract_id": "adc-synthetic-v1",
                    "values": [1.0, 2.0, 3.0, 4.0, 5.0],
                    "unit": "mV",
                }
            },
        )

    results = (contract, power, offset, settling, fft, linearity, corners, monte_carlo)
    assert all(not result.is_error for result in results)
    assert cast(dict[str, Any], contract.structured_content)["version"] == 1
    assert cast(dict[str, Any], power.structured_content)["unit"] == "W"
    assert cast(dict[str, Any], settling.structured_content)["settled"] is True
    assert cast(dict[str, Any], fft.structured_content)["fundamental_bin"] == 64
    assert cast(dict[str, Any], linearity.structured_content)["method"] == "endpoint"
    assert cast(dict[str, Any], corners.structured_content)["reference_corner"] == "NN"
    assert cast(dict[str, Any], monte_carlo.structured_content)["count"] == 5


@pytest.mark.asyncio
async def test_measurement_tool_rejects_request_without_contract() -> None:
    server = create_server(CadenceService(FakeBackend()))

    async with Client(server) as client:
        result = await client.call_tool(
            "cadence_measure_dc_power",
            {
                "request": {
                    "supply_voltage_v": [1.8, 1.8],
                    "supply_current_a": [0.001, 0.001],
                }
            },
        )

    assert result.is_error


@pytest.mark.asyncio
async def test_in_memory_client_calls_fixed_design_write_tools() -> None:
    server = create_server(CadenceService(FakeBackend()))

    async with Client(server) as client:
        plan = await client.call_tool("cadence_design_write_plan")
        result = await client.call_tool(
            "cadence_execute_design_write_validation",
            {"confirmation": "APPROVE_MCP_WRITE_VALIDATED_V2"},
        )

    assert not plan.is_error
    assert not result.is_error
    assert cast(dict[str, Any], plan.structured_content)["ready"] is True
    payload = cast(dict[str, Any], result.structured_content)
    assert payload["apply_verified"] is True
    assert payload["rollback_verified"] is True
    assert payload["source_unchanged"] is True


@pytest.mark.asyncio
async def test_discovery_rejects_out_of_allowlist_before_backend() -> None:
    server = create_server(CadenceService(FakeBackend()))

    async with Client(server) as client:
        response = await client.call_tool("cadence_list_cells", {"library": "gpdk090"})

    content = cast(dict[str, Any], response.structured_content)
    assert response.is_error is True
    assert content["error"]["code"] == "invalid_input"


@pytest.mark.asyncio
async def test_bridge_error_becomes_stable_error_envelope() -> None:
    backend = FakeBackend()
    backend.failure = AuthenticationError("SSH authentication failed")
    server = create_server(CadenceService(backend))

    async with Client(server) as client:
        response = await client.call_tool("cadence_health")

    content = cast(dict[str, Any], response.structured_content)
    assert content == {
        "ok": False,
        "error": {
            "code": "authentication_failed",
            "message": "SSH authentication failed",
            "retryable": False,
            "details": {},
        },
    }
    assert response.is_error is True


@pytest.mark.asyncio
async def test_invalid_job_id_becomes_stable_error_envelope() -> None:
    server = create_server(CadenceService(FakeBackend()))

    async with Client(server) as client:
        response = await client.call_tool("cadence_job_status", {"job_id": "../x"})

    content = cast(dict[str, Any], response.structured_content)
    assert content["ok"] is False
    assert content["error"]["code"] == "invalid_input"


def test_stdio_startup_has_no_banner_on_stdout() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "cadence_mcp_bridge"],
        input=b"",
        capture_output=True,
        check=False,
        timeout=10,
    )

    assert completed.returncode == 0
    assert completed.stdout == b""
