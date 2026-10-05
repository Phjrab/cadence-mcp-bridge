from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from mcp import Client
from pydantic import ValidationError
from test_analyses import NativeBackend, selection, submission

import cadence_mcp_bridge.__main__ as cli
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.pdk_adapters import (
    LIMIT,
    PdkAdapter,
    PdkRegistry,
    PdkRejected,
    load_pdk_registry,
    register_pdk_adapters,
)
from cadence_mcp_bridge.pdk_reference import REFERENCE_ID, reference_pdk_registry
from cadence_mcp_bridge.server import create_default_server, create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService

ROOT = Path(__file__).resolve().parents[2]
DESIGN = "reference-differential-amplifier-tb2"


def fixture() -> dict[str, Any]:
    return json.loads((ROOT / "docs/examples/pdk-registry-v2.fictional.json").read_bytes())


def test_public_contracts_and_history() -> None:
    schema = json.loads((ROOT / "docs/schemas/pdk-registry-v2.schema.json").read_bytes())
    assert schema == PdkRegistry.model_json_schema()
    for path in (
        "docs/examples/pdk-registry-v2.fictional.json",
        "docs/technology/gpdk090-runtime-regression-v2.json",
    ):
        registry, data = load_pdk_registry(ROOT / path)
        Draft202012Validator(schema).validate(json.loads(data))
        assert len(registry.adapters) == 1
    old = ROOT / "docs/technology/gpdk090-v4-6-regression.json"
    with pytest.raises(PdkRejected):
        load_pdk_registry(old)
    historical = json.loads(old.read_bytes())
    assert historical["lifecycle"] == "draft" and not historical["execution_authorized"]


@pytest.mark.parametrize(
    "update",
    [
        {"adapter_id": "other-reference"},
        {"technology_id": "other-pdk"},
        {"environment_ids": ["other-host"]},
        {"process_corner_ids": ["tt"]},
        {"rc_corner_ids": ["nominal"]},
        {"binding_sha256": "0" * 64},
        {"binding_ref": "other-binding"},
        {"capabilities": []},
        {
            "binding_kind": "unqualified",
            "binding_ref": None,
            "binding_sha256": None,
            "capabilities": [],
        },
        {"model_path": "/private/model"},
    ],
)
def test_reserved_reference_cannot_be_rebound(update: dict[str, Any]) -> None:
    raw = reference_pdk_registry().model_dump(mode="json")["adapters"][0]
    raw.update(update)
    with pytest.raises(ValidationError):
        PdkAdapter.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "update",
    [
        {"schema_version": True},
        {"schema_version": 2.0},
        {"schema_version": "2"},
        {"adapter_id": "../pdk"},
        {"adapter_id": "pdk\n"},
        {"environment_ids": ["x;run"]},
        {"process_corner_ids": ["tt", "tt"]},
        {"rc_corner_ids": ["/private"]},
        {"binding_ref": "something"},
        {"binding_sha256": "0" * 64},
        {"execution_authorized": True},
        {
            "capabilities": [
                {
                    "capability_id": "native-dc",
                    "status": "fixed_native_compatibility",
                    "evidence_ref": "made-up",
                }
            ]
        },
        {
            "capabilities": [
                {"capability_id": "eval-skill", "status": "unqualified", "evidence_ref": None}
            ]
        },
        {
            "capabilities": [
                {"capability_id": "native-dc", "status": "observed", "evidence_ref": None}
            ]
        },
    ],
)
def test_closed_unqualified_contract(update: dict[str, Any]) -> None:
    raw = fixture()["adapters"][0]
    raw.update(update)
    with pytest.raises(ValidationError):
        PdkAdapter.model_validate_json(json.dumps(raw))


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":2,"schema_version":2,"adapters":[]}',
        b'{"schema_version":2,"adapters":[],"extra":NaN}',
        b"[]",
        b"\xff",
        b"[" * 2000,
        b" " * (LIMIT + 1),
        b'{"schema_version":true,"adapters":[]}',
        b'{"schema_version":2.0,"adapters":[]}',
    ],
    ids=["duplicate", "nonfinite", "array", "utf8", "depth", "oversize", "bool", "float"],
)
def test_bounded_snapshot_closed_errors(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "pdk.json"
    path.write_bytes(raw)
    with pytest.raises(PdkRejected, match="^pdk_registry_invalid$"):
        load_pdk_registry(path)


def test_duplicates_and_capacity(tmp_path: Path) -> None:
    for payload in (
        {"schema_version": 2, "adapters": fixture()["adapters"] * 2},
        {
            "schema_version": 2,
            "adapters": [dict(fixture()["adapters"][0], adapter_id=f"pdk-{i}") for i in range(17)],
        },
    ):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(payload))
        with pytest.raises(PdkRejected):
            load_pdk_registry(path)
    raw = fixture()
    raw["adapters"][0]["capabilities"] *= 2
    with pytest.raises(ValidationError):
        PdkRegistry.model_validate_json(json.dumps(raw))


