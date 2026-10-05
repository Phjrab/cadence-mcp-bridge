from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cadence_mcp_bridge import __main__ as cli
from cadence_mcp_bridge import environments, onboarding
from cadence_mcp_bridge.config import BridgeConfig

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples" / "onboarding"


@pytest.fixture
def contracts(tmp_path: Path) -> tuple[Path, Path, Path]:
    paths = tuple(tmp_path / name for name in ("environment.json", "designs.json", "pdks.json"))
    for path in paths:
        path.write_bytes((EXAMPLES / path.name).read_bytes())
    return paths  # type: ignore[return-value]


def test_coherent_example_is_description_only(contracts: tuple[Path, Path, Path]) -> None:
    result = onboarding.verify_contracts(*contracts)
    assert result["status"] == "consistent_local_contracts"
    assert result["remote_contact"] is False
    assert result["execution_authorized"] is False
    assert result["generic_execution_qualified"] is False
    assert result["spec_evaluation"] == "not_evaluated"
    text = json.dumps(result)
    assert "ExampleLib" not in text and "/srv" not in text and "fictional-host" not in text


@pytest.mark.parametrize(
    ("target", "field", "value", "reason"),
    [
        (0, "environment_id", "other-env", "design_environment_mismatch"),
        (0, "requested_capabilities", ["dc"], "environment_analysis_mismatch"),
        (2, "adapter_id", "other-pdk", "pdk_adapter_missing"),
        (2, "environment_ids", ["other-env"], "pdk_environment_mismatch"),
        (2, "process_corner_ids", [], "pdk_corner_mismatch"),
    ],
    ids=["design-env", "analysis", "missing-pdk", "pdk-env", "corner"],
)
def test_cross_contract_mismatches_fail_before_transport(
    contracts: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    target: int,
    field: str,
    value: Any,
    reason: str,
) -> None:
    data = json.loads(contracts[target].read_bytes())
    selected = data["adapters"][0] if target == 2 else data
    selected[field] = value
    contracts[target].write_text(json.dumps(data), encoding="utf-8")
    remote = MagicMock()
    monkeypatch.setattr(onboarding, "qualify_environment", remote)
    with pytest.raises(onboarding.OnboardingRejected, match=reason):
        onboarding.verify_contracts(*contracts, remote_preflight=True)
    remote.assert_not_called()


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize(
    "bad",
    [b'{"schema_version":1,"schema_version":1}', b"NaN", b"[", b"x" * 65537],
    ids=["duplicate", "nan", "syntax", "size"],
)
def test_closed_invalid_contract_errors(
    contracts: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str], index: int, bad: bytes
) -> None:
    contracts[index].write_bytes(bad)
    assert cli.main(verify_args(contracts)) == 1
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "status": "blocked",
        "reason": "onboarding_contract_invalid",
        "execution_authorized": False,
    }


def verify_args(paths: tuple[Path, Path, Path]) -> list[str]:
    return [
        "verify",
        "--profile",
        str(paths[0]),
        "--design-registry",
        str(paths[1]),
        "--pdk-registry",
        str(paths[2]),
    ]


