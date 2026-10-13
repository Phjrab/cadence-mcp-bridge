"""Offline operator setup contracts; these are not VM execution qualifications."""

from __future__ import annotations

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
from cadence_mcp_bridge import native_service, onboarding, runtime_context


@pytest.fixture(autouse=True)
def offline_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    denied = MagicMock(side_effect=AssertionError("setup must not dispatch or construct services"))
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(onboarding, "qualify_environment", denied)
    monkeypatch.setattr(runtime_context, "create_operator_service", denied)
    monkeypatch.setattr(native_service, "NativeOperationService", denied)
    monkeypatch.setattr(native_service, "AuthenticatedOperatorProvider", denied)
    monkeypatch.setenv("CADENCE_MCP_RUNTIME_SETTINGS_PATH", str(tmp_path / "other-user.json"))
    monkeypatch.setenv("CADENCE_MCP_RUNTIME_CONTEXT_ID", "other-user")
    monkeypatch.setenv("CADENCE_MCP_SSH_ALIAS", "unapproved-other-host")
    monkeypatch.setenv("CADENCE_MCP_REMOTE_ROOT", "/unapproved/other-user")


@pytest.fixture
def starter(tmp_path: Path) -> Path:
    target = tmp_path / "운영자 setup"
    onboarding.export_starter(target)
    return target


def contract_args(starter: Path) -> list[str]:
    return [
        "--profile", str(starter / "environment.json"),
        "--design-registry", str(starter / "designs.json"),
        "--pdk-registry", str(starter / "pdks.json"),
    ]


def runtime_args(starter: Path) -> list[str]:
    return [
        "operator-setup", "export-runtime", *contract_args(starter),
        "--resource-state-root", str(starter), "--context", "student-context",
        "--runner-sha256", "b" * 64, "--authority-ref", "operator-owned-authority",
        "--ledger-ref", "preserve-existing-ledger",
        "--journal", str(starter / "analysis.sqlite3"),
        "--sweep-journal", str(starter / "sweep.sqlite3"),
        "--output", str(starter / "runtime.json"),
    ]


def replace_arg(args: list[str], name: str, value: str | Path) -> list[str]:
    changed = list(args)
    changed[changed.index(name) + 1] = str(value)
    return changed


def invoke(
    args: list[str], capsys: pytest.CaptureFixture[str], *, expected: int = 0,
) -> dict[str, Any]:
    assert cli.main(args) == expected
    captured = capsys.readouterr()
    assert captured.err == ""
    result: dict[str, Any] = json.loads(captured.out)
    assert result["remote_contact"] is False
    assert result["execution_authorized"] is False
    assert result["new_simulations"] == 0
    assert result["new_reservations"] == 0
    if expected:
        assert result["status"] == "BLOCKED"
        assert isinstance(result["reason"], str) and result["reason"]
        assert isinstance(result["guidance"], str) and result["guidance"]
    return result


