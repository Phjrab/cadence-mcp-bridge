from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import Client
from pydantic import ValidationError

import cadence_mcp_bridge.__main__ as cli
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.designs import (
    REGISTRY_LIMIT,
    DesignRegistry,
    DesignRejected,
    load_design_registry,
    reference_registry,
    register_designs,
)
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.server import create_default_server, create_server
from cadence_mcp_bridge.service import CadenceBackend, CadenceService


def description() -> dict[str, Any]:
    value = reference_registry().model_dump(mode="json")
    profile = value["designs"][0]
    profile.update(
        design_id="example-amplifier",
        environment_id="example-lab",
        pdk_adapter_id="example-technology",
        binding={
            "library": "PrivateLibrary",
            "cell": "PrivateCell",
            "view": "schematic",
            "ade": {"kind": "ade_l", "state": "PrivateState"},
        },
    )
    return value


def write_registry(tmp_path: Path, value: dict[str, Any]) -> Path:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_registry_preserves_private_bindings_but_projection_is_bounded(tmp_path: Path) -> None:
    registry, data = load_design_registry(write_registry(tmp_path, description()))
    assert registry.designs[0].binding.library == "PrivateLibrary"
    result = registry.describe("example-amplifier")
    assert result.execution_authorized is False
    assert result.spec_evaluation == "not_evaluated"
    assert result.environment_binding_status == "not_resolved"
    assert result.pdk_adapter_status == "not_resolved"
    assert result.variable_ranges_status == "unqualified"
    assert result.allowed_analyses == ("dc", "ac", "tran")
    public = result.model_dump_json() + registry.listing().model_dump_json()
    for secret in ("PrivateLibrary", "PrivateCell", "PrivateState", '"binding":', "sha256"):
        assert secret not in public
    assert json.loads(data) == description()


@pytest.mark.parametrize("field", ["schema_version", "protected_source"])
@pytest.mark.parametrize("value", [False, 0, 1.0, "1", "true", None])
def test_contract_constants_reject_coercion(field: str, value: Any) -> None:
    payload = description()
    payload["designs"][0][field] = value
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("value", [True, 1.0, "1", 2])
def test_registry_version_is_exact_integer(value: Any) -> None:
    payload = description()
    payload["schema_version"] = value
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("field", ["design_id", "environment_id", "pdk_adapter_id"])
@pytest.mark.parametrize("value", ["../escape", "a;b", "a\n", "A", "a" * 65, "", 1])
def test_logical_ids_reject_paths_commands_unicode_and_oversize(field: str, value: Any) -> None:
    payload = description()
    payload["designs"][0][field] = value
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("field", ["library", "cell", "view"])
@pytest.mark.parametrize("value", ["/home/private", "a$(id)", "a\n", "한글", "a" * 65])
def test_private_binding_is_a_bounded_name(field: str, value: str) -> None:
    payload = description()
    payload["designs"][0]["binding"][field] = value
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "field", ["allowed_analyses", "allowed_variables", "allowed_measurements", "allowed_corners"]
)
def test_duplicate_allowlist_and_nonarray_rejected(field: str) -> None:
    payload = description()
    payload["designs"][0][field] = ["dc", "dc"]
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))
    payload["designs"][0][field] = "dc"
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("field", ["allowed_variables", "allowed_measurements", "allowed_corners"])
def test_allowlist_size_is_bounded(field: str) -> None:
    payload = description()
    payload["designs"][0][field] = [f"item-{number}" for number in range(33)]
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "field", ["execution_authorized", "qualified", "script", "netlist", "path", "variable_ranges"]
)
def test_registration_cannot_grant_execution_or_supply_code(field: str) -> None:
    payload = description()
    payload["designs"][0][field] = True
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))