def test_exclusive_registration_snapshot_and_cli(tmp_path: Path, capsys: Any) -> None:
    source, target = tmp_path / "source.json", tmp_path / "target.json"
    source.write_bytes(json.dumps(fixture(), indent=3).encode())
    assert cli.main(["pdk", "schema"]) == 0
    assert json.loads(capsys.readouterr().out) == PdkRegistry.model_json_schema()
    assert cli.main(["pdk", "validate", "--registry", str(source)]) == 0
    assert not json.loads(capsys.readouterr().out)["execution_authorized"]
    assert cli.main(["pdk", "register", "--registry", str(source), "--output", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "registered_local_only"
    assert source.read_bytes() == target.read_bytes()
    registry, _ = load_pdk_registry(target)
    source.write_text("invalid-private-data")
    assert registry.adapters[0].adapter_id == "example-pdk"
    with pytest.raises(FileExistsError):
        register_pdk_adapters(target, target)
    assert cli.main(["pdk", "validate", "--registry", str(source)]) == 1
    output = capsys.readouterr().out
    assert "pdk_registry_invalid" in output and "invalid-private-data" not in output
    with pytest.raises(ValidationError):
        registry.adapters[0].adapter_id = "mutated"


def test_symlink_input_and_existing_output_fail_closed(tmp_path: Path) -> None:
    source, link = tmp_path / "source.json", tmp_path / "link.json"
    source.write_text(json.dumps(fixture()))
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("OS does not permit symlinks")
    with pytest.raises(PdkRejected):
        load_pdk_registry(link)
    with pytest.raises(FileExistsError):
        register_pdk_adapters(source, link)
    assert source.read_text() == json.dumps(fixture())


@pytest.mark.asyncio
async def test_configured_missing_adapter_blocks_before_admission_or_transport(
    tmp_path: Path,
) -> None:
    backend = NativeBackend()
    default = CadenceService(
        cast(CadenceBackend, backend), analysis_journal=tmp_path / "old.sqlite3"
    )
    sent = await submission(default)
    pdks = PdkRegistry(schema_version=2, adapters=())
    journal = tmp_path / "absent.sqlite3"
    blocked = CadenceService(cast(CadenceBackend, backend), pdks=pdks, analysis_journal=journal)
    plan = await blocked.plan_analysis(selection())
    assert not plan.dispatch_eligible and plan.plan_hash == sent.expected_plan_hash
    assert (await blocked.design_pdk_status(DESIGN)).status == "not_registered"
    with pytest.raises(InvalidInputError):
        await blocked.submit_analysis(sent)
    assert not journal.exists() and backend.submissions == [] and backend.reads == []


@pytest.mark.asyncio
async def test_old_plan_admission_and_restart_survive_exact_reference(tmp_path: Path) -> None:
    backend, journal = NativeBackend(), tmp_path / "journal.sqlite3"
    old = CadenceService(cast(CadenceBackend, backend), analysis_journal=journal)
    sent = await submission(old)
    await old.submit_analysis(sent)
    path = tmp_path / "reference.json"
    path.write_text(reference_pdk_registry().model_dump_json())
    registry, _ = load_pdk_registry(path)
    new = CadenceService(cast(CadenceBackend, backend), pdks=registry, analysis_journal=journal)
    assert (await new.plan_analysis(selection())).plan_hash == sent.expected_plan_hash
    await new.submit_analysis(sent)
    assert len(backend.submissions) == 1 and len(backend.reads) == 1
    assert (await new.design_pdk_status(DESIGN)).status == "fixed_native_compatibility"


@pytest.mark.asyncio
async def test_logical_resolution_and_mcp_closed_projection(tmp_path: Path) -> None:
    backend = NativeBackend()
    raw = reference_pdk_registry().model_dump(mode="json")
    raw["adapters"].extend(fixture()["adapters"])
    registry = PdkRegistry.model_validate_json(json.dumps(raw))
    svc = CadenceService(
        cast(CadenceBackend, backend), pdks=registry, analysis_journal=tmp_path / "unused.sqlite3"
    )
    assert registry.resolve("example", "example-pdk", "example-lab").status == "unqualified"
    assert registry.resolve("example", REFERENCE_ID, "example-lab").status == "environment_mismatch"
    async with Client(create_server(svc)) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert len(tools) == 66
        for name in (
            "cadence_list_pdk_adapters",
            "cadence_describe_pdk_adapter",
            "cadence_design_pdk_status",
        ):
            assert tools[name].input_schema["additionalProperties"] is False
            assert tools[name].annotations.read_only_hint is True
        listed = await client.call_tool("cadence_list_pdk_adapters")
        assert listed.structured_content == registry.listing().model_dump(mode="json")
        for adapter in registry.adapters:
            value = await client.call_tool(
                "cadence_describe_pdk_adapter", {"adapter_id": adapter.adapter_id}
            )
            assert not value.is_error
            assert value.structured_content == registry.describe(adapter.adapter_id).model_dump(
                mode="json"
            )
            assert not any(
                k in str(value.structured_content)
                for k in (
                    "binding_ref",
                    "binding_sha256",
                    "environment_ids",
                    "model_path",
                    "license",
                )
            )
        for name, arguments in (
            ("cadence_list_pdk_adapters", {"path": "/private"}),
            ("cadence_describe_pdk_adapter", {"adapter_id": "../x"}),
            ("cadence_describe_pdk_adapter", {"adapter_id": REFERENCE_ID, "execute": True}),
            ("cadence_describe_pdk_adapter", {"adapter_id": 1}),
            ("cadence_describe_pdk_adapter", {"adapter_id": "unknown"}),
            ("cadence_design_pdk_status", {"design_id": "unknown"}),
            ("cadence_design_pdk_status", {"design_id": DESIGN, "adapter_id": "example-pdk"}),
        ):
            assert (await client.call_tool(name, arguments)).is_error
        value = await client.call_tool("cadence_design_pdk_status", {"design_id": DESIGN})
        assert value.structured_content["generic_execution_qualified"] is False
    assert backend.submissions == backend.reads == backend.results == []


def test_startup_and_config_check_fail_closed(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(fixture()))
    monkeypatch.setenv("CADENCE_MCP_PDK_REGISTRY_PATH", str(path))
    create_default_server()
    assert cli.main(["config-check"]) == 0
    capsys.readouterr()
    path.write_text("private-invalid")
    with pytest.raises(ConfigurationError, match="Configured PDK registry is invalid"):
        create_default_server()
    assert cli.main(["config-check"]) == 1
    assert "private-invalid" not in capsys.readouterr().out
