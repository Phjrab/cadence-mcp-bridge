"""Synthetic context routing and fail-closed operator isolation, no Cadence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from cadence_mcp_bridge import __main__ as cli
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.config import BridgeConfig, OperatorTransport
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.onboarding import export_client_config
from cadence_mcp_bridge.runtime_context import (
    RuntimeRejected,
    create_operator_service,
    load_runtime,
    resource_lock,
    runtime_observation,
    select_context,
)
from cadence_mcp_bridge.server import create_default_server
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

EXAMPLES = Path(__file__).resolve().parents[2] / "docs/examples/onboarding"


def make_settings(tmp_path: Path, *, shared: bool = False) -> Path:
    bindings = []
    for number in (1, 2):
        env = json.loads((EXAMPLES / "environment.json").read_bytes())
        env["environment_id"] = f"lab-{number}"
        env["ssh_alias"] = f"operator-{number}"
        env["host"]["hostname"] = "same-host" if shared else f"host-{number}"
        design = json.loads((EXAMPLES / "designs.json").read_bytes())["designs"][0]
        design.update(design_id=f"design-{number}", environment_id=f"lab-{number}")
        design["binding"]["cell"] = f"TestCell{number}"
        pdk = json.loads((EXAMPLES / "pdks.json").read_bytes())
        pdk["adapters"][0]["environment_ids"] = [f"lab-{number}"]
        paths = [tmp_path / f"{name}-{number}.json" for name in ("environment", "design", "pdk")]
        for path, data in zip(
            paths, (env, {"schema_version": 1, "designs": [design]}, pdk), strict=True
        ):
            path.write_text(json.dumps(data), encoding="utf-8")
        binding = {
            "context_id": f"context-{number}",
            "environment_profile": str(paths[0]),
            "environment_sha256": hashlib.sha256(paths[0].read_bytes()).hexdigest(),
            "design_registry": str(paths[1]),
            "design_sha256": hashlib.sha256(paths[1].read_bytes()).hexdigest(),
            "pdk_registry": str(paths[2]),
            "pdk_sha256": hashlib.sha256(paths[2].read_bytes()).hexdigest(),
            "runner_sha256": "b" * 64,
            "authority_ref": "unverified-operator-grant",
            "ledger_ref": "preserve-shared-ledger",
            "analysis_journal": str(tmp_path / f"analysis-{number}.sqlite3"),
            "sweep_journal": str(tmp_path / f"sweep-{number}.sqlite3"),
        }
        bindings.append(binding)
    path = tmp_path / "runtime.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "resource_state_root": str(tmp_path),
                "contexts": bindings,
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Path:
    return make_settings(tmp_path)


def config(path: Path | None, identity: str | None = "context-1") -> BridgeConfig:
    return BridgeConfig(
        runtime_mode="operator", runtime_settings_path=path, runtime_context_id=identity
    )


def test_resolved_backends_and_immutable_selection(settings: Path) -> None:
    first, second = load_runtime(settings)
    spy = MagicMock()
    service = create_operator_service(config(settings), spy)
    assert service.context == first
    spy.assert_called_once_with(first.transport)
    assert first.resolve("design-1") is first
    assert first.transport.ssh_alias == "operator-1"
    assert second.transport.ssh_alias == "operator-2"
    assert first.transport.runner_path == "/srv/project/.cadence_mcp/bin/cadence-runner"
    assert first.resource_domain_sha256 != second.resource_domain_sha256
    with pytest.raises(FrozenInstanceError):
        first.transport.ssh_alias = "attacker"  # type: ignore[misc]
    with pytest.raises(InvalidInputError):
        first.resolve("design-2")
    settings.write_text("{}", encoding="utf-8")
    # Restart rejects changed settings; a live context remains its admitted snapshot.
    assert service.context == first
    with pytest.raises(RuntimeRejected):
        create_operator_service(config(settings), spy)
    assert spy.call_count == 1


def test_shared_resource_aliases_lock_and_preserve_ledgers(tmp_path: Path) -> None:
    first, second = load_runtime(make_settings(tmp_path, shared=True))
    assert first.resource_domain_sha256 == second.resource_domain_sha256
    assert first.lock_path == second.lock_path
    baseline = tmp_path / "existing-ledger.json"
    baseline.write_bytes(b'{"attempts":82,"reserved_bytes":9798942720}')
    before = baseline.read_bytes()
    with resource_lock(first), pytest.raises(RuntimeRejected), resource_lock(second):
        pytest.fail("A second context obtained the shared EDA lock")
    with resource_lock(second):
        pass
    assert baseline.read_bytes() == before


def test_lock_is_shared_across_processes(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, shared=True)
    first = load_runtime(settings)[0]
    code = (
        "import sys; from pathlib import Path; "
        "from cadence_mcp_bridge.runtime_context import load_runtime,resource_lock; "
        "context=load_runtime(Path(sys.argv[1]))[1]; "
        "lock=resource_lock(context); lock.__enter__(); "
        "print('LOCKED',flush=True); sys.stdin.readline(); lock.__exit__(None,None,None)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(settings)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None and process.stdin is not None
        assert process.stdout.readline().strip() == "LOCKED"
        with pytest.raises(RuntimeRejected), resource_lock(first):
            pytest.fail("cross-process lock bypass")
        process.stdin.write("\n")
        process.stdin.flush()
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream:
                stream.close()
    with resource_lock(first):
        pass


def test_no_configuration_cannot_construct_backend_or_create_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    spy = MagicMock()
    assert runtime_observation(config(None, None))["status"] == "SETUP_REQUIRED"
    service = create_operator_service(config(None, None), spy)
    spy.assert_not_called()
    assert service.context is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_operator_services_do_not_read_other_journals_or_dispatch(settings: Path) -> None:
    contexts = load_runtime(settings)
    operation = str(uuid4())
    store = AnalysisStore(contexts[0].binding.analysis_journal)
    store.admit(operation, "design-1", "dc", "a" * 64)
    before = contexts[0].binding.analysis_journal.read_bytes()
    with pytest.raises(InvalidInputError):
        AnalysisStore(contexts[1].binding.analysis_journal).require(
            operation,
            "design-1",
            "dc",
            "a" * 64,
        )
    fake = MagicMock()
    for identity in ("context-1", "context-2"):
        service = create_operator_service(config(settings, identity), lambda _: fake)
        for name, args in (
            ("health", ()),
            ("submit_smoke", ()),
            ("sweep_status", (operation,)),
            ("analysis_result", ({},)),
            ("submit_native_diagnostic", ({},)),
            ("storage_summary", ()),
            ("execute_storage_cleanup", ({},)),
        ):
            with pytest.raises(ConfigurationError, match="RUNNER_SETUP_REQUIRED"):
                await getattr(service, name)(*args)
        assert fake.mock_calls == []
    assert contexts[0].binding.analysis_journal.read_bytes() == before
    assert not contexts[1].binding.analysis_journal.exists()


@pytest.mark.parametrize("field", ["environment_profile", "design_registry", "pdk_registry"])
def test_stale_digests_block_before_backend(settings: Path, field: str) -> None:
    data = json.loads(settings.read_bytes())
    path = Path(data["contexts"][0][field])
    path.write_bytes(path.read_bytes() + b"\n")
    spy = MagicMock()
    with pytest.raises(RuntimeRejected) as error:
        create_operator_service(config(settings), spy)
    assert error.value.reason == "stale_contract_digest"
    spy.assert_not_called()
    assert str(path) not in str(error.value.to_envelope())


@pytest.mark.parametrize(
    "change,reason",
    [
        ("extra", "runtime_contract_invalid"),
        ("duplicate", "duplicate_context_id"),
        ("journals", "journal_context_conflict"),
        ("collision", "journal_contract_collision"),
        ("relative", "absolute_contract_paths_required"),
        ("invalid-runner", "runtime_contract_invalid"),
    ],
)
def test_manifest_inconsistency(settings: Path, change: str, reason: str) -> None:
    data = json.loads(settings.read_bytes())
    binding = data["contexts"][1]
    if change == "extra":
        binding["script"] = "whoami"
    elif change == "duplicate":
        binding["context_id"] = data["contexts"][0]["context_id"]
    elif change == "journals":
        binding["analysis_journal"] = binding["sweep_journal"]
    elif change == "collision":
        binding["analysis_journal"] = binding["design_registry"]
    elif change == "relative":
        binding["environment_profile"] = "../environment.json"
    else:
        binding["runner_sha256"] = "not-a-digest"
    settings.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeRejected) as error:
        load_runtime(settings)
    assert error.value.reason == reason


@pytest.mark.parametrize(
    "payload",
    ['{"schema_version":1,"schema_version":1}', "NaN", "x" * 65_537, "[]"],
    ids=["duplicate", "nonfinite", "oversize", "array"],
)
def test_closed_json(settings: Path, payload: str) -> None:
    settings.write_text(payload, encoding="utf-8")
    with pytest.raises(RuntimeRejected):
        load_runtime(settings)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ssh_alias", "-oProxyCommand=id"),
        ("ssh_alias", "host;id"),
        ("ssh_alias", "host\nid"),
        ("ssh_alias", "$(id)"),
        ("paths", None),
    ],
)
def test_transport_injection_before_factory(settings: Path, field: str, value: Any) -> None:
    data = json.loads(settings.read_bytes())
    path = Path(data["contexts"][0]["environment_profile"])
    profile = json.loads(path.read_bytes())
    profile[field] = value
    path.write_text(json.dumps(profile), encoding="utf-8")
    spy = MagicMock()
    with pytest.raises(RuntimeRejected):
        create_operator_service(config(settings), spy)
    spy.assert_not_called()


def test_alias_and_resource_policy_conflicts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, shared=True)
    data = json.loads(settings.read_bytes())
    data["contexts"][1]["ledger_ref"] = "new-reset-ledger"
    settings.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeRejected) as error:
        load_runtime(settings)
    assert error.value.reason == "shared_resource_policy_conflict"


def test_ambiguous_design_id_denied(settings: Path) -> None:
    data = json.loads(settings.read_bytes())
    path = Path(data["contexts"][1]["design_registry"])
    registry = json.loads(path.read_bytes())
    registry["designs"][0]["design_id"] = "design-1"
    path.write_text(json.dumps(registry), encoding="utf-8")
    data["contexts"][1]["design_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    settings.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeRejected) as error:
        load_runtime(settings)
    assert error.value.reason == "ambiguous_design_id"


def test_explicit_selection_and_legacy_conflicts(settings: Path) -> None:
    with pytest.raises(RuntimeRejected) as error:
        select_context(config(settings, None))
    assert error.value.reason == "explicit_context_selection_required"
    with pytest.raises(RuntimeRejected):
        select_context(config(settings, "unknown"))
    with pytest.raises(ValueError):
        BridgeConfig(runtime_settings_path=settings)
    with pytest.raises(ValueError):
        BridgeConfig(runtime_mode="operator", design_registry_path=settings)
    with pytest.raises(ValueError):
        BridgeConfig(runtime_mode="operator", remote_root="/other", runner_path="/other/bin/runner")


def test_cli_redacts_and_never_claims_authority(
    settings: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli.main(
            [
                "runtime",
                "resolve",
                "--settings",
                str(settings),
                "--context",
                "context-1",
                "--design-id",
                "design-1",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "RUNNER_SETUP_REQUIRED" and report["execution_authorized"] is False
    assert report["build"]["commit_sha"] is None
    text = json.dumps(report)
    assert "operator-1" not in text and "/srv" not in text and str(settings.parent) not in text
    assert "TestCell" not in text
    assert (
        cli.main(
            [
                "runtime",
                "resolve",
                "--settings",
                str(settings),
                "--context",
                "context-1",
                "--design-id",
                "design-2",
            ]
        )
        == 1
    )
    assert "BLOCKED" in capsys.readouterr().out


def test_no_follow_runtime_file(tmp_path: Path) -> None:
    source = make_settings(tmp_path)
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("OS denies unprivileged symlink creation")
    with pytest.raises(RuntimeRejected):
        load_runtime(link)


def test_direct_operator_transport_cannot_invoke_legacy_runner(
    settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.shutil.which", lambda _: "ssh.exe")
    remote = MagicMock()
    monkeypatch.setattr("cadence_mcp_bridge.ssh_backend.subprocess.run", remote)
    transport = load_runtime(settings)[0].transport
    assert isinstance(transport, OperatorTransport)
    backend = OpenSshBackend(transport)
    with pytest.raises(ConfigurationError, match="RUNNER_SETUP_REQUIRED"):
        backend._invoke_at_path(transport.runner_path, "health")
    remote.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", [False, True])
async def test_operator_stdio_without_state_or_reference_fallback(
    configured: bool,
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    env = {k: v for k, v in os.environ.items() if not k.startswith("CADENCE_MCP_")}
    if configured:
        env.update(
            CADENCE_MCP_RUNTIME_SETTINGS_PATH=str(settings),
            CADENCE_MCP_RUNTIME_CONTEXT_ID="context-1",
        )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cadence_mcp_bridge", "serve-operator"],
        env=env,
        cwd=str(tmp_path),
    )
    async with Client(params) as client:
        assert len((await client.list_tools()).tools) == 85
        designs = await client.call_tool("cadence_list_designs")
        assert not designs.is_error and designs.structured_content is not None
        assert len(designs.structured_content["designs"]) == int(configured)
        if configured:
            assert designs.structured_content["designs"][0]["design_id"] == "design-1"
        denied = await client.call_tool("cadence_health")
        assert denied.is_error
        assert ("RUNNER_SETUP_REQUIRED" if configured else "SETUP_REQUIRED") in str(denied.content)
        runtime = await client.call_tool("cadence_runtime_info_v2")
        if configured:
            assert not runtime.is_error and runtime.structured_content is not None
            assert runtime.structured_content["designs"]["source"] == "operator_supplied"
        else:
            assert runtime.is_error and "SETUP_REQUIRED" in str(runtime.content)
    assert not list(tmp_path.glob("*.sqlite3"))


@pytest.mark.parametrize("format", ["codex", "mcp-json", "claude-desktop"])
def test_operator_client_export_preserves_selection(
    settings: Path,
    format: Any,
    tmp_path: Path,
) -> None:
    context = load_runtime(settings)[0]
    binding = context.binding
    output = tmp_path / f"client-{format}.json"
    exported = export_client_config(
        binding.environment_profile,
        binding.design_registry,
        binding.pdk_registry,
        binding.analysis_journal,
        output,
        format=format,
        sweep_journal=binding.sweep_journal,
        runtime_settings=settings,
        context_id=binding.context_id,
    )
    assert exported["server_execution_routing"] == "operator_context_pending_runner"
    import tomllib

    data = (
        tomllib.loads(output.read_text(encoding="utf-8"))
        if format == "codex"
        else json.loads(output.read_bytes())
    )
    server = data["mcp_servers" if format == "codex" else "mcpServers"]["cadence-mcp-bridge"]
    assert server["args"][-1] == "serve-operator"
    env = server["env"]
    assert env["CADENCE_MCP_RUNTIME_CONTEXT_ID"] == "context-1"
    assert env["CADENCE_MCP_RUNTIME_MODE"] == "operator"
    assert "CADENCE_MCP_ANALYSIS_JOURNAL_PATH" not in env
    assert not binding.analysis_journal.exists() and not binding.sweep_journal.exists()


@pytest.mark.asyncio
async def test_setup_server_construction_has_no_legacy_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("CADENCE_MCP_"):
            monkeypatch.delenv(key)
    factory = MagicMock(side_effect=AssertionError("legacy backend constructed"))
    monkeypatch.setattr("cadence_mcp_bridge.server.OpenSshBackend", factory)
    async with Client(create_default_server(operator_mode=True)) as client:
        assert (await client.call_tool("cadence_submit_smoke")).is_error
    factory.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_default_new_install_launch_is_operator(monkeypatch: pytest.MonkeyPatch) -> None:
    launch = MagicMock()
    monkeypatch.setattr(cli, "run_stdio_server", launch)
    assert cli.main([]) == 0
    launch.assert_called_once_with(operator_mode=True)


def test_same_alias_cannot_select_different_environment(settings: Path) -> None:
    data = json.loads(settings.read_bytes())
    path = Path(data["contexts"][1]["environment_profile"])
    env = json.loads(path.read_bytes())
    env["ssh_alias"] = "operator-1"
    path.write_text(json.dumps(env), encoding="utf-8")
    data["contexts"][1]["environment_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    settings.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeRejected) as error:
        load_runtime(settings)
    assert error.value.reason == "environment_alias_conflict"


def test_lock_rejects_hardlink_alias(settings: Path, tmp_path: Path) -> None:
    context = load_runtime(settings)[0]
    original = tmp_path / "protected.txt"
    original.write_bytes(b"protected")
    try:
        context.lock_path.hardlink_to(original)
    except OSError:
        pytest.skip("OS does not permit synthetic hardlinks")
    with pytest.raises(RuntimeRejected), resource_lock(context):
        pytest.fail("hardlinked protected leaf accepted")
    assert original.read_bytes() == b"protected"


def test_explicit_legacy_launch_ignores_inherited_operator_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cadence_mcp_bridge import server

    for key in list(os.environ):
        if key.startswith("CADENCE_MCP_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("CADENCE_MCP_RUNTIME_MODE", "operator")
    monkeypatch.setenv("CADENCE_MCP_RUNTIME_SETTINGS_PATH", "unused-operator-settings.json")
    monkeypatch.setenv("CADENCE_MCP_RUNTIME_CONTEXT_ID", "operator-session")
    selected = []
    factory = MagicMock(side_effect=lambda config: selected.append(config) or MagicMock())
    monkeypatch.setattr(server, "OpenSshBackend", factory)
    server.create_default_server()
    assert selected[0].runtime_mode == "legacy_reference"
    assert selected[0].runtime_settings_path is None
    assert selected[0].runtime_context_id is None