def test_duplicates_limits_and_unknown_modes() -> None:
    payload = description()
    payload["designs"] *= 2
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))
    payload["designs"] = [
        {**payload["designs"][0], "design_id": f"design-{number}"} for number in range(17)
    ]
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))
    payload = description()
    payload["designs"][0]["allowed_analyses"] = ["monte-carlo"]
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))
    payload = description()
    payload["designs"][0]["work_copy_policy"] = "source_write"
    with pytest.raises(ValidationError):
        DesignRegistry.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "data",
    [b'{"schema_version":1,"schema_version":1,"designs":[]}', b"NaN", b"\xff", b"[" * 2000],
)
def test_malformed_json_has_closed_error(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "secret-name.json"
    path.write_bytes(data)
    with pytest.raises(DesignRejected, match="^design_registry_invalid$"):
        load_design_registry(path)


def test_missing_directory_and_oversized_inputs_rejected(tmp_path: Path) -> None:
    for path in (tmp_path, tmp_path / "missing"):
        with pytest.raises(DesignRejected):
            load_design_registry(path)
    path = tmp_path / "huge.json"
    path.write_bytes(b" " * (REGISTRY_LIMIT + 1))
    with pytest.raises(DesignRejected):
        load_design_registry(path)


def test_symlink_input_rejected(tmp_path: Path) -> None:
    path = write_registry(tmp_path, description())
    link = tmp_path / "link.json"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("OS account cannot create symbolic links")
    with pytest.raises(DesignRejected):
        load_design_registry(link)


def test_symlink_gate_without_os_link_privileges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_registry(tmp_path, description())
    monkeypatch.setattr(Path, "is_symlink", lambda _: True)
    with pytest.raises(DesignRejected):
        load_design_registry(path)


def test_registration_is_exclusive_and_byte_preserving(tmp_path: Path) -> None:
    source = write_registry(tmp_path, description())
    output = tmp_path / "registered.json"
    result = register_designs(source, output)
    assert result["execution_authorized"] is False
    assert output.read_bytes() == source.read_bytes()
    with pytest.raises(FileExistsError):
        register_designs(source, output)
    assert output.read_bytes() == source.read_bytes()


def test_cli_schema_validate_register_and_closed_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["design", "schema"]) == 0
    assert json.loads(capsys.readouterr().out)["additionalProperties"] is False
    source = write_registry(tmp_path, description())
    assert cli.main(["design", "validate", "--registry", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid_description"
    output = tmp_path / "registered.json"
    args = ["design", "register", "--registry", str(source), "--output", str(output)]
    assert cli.main(args) == 0
    assert json.loads(capsys.readouterr().out)["execution_authorized"] is False
    assert cli.main(args) == 1
    assert "PrivateLibrary" not in capsys.readouterr().out
    source.write_text('{"password":"very-private"}', encoding="utf-8")
    assert cli.main(["design", "validate", "--registry", str(source)]) == 1
    error = capsys.readouterr().out
    assert "very-private" not in error
    assert str(source) not in error


def test_operator_settings_load_once_and_fail_without_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = write_registry(tmp_path, description())
    monkeypatch.setenv("CADENCE_MCP_DESIGN_REGISTRY_PATH", str(source))
    assert BridgeConfig().design_registry_path == source
    assert cli.main(["config-check"]) == 0
    capsys.readouterr()
    server = create_default_server()
    assert server is not None
    source.write_text("bad", encoding="utf-8")
    assert cli.main(["config-check"]) == 1
    assert capsys.readouterr().out == "configuration: invalid design registry\n"
    with pytest.raises(ConfigurationError, match="Configured design registry is invalid"):
        create_default_server()


class NoRemote:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"Design introspection contacted the backend: {name}")


@pytest.mark.asyncio
async def test_introspection_uses_snapshot_and_never_contacts_backend(tmp_path: Path) -> None:
    source = write_registry(tmp_path, description())
    registry, _ = load_design_registry(source)
    service = CadenceService(cast(CadenceBackend, NoRemote()), registry)
    source.write_text("bad", encoding="utf-8")
    async with Client(create_server(service)) as client:
        listing = await client.call_tool("cadence_list_designs")
        assert (await client.call_tool("cadence_list_designs", {"path": "/private"})).is_error
        result = await client.call_tool(
            "cadence_describe_design", {"design_id": "example-amplifier"}
        )
        assert not listing.is_error and not result.is_error
        public = str(result.structured_content)
        assert "PrivateLibrary" not in public and "PrivateState" not in public
        assert cast(dict[str, Any], result.structured_content)["execution_authorized"] is False
        unknown = await client.call_tool("cadence_describe_design", {"design_id": "unknown"})
        assert unknown.is_error
        for arguments in (
            {"design_id": "../escape"},
            {"design_id": 1},
            {"design_id": "example-amplifier", "library": "Other"},
            {"design_id": "example-amplifier", "path": "/home/private"},
        ):
            assert (await client.call_tool("cadence_describe_design", arguments)).is_error
    with pytest.raises(InvalidInputError):
        await service.describe_design("EXAMPLE-AMPLIFIER")


@pytest.mark.asyncio
async def test_explicit_empty_registry_does_not_restore_reference_design() -> None:
    service = CadenceService(
        cast(CadenceBackend, NoRemote()), DesignRegistry(schema_version=1, designs=())
    )
    assert (await service.list_designs()).designs == ()
    with pytest.raises(InvalidInputError):
        await service.describe_design("reference-differential-amplifier-tb2")


@pytest.mark.asyncio
async def test_custom_registration_does_not_widen_fixed_execution_allowlist() -> None:
    registry = DesignRegistry.model_validate_json(json.dumps(description()))
    service = CadenceService(cast(CadenceBackend, NoRemote()), registry)
    with pytest.raises(InvalidInputError):
        await service.get_profile("example-amplifier")
    assert reference_registry().designs[0].protected_source is True


def test_public_schema_and_fictional_example_are_current() -> None:
    root = Path(__file__).resolve().parents[2]
    assert json.loads((root / "docs/schemas/design-registry-v1.schema.json").read_bytes()) == (
        DesignRegistry.model_json_schema()
    )
    registry, _ = load_design_registry(root / "docs/examples/design-registry-v1.fictional.json")
    assert registry.describe("example-amplifier").execution_authorized is False


def test_largest_registered_projection_fits_existing_transport_limit() -> None:
    payload = description()
    profile = payload["designs"][0]
    for field in ("allowed_variables", "allowed_measurements", "allowed_corners"):
        profile[field] = ["a" * 61 + f"-{number:02d}" for number in range(32)]
    profile["environment_id"] = "e" * 64
    profile["pdk_adapter_id"] = "p" * 64
    payload["designs"] = [
        {**profile, "design_id": "d" * 61 + f"-{number:02d}"} for number in range(16)
    ]
    registry = DesignRegistry.model_validate_json(json.dumps(payload))
    assert len(registry.listing().model_dump_json().encode()) < REGISTRY_LIMIT
    assert len(registry.describe(payload["designs"][0]["design_id"]).model_dump_json().encode()) < (
        REGISTRY_LIMIT
    )


def test_reference_binding_matches_existing_validated_metadata() -> None:
    from cadence_mcp_bridge.profiles import ACTUAL_PROFILE_ID, get_profile

    reference = reference_registry().designs[0]
    actual = get_profile(ACTUAL_PROFILE_ID)
    assert actual.ade is not None
    assert reference.binding.library == actual.ade.library
    assert reference.binding.cell == actual.ade.cell
    assert reference.binding.view == actual.ade.view
    assert reference.binding.ade.state == actual.ade.state
    assert reference.allowed_analyses == ("dc", "ac", "tran")
    assert reference_registry().describe(reference.design_id).qualification_status == "unqualified"