def snapshot(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


@pytest.mark.parametrize("mode", ["fresh", "existing"])
def test_guide_is_explicit_and_does_not_initialize_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = invoke(["operator-setup", "guide", "--mode", mode], capsys)
    serialized = json.dumps(result)
    assert mode in serialized
    assert "native-registration" in serialized
    assert "preflight" in serialized
    assert "submit" in serialized and "result" in serialized
    assert list(tmp_path.iterdir()) == []


def test_starter_check_is_only_local_description(
    starter: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    before = snapshot(starter)
    result = invoke(["operator-setup", "check", *contract_args(starter)], capsys)
    assert result["status"] == "LOCAL_CONTRACTS_VALID"
    assert isinstance(result["notices"], list) and result["notices"]
    assert snapshot(starter) == before


def test_runtime_export_binds_explicit_unicode_operator_inputs_and_creates_no_journal(
    starter: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    before = snapshot(starter)
    invoke(runtime_args(starter), capsys)
    contexts = runtime_context.load_runtime(starter / "runtime.json")
    assert len(contexts) == 1
    context = contexts[0]
    assert context.binding.context_id == "student-context"
    assert context.binding.authority_ref == "operator-owned-authority"
    assert context.binding.ledger_ref == "preserve-existing-ledger"
    assert context.binding.runner_sha256 == "b" * 64
    assert context.binding.environment_profile == (starter / "environment.json").resolve()
    assert context.binding.environment_sha256 == hashlib.sha256(
        before["environment.json"],
    ).hexdigest()
    if os.name != "nt":
        assert (starter / "runtime.json").stat().st_mode & 0o777 == 0o600
    assert context.transport.ssh_alias == "fictional-host"
    assert context.transport.remote_root == "/srv/project/.cadence_mcp"
    assert not context.binding.analysis_journal.exists()
    assert not context.binding.sweep_journal.exists()
    assert not context.lock_path.exists()
    after = snapshot(starter)
    assert set(after) == set(before) | {"runtime.json"}
    assert all(after[name] == content for name, content in before.items())
    result = invoke([
        "operator-setup", "check", "--settings", str(starter / "runtime.json"),
        "--context", "student-context",
    ], capsys)
    assert result["status"] == "LOCAL_CONTEXT_VALID"
    assert isinstance(result["notices"], list) and result["notices"]
    assert snapshot(starter) == after


def test_existing_journals_and_ledger_are_never_opened_or_replaced(
    starter: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    # Deliberately not valid SQLite: setup must not inspect, repair, or initialize it.
    for name in ("analysis.sqlite3", "sweep.sqlite3"):
        (starter / name).write_bytes(b"retained journal and replay evidence\x00")
    (starter / "ledger.json").write_bytes(b'{"attempts":112,"reserved_bytes":13825474560}')
    before = snapshot(starter)
    invoke(runtime_args(starter), capsys)
    invoke([
        "operator-setup", "check", "--settings", str(starter / "runtime.json"),
        "--context", "student-context",
    ], capsys)
    assert all((starter / name).read_bytes() == value for name, value in before.items())
    assert not list(starter.glob("*.lock"))


def add_second_context(starter: Path) -> Path:
    settings = starter / "runtime.json"
    document = json.loads(settings.read_bytes())
    second = dict(document["contexts"][0])
    environment = json.loads((starter / "environment.json").read_bytes())
    environment["environment_id"] = "second-environment"
    environment["ssh_alias"] = "second-operator"
    environment["host"]["hostname"] = "second-fictional-host"
    design = json.loads((starter / "designs.json").read_bytes())["designs"][0]
    design.update(environment_id="second-environment", design_id="second-design")
    pdk = json.loads((starter / "pdks.json").read_bytes())
    pdk["adapters"][0]["environment_ids"] = ["second-environment"]
    for field, digest_field, data in (
        ("environment_profile", "environment_sha256", environment),
        ("design_registry", "design_sha256", {"schema_version": 1, "designs": [design]}),
        ("pdk_registry", "pdk_sha256", pdk),
    ):
        path = starter / ("second-" + field + ".json")
        path.write_text(json.dumps(data), encoding="utf-8")
        second[field] = str(path)
        second[digest_field] = hashlib.sha256(path.read_bytes()).hexdigest()
    second.update(
        context_id="second-context", analysis_journal=str(starter / "second-analysis.sqlite3"),
        sweep_journal=str(starter / "second-sweep.sqlite3"),
    )
    document["contexts"].append(second)
    settings.write_text(json.dumps(document), encoding="utf-8")
    return settings


def test_multiple_context_selection_does_not_choose_the_first_or_inherited_context(
    starter: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    invoke(runtime_args(starter), capsys)
    settings = add_second_context(starter)
    contexts = runtime_context.load_runtime(settings)
    assert len(contexts) == 2
    for context in contexts:
        context.lock_path.write_bytes(b"retained resource lock inode and contents")
    before = snapshot(starter)
    invoke([
        "operator-setup", "export-client", "--settings", str(settings),
        "--context", "second-context", "--format", "mcp-json", "--output",
        str(starter / "second-client.json"),
    ], capsys)
    client = json.loads((starter / "second-client.json").read_bytes())
    env = client["mcpServers"]["cadence-mcp-bridge"]["env"]
    assert env["CADENCE_MCP_RUNTIME_CONTEXT_ID"] == "second-context"
    assert all((starter / name).read_bytes() == content for name, content in before.items())
    result = invoke([
        "operator-setup", "check", "--settings", str(settings), "--context", "unknown-context",
    ], capsys, expected=1)
    assert result["reason"] == "unknown_context_id"


@pytest.mark.parametrize(
    "target", ["removed-analysis", "removed-sweep", "removed-lock", "new-file"],
)
def test_export_client_retains_one_complete_snapshot_when_runtime_changes(
    starter: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    invoke(runtime_args(starter), capsys)
    settings = add_second_context(starter)
    contexts = runtime_context.load_runtime(settings)
    original_load = runtime_context.load_runtime
    calls: list[Path] = []
    before = snapshot(starter)
    removed = contexts[1]
    output = {
        "removed-analysis": removed.binding.analysis_journal,
        "removed-sweep": removed.binding.sweep_journal,
        "removed-lock": removed.lock_path,
        "new-file": starter / "new-client.json",
    }[target]

    def changed_after_load(path: Path) -> tuple[runtime_context.ExecutionContext, ...]:
        captured = original_load(path)
        calls.append(path)
        changed = json.loads(path.read_bytes())
        changed["contexts"] = changed["contexts"][:1]
        replacement = path.with_suffix(".replacement")
        replacement.write_text(json.dumps(changed), encoding="utf-8")
        os.replace(replacement, path)
        return captured

    monkeypatch.setattr(runtime_context, "load_runtime", changed_after_load)
    result = invoke([
        "operator-setup", "export-client", "--settings", str(settings),
        "--context", "student-context", "--format", "mcp-json", "--output", str(output),
    ], capsys, expected=0 if target == "new-file" else 1)
    assert calls == [settings.resolve()]
    assert len(json.loads(settings.read_bytes())["contexts"]) == 1
    if target == "new-file":
        client = json.loads(output.read_bytes())
        env = client["mcpServers"]["cadence-mcp-bridge"]["env"]
        assert env["CADENCE_MCP_RUNTIME_CONTEXT_ID"] == "student-context"
        assert env["CADENCE_MCP_RUNTIME_SETTINGS_PATH"] == str(settings.resolve())
    else:
        assert result["reason"] == "runtime_export_reserved_path"
        assert not output.exists()
    for context in contexts:
        assert not context.binding.analysis_journal.exists()
        assert not context.binding.sweep_journal.exists()
        assert not context.lock_path.exists()
    assert all(
        (starter / name).read_bytes() == content
        for name, content in before.items() if name != "runtime.json"
    )


@pytest.mark.parametrize("format", ["codex", "mcp-json", "claude-desktop"])
def test_export_client_reuses_selected_runtime_without_legacy_or_inherited_defaults(
    starter: Path, capsys: pytest.CaptureFixture[str], format: str,
) -> None:
    invoke(runtime_args(starter), capsys)
    before = snapshot(starter)
    output = starter / "client fragment.conf"
    invoke([
        "operator-setup", "export-client", "--settings", str(starter / "runtime.json"),
        "--context", "student-context", "--format", format, "--output", str(output),
    ], capsys)
    config = (
        tomllib.loads(output.read_text(encoding="utf-8"))
        if format == "codex" else json.loads(output.read_bytes())
    )
    server = config["mcp_servers" if format == "codex" else "mcpServers"]["cadence-mcp-bridge"]
    assert server["args"] == ["-m", "cadence_mcp_bridge", "serve-operator"]
    assert server["env"]["CADENCE_MCP_RUNTIME_SETTINGS_PATH"] == str(
        (starter / "runtime.json").resolve(),
    )
    assert server["env"]["CADENCE_MCP_RUNTIME_CONTEXT_ID"] == "student-context"
    assert "unapproved" not in output.read_text(encoding="utf-8")
    assert all((starter / name).read_bytes() == value for name, value in before.items())
    assert not (starter / "analysis.sqlite3").exists()
    assert not (starter / "sweep.sqlite3").exists()
    assert not list(starter.glob("*.lock"))


@pytest.mark.parametrize("action", ["export-runtime", "export-client"])
def test_existing_output_survives_repeat_and_has_actionable_closed_error(
    starter: Path, capsys: pytest.CaptureFixture[str], action: str,
) -> None:
    invoke(runtime_args(starter), capsys)
    args = runtime_args(starter)
    if action == "export-client":
        args = [
            "operator-setup", action, "--settings", str(starter / "runtime.json"),
            "--context", "student-context", "--format", "codex", "--output",
            str(starter / "private output.toml"),
        ]
        invoke(args, capsys)
    before = snapshot(starter)
    result = invoke(args, capsys, expected=1)
    assert result["reason"] == "setup_output_exists"
    assert str(starter) not in json.dumps(result, ensure_ascii=False)
    assert snapshot(starter) == before


def test_failed_durability_check_preserves_export_and_requires_a_new_output(
    starter: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_sync = MagicMock(side_effect=OSError("private filesystem diagnostic"))
    monkeypatch.setattr(os, "fsync", failed_sync)
    before = snapshot(starter)
    result = invoke(runtime_args(starter), capsys, expected=1)
    assert result["reason"] == "setup_io_failed"
    assert "private filesystem diagnostic" not in json.dumps(result)
    output = starter / "runtime.json"
    assert output.exists()  # Interrupted evidence is retained, never silently deleted.
    retained = output.read_bytes()
    assert all((starter / name).read_bytes() == content for name, content in before.items())
    retry = invoke(runtime_args(starter), capsys, expected=1)
    assert retry["reason"] == "setup_output_exists"
    assert output.read_bytes() == retained
    assert not (starter / "analysis.sqlite3").exists()
    assert not (starter / "sweep.sqlite3").exists()
    assert not list(starter.glob("*.lock"))


def test_partial_interrupted_output_is_not_repaired_or_overwritten(
    starter: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    output = starter / "runtime.json"
    output.write_bytes(b'{"schema_version":')
    before = snapshot(starter)
    result = invoke([
        "operator-setup", "check", "--settings", str(output), "--context", "student-context",
    ], capsys, expected=1)
    assert result["reason"] == "runtime_contract_invalid"
    retry = invoke(runtime_args(starter), capsys, expected=1)
    assert retry["reason"] == "setup_output_exists"
    assert snapshot(starter) == before


@pytest.mark.parametrize("field", ["environment_profile", "design_registry", "pdk_registry"])
def test_stale_contracts_explain_failure_without_resynchronizing_hashes(
    starter: Path, capsys: pytest.CaptureFixture[str], field: str,
) -> None:
    invoke(runtime_args(starter), capsys)
    settings = starter / "runtime.json"
    document = json.loads(settings.read_bytes())
    changed = Path(document["contexts"][0][field])
    changed.write_bytes(changed.read_bytes() + b"\n")
    before = snapshot(starter)
    result = invoke([
        "operator-setup", "check", "--settings", str(settings),
        "--context", "student-context",
    ], capsys, expected=1)
    assert result["reason"] == "stale_contract_digest"
    assert str(starter) not in json.dumps(result, ensure_ascii=False)
    assert snapshot(starter) == before


@pytest.mark.parametrize("selection", ["missing", "partial-contracts", "partial-context", "mixed"])
def test_check_requires_one_complete_explicit_source(
    starter: Path, capsys: pytest.CaptureFixture[str], selection: str,
) -> None:
    args = {
        "missing": [],
        "partial-contracts": contract_args(starter)[:2],
        "partial-context": ["--context", "student-context"],
        "mixed": [*contract_args(starter), "--settings", str(starter / "runtime.json"),
                  "--context", "student-context"],
    }[selection]
    before = snapshot(starter)
    result = invoke(["operator-setup", "check", *args], capsys, expected=1)
    assert result["reason"] == "setup_inputs_required"
    assert snapshot(starter) == before


@pytest.mark.parametrize("target", ["contract", "analysis", "sweep", "domain-lock"])
def test_runtime_export_rejects_reserved_path_collisions_without_writes(
    starter: Path, capsys: pytest.CaptureFixture[str], target: str,
) -> None:
    invoke(runtime_args(starter), capsys)
    context = runtime_context.load_runtime(starter / "runtime.json")[0]
    path = {
        "contract": starter / "environment.json",
        "analysis": starter / "analysis.sqlite3",
        "sweep": starter / "sweep.sqlite3",
        "domain-lock": context.lock_path,
    }[target]
    before = snapshot(starter)
    invoke(replace_arg(runtime_args(starter), "--output", path), capsys, expected=1)
    assert snapshot(starter) == before


@pytest.mark.parametrize("target", ["output", "journal", "state"])
def test_missing_parent_or_state_directory_is_not_implicitly_created(
    starter: Path, capsys: pytest.CaptureFixture[str], target: str,
) -> None:
    field, path = {
        "output": ("--output", starter / "absent" / "runtime.json"),
        "journal": ("--journal", starter / "absent" / "journal.sqlite3"),
        "state": ("--resource-state-root", starter / "absent"),
    }[target]
    before = snapshot(starter)
    invoke(replace_arg(runtime_args(starter), field, path), capsys, expected=1)
    assert snapshot(starter) == before
    assert not (starter / "absent").exists()


@pytest.mark.parametrize("argument", ["--native-provider-binding", "--native-specifications"])
def test_partial_native_bindings_are_not_invented(
    starter: Path, capsys: pytest.CaptureFixture[str], argument: str,
) -> None:
    before = snapshot(starter)
    result = invoke([
        *runtime_args(starter), argument, str(starter / "private native binding.json"),
    ], capsys, expected=1)
    assert result["reason"] == "setup_input_invalid"
    assert snapshot(starter) == before


@pytest.mark.parametrize("target", ["input", "output", "parent"])
def test_symlinks_are_rejected_without_reading_or_overwriting_targets(
    starter: Path, capsys: pytest.CaptureFixture[str], target: str,
) -> None:
    link = starter / "link"
    try:
        link.symlink_to(starter if target == "parent" else starter / "environment.json",
                        target_is_directory=target == "parent")
    except OSError:
        pytest.skip("OS does not permit unprivileged symlinks")
    before = {name: (starter / name).read_bytes() for name in onboarding.STARTER_FILES}
    flag = "--profile" if target == "input" else "--output"
    path = link / "runtime.json" if target == "parent" else link
    invoke(replace_arg(runtime_args(starter), flag, path), capsys, expected=1)
    assert all((starter / name).read_bytes() == content for name, content in before.items())
    assert not (starter / "runtime.json").exists()
