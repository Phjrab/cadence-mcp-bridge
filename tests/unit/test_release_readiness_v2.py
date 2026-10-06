"""Readiness audit rejects misleading baselines; no technical pass grants publication."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "release_readiness_v2", ROOT / "scripts/verify-release-readiness.py"
)
assert spec is not None and spec.loader is not None
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def fixture(tmp_path: Path) -> Path:
    # Copy only public audit inputs, not operator/private or remote artifacts.
    names = [
        "pyproject.toml",
        "uv.lock",
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
        "src/cadence_mcp_bridge/server.py",
        "src/cadence_mcp_bridge/__init__.py",
        "src/cadence_mcp_bridge/models.py",
        "src/cadence_mcp_bridge/measurement_models.py",
        "docs/contracts/MCP_V1_COMPATIBILITY_SNAPSHOT.json",
        "docs/contracts/MCP_RELEASE_READINESS_V2_SNAPSHOT.json",
        "docs/contracts/MCP_RUNTIME_CONFIG_V1_SNAPSHOT.json",
        "docs/contracts/MCP_POWER_V1_SNAPSHOT.json",
        "docs/contracts/MCP_MEAS_CONTRACT_V2_SNAPSHOT.json",
        "docs/contracts/MCP_BANDWIDTH_STUDY_V1_SNAPSHOT.json",
        "docs/contracts/MCP_SLEW_STUDY_V1_SNAPSHOT.json",
        "docs/contracts/MCP_OFFSET_STUDY_V1_SNAPSHOT.json",
        "docs/contracts/MCP_AMPLIFIER_SWEEP_V1_SNAPSHOT.json",
        "docs/contracts/MCP_AMPLIFIER_SPEC_V1_SNAPSHOT.json",
        *(f"docs/schemas/design-registry-v{i}.schema.json" for i in range(1, 9)),
    ]
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    return tmp_path


def update(path: Path, key: str, value: Any) -> None:
    data = json.loads(path.read_bytes())
    data[key] = value
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.asyncio
async def test_current_contract_audit_does_not_claim_app_legal_or_publication() -> None:
    result = audit.inspect(ROOT, await audit.inventory())
    assert result["technical_contract_audit"] == "PASS"
    assert result["mcp_tools"] == 85 and result["legacy_declarations_preserved"] == 22
    assert result["registry_schemas_preserved"] == 7
    assert not result["publication_authorized"] and not result["remote_contact"]
    assert result["runtime_service_calls"] == result["new_simulations"] == 0
    assert "CLAUDE_REAL_CLIENT_UNVERIFIED" in result["unverified_external_gates"]
    assert (
        "imported_planning_LEGAL_REVIEW_REQUIRED_for_repository_bundle"
        in (result["unverified_external_gates"])
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "baseline,key,value",
    [
        ("MCP_AMPLIFIER_SPEC_V1_SNAPSHOT.json", "tools", {}),
        ("MCP_AMPLIFIER_SPEC_V1_SNAPSHOT.json", "schema_version", True),
        ("MCP_AMPLIFIER_SPEC_V1_SNAPSHOT.json", "source_main", "0" * 40),
        ("MCP_AMPLIFIER_SWEEP_V1_SNAPSHOT.json", "tools", {}),
        ("MCP_AMPLIFIER_SWEEP_V1_SNAPSHOT.json", "schema_version", True),
        ("MCP_AMPLIFIER_SWEEP_V1_SNAPSHOT.json", "source_main", "0" * 40),
        ("MCP_V1_COMPATIBILITY_SNAPSHOT.json", "tools", {}),
        ("MCP_V1_COMPATIBILITY_SNAPSHOT.json", "tag_commit", "0" * 40),
        ("MCP_V1_COMPATIBILITY_SNAPSHOT.json", "schema_version", True),
        ("MCP_RELEASE_READINESS_V2_SNAPSHOT.json", "tools", {}),
        ("MCP_RELEASE_READINESS_V2_SNAPSHOT.json", "source_main", "0" * 40),
        ("MCP_RELEASE_READINESS_V2_SNAPSHOT.json", "schema_version", True),
        ("MCP_RELEASE_READINESS_V2_SNAPSHOT.json", "legacy_model_canonical_lf_sha256", {}),
        ("MCP_RUNTIME_CONFIG_V1_SNAPSHOT.json", "tools", {}),
        ("MCP_RUNTIME_CONFIG_V1_SNAPSHOT.json", "source_main", "0" * 40),
        ("MCP_RUNTIME_CONFIG_V1_SNAPSHOT.json", "schema_version", True),
        ("MCP_POWER_V1_SNAPSHOT.json", "tools", {}),
        ("MCP_POWER_V1_SNAPSHOT.json", "schema_version", True),
        ("MCP_MEAS_CONTRACT_V2_SNAPSHOT.json", "tools", {}),
        ("MCP_MEAS_CONTRACT_V2_SNAPSHOT.json", "schema_version", True),
        ("MCP_BANDWIDTH_STUDY_V1_SNAPSHOT.json", "tools", {}),
        ("MCP_BANDWIDTH_STUDY_V1_SNAPSHOT.json", "schema_version", True),
        ("MCP_BANDWIDTH_STUDY_V1_SNAPSHOT.json", "source_main", "0" * 40),
        ("MCP_OFFSET_STUDY_V1_SNAPSHOT.json", "tools", {}),
        ("MCP_OFFSET_STUDY_V1_SNAPSHOT.json", "schema_version", True),
        ("MCP_OFFSET_STUDY_V1_SNAPSHOT.json", "source_main", "0" * 40),
        ("MCP_SLEW_STUDY_V1_SNAPSHOT.json", "tools", {}),
        ("MCP_SLEW_STUDY_V1_SNAPSHOT.json", "schema_version", True),
        ("MCP_SLEW_STUDY_V1_SNAPSHOT.json", "source_main", "0" * 40),
    ],
)
async def test_empty_substituted_and_bad_baselines_rejected(
    tmp_path: Path,
    baseline: str,
    key: str,
    value: Any,
) -> None:
    project = fixture(tmp_path)
    update(project / "docs/contracts" / baseline, key, value)
    with pytest.raises(ValueError):
        audit.inspect(project, await audit.inventory())


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["input", "output", "annotation", "removed", "extra"])
async def test_full_schema_drift_requires_review(change: str, tmp_path: Path) -> None:
    project = fixture(tmp_path)
    schemas = await audit.inventory()
    if change == "removed":
        schemas.pop("cadence_health")
    elif change == "extra":
        schemas["arbitrary-shell"] = schemas["cadence_health"]
    elif change == "input":
        schemas["cadence_health"]["inputSchema"]["properties"]["command"] = {"type": "string"}
    elif change == "output":
        schemas["cadence_health"]["outputSchema"] = {}
    else:
        schemas["cadence_health"]["annotations"]["readOnlyHint"] = False
    with pytest.raises(ValueError):
        audit.inspect(project, schemas)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["version", "runtime", "license", "notice", "model", "registry"])
async def test_version_license_model_and_schema_drift_rejected(
    tmp_path: Path,
    change: str,
) -> None:
    project = fixture(tmp_path)
    if change == "version":
        path = project / "pyproject.toml"
        path.write_text(path.read_text().replace('version = "1.0.0"', 'version = "1.1.0"'))
    elif change == "runtime":
        path = project / "src/cadence_mcp_bridge/__init__.py"
        path.write_text(path.read_text().replace('"1.0.0"', '"1.1.0"'))
    elif change == "license":
        (project / "LICENSE").write_text("altered grant")
    elif change == "notice":
        (project / "NOTICE").write_bytes(b"")
    elif change == "model":
        path = project / "src/cadence_mcp_bridge/models.py"
        path.write_bytes(path.read_bytes() + b"\n# material model drift\n")
    else:
        path = project / "docs/schemas/design-registry-v7.schema.json"
        update(path, "properties", {})
    with pytest.raises(ValueError):
        audit.inspect(project, await audit.inventory())


@pytest.mark.asyncio
async def test_removed_legacy_declaration_and_unsafe_duplicate(tmp_path: Path) -> None:
    project = fixture(tmp_path)
    path = project / "src/cadence_mcp_bridge/server.py"
    path.write_text(path.read_text().replace("job_id: JobIdInput", "job_id: str", 1))
    with pytest.raises(ValueError):
        audit.inspect(project, await audit.inventory())
    source = '@server.tool(name="x")\ndef x(a: str) -> str: pass\n'
    with pytest.raises(ValueError):
        audit.declarations(source + source)


@pytest.mark.parametrize("payload", ['{"a":1,"a":2}', '{"a":NaN}', "[]"])
def test_ambiguous_json_baseline_rejected(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "audit.json"
    path.write_text(payload)
    with pytest.raises(ValueError):
        audit.read_json(path)


def test_oversized_baseline_rejected(tmp_path: Path) -> None:
    path = tmp_path / "audit.json"
    path.write_bytes(b" " * (2 * 1024**2 + 1))
    with pytest.raises(ValueError):
        audit.read_json(path)
