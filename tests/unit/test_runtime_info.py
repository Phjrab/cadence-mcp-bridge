"""Local runtime metadata must describe loading without IO or implied authority."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import Client

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.analog_registry import reference_analog_registry
from cadence_mcp_bridge.designs import (
    reference_analysis_registry,
    reference_contract_registry,
    reference_measurement_registry,
    reference_registry,
)
from cadence_mcp_bridge.pdk_reference import reference_pdk_registry
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService
from cadence_mcp_bridge.specification_registry import reference_specification_registry
from cadence_mcp_bridge.sweep_registry import DesignSweepRegistry
from cadence_mcp_bridge.variable_contracts import canonical_digest


class NoBackendCalls:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Unexpected backend access: {name}")


def backend() -> CadenceBackend:
    return cast(CadenceBackend, NoBackendCalls())


@pytest.mark.asyncio
async def test_default_snapshot_is_local_bounded_and_not_qualification(tmp_path: Path) -> None:
    service = CadenceService(backend())
    report = await service.runtime_info()
    assert report.bridge_version == __version__
    assert report.designs.source == report.pdks.source == "builtin_reference"
    assert report.designs.schema_version == 4 and report.pdks.schema_version == 2
    assert report.designs.semantic_sha256 == canonical_digest(reference_measurement_registry())
    assert report.journals.analysis == "platform_default"
    assert report.journals.sweep == "package_relative_default"
    assert not report.journals.health_assessed
    assert not report.remote_contact
    assert not report.execution_authority_assessed
    assert not report.environment_qualification_assessed
    assert len(report.model_dump_json()) < 2048
    assert str(tmp_path) not in report.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("version", range(1, 8))
async def test_loaded_versions_and_explicit_journals_never_touch_files(
    version: int, tmp_path: Path
) -> None:
    v4 = reference_measurement_registry()
    v5 = DesignSweepRegistry(**{**v4.model_dump(), "schema_version": 5})
    registries = (
        reference_registry(),
        reference_contract_registry(),
        reference_analysis_registry(),
        v4,
        v5,
        reference_analog_registry(),
        reference_specification_registry(),
    )
    registry = registries[version - 1]
    pdks = reference_pdk_registry()
    analysis = tmp_path / "private-license-server-analyses.sqlite3"
    sweep = tmp_path / "private-host-sweeps.sqlite3"
    service = CadenceService(
        backend(), registry, pdks=pdks, analysis_journal=analysis, sweep_journal=sweep
    )
    # The existing sweep supervisor initializes its database at service startup.
    # The new observation must preserve those exact bytes, not claim startup is IO-free.
    sweep_before = sweep.read_bytes()
    # Runtime reads must not reread registry/configuration files, journal files or backend.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "read_bytes", lambda _: pytest.fail("unexpected filesystem read"))
        patch.setattr(Path, "open", lambda *a, **kw: pytest.fail("unexpected filesystem open"))
        reports = await asyncio.gather(*(service.runtime_info() for _ in range(10)))
    report = reports[0]
    assert all(r == report for r in reports)
    assert report.designs.schema_version == version
    assert report.designs.semantic_sha256 == canonical_digest(registry)
    assert report.pdks.semantic_sha256 == canonical_digest(pdks)
    assert report.designs.source == report.pdks.source == "operator_supplied"
    assert report.journals.analysis == report.journals.sweep == "operator_supplied"
    assert not analysis.exists() and sweep.read_bytes() == sweep_before
    assert "private-" not in report.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("analysis,sweep", [(False, True), (True, False)])
async def test_independent_journal_selection(analysis: bool, sweep: bool, tmp_path: Path) -> None:
    service = CadenceService(
        backend(),
        analysis_journal=tmp_path / "a" if analysis else None,
        sweep_journal=tmp_path / "s" if sweep else None,
    )
    report = await service.runtime_info()
    assert (report.journals.analysis == "operator_supplied") is analysis
    assert (report.journals.sweep == "operator_supplied") is sweep


@pytest.mark.asyncio
async def test_mcp_schema_strict_inputs_safe_annotations_and_repeat() -> None:
    service = CadenceService(backend())
    async with Client(create_server(service)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        tool = tools["cadence_runtime_info"]
        assert tool.input_schema["properties"] == {}
        assert tool.input_schema["additionalProperties"] is False
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint and tool.annotations.idempotent_hint
        assert not tool.annotations.destructive_hint and not tool.annotations.open_world_hint
        first = await client.call_tool(tool.name)
        repeat = await client.call_tool(tool.name)
        assert not first.is_error and first.structured_content == repeat.structured_content
        assert first.structured_content == (await service.runtime_info()).model_dump(mode="json")
        for arguments in (
            {"path": "../private"},
            {"command": "whoami"},
            {"request": {}},
            {"design_id": "unknown"},
            {"reload": True},
        ):
            rejected = await client.call_tool(tool.name, arguments)
            assert rejected.is_error
            assert "../private" not in str(rejected.content)
