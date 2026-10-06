"""Local contract audit. Passing never authorizes publication or qualifies a Desktop app."""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any, cast

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.analog_registry import DesignAnalogRegistry
from cadence_mcp_bridge.designs import (
    DesignAnalysisRegistry,
    DesignContractRegistry,
    DesignMeasurementRegistry,
    DesignRegistry,
)
from cadence_mcp_bridge.measurement_bindings import DesignPowerSpecificationRegistry
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.specification_registry import DesignSpecificationRegistry
from cadence_mcp_bridge.sweep_registry import DesignSweepRegistry

ROOT = Path(__file__).resolve().parents[1]
TAG_COMMIT = "8a0d44fab90e2095cc39322baef60fc09d741cd6"
SNAPSHOT_COMMIT = "4ea17e2641f316ec0899c9c91f8bea97c6b4086f"
RUNTIME_CONFIG_COMMIT = "b015b7151239e5613f8960fa896b8422b0b680aa"
APACHE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def read_json(path: Path) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate audit field")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise ValueError("nonfinite audit data")

    if path.is_symlink() or not path.is_file():
        raise ValueError("regular audit file required")
    with path.open("rb") as stream:
        data = stream.read(2 * 1024**2 + 1)
    if len(data) > 2 * 1024**2:
        raise ValueError("audit file exceeds bound")
    value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError("audit object required")
    return value


def declarations(source: str) -> dict[str, dict[str, str]]:
    """Parse declarations without evaluating project source or expressions."""
    result = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                not isinstance(decorator, ast.Call)
                or not isinstance(decorator.func, ast.Attribute)
                or not isinstance(decorator.func.value, ast.Name)
                or decorator.func.value.id != "server"
                or decorator.func.attr != "tool"
            ):
                continue
            name = next((k.value for k in decorator.keywords if k.arg == "name"), None)
            if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
                raise ValueError("literal tool identity required")
            if name.value in result or node.returns is None:
                raise ValueError("duplicate or untyped tool declaration")
            result[name.value] = {
                "parameters": ast.unparse(node.args),
                "returns": ast.unparse(node.returns),
            }
    return result


class _NoServiceCalls:
    def __getattr__(self, _: str) -> Any:
        raise AssertionError("Contract audit must not call service or transport")


async def inventory() -> dict[str, dict[str, Any]]:
    # Register typed closures only. No service constructor, SweepStore, backend,
    # tool call or Cadence transport is needed to reflect SDK schemas.
    server = create_server(cast(CadenceService, _NoServiceCalls()))
    tools = await server.list_tools()
    result = {t.name: t.model_dump(mode="json", by_alias=True) for t in tools}
    if len(result) != len(tools):
        raise ValueError("duplicate MCP tool identity")
    return result