def test_remote_is_explicit_and_hash_bound(
    contracts: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = MagicMock(
        return_value={"status": "qualified_environment_preflight", "execution_authorized": False}
    )
    monkeypatch.setattr(onboarding, "qualify_environment", remote)
    onboarding.verify_contracts(*contracts)
    remote.assert_not_called()
    result = onboarding.verify_contracts(*contracts, remote_preflight=True)
    remote.assert_called_once_with(
        contracts[0], expected_profile_sha256=hashlib.sha256(contracts[0].read_bytes()).hexdigest()
    )
    assert result["remote_contact"] is True and result["execution_authorized"] is False


def test_changed_profile_denied_before_ssh(
    contracts: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = MagicMock()
    monkeypatch.setattr(environments.subprocess, "Popen", remote)
    with pytest.raises(ValueError, match="changed"):
        environments.qualify_environment(contracts[0], expected_profile_sha256="0" * 64)
    remote.assert_not_called()


@pytest.mark.parametrize("format", ["codex", "mcp-json", "claude-desktop"])
def test_export_roundtrip_explicit_defaults_and_exclusive_write(
    contracts: tuple[Path, Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, format: Any
) -> None:
    # Quotes, spaces and Unicode must round-trip without TOML/script injection.
    folder = tmp_path / "한글 \" quote' path"
    if '"' in folder.name and __import__("sys").platform == "win32":
        folder = tmp_path / "한글 quote' path"
    folder.mkdir()
    paths = tuple(folder / p.name for p in contracts)
    for source, destination in zip(contracts, paths, strict=True):
        destination.write_bytes(source.read_bytes())
    monkeypatch.setenv("CADENCE_MCP_REMOTE_ROOT", "/inherited/unreviewed")
    monkeypatch.setenv("CADENCE_MCP_SSH_ALIAS", "unapproved-host")
    journal, output = folder / "journal.sqlite3", folder / "client.conf"
    before = [p.read_bytes() for p in paths]
    result = onboarding.export_client_config(*paths, journal, output, format=format)
    assert result["status"] == "exported_local_only" and result["journal_created"] is False
    assert not journal.exists()
    assert [p.read_bytes() for p in paths] == before
    config = (
        tomllib.loads(output.read_text(encoding="utf-8"))
        if format == "codex"
        else json.loads(output.read_bytes())
    )
    server = config["mcp_servers" if format == "codex" else "mcpServers"]["cadence-mcp-bridge"]
    assert server["args"] == ["-m", "cadence_mcp_bridge", "serve"]
    env = server["env"]
    assert env["CADENCE_MCP_DESIGN_REGISTRY_PATH"] == str(paths[1].resolve())
    assert env["CADENCE_MCP_PDK_REGISTRY_PATH"] == str(paths[2].resolve())
    assert env["CADENCE_MCP_ANALYSIS_JOURNAL_PATH"] == str(journal.resolve())
    assert env["CADENCE_MCP_SSH_ALIAS"] == "cadence-vm"
    assert env["CADENCE_MCP_REMOTE_ROOT"] == "/home/buet/cds_work/.cadence_mcp"
    checked = subprocess.run(
        [server["command"], *server["args"][:-1], "config-check"],
        env={**os.environ, **env},
        cwd=tmp_path,
        capture_output=True,
        timeout=20,
    )
    assert checked.returncode == 0, checked.stderr.decode("utf-8")
    if format == "codex":
        assert server["default_tools_approval_mode"] == "writes"
        assert server["tools"]["cadence_submit_analysis"]["approval_mode"] == "prompt"
        assert all(v["approval_mode"] == "prompt" for v in server["tools"].values())
    previous = output.read_bytes()
    with pytest.raises(FileExistsError):
        onboarding.export_client_config(*paths, journal, output, format=format)
    assert output.read_bytes() == previous


@pytest.mark.parametrize("collision", ["profile", "design", "pdk", "journal", "parent"])
def test_export_does_not_overwrite_inputs_or_bad_output(
    contracts: tuple[Path, Path, Path], tmp_path: Path, collision: str
) -> None:
    journal = tmp_path / "admissions.sqlite3"
    outputs = {
        "profile": contracts[0],
        "design": contracts[1],
        "pdk": contracts[2],
        "journal": journal,
        "parent": tmp_path / "absent" / "client.toml",
    }
    before = [p.read_bytes() for p in contracts]
    with pytest.raises(onboarding.OnboardingRejected):
        onboarding.export_client_config(*contracts, journal, outputs[collision], format="codex")
    assert [p.read_bytes() for p in contracts] == before
    assert not journal.exists()


def test_doctor_checks_explicit_catalogs_and_redacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private = tmp_path / "private-missing.json"
    monkeypatch.setenv("CADENCE_MCP_PDK_REGISTRY_PATH", str(private))
    monkeypatch.setattr(cli.shutil, "which", lambda _: "ssh.exe")
    assert cli.main(["doctor"]) == 1
    text = capsys.readouterr().out
    assert str(private) not in text
    assert json.loads(text)["configured_registries_valid"] is False


def test_legacy_design_versions_verify_without_inherited_analysis_authority(
    contracts: tuple[Path, Path, Path],
) -> None:
    data = json.loads(contracts[1].read_bytes())
    for version in (2, 1):
        older = copy.deepcopy(data)
        older["schema_version"] = version
        older.pop("analysis_contracts")
        if version == 1:
            older.pop("variable_sets")
            older.pop("range_reviews")
        contracts[1].write_text(json.dumps(older), encoding="utf-8")
        result = onboarding.verify_contracts(*contracts)
        assert result["designs"][0]["analysis_contract_count"] == 0  # type: ignore[index]


def test_configured_registry_validation_preserves_default_compatibility() -> None:
    assert onboarding.configured_registries_valid(
        BridgeConfig(design_registry_path=None, pdk_registry_path=None)
    )


@pytest.mark.parametrize("value", ["2", "01", "1.0", "true", "0", "-1", " 1"])
def test_export_concurrency_is_fixed_even_from_environment(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("CADENCE_MCP_DEFAULT_CONCURRENCY", value)
    with pytest.raises(ValueError):
        BridgeConfig()


def test_symlink_input_or_output_denied(contracts: tuple[Path, Path, Path], tmp_path: Path) -> None:
    link = tmp_path / "link"
    try:
        link.symlink_to(contracts[0])
    except OSError:
        pytest.skip("OS does not permit unprivileged symlinks")
    with pytest.raises(onboarding.OnboardingRejected):
        onboarding.verify_contracts(link, *contracts[1:])
    with pytest.raises(onboarding.OnboardingRejected):
        onboarding.export_client_config(
            *contracts, tmp_path / "journal.sqlite3", link, format="codex"
        )