def inspect(project: Path, schemas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Check current contracts, not live app/remote/legal or publication authority."""
    legacy = read_json(project / "docs/contracts/MCP_V1_COMPATIBILITY_SNAPSHOT.json")
    snapshot = read_json(project / "docs/contracts/MCP_RELEASE_READINESS_V2_SNAPSHOT.json")
    addition = read_json(project / "docs/contracts/MCP_RUNTIME_CONFIG_V1_SNAPSHOT.json")
    power_addition = read_json(project / "docs/contracts/MCP_POWER_V1_SNAPSHOT.json")
    binding_addition = read_json(project / "docs/contracts/MCP_MEAS_CONTRACT_V2_SNAPSHOT.json")
    bandwidth_addition = read_json(project / "docs/contracts/MCP_BANDWIDTH_STUDY_V1_SNAPSHOT.json")
    if (
        type(bandwidth_addition.get("schema_version")) is not int
        or bandwidth_addition.get("schema_version") != 1
        or bandwidth_addition.get("source_main") != "d97d9934341d382c1131ee1f5d61ab8cc75ace38"
        or set(bandwidth_addition.get("tools", {})) != {"cadence_bandwidth_study_result"}
        or any(schemas.get(n) != t for n, t in bandwidth_addition["tools"].items())
    ):
        raise ValueError("unreviewed bandwidth study schema drift")
    if (
        type(binding_addition.get("schema_version")) is not int
        or binding_addition.get("schema_version") != 1
        or binding_addition.get("source_main") != "0e85a12804d550279a9da0c5ebe9f92acabcc62e"
        or set(binding_addition.get("tools", {}))
        != {
            "cadence_measurement_catalog",
            "cadence_evaluate_specification_v2",
            "cadence_runtime_info_v2",
        }
        or any(schemas.get(n) != t for n, t in binding_addition["tools"].items())
    ):
        raise ValueError("unreviewed versioned measurement binding schema drift")
    if (
        type(power_addition.get("schema_version")) is not int
        or power_addition.get("schema_version") != 1
        or power_addition.get("source_main") != "8009060edc076ccacb371c45d8f8fb3a335b150f"
        or set(power_addition.get("tools", {}))
        != {"cadence_describe_power_measurement", "cadence_power_measurement_result"}
        or any(schemas.get(n) != t for n, t in power_addition["tools"].items())
    ):
        raise ValueError("unreviewed power schema drift")
    if (
        type(legacy.get("schema_version")) is not int
        or legacy["schema_version"] != 1
        or legacy.get("release_tag") != "v1.0.0"
        or legacy.get("tag_commit") != TAG_COMMIT
        or not isinstance(legacy.get("tools"), dict)
        or len(legacy["tools"]) != 22
    ):
        raise ValueError("historical baseline is empty, substituted or invalid")
    if (
        type(snapshot.get("schema_version")) is not int
        or snapshot["schema_version"] != 1
        or snapshot.get("source_main") != SNAPSHOT_COMMIT
        or not isinstance(snapshot.get("tools"), dict)
        or len(snapshot["tools"]) != 69
        or any(schemas.get(name) != tool for name, tool in snapshot["tools"].items())
    ):
        raise ValueError("current full tool schema inventory differs from reviewed snapshot")
    if (
        type(addition.get("schema_version")) is not int
        or addition["schema_version"] != 1
        or addition.get("source_main") != RUNTIME_CONFIG_COMMIT
        or not isinstance(addition.get("tools"), dict)
        or set(addition["tools"]) != {"cadence_runtime_info"}
        or set(schemas)
        != (
            set(snapshot["tools"])
            | set(addition["tools"])
            | set(power_addition["tools"])
            | set(binding_addition["tools"])
            | set(bandwidth_addition["tools"])
        )
        or any(schemas.get(name) != tool for name, tool in addition["tools"].items())
    ):
        raise ValueError("unreviewed additive tool or runtime metadata schema drift")
    source = (project / "src/cadence_mcp_bridge/server.py").read_text(encoding="utf-8")
    current = declarations(source)
    if set(current) != set(schemas) or any(current.get(n) != d for n, d in legacy["tools"].items()):
        raise ValueError("legacy tool declaration changed or was removed")
    expected_models = snapshot.get("legacy_model_canonical_lf_sha256")
    if not isinstance(expected_models, dict) or set(expected_models) != {
        "models.py",
        "measurement_models.py",
    }:
        raise ValueError("legacy shared model baseline is invalid")
    for name, expected in expected_models.items():
        data = (project / "src/cadence_mcp_bridge" / name).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("legacy shared model content changed")
    registry_models = (
        DesignRegistry,
        DesignContractRegistry,
        DesignAnalysisRegistry,
        DesignMeasurementRegistry,
        DesignSweepRegistry,
        DesignAnalogRegistry,
        DesignSpecificationRegistry,
        DesignPowerSpecificationRegistry,
    )
    for version, model in enumerate(registry_models, 1):
        if read_json(project / f"docs/schemas/design-registry-v{version}.schema.json") != (
            model.model_json_schema()
        ):
            raise ValueError("published registry schema changed")
    metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((project / "uv.lock").read_text(encoding="utf-8"))
    versions = [p["version"] for p in lock["package"] if p["name"] == "cadence-mcp-bridge"]
    runtime = ast.parse(
        (project / "src/cadence_mcp_bridge/__init__.py").read_text(encoding="utf-8")
    )
    runtime_versions = [
        n.value.value
        for n in runtime.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets)
        and isinstance(n.value, ast.Constant)
    ]
    if (
        versions != [metadata["project"]["version"]]
        or runtime_versions != versions
        or versions != [__version__]
    ):
        raise ValueError("source, runtime, imported package and lock versions differ")
    if metadata["project"].get("license") != "Apache-2.0" or set(
        metadata["project"].get("license-files", [])
    ) != {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"}:
        raise ValueError("modern license metadata differs")
    if hashlib.sha256((project / "LICENSE").read_bytes()).hexdigest() != APACHE_SHA256:
        raise ValueError("canonical Apache license differs")
    for notice in ("NOTICE", "THIRD_PARTY_NOTICES.md"):
        if not (project / notice).read_bytes().strip():
            raise ValueError("required notice is absent or empty")
    return {
        "audit_version": 1,
        "technical_contract_audit": "PASS",
        "mcp_tools": len(schemas),
        "legacy_declarations_preserved": 22,
        "legacy_models_preserved": 2,
        "registry_schemas_preserved": 7,
        "registry_schemas": 8,
        "package_version": __version__,
        "license": "Apache-2.0",
        "conditional_semver_recommendation": "v1.1.0",
        "comparison_scope": "declarations_shared_models_current_schemas_not_universal_behavior",
        "publication_authorized": False,
        "unverified_external_gates": [
            "exact_release_candidate_and_version_qualification",
            "CLAUDE_REAL_CLIENT_UNVERIFIED",
            "full_Codex_application_schema_version_lifecycle_NOT_TESTED",
            "imported_planning_LEGAL_REVIEW_REQUIRED_for_repository_bundle",
            "explicit_exact_publication_authority",
        ],
        "runtime_service_calls": 0,
        "remote_contact": False,
        "new_simulations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        result = inspect(ROOT, asyncio.run(inventory()))
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"technical_contract_audit": "FAIL", "publication_authorized": False}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
